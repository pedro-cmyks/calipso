"""Tests del urbanismo: fisica de afinidad determinista y estable."""
import math

from calipso.mapa import urbanismo as urb


def _edi(id, orden, tamano=3, zona="fabrica"):
    return {"id": id, "orden": orden, "tamano": tamano, "zona": zona}


def _dist(pos, a, b):
    return math.dist(pos[a], pos[b])


def test_el_mas_viejo_queda_clavado_en_el_origen():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1), _edi("dep:c", 2)]
    pos = urb.urbanizar(edis, [])
    assert pos["dep:a"] == (0, 0)
    assert pos["dep:b"] != (0, 0)


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
    ids = sorted(pos)
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            assert _dist(pos, x, y) > 20


def test_la_zona_personal_queda_agrupada_y_aparte():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1),
            _edi("personal:x", 2, zona="personal"),
            _edi("personal:y", 3, zona="personal")]
    pos = urb.urbanizar(edis, [])
    entre_personales = _dist(pos, "personal:x", "personal:y")
    cruzada = min(_dist(pos, p, f) for p in ("personal:x", "personal:y")
                  for f in ("dep:a", "dep:b"))
    assert entre_personales < cruzada


def test_zona_personal_se_agrupa_a_escala_realista():
    """multizona es el camino de produccion (fabrica + personal), no un
    caso de borde: doce departamentos de fabrica y tres personales."""
    edis = [_edi(f"dep:{n}", n) for n in range(12)]
    edis += [_edi(f"personal:{n}", 12 + n, zona="personal") for n in range(3)]
    pos = urb.urbanizar(edis, [])
    ids = sorted(pos)
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            assert _dist(pos, x, y) > 20
    personales = [e["id"] for e in edis if e["zona"] == "personal"]
    fabrica = [e["id"] for e in edis if e["zona"] != "personal"]
    pares_personales = [(a, b) for i, a in enumerate(personales)
                         for b in personales[i + 1:]]
    pares_cruzados = [(a, b) for a in personales for b in fabrica]
    media_personal = sum(_dist(pos, a, b) for a, b in pares_personales) \
        / len(pares_personales)
    media_cruzada = sum(_dist(pos, a, b) for a, b in pares_cruzados) \
        / len(pares_cruzados)
    assert media_personal < media_cruzada


def test_zona_personal_se_agrupa_con_reparto_desparejo():
    """caso senalado por la revision como no confirmado: un solo edificio
    de fabrica contra seis personales."""
    edis = [_edi("dep:0", 0)]
    edis += [_edi(f"personal:{n}", 1 + n, zona="personal") for n in range(6)]
    pos = urb.urbanizar(edis, [])
    ids = sorted(pos)
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            assert _dist(pos, x, y) > 20
    personales = [e["id"] for e in edis if e["zona"] == "personal"]
    fabrica = [e["id"] for e in edis if e["zona"] != "personal"]
    pares_personales = [(a, b) for i, a in enumerate(personales)
                         for b in personales[i + 1:]]
    pares_cruzados = [(a, b) for a in personales for b in fabrica]
    media_personal = sum(_dist(pos, a, b) for a, b in pares_personales) \
        / len(pares_personales)
    media_cruzada = sum(_dist(pos, a, b) for a, b in pares_cruzados) \
        / len(pares_cruzados)
    assert media_personal < media_cruzada


def test_un_departamento_nuevo_no_reacomoda_la_ciudad():
    """Anclaje por antiguedad: la ciudad crece hacia afuera."""
    viejos = [_edi("dep:a", 0), _edi("dep:b", 1), _edi("dep:c", 2)]
    antes = urb.urbanizar(viejos, [])
    despues = urb.urbanizar(viejos + [_edi("dep:nuevo", 3)], [])
    assert despues["dep:a"] == antes["dep:a"] == (0, 0)
    corrimiento = max(math.dist(antes[i], despues[i]) for i in antes)
    assert corrimiento < 60


def test_ciudad_vacia_y_de_uno_no_rompen():
    assert urb.urbanizar([], []) == {}
    assert urb.urbanizar([_edi("dep:solo", 0)], []) == {"dep:solo": (0, 0)}
