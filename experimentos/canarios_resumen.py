"""El resumen de los canarios sobre telemetry.jsonl (spec 2026-09-11,
seccion 3): cuantos turnos, cuantos con `sin_anclaje` (y de esos cuantos
aplicaron y por que), las senales de degeneracion por nombre, la ventana
(recortes, truncados, no cupo, tokenizador real o fallback), todo por ruta.
Ruling YAGNI del spec: el contador en /fabrica se hace cuando estos numeros
digan cual conviene mirar.

Uso: `python -m experimentos.canarios_resumen [ruta/telemetry.jsonl]`
(sin ruta: $CALIPSO_HOME/telemetry.jsonl o ~/.calipso/telemetry.jsonl, solo
lectura). No importa `calipso`.
"""
from __future__ import annotations

import collections
import json
import os
import pathlib
import sys


def leer(ruta: pathlib.Path) -> list[dict]:
    filas = []
    if not ruta.exists():
        return filas
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            f = json.loads(linea)
        except ValueError:
            continue
        if f.get("kind") == "chat_turn" and isinstance(f.get("canarios"), dict):
            filas.append(f)
    return filas


def resumir(filas: list[dict]) -> dict:
    r = {"turnos": len(filas), "fallidos": 0, "por_ruta": collections.Counter(),
         "sin_anclaje_turnos": 0, "sin_anclaje_aplica": 0, "sin_anclaje_por_tipo": collections.Counter(),
         "aplica_por": collections.Counter(), "solo_calipso_turnos": 0, "tapados": 0,
         "degeneracion": collections.Counter(), "degeneracion_turnos": 0,
         "pasadas": 0, "recortes": collections.Counter(), "truncadas": 0, "sin_medicion": 0,
         "no_cabe": 0, "tokenizador": collections.Counter(), "por_ruta_sin_anclaje": collections.Counter()}
    for f in filas:
        v = f["canarios"]
        ruta = f.get("route_used") or "?"
        r["por_ruta"][ruta] += 1
        if v.get("error") or v.get("anclaje") is None:
            r["fallidos"] += 1
            continue
        a = v["anclaje"]
        if a.get("sin_anclaje"):
            r["sin_anclaje_turnos"] += 1
            r["por_ruta_sin_anclaje"][ruta] += 1
            if a.get("aplica"):
                r["sin_anclaje_aplica"] += 1
            for s in a["sin_anclaje"]:
                r["sin_anclaje_por_tipo"][s.get("tipo", "?")] += 1
        for motivo in a.get("aplica_por") or []:
            r["aplica_por"][motivo] += 1
        if a.get("anclado_solo_en_calipso"):
            r["solo_calipso_turnos"] += 1
        if a.get("tapado"):
            r["tapados"] += 1
        if v.get("degeneracion"):
            r["degeneracion_turnos"] += 1
            for s in v["degeneracion"]:
                r["degeneracion"][s.get("senal", "?")] += 1
        for p in v.get("ventana") or []:
            r["pasadas"] += 1
            for rec in p.get("recorte") or []:
                r["recortes"][rec] += 1
            if p.get("truncado") is True:
                r["truncadas"] += 1
            elif p.get("truncado") == "sin medicion":
                r["sin_medicion"] += 1
            if p.get("no_cabe"):
                r["no_cabe"] += 1
            r["tokenizador"][p.get("tokenizador") or "?"] += 1
    return r


def texto(r: dict) -> str:
    def fila(c):
        return ", ".join(f"{k}={n}" for k, n in sorted(c.items())) or "-"
    return "\n".join([
        f"turnos con canario: {r['turnos']} (fallidos: {r['fallidos']}); por ruta: {fila(r['por_ruta'])}",
        f"anclaje: {r['sin_anclaje_turnos']} turnos con sin_anclaje ({r['sin_anclaje_aplica']} con la marca visible); "
        f"por tipo: {fila(r['sin_anclaje_por_tipo'])}; por ruta: {fila(r['por_ruta_sin_anclaje'])}",
        f"  aplica_por: {fila(r['aplica_por'])}; anclado solo en Calipso: {r['solo_calipso_turnos']} turnos; "
        f"tapados: {r['tapados']}",
        f"degeneracion: {r['degeneracion_turnos']} turnos; por senal: {fila(r['degeneracion'])}",
        f"ventana: {r['pasadas']} pasadas; recortes: {fila(r['recortes'])}; truncadas: {r['truncadas']}; "
        f"sin medicion: {r['sin_medicion']}; no cupo: {r['no_cabe']}; tokenizador: {fila(r['tokenizador'])}",
    ])


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ruta = pathlib.Path(argv[0]) if argv else pathlib.Path(
        os.environ.get("CALIPSO_HOME", os.path.expanduser("~/.calipso"))) / "telemetry.jsonl"
    filas = leer(ruta)
    print(f"{ruta}: {len(filas)} filas chat_turn con canarios")
    print(texto(resumir(filas)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
