#!/usr/bin/env python3
"""
calipso/resource_dispatcher.py — Dispatcher consciente de recursos.

Antes de despachar cualquier tarea a un modelo local (Ollama) lee el estado
real del sistema (RAM libre, modelos cargados, carga de CPU) y decide:

  RUN      — hay recursos suficientes, ejecuta ahora.
  DOWNGRADE — RAM justa; baja a un modelo más pequeño.
  REROUTE  — sin RAM para local; manda a suscripción/API.
  DEFER    — cola prioritaria; ejecuta cuando haya recursos.

También expone un TaskQueue que Pedro (o el servidor) puede usar para
programar tareas con prioridad y que el dispatcher las drene en orden.

Sin dependencias externas: usa /proc/meminfo, /proc/loadavg y urllib
para hablar con Ollama.

Límites conocidos del ROG Ally (12 GB RAM total, compartida con iGPU):
  < 3 GB disponible  → zona de peligro, nada local
  < 5 GB disponible  → solo modelos 3b
  < 7 GB disponible  → modelos hasta 7b
  ≥ 7 GB disponible  → ok para 7b + carga concurrente ligera
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger("calipso.resource_dispatcher")

# ---------------------------------------------------------------------------
# RAM estimada por modelo (MB).  Se amplia automáticamente vía Ollama /api/ps.
# ---------------------------------------------------------------------------
MODEL_RAM_MB: dict[str, int] = {
    "qwen2.5:3b":    2_500,
    "qwen2.5:7b":    5_500,
    "qwen2.5:14b":  10_000,
    "qwen2.5:32b":  22_000,
    "bge-m3":        1_000,
    "llama3.2:3b":   2_200,
    "llama3:8b":     5_000,
    "llama3:13b":    8_500,
    "mistral:7b":    5_000,
    "gemma2:9b":     6_500,
    "phi3:mini":     2_300,
}

# Umbrales de RAM disponible (MB) para tomar decisiones.
DANGER_MB   = 3_000   # nada local bajo este umbral
SMALL_MB    = 5_000   # solo 3b o menores
MEDIUM_MB   = 7_000   # hasta 7b
CPU_HIGH    = 0.85    # carga normalizada (load1 / ncpu); por encima → advertencia


# ---------------------------------------------------------------------------
# Lectura del sistema  (sin psutil)
# ---------------------------------------------------------------------------

def sys_memory() -> dict:
    """Lee /proc/meminfo. Devuelve MB de total, disponible y usado."""
    info: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith(("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")):
                    key, val, *_ = line.split()
                    info[key.rstrip(":")] = int(val)  # en kB
    except OSError:
        return {"total_mb": 0, "available_mb": 0, "used_mb": 0, "swap_used_mb": 0}
    total     = info.get("MemTotal", 0) // 1024
    available = info.get("MemAvailable", 0) // 1024
    swap_used = (info.get("SwapTotal", 0) - info.get("SwapFree", 0)) // 1024
    return {
        "total_mb":     total,
        "available_mb": available,
        "used_mb":      total - available,
        "swap_used_mb": swap_used,
        "percent_used": round((total - available) / max(total, 1) * 100, 1),
    }


def cpu_load() -> float:
    """Carga normalizada (load average 1 min / nCPU). 1.0 = CPU al 100%."""
    try:
        with open("/proc/loadavg", encoding="utf-8") as f:
            load1 = float(f.read().split()[0])
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            ncpu = sum(1 for l in f if l.startswith("processor"))
        return round(load1 / max(ncpu, 1), 3)
    except OSError:
        return 0.0


def _ollama_get(path: str, base: str = "http://localhost:11434") -> dict | list | None:
    try:
        req = urllib.request.Request(f"{base}{path}")
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def ollama_loaded_models(base: str = "http://localhost:11434") -> list[dict]:
    """Modelos actualmente cargados en Ollama (/api/ps).
    Cada entrada: {name, size_mb, expires_at}."""
    data = _ollama_get("/api/ps", base)
    if not isinstance(data, dict):
        return []
    out = []
    for m in data.get("models") or []:
        size_bytes = m.get("size_vram") or m.get("size") or 0
        out.append({
            "name":       m.get("name", ""),
            "size_mb":    size_bytes // (1024 * 1024),
            "expires_at": m.get("expires_at", ""),
        })
    return out


def ollama_evict(model: str, base: str = "http://localhost:11434") -> bool:
    """Fuerza la descarga de un modelo de la VRAM/RAM de Ollama
    enviando una inferencia con keep_alive=0."""
    payload = json.dumps({
        "model": model, "prompt": "", "stream": False,
        "keep_alive": 0,
    }).encode()
    try:
        req = urllib.request.Request(
            f"{base}/api/generate", data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10):
            pass
        return True
    except Exception:
        return False


def _is_embedding_model(name: str) -> bool:
    """Los modelos de embeddings no sirven para chatear: nunca son un downgrade."""
    low = name.lower()
    return "embed" in low or low.startswith("bge")


def ollama_installed_models(base: str = "http://localhost:11434") -> list[str]:
    """Modelos que Ollama tiene realmente descargados (/api/tags).

    Reusa discovery.discover_ollama, que ya descarta los de embeddings.
    Si discovery no esta disponible, cae a /api/tags directo.
    """
    try:
        from calipso import discovery
        return discovery.discover_ollama(base)
    except Exception:
        data = _ollama_get("/api/tags", base)
        if not isinstance(data, dict):
            return []
        names = [m.get("name", "") for m in (data.get("models") or [])]
        return [n for n in names if n and not _is_embedding_model(n)]


def model_ram_mb(model_name: str) -> int:
    """Estimación de RAM necesaria para cargar model_name (MB)."""
    name = model_name.lower().split(":")[0] + (
        ":" + model_name.split(":")[1] if ":" in model_name else "")
    # Coincidencia exacta primero.
    if name in MODEL_RAM_MB:
        return MODEL_RAM_MB[name]
    # Coincidencia por prefijo (e.g. "qwen2.5" → primer match).
    base = model_name.split(":")[0].lower()
    for k, v in MODEL_RAM_MB.items():
        if k.startswith(base):
            return v
    # Heurística por número de parámetros en el nombre.
    import re
    m = re.search(r"(\d+(?:\.\d+)?)b", model_name, re.IGNORECASE)
    if m:
        params_b = float(m.group(1))
        return int(params_b * 750)  # ~750 MB/B de parámetros (Q4)
    return 5_000  # default conservador


# ---------------------------------------------------------------------------
# Snapshot de recursos
# ---------------------------------------------------------------------------

@dataclass
class ResourceSnapshot:
    mem:              dict = field(default_factory=dict)
    cpu_load:         float = 0.0
    loaded_models:    list = field(default_factory=list)
    installed_models: list = field(default_factory=list)
    timestamp:        float = field(default_factory=time.time)

    @classmethod
    def take(cls) -> "ResourceSnapshot":
        return cls(
            mem=sys_memory(),
            cpu_load=cpu_load(),
            loaded_models=ollama_loaded_models(),
            installed_models=ollama_installed_models(),
        )

    @property
    def available_mb(self) -> int:
        return self.mem.get("available_mb", 0)

    @property
    def swap_used_mb(self) -> int:
        return self.mem.get("swap_used_mb", 0)

    def summary(self) -> str:
        s = self.mem
        loaded = ", ".join(m["name"] for m in self.loaded_models) or "ninguno"
        return (
            f"RAM {s.get('used_mb',0):,} / {s.get('total_mb',0):,} MB "
            f"(libre {self.available_mb:,} MB, swap {self.swap_used_mb:,} MB) | "
            f"CPU load {self.cpu_load:.2f} | modelos Ollama cargados: {loaded}"
        )


# ---------------------------------------------------------------------------
# Decisión de despacho
# ---------------------------------------------------------------------------

@dataclass
class ResourceDecision:
    action:     str            # "run" | "evict_then_run" | "downgrade"
                               # | "reroute" | "defer"
    model:      str | None     # modelo a usar (puede ser diferente al pedido)
    route:      str | None     # "local" | "subscription" | "api"
    reason:     str = ""
    snapshot:   ResourceSnapshot | None = None
    warn_cpu:   bool = False
    queue_pos:  int | None = None  # posición en la cola si action=="defer"


def gate(
    model: str,
    route: str = "local",
    fallback_route: str = "subscription",
    snap: ResourceSnapshot | None = None,
) -> ResourceDecision:
    """
    Decide si se puede ejecutar `model` en `route` ahora mismo.

    Devuelve un ResourceDecision con la acción recomendada.
    El llamador es responsable de actuar según la decisión.
    """
    if route != "local":
        # Rutas no-locales no tienen restricciones de RAM aquí.
        return ResourceDecision(action="run", model=model, route=route,
                                reason="ruta no-local, sin restricción de RAM")

    snap = snap or ResourceSnapshot.take()
    avail = snap.available_mb
    needed = model_ram_mb(model)
    warn_cpu = snap.cpu_load > CPU_HIGH

    log.debug("gate: modelo=%s necesita=%d MB disponible=%d MB cpu=%.2f",
              model, needed, avail, snap.cpu_load)

    if avail < DANGER_MB:
        return ResourceDecision(
            action="reroute", model=None, route=fallback_route,
            reason=(f"RAM crítica: solo {avail:,} MB libres "
                    f"(mínimo {DANGER_MB:,} MB para local)"),
            snapshot=snap, warn_cpu=warn_cpu)

    if avail < needed + 500:        # +500 MB de margen de seguridad
        # ¿Hay modelos cargados que podemos desalojar para ganar RAM?
        loaded_mb = sum(m["size_mb"] for m in snap.loaded_models)
        if loaded_mb > 0 and avail + loaded_mb >= needed + 500:
            return ResourceDecision(
                action="evict_then_run", model=model, route="local",
                reason=(f"RAM insuficiente ({avail:,}/{needed:,} MB) pero "
                        f"desalojando modelos cargados ({loaded_mb:,} MB) alcanza"),
                snapshot=snap, warn_cpu=warn_cpu)
        # ¿Hay un modelo más pequeño viable?
        smaller = _smaller_model(model, avail, snap.installed_models)
        if smaller:
            return ResourceDecision(
                action="downgrade", model=smaller, route="local",
                reason=(f"RAM insuficiente para {model} ({needed:,} MB); "
                        f"bajando a {smaller} ({model_ram_mb(smaller):,} MB)"),
                snapshot=snap, warn_cpu=warn_cpu)
        return ResourceDecision(
            action="reroute", model=None, route=fallback_route,
            reason=(f"RAM insuficiente ({avail:,} MB libres) y no hay modelo "
                    f"local más pequeño viable; redirigiendo a {fallback_route}"),
            snapshot=snap, warn_cpu=warn_cpu)

    return ResourceDecision(
        action="run", model=model, route="local",
        reason=f"RAM OK ({avail:,} MB libres, {needed:,} MB necesarios)",
        snapshot=snap, warn_cpu=warn_cpu)


def _norm_model(name: str) -> str:
    """qwen2.5:7b y qwen2.5:7b-latest son el mismo modelo."""
    return name.lower().removesuffix(":latest")


def _smaller_model(model: str, available_mb: int,
                   installed: list[str] | None = None) -> str | None:
    """El modelo más grande que cabe en available_mb Y está instalado.

    Elegir de la tabla estática MODEL_RAM_MB no alcanza: bajar a un modelo
    que Ollama no tiene descargado hace fallar la tarea con un 404.
    """
    if installed is None:
        installed = ollama_installed_models()
    target = _norm_model(model)
    candidates: dict[str, int] = {}
    for name in installed:
        if not name or _norm_model(name) == target or _is_embedding_model(name):
            continue
        ram = model_ram_mb(name)
        if ram + 500 <= available_mb:
            candidates[name] = ram
    if not candidates:
        return None
    return max(candidates, key=lambda k: candidates[k])


def evict_all_and_retry(model: str, snap: ResourceSnapshot | None = None
                        ) -> ResourceDecision:
    """Desaloja todos los modelos cargados en Ollama y vuelve a evaluar."""
    snap = snap or ResourceSnapshot.take()
    for m in snap.loaded_models:
        ollama_evict(m["name"])
    time.sleep(1)  # deja que Ollama libere
    fresh = ResourceSnapshot.take()
    return gate(model, route="local", snap=fresh)


# ---------------------------------------------------------------------------
# Cola de tareas con prioridad
# ---------------------------------------------------------------------------

@dataclass(order=True)
class _PriTask:
    priority:   int           # menor número = mayor prioridad
    created_at: float = field(compare=True, default_factory=time.time)
    task_id:    str   = field(compare=False, default="")
    title:      str   = field(compare=False, default="")
    fn:         Callable | None = field(compare=False, default=None)
    model:      str   = field(compare=False, default="")
    route:      str   = field(compare=False, default="local")
    meta:       dict  = field(compare=False, default_factory=dict)


class TaskQueue:
    """
    Cola prioritaria de tareas pendientes.

    Prioridades sugeridas:
      1 — urgente (el usuario está esperando)
      2 — normal
      3 — background / rutinas

    El drainer corre en un hilo dedicado y ejecuta tareas cuando
    hay recursos suficientes.
    """

    def __init__(self, poll_interval: float = 10.0):
        self._q: queue.PriorityQueue = queue.PriorityQueue()
        self._results: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._poll = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None

    # -- enqueue / cancel -------------------------------------------------------

    def enqueue(self, title: str, fn: Callable, model: str = "",
                route: str = "local", priority: int = 2,
                task_id: str | None = None, **meta) -> str:
        import uuid
        tid = task_id or f"rdq_{uuid.uuid4().hex[:8]}"
        item = _PriTask(priority=priority, task_id=tid, title=title,
                        fn=fn, model=model, route=route, meta=meta)
        self._q.put(item)
        with self._lock:
            self._results[tid] = {"status": "queued", "title": title,
                                  "priority": priority, "model": model}
        log.info("TaskQueue: encolada '%s' (id=%s, prio=%d)", title, tid, priority)
        return tid

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            r = self._results.get(task_id)
            if r and r["status"] == "queued":
                r["status"] = "cancelled"
                return True
        return False

    def status(self, task_id: str) -> dict | None:
        with self._lock:
            return dict(self._results.get(task_id, {}))

    def list_pending(self) -> list[dict]:
        with self._lock:
            return [dict(v) for v in self._results.values()
                    if v.get("status") == "queued"]

    # -- drainer ----------------------------------------------------------------

    def start_drainer(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._drain_loop,
                                        daemon=True, name="calipso-rdq-drain")
        self._thread.start()
        log.info("TaskQueue: drainer iniciado (poll=%.0fs)", self._poll)

    def stop_drainer(self) -> None:
        self._running = False

    def _drain_loop(self) -> None:
        while self._running:
            try:
                item: _PriTask = self._q.get(timeout=self._poll)
            except queue.Empty:
                continue
            with self._lock:
                s = self._results.get(item.task_id, {}).get("status")
            if s == "cancelled":
                self._q.task_done()
                continue

            snap = ResourceSnapshot.take()
            decision = gate(item.model, item.route, snap=snap)

            if decision.action in ("run", "evict_then_run"):
                if decision.action == "evict_then_run":
                    for m in snap.loaded_models:
                        ollama_evict(m["name"])
                    time.sleep(1)
                self._execute(item, decision.model or item.model, decision.route or item.route)
            elif decision.action == "downgrade":
                self._execute(item, decision.model, decision.route)
            else:
                # reroute: ejecuta en la ruta alternativa
                self._execute(item, item.model, decision.route or "subscription")
            self._q.task_done()

    def _execute(self, item: _PriTask, model: str, route: str) -> None:
        with self._lock:
            r = self._results.get(item.task_id, {})
            r["status"] = "running"
            r["model_used"] = model
            r["route_used"] = route
            r["started_at"] = time.time()
        log.info("TaskQueue: ejecutando '%s' model=%s route=%s",
                 item.title, model, route)
        try:
            result = item.fn(model=model, route=route, **item.meta)
            with self._lock:
                r = self._results[item.task_id]
                r["status"] = "done"
                r["result"] = result
                r["finished_at"] = time.time()
        except Exception as exc:
            log.exception("TaskQueue: error en '%s': %s", item.title, exc)
            with self._lock:
                r = self._results[item.task_id]
                r["status"] = "error"
                r["error"] = str(exc)


# Instancia global del proceso (el servidor la usa).
_global_queue: TaskQueue | None = None


def get_queue(start: bool = True) -> TaskQueue:
    global _global_queue
    if _global_queue is None:
        _global_queue = TaskQueue()
        if start:
            _global_queue.start_drainer()
    return _global_queue


# ---------------------------------------------------------------------------
# Integración con orchestrator.pick_model
# ---------------------------------------------------------------------------

def resource_aware_pick_model(
    tier: str,
    task_type: str,
    available: dict,
    project_root: str | None = None,
    snap: ResourceSnapshot | None = None,
) -> tuple | None:
    """
    Wrapper de orchestrator.pick_model que filtra modelos locales sin RAM.

    Devuelve (key, model_dict) o None si no hay ninguno disponible.
    Modifica `available` in-place para marcar como False los locales sin RAM.
    """
    from calipso import capabilities

    snap = snap or ResourceSnapshot.take()
    backends = capabilities.load_backends(project_root)

    # Marca modelos locales que no tienen RAM suficiente como no disponibles.
    patched = dict(available)
    for key, m in backends.items():
        if m.get("route") == "local" and patched.get(key):
            model_name = m.get("model", key.split(":")[-1])
            dec = gate(model_name, route="local", snap=snap)
            if dec.action in ("reroute", "defer"):
                patched[key] = False
                log.info("resource_aware_pick_model: descartando %s (%s)",
                         key, dec.reason)

    from calipso import orchestrator
    return orchestrator.pick_model(tier, task_type, patched, project_root)


# ---------------------------------------------------------------------------
# Helpers de logging / diagnóstico
# ---------------------------------------------------------------------------

def diagnose() -> dict:
    """Snapshot completo del estado de recursos + recomendación."""
    snap = ResourceSnapshot.take()
    avail = snap.available_mb
    if avail < DANGER_MB:
        level, msg = "critical", "RAM crítica — evita tareas locales"
    elif avail < SMALL_MB:
        level, msg = "warning", "RAM baja — solo modelos 3b"
    elif avail < MEDIUM_MB:
        level, msg = "caution", "RAM moderada — modelos hasta 7b"
    else:
        level, msg = "ok", "Recursos suficientes"
    return {
        "level": level,
        "message": msg,
        "summary": snap.summary(),
        "memory": snap.mem,
        "cpu_load": snap.cpu_load,
        "cpu_high": snap.cpu_load > CPU_HIGH,
        "loaded_models": snap.loaded_models,
        "queue_pending": len(get_queue(start=False).list_pending())
        if _global_queue else 0,
    }
