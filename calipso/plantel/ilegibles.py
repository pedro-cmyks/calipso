#!/usr/bin/env python3
"""
calipso/plantel/ilegibles.py — la valvula de la gramatica de `proponer`.

Una ficha que no se entiende NO cae en `nada`: cae aca, y de aca sale a la
bandeja de la fabrica como un aviso con la prosa cruda adentro.

Por que no va al bus: el libro es contable y un aviso no es un objeto
economico -- no ocupa lugar, no compite, no se puede financiar y no cuenta
para el badge. Y por que existe: sin esto, la gramatica amordazaria al
departamento, porque lo que no entra en cuatro renglones desapareceria sin
dejar rastro.

Append-only y sin candado, como `cola._apilar`: una linea corta abierta en
modo "a" no se entrelaza con la de otro proceso.
"""
from __future__ import annotations

import datetime
import json
import pathlib

ARCHIVO = "ilegibles.jsonl"


def _ahora() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def ruta(base) -> pathlib.Path:
    # al lado del bus, que es donde vive el resto del estado del plantel
    return pathlib.Path(base) / "economia" / ARCHIVO


def anotar(base, semana: str, departamento: str, crudo: str) -> None:
    """La hora se la pone esta funcion, no el llamador.

    Al reves que un asiento del libro, que la recibe de afuera para que dos
    escrituras del mismo tic queden con la misma: esto es un rastro, nadie
    lo concilia contra nada, y `jefe.tic` no tiene ningun timestamp a mano
    -- su firma es `(ctx, cuenta, semana)`.
    """
    p = ruta(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    linea = json.dumps({"ts": _ahora(), "semana": semana,
                        "departamento": departamento, "crudo": crudo},
                       ensure_ascii=False)
    with p.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def colapsados(base) -> list[dict]:
    """Una fila por texto distinto, con su contador y su ts mas nuevo.

    Se colapsa por igualdad EXACTA del texto, no por parecido: el modelo
    local corre a temperatura 0, asi que la repeticion dentro de una semana
    es byte a byte y doscientos tics dan una fila con `veces: 200`. Un
    colapso difuso no se podria explicar y no haria falta.

    Una linea rota no voltea la lectura: el archivo lo escribe un proceso
    que puede morir a la mitad, y una linea cortada no puede esconder las
    demas.
    """
    p = ruta(base)
    try:
        crudo_texto = p.read_text(encoding="utf-8")
    except OSError:
        return []
    filas: dict[tuple[str, str], dict] = {}
    for linea in crudo_texto.splitlines():
        if not linea.strip():
            continue
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        clave = (d.get("departamento", ""), d.get("crudo", ""))
        fila = filas.get(clave)
        if fila is None:
            filas[clave] = {"departamento": clave[0], "crudo": clave[1],
                            "veces": 1, "ts": d.get("ts", "")}
        else:
            fila["veces"] += 1
            fila["ts"] = d.get("ts", "") or fila["ts"]
    return sorted(filas.values(), key=lambda f: f["ts"], reverse=True)
