#!/usr/bin/env python3
"""
test_sesiones.py — El almacen de sesiones (spec de la capa de sesion, 3 y 6).

Los tests pisan `sesiones._ruta` en vez de `CALIPSO_HOME`: el modulo resuelve
la ruta en CADA llamada, asi que el temporal queda explicito en cada assert y
ningun test toca el ~/.calipso real. El reloj tambien se pisa, porque los
plazos de esta capa son de dias y no se pueden esperar.

Los dos tests de `escribir_json_atomico` viven aca, y no en un archivo de
economia, porque el parametro `modo` nacio para este almacen: sin el, el
archivo de credenciales pasaria por una ventana en 0644.
"""
import hashlib
import json
import os
import stat

import pytest

from calipso import sesiones
from calipso.economia import candado

T0 = 1_800_000_000.0     # un epoch cualquiera: lo que importa son los deltas
DIA = 86400.0
MIN = 60.0


@pytest.fixture
def ruta(tmp_path, monkeypatch):
    p = tmp_path / "sesiones.json"
    monkeypatch.setattr(sesiones, "_ruta", lambda: p)
    # la cache es un dict de modulo: uno nuevo por test para que ninguno
    # herede el archivo del anterior
    monkeypatch.setattr(sesiones, "_CACHE", sesiones._cache_vacia())
    return p


@pytest.fixture
def reloj(monkeypatch):
    t = [T0]
    monkeypatch.setattr(sesiones, "_reloj", lambda: t[0])
    return t


def vivir(aparato="Ally", tipo="navegador"):
    """El camino feliz completo: golpear, aprobar, canjear."""
    pedido = sesiones.golpear(aparato, tipo)["id_pedido"]
    sesiones.aprobar(pedido, tipo)
    return sesiones.canjear(pedido)


def en_disco(ruta) -> list[dict]:
    return json.loads(ruta.read_text(encoding="utf-8"))["sesiones"]


# --------------------------------------------------------------------------
# el ciclo de vida
# --------------------------------------------------------------------------

def test_el_ciclo_completo_deja_una_sesion_viva_con_el_tipo_de_pedro(ruta,
                                                                    reloj):
    pedido = sesiones.golpear("Musnap Neo C", "lector")["id_pedido"]
    assert sesiones.estado(pedido) == "golpeando"
    # el tipo lo fija Pedro: el que sugiere el aparato es solo una pista
    sesiones.aprobar(pedido, "tablero")
    assert sesiones.estado(pedido) == "viva"
    id_claro = sesiones.canjear(pedido)
    reg = sesiones.resolver(id_claro)
    assert reg["tipo"] == "tablero"
    assert reg["aparato"] == "Musnap Neo C"
    assert reg["estado"] == "viva"


def test_el_canje_es_unico_y_quema_el_id_pedido(ruta, reloj):
    pedido = sesiones.golpear("Ally", "navegador")["id_pedido"]
    sesiones.aprobar(pedido, "navegador")
    id_claro = sesiones.canjear(pedido)
    assert sesiones.canjear(pedido) is None
    assert sesiones.estado(pedido) is None
    # el segundo canje no lastima a la sesion que ya se entrego
    assert sesiones.resolver(id_claro) is not None


def test_canjear_antes_de_aprobar_o_desconocido_devuelve_none(ruta, reloj):
    pedido = sesiones.golpear("Ally", "navegador")["id_pedido"]
    assert sesiones.canjear(pedido) is None
    assert sesiones.canjear("no-existe") is None
    assert sesiones.canjear("") is None
    assert sesiones.estado(pedido) == "golpeando"


def test_entre_aprobar_y_canjear_no_hay_nada_que_resolver(ruta, reloj):
    pedido = sesiones.golpear("Ally", "navegador")["id_pedido"]
    sesiones.aprobar(pedido, "navegador")
    reg = sesiones.listar()[0]
    # el id de sesion nace en el canje: por eso el registro esta viva y sin
    # hash, y por eso ningun id en claro espero nunca en el disco
    assert reg["estado"] == "viva"
    assert reg["hash_id"] is None
    assert sesiones.resolver("") is None
    assert sesiones.resolver(None) is None
    assert sesiones.canjear(pedido)


def test_aprobar_valida_el_tipo(ruta, reloj):
    pedido = sesiones.golpear("Ally", "navegador")["id_pedido"]
    with pytest.raises(ValueError):
        sesiones.aprobar(pedido, "impresora")
    assert sesiones.estado(pedido) == "golpeando"


def test_rechazar_corta_el_golpe_y_no_revive(ruta, reloj):
    pedido = sesiones.golpear("Ally", "navegador")["id_pedido"]
    sesiones.rechazar(pedido)
    assert sesiones.estado(pedido) == "rechazada"
    assert sesiones.canjear(pedido) is None
    with pytest.raises(KeyError):
        sesiones.aprobar(pedido, "navegador")
    with pytest.raises(KeyError):
        sesiones.rechazar("no-existe")


def test_revocar_mata_la_sesion_y_no_revive(ruta, reloj):
    id_claro = vivir()
    hash_id = sesiones.listar()[0]["hash_id"]
    sesiones.revocar(hash_id)
    assert sesiones.resolver(id_claro) is None
    assert sesiones.listar()[0]["efectivo"] == "revocada"
    with pytest.raises(KeyError):
        sesiones.revocar(hash_id)        # ya no esta viva
    with pytest.raises(KeyError):
        sesiones.revocar("no-existe")


# --------------------------------------------------------------------------
# los plazos (reloj inyectado)
# --------------------------------------------------------------------------

def test_el_golpe_caduca_a_los_diez_minutos(ruta, reloj):
    pedido = sesiones.golpear("Ally", "navegador")["id_pedido"]
    reloj[0] += sesiones.GOLPE_TTL_MIN * MIN
    assert sesiones.estado(pedido) is None
    assert [s["efectivo"] for s in sesiones.listar()] == ["caduca"]
    with pytest.raises(KeyError):
        sesiones.aprobar(pedido, "navegador")


def test_cinco_golpes_pendientes_y_el_sexto_rebota(ruta, reloj):
    for i in range(sesiones.GOLPES_PENDIENTES_MAX):
        sesiones.golpear(f"aparato-{i}", "navegador")
    with pytest.raises(sesiones.Lleno):
        sesiones.golpear("el sexto", "navegador")
    # los vencidos por TTL no ocupan lugar: se podan en el golpe siguiente
    reloj[0] += sesiones.GOLPE_TTL_MIN * MIN
    sesiones.golpear("el sexto", "navegador")
    assert [s["aparato"] for s in sesiones.listar()] == ["el sexto"]


def test_dormida_treinta_dias_muere_y_queda_revocada(ruta, reloj):
    id_claro = vivir()
    reloj[0] += sesiones.SESION_SUENO_DIAS * DIA
    assert sesiones.resolver(id_claro) is None
    assert en_disco(ruta)[0]["estado"] == "revocada"
    assert sesiones.resolver(id_claro) is None      # sin marcha atras


def test_la_vida_maxima_de_ciento_ochenta_dias_no_la_estira_el_uso(ruta,
                                                                  reloj):
    id_claro = vivir()
    for _ in range(sesiones.SESION_VIDA_MAX_DIAS - 1):
        reloj[0] += DIA
        assert sesiones.resolver(id_claro) is not None
    reloj[0] += DIA
    assert sesiones.resolver(id_claro) is None
    assert en_disco(ruta)[0]["estado"] == "revocada"


def test_la_renovacion_tiene_histeresis_de_una_hora(ruta, reloj):
    id_claro = vivir()
    antes = en_disco(ruta)[0]["ultima_vez"]
    reloj[0] += sesiones.RENOVACION_HISTERESIS_S - 1
    assert sesiones.resolver(id_claro)["renovada"] is False
    assert en_disco(ruta)[0]["ultima_vez"] == antes
    reloj[0] += 2
    assert sesiones.resolver(id_claro)["renovada"] is True
    assert en_disco(ruta)[0]["ultima_vez"] != antes


def test_listar_reporta_el_estado_efectivo_sin_escribir(ruta, reloj):
    vivir()
    pendiente = sesiones.golpear("otro", "lector")["id_pedido"]
    # la UI de /fabrica aprueba por body: necesita ver el id_pedido
    assert pendiente in [s["id_pedido"] for s in sesiones.listar()]
    st = os.stat(ruta)
    reloj[0] += sesiones.SESION_SUENO_DIAS * DIA
    assert sorted(s["efectivo"] for s in sesiones.listar()) == ["caduca",
                                                                "caduca"]
    # el archivo no miente y tampoco lo toco: la muerte la escribe resolver
    assert en_disco(ruta)[0]["estado"] == "viva"
    assert os.stat(ruta).st_mtime_ns == st.st_mtime_ns


# --------------------------------------------------------------------------
# validacion del golpe
# --------------------------------------------------------------------------

@pytest.mark.parametrize("aparato,tipo", [
    ("Ally", "impresora"),            # tipo fuera de ALCANCES
    ("Ally", ""),
    ("", "navegador"),                # aparato vacio
    ("   ", "navegador"),
    ("x" * (sesiones.APARATO_MAX + 1), "navegador"),
    ("Ally\nfalsa", "navegador"),     # es input NO autenticado que va a la UI
])
def test_golpear_valida_y_no_estaciona(ruta, reloj, aparato, tipo):
    with pytest.raises(ValueError):
        sesiones.golpear(aparato, tipo)
    assert not ruta.exists()


def test_crear_viva_valida_igual_que_golpear(ruta, reloj):
    with pytest.raises(ValueError):
        sesiones.crear_viva("Ally", "impresora")
    with pytest.raises(ValueError):
        sesiones.crear_viva("x" * (sesiones.APARATO_MAX + 1), "navegador")
    assert not ruta.exists()


def test_crear_viva_no_pasa_por_el_tope_de_pendientes(ruta, reloj):
    for i in range(sesiones.GOLPES_PENDIENTES_MAX):
        sesiones.golpear(f"martillo-{i}", "navegador")
    # cinco golpes de un desconocido no pueden dejar a Pedro sin /login
    id_claro = sesiones.crear_viva("PWA de Pedro", "navegador")
    reg = sesiones.resolver(id_claro)
    assert reg["tipo"] == "navegador"
    assert reg["aparato"] == "PWA de Pedro"
    assert reg["id_pedido"] is None


# --------------------------------------------------------------------------
# el archivo
# --------------------------------------------------------------------------

def test_el_archivo_jamas_contiene_el_id_en_claro(ruta, reloj):
    id_canje = vivir("Ally")
    id_directo = sesiones.crear_viva("PWA de Pedro", "navegador")
    crudo = ruta.read_text(encoding="utf-8")
    assert id_canje not in crudo
    assert id_directo not in crudo
    assert hashlib.sha256(id_canje.encode()).hexdigest() in crudo
    assert hashlib.sha256(id_directo.encode()).hexdigest() in crudo


def test_el_archivo_nace_en_0600(ruta, reloj):
    sesiones.golpear("Ally", "navegador")
    assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600


def test_el_archivo_ilegible_se_preserva_antes_de_escribir(ruta, reloj,
                                                           capsys):
    ruta.write_text("{ esto no es json", encoding="utf-8")
    sesiones.golpear("Ally", "navegador")
    copias = list(ruta.parent.glob("sesiones.json.corrupto-*"))
    assert len(copias) == 1
    assert copias[0].read_text(encoding="utf-8") == "{ esto no es json"
    assert [s["aparato"] for s in sesiones.listar()] == ["Ally"]
    assert "corrupto" in capsys.readouterr().err


def test_leer_un_archivo_ilegible_no_resuelve_nada_ni_lo_pisa(ruta, reloj,
                                                              capsys):
    id_claro = vivir()
    ruta.write_text('{"version": 1, "sesiones": "no es una lista"}',
                    encoding="utf-8")
    st = os.stat(ruta)
    assert sesiones.resolver(id_claro) is None
    assert sesiones.listar() == []
    assert sesiones.estado("lo que sea") is None
    assert os.stat(ruta).st_mtime_ns == st.st_mtime_ns
    assert "ilegible" in capsys.readouterr().err


def test_la_cache_se_recarga_cuando_el_archivo_cambia(ruta, reloj):
    id_claro = vivir()
    assert sesiones.resolver(id_claro) is not None
    # otro proceso (dispatch, otra instancia del server) revoca: la cache se
    # apoya en el stat del archivo, no en la memoria de este proceso
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["sesiones"][0]["estado"] = "revocada"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    assert sesiones.resolver(id_claro) is None


# --------------------------------------------------------------------------
# la tabla de alcances (la Task 2 la consume)
# --------------------------------------------------------------------------

def test_los_alcances_son_la_tabla_del_spec():
    assert set(sesiones.ALCANCES) == {"navegador", "lector", "tablero"}
    assert sesiones.ALCANCES["navegador"] == (("*", "*"),)
    assert sesiones.ALCANCES["lector"] == (("/api/lectura/", "*"),)
    prefijos = [p for p, _ in sesiones.ALCANCES["tablero"]]
    assert "/fabrica" in prefijos
    assert "/api/economia/bus/" in prefijos
    assert "/api/permisos/responder" in prefijos
    # el criterio fijo del spec: ver todo, firmar mesa y permisos, jamas
    # tocar la maquina
    for vedada in ("/api/file", "/api/commands", "/api/config", "/api/project"):
        assert not any(p.startswith(vedada) for p in prefijos)


# --------------------------------------------------------------------------
# el escritor atomico con modo (lo que hace que el archivo nazca 0600)
# --------------------------------------------------------------------------

def test_escribir_json_atomico_con_modo_crea_el_archivo_ya_con_ese_modo(
        tmp_path):
    p = tmp_path / "secreto.json"
    candado.escribir_json_atomico(p, {"a": 1}, modo=0o600)
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1}
    # reescribir sobre uno que ya existe mantiene el modo
    candado.escribir_json_atomico(p, {"a": 2}, modo=0o600)
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_escribir_json_atomico_sin_modo_escribe_los_mismos_bytes(tmp_path):
    datos = {"a": [1, 2], "enie": "ñ"}
    viejo = tmp_path / "viejo.json"
    nuevo = tmp_path / "nuevo.json"
    candado.escribir_json_atomico(viejo, datos)
    candado.escribir_json_atomico(nuevo, datos, modo=0o600)
    # los llamadores de siempre no cambian de formato por el parametro nuevo
    assert viejo.read_text(encoding="utf-8") == json.dumps(
        datos, ensure_ascii=False, indent=1)
    assert nuevo.read_bytes() == viejo.read_bytes()
