#!/usr/bin/env python3
"""
calipso/consumo.py - probe pasivo de consumo de las suscripciones (Claude,
Codex).

El problema que resuelve: Calipso invoca `claude` y `codex` por CLI para la
ruta "subscription", y la pregunta de Pedro es "cuantas unidades da de
verdad un ciclo" -- hoy `capacidad_ciclo` en `economia/capacidad.py` es una
ESTIMACION sin medir (ver el comentario junto a `EcoSembrarSuscripcionBody`
en server.py: "Nadie lo sabe todavia... ESTIMACION A AJUSTAR").

Por que PASIVO. Medido en esta maquina: preguntarle al CLI su propio estado
(dos llamadas triviales) subio el `used_percent` de la ventana de 5 horas de
Codex de 7.0 a 9.0. Un probe que pregunta se come la cuota que quiere medir.
La alternativa correcta -- y la que implementa este modulo -- es leer lo que
los dos CLIs YA escriben solos en disco, sin que nadie se lo pida:

  - Claude Code: `~/.claude/projects/<proyecto>/<sesion>.jsonl` (y sus
    subagentes, en `subagents/**/*.jsonl` -- son llamadas API reales contra
    la MISMA cuota, verificado en esta maquina: mismo formato, mismo
    `message.usage`). Cada linea `"type": "assistant"` trae `message.usage`
    con `input_tokens`, `output_tokens`, `cache_creation_input_tokens`,
    `cache_read_input_tokens` y, cuando hay razonamiento,
    `output_tokens_details.thinking_tokens`. NINGUN porcentaje de cuota.
  - Codex: `~/.codex/sessions/<anio>/<mes>/<dia>/rollout-*.jsonl` trae
    eventos `{"type": "event_msg", "payload": {"type": "token_count", ...}}`
    con `info.last_token_usage` (tokens del ULTIMO turno; `total_token_usage`
    es un contador ACUMULADO de toda la sesion, no sirve para sumar) y,
    Y ESTO ES EL DATO BUENO, `rate_limits`: `primary.used_percent` (ventana
    de 300 minutos = 5 horas) y `secondary.used_percent` (ventana de 10080
    minutos = 1 semana), cada una con su `resets_at` (epoch) y `plan_type`.
    Codex SI expone el porcentaje real de cuota consumida; Claude no.

LO MAS IMPORTANTE: esos jsonl son las conversaciones reales de Pedro. Este
modulo extrae NUMEROS DE USO Y NADA MAS, por construccion: las funciones de
extraccion (`_extraer_claude`, `_extraer_codex`) leen un puñado de claves
fijas y conocidas (`message.id`, `message.model`, `message.usage.*`,
`payload.info.*`, `payload.rate_limits.*`, el `timestamp` de la linea) y
jamas tocan `message.content` ni ningun campo de texto libre. No hay un
`for k, v in obj.items(): guardar(k, v)` en ningun lado de este archivo: si
lo hubiera, un campo de texto se colaria el dia que alguien le agregue una
clave a estas structuras. Los registros que se persisten (`_Fila*`) tienen
un esquema CERRADO de numeros, ids opacos y timestamps -- no hay ningun
campo de texto libre que pueda cargar una frase. `test_consumo.py` siembra
un jsonl falso con una frase reconocible adentro de `message.content` (y
tambien en una linea que no parsea, para probar que ni un error de JSON la
deja escapar) y verifica que esa frase no aparece en ningun archivo bajo
CALIPSO_HOME ni en ninguna excepcion.

INCREMENTALIDAD. Los jsonl de Pedro ya suman ~200 MB en esta maquina y
crecen con cada turno; releerlos enteros en cada corrida no escala, y un
jsonl de sesion viva recibe lineas nuevas al final mientras el probe podria
estar leyendo. Se lleva un archivo de POSICIONES
(`consumo_posiciones.json`, {ruta: {"offset": N}}) que recuerda hasta que
byte de cada archivo ya se leyo: cada corrida solo abre, hace `seek(offset)`
y lee lo nuevo. Una linea que todavia no termina en "\n" (el CLI la sigue
escribiendo) se descarta de esta vuelta sin avanzar el offset sobre ella --
la proxima corrida la vuelve a intentar completa.

IDENTIDAD (por que el offset solo no alcanza). Verificado en los jsonl
reales de Pedro: un mismo turno de Claude aparece en VARIAS lineas del
archivo -- una por bloque de contenido (thinking, tool_use, text) -- y
todas comparten el mismo `message.id` pero el `usage` de las primeras es
PARCIAL (el bloque de thinking se escribe con `output_tokens` bajo, antes
de que el turno termine de generarse; el bloque final ya trae el total).
Confirmado con un ejemplo real: la misma `message.id` con `output_tokens`
7 en la linea de thinking y 405 en la linea final. Contar cada linea por
separado sobrecuenta Y subestima (la primera lectura parcial se cuenta como
si fuera el turno completo). La solucion: el escaneo (`escanear_*`)
ANOTA cada linea reconocida tal cual, sin decidir nada -- son eventos, el
registro es append-only de verdad. Quien DECIDE es el lector
(`_ultimo_por_id`): pliega por `id` quedandose con la ULTIMA fila en orden
de archivo, que en Claude siempre es la mas completa (las capturas de
Claude Code nunca retroceden en `output_tokens` para el mismo `message.id`,
verificado en los ejemplos reales). Esto ademas hace que una corrida
duplicada -- el probe corriendo dos veces, o un offset que por lo que sea
retrocede -- sea inofensiva: como mucho aparece una fila identica dos
veces en el registro, y "el ultimo gana" pliega igual. Para Codex no hace
falta: cada evento `token_count` es un turno distinto (nunca se repite el
mismo evento), asi que la identidad es simplemente `timestamp:total_tokens`
del propio evento -- unica por construccion, sin necesitar coordinacion.

ROBUSTEZ. Nada de lo que puede salir mal en estos archivos puede tumbar el
probe: un archivo que desaparece entre el listado y la lectura (`OSError` ->
se lo salta), una linea que no es JSON valido (`json.JSONDecodeError` -> se
la salta; el mensaje de esa excepcion de la stdlib nunca incluye el texto
de la linea, solo posicion), un campo ausente o de tipo raro (`_int`/`_num`
devuelven 0/None en vez de lanzar), un archivo mas chico que el offset
guardado (se relee desde cero en vez de reventar con un `seek` invalido).

Registro propio, NO en `suscripciones.json` (ese archivo es de escritura
unica -- `Pagador.desde_entorno` lo exige creado por `/api/economia/sembrar`
y este modulo no participa de esa escritura). Dos archivos append-only bajo
CALIPSO_HOME, uno por proveedor (esquemas distintos: Claude trae tokens,
Codex trae tokens + `rate_limits`; forzarlos a un esquema comun perderia
justamente el dato mas valioso de Codex): `consumo_claude.jsonl` y
`consumo_codex.jsonl`. `resumen()` los pliega y escribe
`consumo_resumen.json` (cache derivada, sobreescritura atomica -- mismo
patron que `routines.save`/`catastro._guardar_json`, no append-only: es una
FOTO, no un evento mas).
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
import threading
from typing import Any, Callable


# --------------------------------------------------------------------------
# Raices: resueltas EN CADA LLAMADA, nunca cacheadas en una constante de
# modulo. Mismo problema y misma solucion que calipso/catastro.py:
# calipso_home() (ver su docstring): un modulo importado una vez con el
# CALIPSO_HOME real queda cacheado en sys.modules, y una constante fijada
# al importar ignora cualquier `monkeypatch.setenv` posterior de un test
# que se creia aislado. Ademas reusamos el nombre de variable que YA usan
# el resto de los modulos del repo para cada CLI (`CLAUDE_HOME` en
# calipso/plugins.py; `CODEX_HOME` es la convencion real del propio Codex
# CLI): si Pedro alguna vez mueve esas carpetas, el probe las sigue solo.
# --------------------------------------------------------------------------

def calipso_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get(
        "CALIPSO_HOME", os.path.expanduser("~/.calipso")))


def raiz_claude() -> pathlib.Path:
    base = pathlib.Path(os.environ.get(
        "CLAUDE_HOME", os.path.expanduser("~/.claude")))
    return base / "projects"


def raiz_codex() -> pathlib.Path:
    base = pathlib.Path(os.environ.get(
        "CODEX_HOME", os.path.expanduser("~/.codex")))
    return base / "sessions"


# La economia mide ciclos de 4 semanas (economia/capacidad.py:
# SEMANAS_POR_CICLO). Se duplica el numero ACA a proposito, en vez de
# importarlo: este modulo no depende de nada bajo calipso/economia/ (ese
# arbol tiene otro trabajo en curso en la misma rama al escribir esto), y
# conceptualmente el probe no necesita saber nada de la economia -- solo le
# presta un numero al final. Si `SEMANAS_POR_CICLO` cambia alla, este
# modulo no se entera solo; es el precio de no acoplarse.
SEMANAS_POR_CICLO = 4


def _int(valor: Any) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _num(valor: Any) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _parse_ts(valor: Any) -> datetime.datetime | None:
    if not isinstance(valor, str) or not valor:
        return None
    try:
        d = datetime.datetime.fromisoformat(valor)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d


# --------------------------------------------------------------------------
# Lectura incremental de un jsonl: solo lineas COMPLETAS (terminadas en
# "\n") a partir de `offset`. Nunca lanza.
# --------------------------------------------------------------------------

def _leer_nuevas_lineas(path: pathlib.Path, offset: int) -> tuple[list[str], int]:
    try:
        size = path.stat().st_size
    except OSError:
        return [], offset  # desaparecio entre el listado y la lectura
    if size < offset:
        offset = 0  # se trunco/reemplazo: releer desde el principio
    if size == offset:
        return [], offset
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
    except OSError:
        return [], offset
    partes = data.split(b"\n")
    if data.endswith(b"\n"):
        completas = partes[:-1]
        nuevo_offset = offset + len(data)
    else:
        # ultima parte a medio escribir: se descarta esta vuelta, sin
        # avanzar el offset sobre ella
        completas = partes[:-1]
        nuevo_offset = offset + len(data) - len(partes[-1])
    lineas: list[str] = []
    for cruda in completas:
        if not cruda.strip():
            continue
        try:
            lineas.append(cruda.decode("utf-8"))
        except UnicodeDecodeError:
            continue  # basura binaria: se salta esa linea, no revienta
    return lineas, nuevo_offset


def _archivos_jsonl(raiz: pathlib.Path) -> list[pathlib.Path]:
    try:
        if not raiz.is_dir():
            return []
        return sorted(raiz.rglob("*.jsonl"))
    except OSError:
        return []


# --------------------------------------------------------------------------
# Extraccion: solo estas claves, nunca `content`/`text`. Ver el docstring
# del modulo -- esto es lo que hace la garantia "no se filtra contenido"
# cierta por construccion.
# --------------------------------------------------------------------------

def _extraer_claude(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict) or obj.get("type") != "assistant":
        return None
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return None
    mid = msg.get("id")
    usage = msg.get("usage")
    if not mid or not isinstance(usage, dict):
        return None
    detalles = usage.get("output_tokens_details")
    thinking = _int(detalles.get("thinking_tokens")) if isinstance(detalles, dict) else 0
    modelo = msg.get("model")
    return {
        "ts": obj.get("timestamp"),
        "id": str(mid),
        "modelo": modelo if isinstance(modelo, str) else None,
        "input_tokens": _int(usage.get("input_tokens")),
        "output_tokens": _int(usage.get("output_tokens")),
        "cache_creation_input_tokens": _int(usage.get("cache_creation_input_tokens")),
        "cache_read_input_tokens": _int(usage.get("cache_read_input_tokens")),
        "thinking_tokens": thinking,
    }


def _extraer_codex(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict) or obj.get("type") != "event_msg":
        return None
    payload = obj.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    ultimo = info.get("last_token_usage")
    if not isinstance(ultimo, dict):
        return None
    ts = obj.get("timestamp")
    if not isinstance(ts, str) or not ts:
        return None  # sin timestamp no hay identidad ni ventana: se salta
    total_acum = info.get("total_token_usage")
    total = (_int(total_acum.get("total_tokens"))
             if isinstance(total_acum, dict) else 0)
    rl = payload.get("rate_limits")
    rl = rl if isinstance(rl, dict) else {}
    primaria = rl.get("primary") if isinstance(rl.get("primary"), dict) else {}
    secundaria = rl.get("secondary") if isinstance(rl.get("secondary"), dict) else {}
    plan = rl.get("plan_type")
    return {
        "ts": ts,
        # identidad = (momento, total acumulado a ese momento): un evento
        # `token_count` de Codex no se repite nunca con los mismos dos
        # valores salvo que sea, de hecho, el mismo evento (ver docstring).
        "id": f"{ts}:{total}",
        "input_tokens": _int(ultimo.get("input_tokens")),
        "output_tokens": _int(ultimo.get("output_tokens")),
        "cached_input_tokens": _int(ultimo.get("cached_input_tokens")),
        "reasoning_output_tokens": _int(ultimo.get("reasoning_output_tokens")),
        "primary_used_percent": _num(primaria.get("used_percent")),
        "primary_window_minutos": _int(primaria.get("window_minutes")) or None,
        "primary_resets_at": _int(primaria.get("resets_at")) or None,
        "secondary_used_percent": _num(secundaria.get("used_percent")),
        "secondary_window_minutos": _int(secundaria.get("window_minutes")) or None,
        "secondary_resets_at": _int(secundaria.get("resets_at")) or None,
        "plan_type": plan if isinstance(plan, str) else None,
    }


# --------------------------------------------------------------------------
# Persistencia: posiciones (estado del escaneo) + los dos registros
# append-only. Mismo patron atomico (tmp + os.replace) que routines.save.
# --------------------------------------------------------------------------

def _posiciones_file() -> pathlib.Path:
    home = calipso_home()
    home.mkdir(parents=True, exist_ok=True)
    return home / "consumo_posiciones.json"


def _cargar_posiciones() -> dict[str, dict]:
    f = _posiciones_file()
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _guardar_posiciones(data: dict) -> None:
    p = _posiciones_file()
    tmp = p.with_name(f"{p.name}.tmp{os.getpid()}.{threading.get_ident()}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, p)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def _registro_claude_file() -> pathlib.Path:
    return calipso_home() / "consumo_claude.jsonl"


def _registro_codex_file() -> pathlib.Path:
    return calipso_home() / "consumo_codex.jsonl"


def _append_registro(path: pathlib.Path, filas: list[dict]) -> None:
    if not filas:
        return
    calipso_home().mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for fila in filas:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")


def _leer_registro(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        texto = path.read_text(encoding="utf-8")
    except OSError:
        return []
    filas: list[dict] = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            obj = json.loads(linea)
        except ValueError:
            continue
        if isinstance(obj, dict):
            filas.append(obj)
    return filas


def _ultimo_por_id(filas: list[dict]) -> list[dict]:
    """Pliega por `id`, quedandose con la ULTIMA fila en orden de archivo
    (que es orden de escritura: el registro es append-only). Ver "IDENTIDAD"
    en el docstring del modulo."""
    por_id: dict[str, dict] = {}
    for fila in filas:
        ident = fila.get("id")
        if ident is None:
            continue
        por_id[str(ident)] = fila
    return list(por_id.values())


# --------------------------------------------------------------------------
# Escaneo
# --------------------------------------------------------------------------

def _escanear_proveedor(raiz: pathlib.Path, registro: pathlib.Path,
                        extraer: Callable[[Any], dict | None]) -> int:
    posiciones = _cargar_posiciones()
    nuevas = 0
    for archivo in _archivos_jsonl(raiz):
        clave = str(archivo)
        offset = _int((posiciones.get(clave) or {}).get("offset", 0))
        lineas, nuevo_offset = _leer_nuevas_lineas(archivo, offset)
        if lineas:
            filas = []
            for linea in lineas:
                try:
                    obj = json.loads(linea)
                except ValueError:
                    continue  # linea corrupta (a medio escribir, binaria): se salta
                fila = extraer(obj)
                if fila is not None:
                    filas.append(fila)
            _append_registro(registro, filas)
            nuevas += len(filas)
        if nuevo_offset != offset:
            posiciones[clave] = {"offset": nuevo_offset}
    _guardar_posiciones(posiciones)
    return nuevas


def escanear_claude() -> int:
    """Escanea ~/.claude/projects (incremental) y devuelve cuantas filas
    nuevas se agregaron a consumo_claude.jsonl."""
    return _escanear_proveedor(raiz_claude(), _registro_claude_file(), _extraer_claude)


def escanear_codex() -> int:
    """Escanea ~/.codex/sessions (incremental) y devuelve cuantas filas
    nuevas se agregaron a consumo_codex.jsonl."""
    return _escanear_proveedor(raiz_codex(), _registro_codex_file(), _extraer_codex)


def escanear() -> dict[str, int]:
    return {"claude": escanear_claude(), "codex": escanear_codex()}


# --------------------------------------------------------------------------
# Resumen: pliega los registros y propone un capacidad_ciclo por proveedor.
# Ver el docstring del modulo para la distincion medicion/inferencia.
# --------------------------------------------------------------------------

def _resumen_claude() -> dict[str, Any]:
    filas = _ultimo_por_id(_leer_registro(_registro_claude_file()))
    turnos = len(filas)
    tokens = {
        "input_tokens": sum(_int(f.get("input_tokens")) for f in filas),
        "output_tokens": sum(_int(f.get("output_tokens")) for f in filas),
        "cache_creation_input_tokens": sum(_int(f.get("cache_creation_input_tokens")) for f in filas),
        "cache_read_input_tokens": sum(_int(f.get("cache_read_input_tokens")) for f in filas),
        "thinking_tokens": sum(_int(f.get("thinking_tokens")) for f in filas),
    }
    fechas = [d for d in (_parse_ts(f.get("ts")) for f in filas) if d is not None]

    ritmo_semanal = None
    capacidad_propuesta = None
    if len(fechas) >= 2:
        span_dias = (max(fechas) - min(fechas)).total_seconds() / 86400
        if span_dias > 0:
            ritmo_semanal = turnos / (span_dias / 7)
            capacidad_propuesta = round(ritmo_semanal * SEMANAS_POR_CICLO)

    if capacidad_propuesta is not None:
        nota = (f"extrapolacion lineal: {turnos} turnos observados en "
               f"{(max(fechas) - min(fechas)).days} dias de historia, "
               f"proyectados a {SEMANAS_POR_CICLO} semanas. Claude no "
               "expone ningun porcentaje de cuota consumida (a diferencia "
               "de Codex): esto NO mide cuota real, es un piso basado en "
               "el ritmo historico de uso de Pedro.")
    else:
        nota = ("sin suficiente historia todavia (menos de dos turnos con "
                "timestamp legible, o todos en el mismo instante)")

    return {
        "medicion": {
            "turnos_observados": turnos,
            "tokens": tokens,
            "desde": min(fechas).isoformat() if fechas else None,
            "hasta": max(fechas).isoformat() if fechas else None,
        },
        "inferencia": {
            "ritmo_turnos_por_semana": (round(ritmo_semanal, 2)
                                        if ritmo_semanal is not None else None),
            "capacidad_ciclo_propuesta": capacidad_propuesta,
            "nota": nota,
        },
    }


def _ventana_codex(ultimo: dict, con_fecha: list[tuple[dict, datetime.datetime]],
                   prefijo: str) -> dict[str, Any]:
    pct = ultimo.get(f"{prefijo}_used_percent")
    minutos = ultimo.get(f"{prefijo}_window_minutos")
    resets_at = ultimo.get(f"{prefijo}_resets_at")
    turnos_ventana = None
    capacidad_ventana = None
    if isinstance(minutos, int) and resets_at:
        try:
            fin = datetime.datetime.fromtimestamp(int(resets_at), tz=datetime.timezone.utc)
        except (OverflowError, OSError, ValueError, TypeError):
            fin = None
        if fin is not None:
            inicio = fin - datetime.timedelta(minutes=minutos)
            turnos_ventana = sum(1 for _, d in con_fecha if d >= inicio)
    if turnos_ventana and isinstance(pct, (int, float)) and pct > 0:
        capacidad_ventana = round(turnos_ventana / (pct / 100))
    return {
        "used_percent": pct,
        "window_minutos": minutos,
        "resets_at": resets_at,
        "turnos_en_la_ventana": turnos_ventana,
        "capacidad_ventana_inferida": capacidad_ventana,
    }


def _resumen_codex() -> dict[str, Any]:
    filas = _ultimo_por_id(_leer_registro(_registro_codex_file()))
    con_fecha = [(f, d) for f in filas for d in [_parse_ts(f.get("ts"))] if d is not None]
    if not con_fecha:
        return {"medicion": None, "inferencia": None,
                "nota": "sin datos de codex todavia"}

    ultimo, _ = max(con_fecha, key=lambda par: par[1])
    primaria = _ventana_codex(ultimo, con_fecha, "primary")
    secundaria = _ventana_codex(ultimo, con_fecha, "secondary")

    capacidad_propuesta = None
    if secundaria["capacidad_ventana_inferida"] is not None:
        capacidad_propuesta = secundaria["capacidad_ventana_inferida"] * SEMANAS_POR_CICLO

    return {
        "medicion": {
            "plan_type": ultimo.get("plan_type"),
            # used_percent es la MEDICION honesta: Codex la reporta
            # directa, sin que este modulo estime nada.
            "ventana_primaria_5h": primaria,
            "ventana_secundaria_semanal": secundaria,
        },
        "inferencia": {
            "capacidad_ciclo_propuesta": capacidad_propuesta,
            "nota": (
                "capacidad_ventana_inferida (turnos que llenarian la "
                "ventana al ritmo actual, derivado de used_percent real) "
                "SI se apoya en una medicion; multiplicarla por "
                f"{SEMANAS_POR_CICLO} para estimar un capacidad_ciclo NO: "
                "asume ritmo constante, y ademas la ventana secundaria de "
                "Codex resetea cada semana real mientras que la economia "
                "de Calipso factura ciclos de 4 semanas -- son cadencias "
                "distintas, esto no las concilia, solo las multiplica."
            ),
        },
    }


def resumen(ahora: datetime.datetime | None = None) -> dict[str, Any]:
    ahora = ahora or datetime.datetime.now(datetime.timezone.utc)
    datos = {
        "generado": ahora.isoformat(timespec="seconds"),
        "claude": _resumen_claude(),
        "codex": _resumen_codex(),
    }
    _guardar_resumen(datos)
    return datos


def _resumen_file() -> pathlib.Path:
    return calipso_home() / "consumo_resumen.json"


def _guardar_resumen(datos: dict) -> None:
    calipso_home().mkdir(parents=True, exist_ok=True)
    p = _resumen_file()
    tmp = p.with_name(f"{p.name}.tmp{os.getpid()}.{threading.get_ident()}")
    try:
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, p)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def cargar_resumen() -> dict[str, Any] | None:
    f = _resumen_file()
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
