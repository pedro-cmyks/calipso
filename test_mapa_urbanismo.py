"""Tests del urbanismo: colocacion incremental determinista y anclada.

Las dos garantias de la fisica —crecimiento anclado y un barrio personal
legible— se verifican sobre modelos que salen de `ciudad()`, no sobre
diccionarios escritos a mano: un test que corre sobre una forma que la
produccion no emite no certifica nada.
"""
import json
import math
import pathlib
import subprocess
import sys

import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import cola as cola_mod
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.mapa import ciudad as ciu
from calipso.mapa import urbanismo as urb

TS = "2026-08-25T10:00:00"
W = "2026-W35"
RAIZ = pathlib.Path(__file__).parent


def _edi(id, orden, tamano=3, zona="fabrica"):
    return {"id": id, "orden": orden, "tamano": tamano, "zona": zona}


def _dist(pos, a, b):
    return math.dist(pos[a], pos[b])


# -- libro sintetico y modelo -------------------------------------------------

def _fundar(ruta, fabrica, personales):
    """Un libro con `fabrica` departamentos de fabrica y `personales` de la
    zona personal, todos con capital propio, mas la casa de Pedro."""
    ruta.mkdir(parents=True, exist_ok=True)
    k = Kernel(Libro(ruta / "libro.jsonl"))
    r = deps.Registro(ruta / "departamentos.json")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    pt.expirar_pools(k, TS, W)
    k.acunar(TS, W, t.CUENTA_PEDRO, 5_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    for i in range(fabrica):
        r.alta(deps.Departamento(f"f{i}", deps.ZONA_FABRICA))
        k.acunar(TS, W, f"dep:f{i}", 50_000 * (i + 1),
                 t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    for i in range(personales):
        r.alta(deps.Departamento(f"p{i}", deps.ZONA_PERSONAL))
        k.acunar(TS, W, f"personal:p{i}", 10_000 * (i + 1),
                 t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    return ruta


def _nace_un_departamento(ruta):
    """El alta y el primer asiento de un departamento nuevo, AL FINAL del
    libro: asi aparece en la realidad, no intercalado en la historia."""
    k = Kernel(Libro(ruta / "libro.jsonl"))
    r = deps.Registro(ruta / "departamentos.json")
    r.alta(deps.Departamento("nuevo", deps.ZONA_FABRICA))
    k.acunar("2026-08-26T10:00:00", W, "dep:nuevo", 30_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    return ruta


def _modelo(ruta):
    k = Kernel(Libro(ruta / "libro.jsonl"))
    r = deps.Registro(ruta / "departamentos.json")
    b = bus_mod.Bus(ruta / "bus.jsonl")
    c = cola_mod.Cola(ruta / "cola.jsonl")
    return ciu.ciudad(k.libro.asientos(), r, b, c, W)


def _urbanizada(ruta):
    m = _modelo(ruta)
    return urb.urbanizar(m["edificios"], m["calles"]), m


# -- los dos criterios, como helpers ------------------------------------------

def crecio_hacia_afuera(antes, despues):
    """Anclaje: al nacer un departamento, los que ya estaban no se mueven ni
    un pixel. Con colocacion incremental esto es exacto, no aproximado."""
    return all(despues[id] == pos for id, pos in antes.items())


def _pares(ids):
    return [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]]


def _media(pos, pares):
    return sum(_dist(pos, a, b) for a, b in pares) / len(pares) if pares else 0.0


def barrio_legible(pos, zonas):
    """El barrio personal se distingue a simple vista y nadie se encima:

    - la separacion minima entre zonas supera la distancia media entre
      edificios de la misma zona (hay un hueco, no una mezcla);
    - los personales estan mas cerca entre si que de la fabrica;
    - ningun par de edificios queda a menos de 20.
    """
    ids = sorted(pos)
    personales = [i for i in ids if zonas[i] == deps.ZONA_PERSONAL]
    fabrica = [i for i in ids if zonas[i] == deps.ZONA_FABRICA]
    mismos = [(a, b) for a, b in _pares(ids) if zonas[a] == zonas[b]]
    cruzados = [(a, b) for a, b in _pares(ids) if zonas[a] != zonas[b]]
    hueco = min(_dist(pos, a, b) for a, b in cruzados)
    encimados = min(_dist(pos, a, b) for a, b in _pares(ids))
    personal_personal = _media(pos, _pares(personales))
    personal_fabrica = _media(pos, [(a, b) for a in personales for b in fabrica])
    return (hueco > _media(pos, mismos)
            and personal_personal < personal_fabrica
            and encimados > 20)


# -- anclaje ------------------------------------------------------------------

@pytest.mark.parametrize("fabrica,personales", [(12, 3), (1, 6)])
def test_un_departamento_nuevo_no_reacomoda_la_ciudad(tmp_path, fabrica,
                                                      personales):
    """Anclaje por antiguedad, sobre un modelo que `ciudad()` emite de
    verdad: la ciudad crece hacia afuera."""
    antes_ruta = _fundar(tmp_path / "antes", fabrica, personales)
    despues_ruta = _nace_un_departamento(
        _fundar(tmp_path / "despues", fabrica, personales))
    antes, m_antes = _urbanizada(antes_ruta)
    despues, _ = _urbanizada(despues_ruta)
    assert "dep:nuevo" in despues and "dep:nuevo" not in antes
    mas_viejo = min(m_antes["edificios"], key=lambda e: (e["orden"], e["id"]))
    assert antes[mas_viejo["id"]] == (0, 0)     # el mas viejo, clavado
    assert crecio_hacia_afuera(antes, despues)


@pytest.mark.parametrize("fabrica,personales", [(12, 3), (1, 6)])
def test_la_zona_personal_es_un_barrio_legible(tmp_path, fabrica, personales):
    pos, modelo = _urbanizada(_fundar(tmp_path / "c", fabrica, personales))
    zonas = {e["id"]: e["zona"] for e in modelo["edificios"]}
    assert barrio_legible(pos, zonas)


def test_el_barrio_sigue_siendo_legible_despues_de_crecer(tmp_path):
    ruta = _nace_un_departamento(_fundar(tmp_path / "c", 12, 3))
    pos, modelo = _urbanizada(ruta)
    zonas = {e["id"]: e["zona"] for e in modelo["edificios"]}
    assert barrio_legible(pos, zonas)


# -- fisica, sobre formas minimas ---------------------------------------------

def test_el_mas_viejo_queda_clavado_en_el_origen():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1), _edi("dep:c", 2)]
    pos = urb.urbanizar(edis, [])
    assert pos["dep:a"] == (0, 0)
    # y los demas quedan lejos del ancla, no encima de ella
    assert _dist(pos, "dep:a", "dep:b") > 20
    assert _dist(pos, "dep:a", "dep:c") > 20


def test_mismo_insumo_mismas_coordenadas():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1), _edi("dep:c", 2)]
    calles = [{"a": "dep:a", "b": "dep:b", "ancho": 4}]
    assert urb.urbanizar(edis, calles) == urb.urbanizar(edis, calles)
    # y no depende del orden en que vengan las listas
    assert urb.urbanizar(edis, calles) == urb.urbanizar(
        list(reversed(edis)), calles)


def test_los_que_comercian_quedan_mas_cerca():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1), _edi("dep:c", 2)]
    juntos = urb.urbanizar(edis, [{"a": "dep:a", "b": "dep:b", "ancho": 4}])
    sueltos = urb.urbanizar(edis, [])
    assert _dist(juntos, "dep:a", "dep:b") < _dist(sueltos, "dep:a", "dep:b")


def test_mas_comercio_es_menos_distancia():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1)]
    fuerte = urb.urbanizar(edis, [{"a": "dep:a", "b": "dep:b", "ancho": 4}])
    debil = urb.urbanizar(edis, [{"a": "dep:a", "b": "dep:b", "ancho": 1}])
    assert _dist(fuerte, "dep:a", "dep:b") < _dist(debil, "dep:a", "dep:b")


def test_nadie_queda_encimado():
    edis = [_edi(f"dep:{n}", i) for i, n in enumerate("abcdef")]
    pos = urb.urbanizar(edis, [])
    for x, y in _pares(sorted(pos)):
        assert _dist(pos, x, y) > 20


def test_ciudad_vacia_y_de_uno_no_rompen():
    assert urb.urbanizar([], []) == {}
    assert urb.urbanizar([_edi("dep:solo", 0)], []) == {"dep:solo": (0, 0)}


# -- determinismo ENTRE PROCESOS ----------------------------------------------

_GUION = """
import json, sys
sys.path.insert(0, {raiz!r})
from calipso.mapa import urbanismo as urb
edis = [{{"id": "dep:%s" % n, "orden": i, "tamano": 3,
          "zona": "personal" if i % 3 == 0 else "fabrica"}}
        for i, n in enumerate("abcdefgh")]
calles = [{{"a": "dep:a", "b": "dep:d", "ancho": 2}}]
print(json.dumps(sorted(urb.urbanizar(edis, calles).items())))
"""


def _urbanizar_en_subproceso(semilla):
    return subprocess.run(
        [sys.executable, "-c", _GUION.format(raiz=str(RAIZ))],
        capture_output=True, text=True, check=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": semilla}).stdout


def test_mismas_coordenadas_en_procesos_con_distinto_hashseed():
    """El invariante bandera de la rama: `hash()` de Python es estable
    DENTRO de un proceso, asi que dos derivaciones en el mismo proceso no
    verifican nada. Este test falla si alguien vuelve a poner hash()."""
    uno = _urbanizar_en_subproceso("0")
    dos = _urbanizar_en_subproceso("98765")
    assert uno == dos
    assert "dep:a" in uno   # el guion corrio de verdad


# -- frontera de imports ------------------------------------------------------

_GUION_IMPORT = """
import json, sys
sys.path.insert(0, {raiz!r})
import calipso.mapa.urbanismo
print(json.dumps([m for m in sys.modules if m.startswith("calipso.economia")]))
"""


def test_urbanismo_no_arrastra_la_economia():
    """La restriccion 'urbanismo importa solo hashlib y math' vale tambien a
    nivel de import, no solo de archivo."""
    salida = subprocess.run(
        [sys.executable, "-c", _GUION_IMPORT.format(raiz=str(RAIZ))],
        capture_output=True, text=True, check=True,
        env={"PATH": "/usr/bin:/bin"}).stdout
    assert json.loads(salida) == []
