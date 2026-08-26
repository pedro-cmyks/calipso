"""Tests del interruptor del plantel (spec seccion 7)."""
import json
import threading

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


def test_techo_tics_cero_persiste_en_roundtrip(tmp_path):
    """Un techo_tics explicito en 0 (parar departamento) no se pisa con el
    default 200. Escribir y releer debe conservar el 0."""
    e = it.Estado(techo_tics=0)
    it.escribir(tmp_path, e)
    e_releido = it.leer(tmp_path)
    assert e_releido.techo_tics == 0
    # y hay_cuerda debe falso desde el primer tic: la cuerda se acaba
    assert it.hay_cuerda(tmp_path, e_releido, "dep:atlas", "2026-W35") is False


def test_tomar_tic_respeta_el_techo(tmp_path):
    """Chequear y anotar en una sola operacion: por debajo del techo pasa,
    en el techo se vuelve sin cuerda. El techo lo saca del archivo, no de un
    Estado que le pase el llamador."""
    it.escribir(tmp_path, it.Estado(techo_tics=2))
    assert it.tomar_tic(tmp_path, "dep:atlas", "2026-W35") is True
    assert it.tomar_tic(tmp_path, "dep:atlas", "2026-W35") is True
    assert it.tomar_tic(tmp_path, "dep:atlas", "2026-W35") is False
    assert it.tics(tmp_path, "dep:atlas", "2026-W35") == 2


def test_tomar_tic_es_atomico_bajo_concurrencia(tmp_path):
    """El ticker de rutinas y el boton de correr a mano pueden solaparse de
    verdad: separado en dos pasos, dos hilos leen el mismo contador y pasan
    los dos. Bajo candado, de N hilos con presion de verdad contra un techo
    de 5 tienen que ganar exactamente 5 -- ni uno mas."""
    it.escribir(tmp_path, it.Estado(techo_tics=5))
    n = 24
    barrera = threading.Barrier(n)
    resultados = []
    candado_resultados = threading.Lock()

    def trabajador():
        barrera.wait()
        gano = it.tomar_tic(tmp_path, "dep:atlas", "2026-W35")
        with candado_resultados:
            resultados.append(gano)

    hilos = [threading.Thread(target=trabajador) for _ in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert resultados.count(True) == 5
    assert it.tics(tmp_path, "dep:atlas", "2026-W35") == 5


def test_boton_de_parar_bajo_escritura_concurrente(tmp_path):
    """Apretar parar mientras la fabrica escribe no puede fallar: write_text
    truncaba el archivo en el lugar, asi que un lector se podia topar con un
    JSON a medias, _crudo devolvia {} y leer() caia al default MAS permisivo
    (encendido=True) -el boton de parar fallaba sin avisar. Con escritura
    atomica (os.replace) el lector ve el contenido viejo o el nuevo, nunca
    uno a medias: de N lecturas concurrentes con un escritor martillando el
    archivo, ninguna puede ver encendido=True."""
    it.escribir(tmp_path, it.Estado(encendido=False, modo="vivo", techo_tics=5))
    seguir = threading.Event()
    seguir.set()

    def escritor():
        while seguir.is_set():
            it.escribir(tmp_path,
                       it.Estado(encendido=False, modo="vivo", techo_tics=5))

    h = threading.Thread(target=escritor)
    h.start()
    try:
        vistos = [it.leer(tmp_path).encendido for _ in range(2000)]
    finally:
        seguir.clear()
        h.join()

    assert not any(vistos), "el boton de parar fallo bajo escritura concurrente"


def test_techo_dict_vacio_da_el_default():
    assert it._techo({}) == it.Estado.techo_tics


def test_techo_valor_raro_cae_en_el_default():
    assert it._techo({"techo_tics": "no-es-numero"}) == it.Estado.techo_tics


def test_techo_cero_se_respeta():
    """El bug real que ya arreglamos: 0 es un valor valido, no "sin dato"."""
    assert it._techo({"techo_tics": 0}) == 0
