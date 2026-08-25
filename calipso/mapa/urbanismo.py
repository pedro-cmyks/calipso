"""
calipso/mapa/urbanismo.py — Donde nace y crece cada departamento.

Resortes donde hay comercio, repulsion entre todos, un resorte de
pertenencia entre vecinos de la misma zona (solo cuando hay mas de una
zona en juego, para que la ciudad se agrupe por barrio), y anclaje por
antiguedad: el mas viejo queda clavado y la inercia baja con el orden de
llegada, asi la ciudad CRECE HACIA AFUERA en vez de reacomodarse entera
cuando nace un departamento. Determinista de punta a punta: la posicion
inicial sale de un SHA-256 del nombre (nunca de hash(), que varia entre
procesos), el numero de iteraciones es fijo y todo recorrido va ordenado.
"""
from __future__ import annotations

import hashlib
import math

K_REPULSION = 150_000.0
K_RESORTE = 0.030
PASO = 0.55
AMORTIGUACION = 0.6
SEPARACION_ZONAS = 9_000.0
K_ZONA = 0.15
REPOSO_ZONA = 150.0
RADIO_INICIAL = 120.0
REPOSO = (0.0, 260.0, 190.0, 130.0, 80.0)  # indexado por ancho 1..4


def _angulo(nombre: str) -> float:
    h = hashlib.sha256(nombre.encode("utf-8")).digest()
    return (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * 2 * math.pi


def urbanizar(edificios: list[dict], calles: list[dict],
              iteraciones: int = 300) -> dict[str, tuple[int, int]]:
    if not edificios:
        return {}
    orden = sorted(edificios, key=lambda e: (e["orden"], e["id"]))
    ancla = orden[0]["id"]
    pos: dict[str, list[float]] = {}
    masa: dict[str, float] = {}
    zona: dict[str, str] = {}
    for i, e in enumerate(orden):
        ang = _angulo(e["id"])
        radio = RADIO_INICIAL * (1 + i)
        pos[e["id"]] = [radio * math.cos(ang), radio * math.sin(ang)]
        masa[e["id"]] = 1.0 + e["tamano"] + max(0.0, 6.0 - e["orden"])
        zona[e["id"]] = e["zona"]
    pos[ancla] = [0.0, 0.0]

    ids = sorted(pos)
    vel = {i: [0.0, 0.0] for i in ids}
    aristas = [(a["a"], a["b"], REPOSO[min(4, max(1, a["ancho"]))])
               for a in calles if a["a"] in pos and a["b"] in pos]
    # el resorte de pertenencia solo entra en juego si hay mas de una zona:
    # con una sola zona (el caso mono-departamento tipico) su ausencia deja
    # el resto de la fisica intacta.
    multizona = len(set(zona.values())) > 1

    for _ in range(iteraciones):
        fuerza = {i: [0.0, 0.0] for i in ids}
        for n, x in enumerate(ids):
            for y in ids[n + 1:]:
                dx = pos[y][0] - pos[x][0]
                dy = pos[y][1] - pos[x][1]
                d2 = max(dx * dx + dy * dy, 1.0)
                d = math.sqrt(d2)
                f = K_REPULSION / d2
                fuerza[x][0] -= f * dx / d
                fuerza[x][1] -= f * dy / d
                fuerza[y][0] += f * dx / d
                fuerza[y][1] += f * dy / d
                if multizona:
                    if zona[x] != zona[y]:
                        g = SEPARACION_ZONAS / d
                        fuerza[x][0] -= g * dx / d
                        fuerza[x][1] -= g * dy / d
                        fuerza[y][0] += g * dx / d
                        fuerza[y][1] += g * dy / d
                    else:
                        g = K_ZONA * (d - REPOSO_ZONA)
                        fuerza[x][0] += g * dx / d
                        fuerza[x][1] += g * dy / d
                        fuerza[y][0] -= g * dx / d
                        fuerza[y][1] -= g * dy / d
        for x, y, reposo in aristas:
            dx = pos[y][0] - pos[x][0]
            dy = pos[y][1] - pos[x][1]
            d = max(math.sqrt(dx * dx + dy * dy), 1.0)
            f = K_RESORTE * (d - reposo)
            fuerza[x][0] += f * dx / d
            fuerza[x][1] += f * dy / d
            fuerza[y][0] -= f * dx / d
            fuerza[y][1] -= f * dy / d
        for i in ids:
            if i == ancla:
                continue
            vel[i][0] = (vel[i][0] + fuerza[i][0] * PASO / masa[i]) * AMORTIGUACION
            vel[i][1] = (vel[i][1] + fuerza[i][1] * PASO / masa[i]) * AMORTIGUACION
            pos[i][0] += vel[i][0]
            pos[i][1] += vel[i][1]

    return {i: (round(pos[i][0]), round(pos[i][1])) for i in ids}
