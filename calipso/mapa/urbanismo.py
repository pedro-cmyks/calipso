"""
calipso/mapa/urbanismo.py — Donde nace y crece cada departamento.

COLOCACION INCREMENTAL POR ANTIGUEDAD. Los edificios se ordenan por su
primera aparicion en el libro; el mas viejo va al origen y cada uno de los
siguientes se relaja SOLO A EL contra los que ya estan colocados, que
quedan congelados. Cuando termina, se congela tambien y sigue el proximo.

Asi el anclaje deja de ser un tuneo y pasa a ser una propiedad de la
forma: un departamento nuevo se agrega al final del orden, y las
posiciones de todos los que ya estaban salen BIT A BIT IDENTICAS. La
ciudad crece hacia afuera de verdad. El precio, elegido a proposito: un
edificio viejo ya no se acerca a un socio comercial nuevo, porque no se
mueve mas.

Sobre el edificio que se coloca actuan tres fuerzas, todas par a par
contra los ya colocados:

  - repulsion inversa al cuadrado, para que nadie se encime;
  - un resorte de pertenencia hacia los de su misma zona (reposo corto) y
    uno de separacion contra los de las otras (reposo largo): las dos
    caras de la misma regla, y lo que deja el barrio personal aparte pero
    en la misma pantalla;
  - el resorte de cada calle que lo toca, mas corto cuanto mas comercio.

Todos los resortes son atractivos mas alla de su reposo, asi que un
edificio suelto siempre tiene equilibrio y la relajacion converge; no hay
un minimo global inestable del que depender.

Determinista de punta a punta: la posicion inicial sale de un SHA-256 del
nombre (nunca de hash(), que varia entre procesos), el numero de
iteraciones es fijo y todo recorrido va ordenado.
"""
from __future__ import annotations

import hashlib
import math

K_REPULSION = 150_000.0
K_RESORTE = 0.030
PASO = 0.55
AMORTIGUACION = 0.6
SEPARACION_ZONAS = 900.0
K_SEPARACION = 0.15
K_ZONA = 0.15
REPOSO_ZONA = 150.0
RADIO_INICIAL = 120.0
ITERACIONES = 300
REPOSO = (0.0, 260.0, 190.0, 130.0, 80.0)  # indexado por ancho 1..4


def _angulo(nombre: str) -> float:
    h = hashlib.sha256(nombre.encode("utf-8")).digest()
    return (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * 2 * math.pi


def _par(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _colocar(id: str, borde: float, tamano: int,
             vecinos: list[tuple[float, float, bool, float | None]],
             iteraciones: int) -> tuple[float, float]:
    """Relaja UN edificio contra los ya colocados, que no se mueven.

    Nace JUSTO AFUERA del borde de la ciudad de ese momento, en el angulo
    que le da su nombre: asi entra por el lado que le toca y le queda
    presupuesto de relajacion para acomodarse, en vez de gastarlo viajando
    desde un radio que crece con el numero de edificios."""
    ang = _angulo(id)
    radio = borde + RADIO_INICIAL
    x, y = radio * math.cos(ang), radio * math.sin(ang)
    vx = vy = 0.0
    masa = 1.0 + tamano
    for _ in range(iteraciones):
        fx = fy = 0.0
        for ox, oy, misma_zona, reposo_calle in vecinos:
            dx, dy = ox - x, oy - y
            d2 = max(dx * dx + dy * dy, 1.0)
            d = math.sqrt(d2)
            # positivo = hacia el vecino, negativo = alejandose
            f = -K_REPULSION / d2
            if misma_zona:
                f += K_ZONA * (d - REPOSO_ZONA)
            else:
                f += K_SEPARACION * (d - SEPARACION_ZONAS)
            if reposo_calle is not None:
                f += K_RESORTE * (d - reposo_calle)
            fx += f * dx / d
            fy += f * dy / d
        vx = (vx + fx * PASO / masa) * AMORTIGUACION
        vy = (vy + fy * PASO / masa) * AMORTIGUACION
        x += vx
        y += vy
    return x, y


def urbanizar(edificios: list[dict], calles: list[dict],
              iteraciones: int = ITERACIONES) -> dict[str, tuple[int, int]]:
    if not edificios:
        return {}
    orden = sorted(edificios, key=lambda e: (e["orden"], e["id"]))
    reposo_calle = {_par(a["a"], a["b"]): REPOSO[min(4, max(1, a["ancho"]))]
                    for a in sorted(calles, key=lambda a: (a["a"], a["b"]))}
    pos: dict[str, tuple[float, float]] = {}
    zona: dict[str, str] = {}
    colocados: list[str] = []
    borde = 0.0
    for e in orden:
        id = e["id"]
        zona[id] = e["zona"]
        if not colocados:
            pos[id] = (0.0, 0.0)
        else:
            vecinos = [(pos[o][0], pos[o][1], zona[o] == zona[id],
                        reposo_calle.get(_par(id, o)))
                       for o in colocados]
            pos[id] = _colocar(id, borde, e["tamano"], vecinos, iteraciones)
        colocados.append(id)
        borde = max(borde, math.hypot(*pos[id]))
    return {i: (round(pos[i][0]), round(pos[i][1])) for i in sorted(pos)}
