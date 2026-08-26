"""Tests del interruptor del plantel (spec seccion 7)."""
import json

from calipso.plantel import interruptor as it


def test_sin_archivo_arranca_encendido_y_en_ensayo(tmp_path):
    """El default tiene que ser el seguro: mira y decide, no gasta."""
    e = it.leer(tmp_path)
    assert e.encendido is True and e.modo == "ensayo"
    assert it.puede_gastar(e) is False


def test_un_archivo_ilegible_no_revienta(tmp_path):
    """Se lee al principio de CADA tic: no puede ser una fuente de fallas."""
    p = it.ruta(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("{esto no es json", encoding="utf-8")
    assert it.leer(tmp_path) == it.Estado()


def test_un_modo_inventado_cae_en_ensayo(tmp_path):
    """El archivo lo puede editar cualquiera a mano; un modo raro no puede
    convertirse en permiso para gastar."""
    p = it.ruta(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"modo": "turbo", "encendido": True}), encoding="utf-8")
    assert it.leer(tmp_path).modo == "ensayo"


def test_parar_y_reanudar_sobreviven_al_archivo(tmp_path):
    it.parar(tmp_path)
    assert it.leer(tmp_path).encendido is False
    it.reanudar(tmp_path)
    assert it.leer(tmp_path).encendido is True


def test_puede_gastar_exige_las_dos_cosas(tmp_path):
    assert it.puede_gastar(it.Estado(encendido=True, modo="vivo")) is True
    assert it.puede_gastar(it.Estado(encendido=False, modo="vivo")) is False
    assert it.puede_gastar(it.Estado(encendido=True, modo="ensayo")) is False


def test_poner_modo_rechaza_lo_que_no_existe(tmp_path):
    it.poner_modo(tmp_path, "vivo")
    assert it.leer(tmp_path).modo == "vivo"
    try:
        it.poner_modo(tmp_path, "turbo")
    except ValueError as e:
        assert "turbo" in str(e)
    else:
        raise AssertionError("acepto un modo que no existe")
    assert it.leer(tmp_path).modo == "vivo"   # no lo piso


def test_los_contadores_no_pisan_el_estado(tmp_path):
    """Viven en el mismo archivo: anotar un tic no puede apagar el modo."""
    it.poner_modo(tmp_path, "vivo")
    assert it.anotar_tic(tmp_path, "dep:atlas", "2026-W35") == 1
    assert it.anotar_tic(tmp_path, "dep:atlas", "2026-W35") == 2
    assert it.tics(tmp_path, "dep:atlas", "2026-W35") == 2
    assert it.leer(tmp_path).modo == "vivo"
    # y escribir el estado no borra los contadores
    it.parar(tmp_path)
    assert it.tics(tmp_path, "dep:atlas", "2026-W35") == 2


def test_los_contadores_son_por_departamento_y_por_semana(tmp_path):
    it.anotar_tic(tmp_path, "dep:atlas", "2026-W35")
    assert it.tics(tmp_path, "dep:mercado", "2026-W35") == 0
    assert it.tics(tmp_path, "dep:atlas", "2026-W36") == 0


def test_la_cuerda_se_acaba_en_el_techo(tmp_path):
    """Un bug que gire no puede vaciar la billetera."""
    e = it.Estado(techo_tics=2)
    assert it.hay_cuerda(tmp_path, e, "dep:atlas", "2026-W35") is True
    it.anotar_tic(tmp_path, "dep:atlas", "2026-W35")
    it.anotar_tic(tmp_path, "dep:atlas", "2026-W35")
    assert it.hay_cuerda(tmp_path, e, "dep:atlas", "2026-W35") is False
