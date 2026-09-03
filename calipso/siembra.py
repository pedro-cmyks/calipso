"""Siembra guiada: orquesta los 7 pasos que prenden la economia de la
fabrica, en orden, re-entrante (se puede re-llamar para completar lo que
falte). Reusa los primitivos existentes, no los reimplementa. Vive arriba
de economia (importa routines y plantel.interruptor), por eso NO esta en
calipso/economia/. NO importa calipso.server ni calipso.memory.

El paso 2 (el padron) es el unico irreversible; los demas son idempotentes.
"""
from __future__ import annotations

import json
import pathlib

from calipso import routines
from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import operacion as op
from calipso.economia import tipos as tipos
from calipso.economia.candado import candado
from calipso.economia.pagador import Pagador
from calipso.plantel import interruptor as it

CONFIRMACION = "sembrar la economia"


def _pagador(base) -> Pagador:
    return Pagador(pathlib.Path(base) / "economia")


def _fabrica(config: dict) -> list[dict]:
    return [d for d in config["departamentos"] if d.get("zona") == "fabrica"]


def estado(base, semana: str) -> dict:
    """Que pasos ya estan hechos. Sirve para el preview y para la
    re-entrancia."""
    p = _pagador(base)
    sembrada = (p.ruta_registro.exists() and p.ruta_libro.exists()
                and p.ruta_sus.exists())
    est = {"sembrada": sembrada, "tesoro_mm": 0, "semana_abierta": False,
           "rutinas": [], "modo": it.leer(str(base)).modo}
    if sembrada:
        k = p.leer_kernel()
        asientos = k.libro.asientos()
        est["tesoro_mm"] = k.saldo(tipos.TESORO)
        est["semana_abierta"] = semana in cap.semanas_operativas(asientos)
    est["rutinas"] = [r.get("cuenta") for r in routines.load()
                      if r.get("kind") == "departamento"]
    return est


def sembrar_guiado(base, config: dict, ts: str, semana: str,
                   ejecutar: bool) -> dict:
    """Corre (o previsualiza) los 7 pasos. Sin `ejecutar`: devuelve el plan
    y el estado, sin escribir NADA. Con `ejecutar`: corre los pasos que
    falten y devuelve el reporte paso a paso."""
    if not ejecutar:
        return {"plan": config, "estado": estado(base, semana)}

    p = _pagador(base)
    pasos: list[dict] = []
    perillas = config["perillas_fabrica"]

    with candado(p.ruta_libro):
        # PASO 2 -- el padron (irreversible). Reusa el camino de `sembrar`.
        if not (p.ruta_registro.exists() and p.ruta_libro.exists()
                and p.ruta_sus.exists()):
            p.eco.mkdir(parents=True, exist_ok=True)
            registro = deps.Registro(p.ruta_registro)
            for d in config["departamentos"]:
                registro.alta(deps.Departamento(**d))
            sus = {n: cap.Suscripcion(nombre=n, **s)
                   for n, s in config["suscripciones"].items()}
            import dataclasses
            p.ruta_sus.write_text(
                json.dumps({n: dataclasses.asdict(s) for n, s in sus.items()},
                           ensure_ascii=False, indent=1), encoding="utf-8")
            p.ruta_libro.touch()
            pasos.append({"paso": "padron", "accion": "sembrado"})
        else:
            pasos.append({"paso": "padron", "accion": "ya estaba (saltea)"})

        # PASO 3 -- abrir la primera semana (antes de acuñar). Idempotente:
        # abrir_semana LEVANTA si la semana ya esta abierta.
        m = p.mercado_fresco()
        if semana not in cap.semanas_operativas(m.k.libro.asientos()):
            op.abrir_semana(m.k, ts, semana, config["cuota_firmable_mpt"],
                            config["reserva_personal_mpt"],
                            suscripciones=m.suscripciones)
            pasos.append({"paso": "semana", "accion": "abierta"})
        else:
            pasos.append({"paso": "semana", "accion": "ya abierta (saltea)"})

        # PASO 4 -- acuñar el capital de genesis al tesoro. Idempotente:
        # solo el faltante.
        k = p.leer_kernel()
        saldo = k.saldo(tipos.TESORO)
        objetivo = int(config["capital_tesoro_mm"])
        if saldo < objetivo:
            k.acunar(ts, semana, tipos.TESORO, objetivo - saldo,
                     tipos.SubtipoAcunacion.CAPITAL, {"tipo": "genesis"})
            pasos.append({"paso": "tesoro", "accion": f"acuñado {objetivo - saldo} mm"})
        else:
            pasos.append({"paso": "tesoro", "accion": "ya tenia capital (saltea)"})

        # PASO 5 -- perillas de cada depto de FABRICA. Idempotente.
        registro = deps.Registro(p.ruta_registro)
        for d in _fabrica(config):
            registro.ajustar(d["nombre"], **perillas)
        pasos.append({"paso": "perillas", "accion": f"{len(_fabrica(config))} deptos"})

    # PASO 6 -- una rutina departamento por depto de fabrica (archivo aparte).
    existentes = {r.get("cuenta") for r in routines.load()
                  if r.get("kind") == "departamento"}
    nuevas = 0
    for d in _fabrica(config):
        cuenta = f"dep:{d['nombre']}"
        if cuenta not in existentes:
            routines.add("departamento", f"jefe {d['nombre']}",
                         config["rutina_interval_min"], enabled=True,
                         cuenta=cuenta)
            nuevas += 1
    pasos.append({"paso": "rutinas", "accion": f"{nuevas} nuevas"})

    # PASO 7 -- plantel a vivo (archivo aparte).
    it.poner_modo(str(base), "vivo")
    pasos.append({"paso": "modo", "accion": "vivo"})

    return {"ok": True, "pasos": pasos, "estado": estado(base, semana)}
