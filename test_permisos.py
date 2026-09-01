#!/usr/bin/env python3
"""
test_permisos.py — El motor de permisos (spec de ojos y manos, seccion 5).

Todo corre con CALIPSO_HOME en un temporal. El fixture lo fija con
`monkeypatch.setenv` y el modulo resuelve el home en CADA llamada, asi que
no importa quien importo que primero: ningun test toca el ~/.calipso real
de Pedro. Eso ya paso una vez con catastro.json y se verifica con md5
antes y despues de correr la suite.
"""
import json
import pathlib

import pytest

from calipso.permisos import acciones, almacen, motor
from calipso.permisos.acciones import (Accion, Contexto, ErrorPermisos,
                                       NIVEL_DIRECTO, NIVEL_NUNCA,
                                       NIVEL_PREGUNTA)


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / ".calipso"
    h.mkdir()
    monkeypatch.setenv("CALIPSO_HOME", str(h))
    # el motor guarda ejecutores en un dict de modulo: se limpia entre
    # tests para que uno no herede el ejecutor de otro
    monkeypatch.setattr(motor, "_EJECUTORES", {})
    return h


def acunar(monto_mm, destino="tesoro"):
    return Accion("plata", "acunar",
                  {"subtipo": "capital", "destino": destino,
                   "monto_mm": monto_mm},
                  {"evidencia": {"tipo": "firma_pedro"}},
                  f"acunar {monto_mm} mm a {destino}")


# --------------------------------------------------------------------------
# 5.3 -- los tres niveles
# --------------------------------------------------------------------------

def test_plata_bajo_el_techo_es_directa(home):
    v = acciones.clasificar(acunar(99_999), almacen.techos())
    assert v.nivel == NIVEL_DIRECTO
    assert motor.evaluar(acunar(99_999), Contexto("pedro")).permitido


def test_plata_sobre_el_techo_pregunta_y_pregunta_siempre(home):
    v = acciones.clasificar(acunar(100_001), almacen.techos())
    assert v.nivel == NIVEL_PREGUNTA
    # el libro es append-only: un si guardado para siempre sobre acunar es
    # un si que cuesta plata de verdad
    assert v.siempre_pregunta is True


def test_el_techo_es_configurable_y_arranca_en_100_monedas(home):
    assert almacen.techos()["plata_mm"] == 100_000  # 100 monedas
    almacen.poner_techo("plata_mm", 500_000)
    assert almacen.techos()["plata_mm"] == 500_000
    assert motor.evaluar(acunar(400_000), Contexto("pedro")).permitido


def test_el_techo_sobrevive_al_reinicio(home):
    almacen.poner_techo("plata_mm", 7_000)
    # "reiniciar" = volver a leer del disco, que es lo unico que hay
    assert json.loads((home / "permisos.json").read_text())["techos"][
        "plata_mm"] == 7_000
    assert almacen.techos()["plata_mm"] == 7_000


def test_la_credencial_del_servidor_es_nunca(home):
    for nombre in ("token", "totp_secret"):
        a = Accion("archivo", "leer", {"ruta": str(home / nombre)})
        assert acciones.clasificar(a).nivel == NIVEL_NUNCA
        r = motor.evaluar(a, Contexto("pedro"))
        assert r.estado == motor.ESTADO_NEGADO
        # negativa, no prompt: no queda nada esperando que alguien conteste
        assert almacen.abiertas() == []


def test_escribir_la_credencial_del_servidor_tampoco(home):
    a = Accion("archivo", "escribir", {"ruta": str(home / "token")})
    assert acciones.clasificar(a).nivel == NIVEL_NUNCA


def test_las_credenciales_de_pedro_preguntan_y_no_admiten_permanente(home):
    for ruta in ("~/.ssh/id_rsa", "~/.aws/credentials", "~/proyecto/.env",
                 "~/x/servidor.pem", "~/.claude/.credentials.json"):
        v = acciones.clasificar(Accion("archivo", "leer", {"ruta": ruta}))
        assert v.nivel == NIVEL_PREGUNTA, ruta
        assert v.siempre_pregunta is True, ruta


def test_leer_cualquier_otro_archivo_es_directo(home):
    a = Accion("archivo", "leer", {"ruta": "/etc/hosts"})
    assert acciones.clasificar(a).nivel == NIVEL_DIRECTO


def test_escribir_dentro_de_calipso_home_es_directo(home):
    a = Accion("archivo", "escribir", {"ruta": str(home / "notas.txt")})
    assert acciones.clasificar(a).nivel == NIVEL_DIRECTO


def test_escribir_afuera_pregunta(home):
    a = Accion("archivo", "escribir", {"ruta": "/tmp/afuera-de-todo/x.txt"})
    assert acciones.clasificar(a).nivel == NIVEL_PREGUNTA


def test_el_allowlist_que_ya_existe_es_directo(home):
    from calipso.tools.commands import ALLOWLIST
    # verificado contra el allowlist real, no contra una copia del spec
    for cid in ("git_status", "git_diff", "git_diff_staged", "git_log",
                "py_compile_core", "ui_syntax", "docs_check", "test_all"):
        assert cid in ALLOWLIST, cid
        a = Accion("comando", "allowlist", {"id": cid})
        assert acciones.clasificar(a).nivel == NIVEL_DIRECTO, cid


def test_un_comando_fuera_del_allowlist_pregunta(home):
    a = Accion("comando", "correr", {"argv": ["npm", "test"], "cwd": "/x"})
    v = acciones.clasificar(a)
    assert v.nivel == NIVEL_PREGUNTA
    assert v.siempre_pregunta is False  # este si admite permiso permanente


def test_las_irreversibles_preguntan_siempre(home):
    for argv in (["git", "push"], ["git", "commit", "--amend"],
                 ["git", "reset", "--hard", "HEAD~1"],
                 ["git", "clean", "-fdx"], ["rm", "-rf", "/x"]):
        v = acciones.clasificar(Accion("comando", "correr", {"argv": argv}))
        assert v.siempre_pregunta is True, argv


def test_irreversible_se_mira_elemento_por_elemento(home):
    # no por la primera palabra: aprobar una cadena por su primera palabra
    # es una aprobacion que no significa nada
    assert acciones.es_irreversible(["git", "-C", "/otro", "push"]) is True
    assert acciones.es_irreversible(["rm", "-r", "-f", "/x"]) is True
    assert acciones.es_irreversible(["/usr/bin/rm", "-rf", "/x"]) is True
    assert acciones.es_irreversible(["git", "status"]) is False
    assert acciones.es_irreversible(["npm", "run", "push"]) is False
    assert acciones.es_irreversible(["echo", "rm -rf /"]) is False
    assert acciones.es_irreversible(["sudo", "rm", "-rf", "/x"]) is True


def test_una_familia_desconocida_pregunta_no_pasa(home):
    v = acciones.clasificar(Accion("teletransporte", "hacerlo", {}))
    assert v.nivel == NIVEL_PREGUNTA


def test_apps_abrir_directo_matar_ajena_pregunta(home):
    assert acciones.clasificar(
        Accion("app", "abrir", {"desktop": "firefox.desktop"})).nivel \
        == NIVEL_DIRECTO
    assert acciones.clasificar(
        Accion("app", "cerrar_propia", {"scope": "calipso-app-1"})).nivel \
        == NIVEL_DIRECTO
    assert acciones.clasificar(
        Accion("app", "matar_pid", {"pid": 4321})).nivel == NIVEL_PREGUNTA


# --------------------------------------------------------------------------
# 5.4 -- el prompt, y "no me preguntes mas para esto"
# --------------------------------------------------------------------------

def npm_test(cwd="/var/home/pedro/Observatory-Global"):
    return Accion("comando", "correr", {"argv": ["npm", "test"], "cwd": cwd},
                  titulo=f"npm test en {cwd}")


def test_permiso_permanente_se_concede_y_tapa_la_segunda_vez(home):
    r1 = motor.evaluar(npm_test(), Contexto("chat", chat="c1"))
    assert r1.estado == motor.ESTADO_PENDIENTE

    salida = motor.responder(r1.solicitud["id"], "si_siempre")
    assert salida["permiso"]["forma"] == {
        "argv": ["npm", "test"], "cwd": "/var/home/pedro/Observatory-Global"}

    r2 = motor.evaluar(npm_test(), Contexto("chat", chat="c1"))
    assert r2.permitido
    assert r2.permiso["id"] == salida["permiso"]["id"]


def test_el_permiso_se_concede_por_forma_no_por_categoria(home):
    r1 = motor.evaluar(npm_test(), Contexto("chat"))
    motor.responder(r1.solicitud["id"], "si_siempre")
    # otro argv: "npm" no quedo concedido, ["npm","test"] si
    otro = Accion("comando", "correr",
                  {"argv": ["npm", "install"],
                   "cwd": "/var/home/pedro/Observatory-Global"})
    assert motor.evaluar(otro, Contexto("chat")).estado \
        == motor.ESTADO_PENDIENTE
    # y el mismo argv en OTRO cwd tampoco
    assert motor.evaluar(npm_test("/otro/repo"), Contexto("chat")).estado \
        == motor.ESTADO_PENDIENTE


def test_el_permiso_permanente_sobrevive_al_reinicio(home):
    r1 = motor.evaluar(npm_test(), Contexto("chat"))
    motor.responder(r1.solicitud["id"], "si_siempre")
    guardado = json.loads((home / "permisos.json").read_text())
    assert guardado["concedidos"][0]["forma"]["argv"] == ["npm", "test"]
    assert guardado["concedidos"][0]["texto"]
    assert guardado["concedidos"][0]["ts"]


def test_las_que_preguntan_siempre_no_admiten_permanente(home):
    r = motor.evaluar(acunar(500_000), Contexto("pedro"))
    assert r.estado == motor.ESTADO_PENDIENTE
    with pytest.raises(ErrorPermisos):
        motor.responder(r.solicitud["id"], "si_siempre")
    # y la solicitud sigue abierta: la negativa no la resolvio de costado
    assert almacen.obtener(r.solicitud["id"])["estado"] == "pendiente"


def test_conceder_se_niega_aunque_lo_llamen_directo(home):
    # el corte vive en el almacen, no solo en el endpoint: ningun llamador
    # futuro puede escribir un si permanente sobre lo irreversible
    with pytest.raises(ErrorPermisos):
        almacen.conceder(acunar(500_000), Contexto("pedro"), "x",
                         siempre_pregunta=True)


def test_un_permiso_permanente_no_cubre_una_operacion_de_siempre(home):
    # se concede el permiso mas ancho que el motor acepta para git...
    libre = Accion("comando", "correr",
                   {"argv": ["git", "fetch"], "cwd": "/x"})
    r = motor.evaluar(libre, Contexto("chat"))
    motor.responder(r.solicitud["id"], "si_siempre")
    assert motor.evaluar(libre, Contexto("chat")).permitido
    # ...y git push sigue preguntando
    push = Accion("comando", "correr",
                  {"argv": ["git", "push"], "cwd": "/x"})
    assert motor.evaluar(push, Contexto("chat")).estado \
        == motor.ESTADO_PENDIENTE


def test_permiso_de_archivo_por_raiz_cubre_lo_de_abajo(home):
    a = Accion("archivo", "escribir", {"ruta": "/tmp/bandeja/uno.txt"})
    r = motor.evaluar(a, Contexto("chat"))
    motor.responder(r.solicitud["id"], "si_siempre",
                    forma_permanente={"raiz": "/tmp/bandeja"})
    otro = Accion("archivo", "escribir", {"ruta": "/tmp/bandeja/sub/dos.txt"})
    assert motor.evaluar(otro, Contexto("chat")).permitido
    afuera = Accion("archivo", "escribir", {"ruta": "/tmp/otra/tres.txt"})
    assert motor.evaluar(afuera, Contexto("chat")).estado \
        == motor.ESTADO_PENDIENTE


def test_no_se_concede_una_forma_que_no_cubre_la_accion(home):
    a = Accion("archivo", "escribir", {"ruta": "/tmp/bandeja/uno.txt"})
    r = motor.evaluar(a, Contexto("chat"))
    with pytest.raises(ErrorPermisos):
        motor.responder(r.solicitud["id"], "si_siempre",
                        forma_permanente={"raiz": "/otra/cosa"})


def test_revocar(home):
    r = motor.evaluar(npm_test(), Contexto("chat"))
    permiso = motor.responder(r.solicitud["id"], "si_siempre")["permiso"]
    assert almacen.revocar(permiso["id"]) is True
    assert almacen.revocar(permiso["id"]) is False
    assert motor.evaluar(npm_test(), Contexto("chat")).estado \
        == motor.ESTADO_PENDIENTE


def test_las_tres_salidas(home):
    r = motor.evaluar(npm_test(), Contexto("chat"))
    assert motor.responder(r.solicitud["id"], "no")["solicitud"]["estado"] \
        == "negada"
    r2 = motor.evaluar(npm_test("/b"), Contexto("chat"))
    salida = motor.responder(r2.solicitud["id"], "si")
    assert salida["solicitud"]["estado"] in ("aprobada", "fallida")
    assert salida["permiso"] is None  # "si una vez" no concede nada
    assert almacen.concedidos() == []


def test_respuesta_invalida(home):
    r = motor.evaluar(npm_test(), Contexto("chat"))
    with pytest.raises(ErrorPermisos):
        motor.responder(r.solicitud["id"], "quiza")


def test_no_se_contesta_dos_veces(home):
    r = motor.evaluar(npm_test(), Contexto("chat"))
    motor.responder(r.solicitud["id"], "no")
    with pytest.raises(ErrorPermisos):
        motor.responder(r.solicitud["id"], "si")


def test_una_regla_de_negar_se_guarda_con_su_efecto(home):
    almacen.anotar_regla(acunar(150_000), Contexto("pedro"),
                         "acunar 150 monedas", siempre_pregunta=True,
                         efecto="denegar")
    reglas = almacen.concedidos()
    assert len(reglas) == 1
    assert reglas[0]["efecto"] == "denegar"
    # la regla de negar vive en la MISMA lista que las de permitir: por eso
    # nace revocable, visible y barrible sin codigo nuevo (D1)
    assert reglas[0]["familia"] == "plata"


def test_negar_para_siempre_si_admite_lo_que_pregunta_siempre(home):
    # el corte de 5.4 es contra el SI en blanco sobre lo irreversible. Un NO
    # permanente sobre acunar falla hacia el lado conservador (D2).
    with pytest.raises(ErrorPermisos):
        almacen.anotar_regla(acunar(500_000), Contexto("pedro"), "x",
                             siempre_pregunta=True, efecto="permitir")
    r = almacen.anotar_regla(acunar(500_000), Contexto("pedro"), "x",
                             siempre_pregunta=True, efecto="denegar")
    assert r["efecto"] == "denegar"


def test_conceder_sigue_siendo_lo_que_era(home):
    # `conceder` es ahora un envoltorio, y no puede cambiar de significado:
    # sigue escribiendo permitir y sigue negandose sobre lo irreversible
    r = almacen.conceder(acunar(99_999), Contexto("pedro"), "x")
    assert r["efecto"] == "permitir"
    assert almacen.regla_que_cubre(acunar(99_999), "permitir") is not None
    assert almacen.regla_que_cubre(acunar(99_999), "denegar") is None


def test_una_regla_sin_efecto_se_lee_como_permitir(home):
    # `config()` no normaliza: un permisos.json escrito por la version
    # anterior tiene reglas sin la clave. El default se aplica al comparar,
    # nunca confiando en que la escritura lo puso.
    almacen.conceder(acunar(99_999), Contexto("pedro"), "x")
    p = almacen.ruta_permisos()
    d = json.loads(p.read_text(encoding="utf-8"))
    del d["concedidos"][0]["efecto"]
    p.write_text(json.dumps(d), encoding="utf-8")
    assert almacen.regla_que_cubre(acunar(99_999), "permitir") is not None


def test_una_regla_nueva_barre_a_la_contraria_sobre_la_misma_forma(home):
    # sin esto la pantalla seria una trampa: Pedro revocaria el "no"
    # esperando volver a que le pregunten, y en silencio quedaria vivo el
    # "si" viejo (D3)
    almacen.conceder(acunar(99_999), Contexto("pedro"), "x")
    almacen.anotar_regla(acunar(99_999), Contexto("pedro"), "x",
                         efecto="denegar")
    reglas = almacen.concedidos()
    assert len(reglas) == 1
    assert reglas[0]["efecto"] == "denegar"


def test_revocar_una_regla_deja_linea_en_el_registro(home):
    # revocar un "no" devuelve el futuro. Sin esta linea no queda en ningun
    # lado cuando dejo de valer.
    r = almacen.anotar_regla(acunar(150_000), Contexto("pedro"), "x",
                             siempre_pregunta=True, efecto="denegar")
    assert almacen.revocar(r["id"]) is True
    lineas = [l for l in almacen.registro(50)
              if l.get("evento") == "revocacion"]
    assert len(lineas) == 1
    assert lineas[0]["permiso"] == r["id"]
    assert lineas[0]["efecto"] == "denegar"


def test_el_barrido_de_la_contraria_deja_linea_en_el_registro(home):
    # el barrido borra una regla del disco sin que Pedro la revoque. Es el
    # mismo agujero que la revocacion: sin la linea no queda en ningun lado
    # cuando esa regla dejo de valer, y el rastro de 5.4 se corta justo en
    # el evento que cambia lo que pasa la proxima vez.
    si_viejo = almacen.conceder(acunar(99_999), Contexto("pedro"), "x")
    no = almacen.anotar_regla(acunar(99_999), Contexto("pedro"), "y",
                              efecto="denegar")
    lineas = [l for l in almacen.registro(50) if l.get("evento") == "barrida"]
    assert len(lineas) == 1
    assert lineas[0]["permiso"] == si_viejo["id"]
    assert lineas[0]["efecto"] == "permitir"
    assert lineas[0]["por"] == no["id"]
    assert lineas[0]["familia"] == "plata"
    assert lineas[0]["forma"] == si_viejo["forma"]


def test_conceder_directo_no_puede_pisar_una_regla_de_no(home):
    # la guarda del si sobre lo tapado por un no vivia solo en
    # `almacen.responder`: llamar a `conceder` directo borraba el no en
    # silencio y `evaluar` volvia a permitir.
    no = almacen.anotar_regla(acunar(150_000), Contexto("pedro"), "x",
                              siempre_pregunta=True, efecto="denegar")
    with pytest.raises(ErrorPermisos) as exc:
        almacen.conceder(acunar(150_000), Contexto("pedro"), "y")
    assert no["id"] in str(exc.value)
    # y el no sigue en pie: la comprobacion corre ANTES del barrido, asi
    # que no se borra a si misma la regla que tenia que encontrar
    assert almacen.regla_que_cubre(acunar(150_000), "denegar") is not None
    assert almacen.regla_que_cubre(acunar(150_000), "permitir") is None
    assert motor.evaluar(acunar(150_000), Contexto("pedro")).estado \
        == motor.ESTADO_NEGADO


def test_una_regla_de_negar_no_acepta_una_forma_a_mano(home):
    # ensanchar un si es su funcion; ensanchar un no es el radio de
    # explosion, y no deja item en ninguna bandeja donde verlo
    a = Accion("archivo", "escribir", {"ruta": "/tmp/bandeja/uno.txt"})
    with pytest.raises(ErrorPermisos):
        almacen.anotar_regla(a, Contexto("pedro"), "x", forma={"raiz": "/"},
                             efecto="denegar")
    assert almacen.concedidos() == []
    # el mismo ensanchamiento del lado del si se sigue aceptando
    ancho = almacen.anotar_regla(a, Contexto("pedro"), "x",
                                 forma={"raiz": "/tmp/bandeja"},
                                 efecto="permitir")
    assert ancho["forma"] == {"raiz": "/tmp/bandeja"}


def test_dos_reglas_iguales_no_se_acumulan(home):
    # dos solicitudes distintas pueden caer bajo la misma regla, y
    # contestar las dos no esta mal: la segunda escritura es un no-op, no
    # un error. Dos tarjetas identicas en la pantalla, con una sola que
    # cambia algo al revocarla, es la misma trampa de la regla 3 del spec.
    uno = almacen.anotar_regla(acunar(150_000), Contexto("pedro"), "x",
                               siempre_pregunta=True, efecto="denegar")
    dos = almacen.anotar_regla(acunar(150_000), Contexto("otro"), "y",
                               siempre_pregunta=True, efecto="denegar")
    assert dos["id"] == uno["id"]
    assert len(almacen.concedidos()) == 1
    # y del lado del si, igual
    tres = almacen.conceder(acunar(99_999), Contexto("pedro"), "x")
    cuatro = almacen.conceder(acunar(99_999), Contexto("pedro"), "y")
    assert cuatro["id"] == tres["id"]
    assert len(almacen.concedidos()) == 2


def test_un_no_permanente_tapa_lo_que_despues_pasa_a_ser_directo(home):
    """El caso que fija DONDE va el corte.

    Acunar 150 monedas esta sobre el techo: pregunta. Pedro contesta que
    nunca mas. Despues sube el techo a 200 monedas, y eso convierte la misma
    accion en NIVEL_DIRECTO.

    Si el corte del no viviera donde vive el del si -- despues de
    `clasificar` y bajo `if not v.siempre_pregunta` -- subir el techo
    anularia en silencio el no permanente de Pedro. Va antes de clasificar
    justamente para que no pueda pasar.
    """
    r = motor.evaluar(acunar(150_000), Contexto("pedro"))
    assert r.estado == motor.ESTADO_PENDIENTE
    motor.responder(r.solicitud["id"], "no_siempre")

    almacen.poner_techo("plata_mm", 200_000)
    assert acciones.clasificar(acunar(150_000),
                               almacen.techos()).nivel == NIVEL_DIRECTO

    r2 = motor.evaluar(acunar(150_000), Contexto("pedro"))
    assert r2.estado == motor.ESTADO_NEGADO
    assert "regla permanente" in r2.motivo


def test_un_no_permanente_no_crea_solicitud(home):
    """La regla filtra en el productor: el item no llega a existir.

    Es tambien la razon por la que la pantalla de reglas deja de ser un lujo
    y pasa a ser requisito: una regla de negar demasiado ancha no deja
    rastro en ninguna bandeja, y el unico lugar donde Pedro puede enterarse
    es la lista de reglas y el registro.
    """
    r = motor.evaluar(acunar(150_000), Contexto("pedro"))
    motor.responder(r.solicitud["id"], "no_siempre")
    antes = len(almacen.solicitudes())

    r2 = motor.evaluar(acunar(150_000), Contexto("otro_chat"))
    assert r2.estado == motor.ESTADO_NEGADO
    assert len(almacen.solicitudes()) == antes


def test_revocar_el_no_devuelve_la_pregunta_y_no_el_si_viejo(home):
    """La otra mitad de D3, del lado del motor.

    El "si viejo" tiene que existir de verdad para que el test pueda
    atrapar una regresion del barrido de la regla contraria: si
    `anotar_regla` dejara de barrer el "si" al escribir el "no", revocar
    el "no" dejaria ese "si" vivo y la reevaluacion volveria PERMITIDO en
    vez de PENDIENTE.
    """
    r0 = motor.evaluar(npm_test(), Contexto("chat", chat="c1"))
    si_viejo = almacen.conceder(npm_test(), Contexto("pedro"), "y")

    salida = motor.responder(r0.solicitud["id"], "no_siempre")
    assert almacen.regla_que_cubre(npm_test(), "permitir") is None

    almacen.revocar(salida["permiso"]["id"])

    r2 = motor.evaluar(npm_test(), Contexto("chat", chat="c1"))
    assert r2.estado == motor.ESTADO_PENDIENTE


def test_no_siempre_deja_la_solicitud_negada(home):
    r = motor.evaluar(acunar(150_000), Contexto("pedro"))
    salida = motor.responder(r.solicitud["id"], "no_siempre")
    assert salida["solicitud"]["estado"] == almacen.ESTADO_NEGADA
    assert salida["ejecucion"] is None
    assert salida["permiso"]["efecto"] == "denegar"


def test_la_regla_de_no_escrita_mientras_la_solicitud_esperaba_bloquea_el_si(home):
    """El agujero de la ventana: la solicitud nacio antes que la regla.

    Si la solicitud ya estaba abierta cuando Pedro escribio el "nunca mas"
    para esa misma forma, la pared de forma (corte 2 de `evaluar`) sigue
    mostrando esa solicitud vieja -- `evaluar` no se vuelve a llamar para
    algo que ya existe, asi que el corte 4 (la regla permanente de no)
    nunca se corre para ella. Sin este chequeo en `responder`, un "si"
    sobre ese item viejo ejecutaria la accion a pesar del no permanente.
    """
    hechos = []
    motor.registrar_ejecutor(
        "plata", "acunar", lambda a: hechos.append(a) or {"ok": True})

    r = motor.evaluar(acunar(150_000), Contexto("pedro"))
    assert r.estado == motor.ESTADO_PENDIENTE

    almacen.anotar_regla(acunar(150_000), Contexto("pedro"), "x",
                         siempre_pregunta=True, efecto="denegar")

    with pytest.raises(ErrorPermisos):
        motor.responder(r.solicitud["id"], "si")
    assert hechos == []
    assert almacen.obtener(r.solicitud["id"])["estado"] == \
        almacen.ESTADO_PENDIENTE


def test_sin_regla_de_no_el_si_sigue_funcionando(home):
    """El caso feliz: sin regla de por medio, un "si" sobre una solicitud
    abierta sigue haciendo lo que siempre hizo."""
    hechos = []
    motor.registrar_ejecutor(
        "plata", "acunar", lambda a: hechos.append(a) or {"ok": True})

    r = motor.evaluar(acunar(150_000), Contexto("pedro"))
    salida = motor.responder(r.solicitud["id"], "si")
    assert hechos
    assert salida["ejecucion"]["ejecutada"] is True


# --------------------------------------------------------------------------
# 5.6 -- cuando no hay nadie a quien preguntar
# --------------------------------------------------------------------------

def test_el_desatendido_no_cae_al_prompt_interactivo(home):
    ctx = Contexto("rutina", departamento="dep:atlas", corrida="corr-1")
    r = motor.evaluar(acunar(500_000), ctx)
    assert r.estado == motor.ESTADO_ESTACIONADA
    # no hay ningun prompt pendiente esperando a nadie
    assert motor.vista()["pendientes"] == []
    assert len(motor.vista()["estacionadas"]) == 1


def test_el_desatendido_no_se_auto_aprueba(home):
    ctx = Contexto("rutina", departamento="dep:atlas", corrida="corr-1")
    r = motor.evaluar(acunar(500_000), ctx)
    assert not r.permitido
    # y sigue sin aprobarse sola por mas que se la vuelva a mirar
    assert almacen.obtener(r.solicitud["id"])["estado"] == "estacionada"


def test_un_origen_que_nadie_declaro_es_desatendido(home):
    # el default seguro: si el llamador no dice quien es, se lo trata como
    # si no hubiera nadie mirando
    r = motor.evaluar(npm_test(), Contexto())
    assert r.estado == motor.ESTADO_ESTACIONADA


def test_la_preautorizacion_del_departamento_pasa_de_noche(home):
    ctx = Contexto("rutina", departamento="dep:atlas", corrida="c1")
    # git_status ya es directo; el caso que importa es uno que SIN la lista
    # preguntaria. Se le declara al departamento su propia lista.
    (home / "permisos.json").write_text(json.dumps({
        "preautorizados": {"dep:atlas": [
            {"familia": "comando", "operacion": "correr",
             "forma": {"argv": ["npm", "test"],
                       "cwd": "/var/home/pedro/Observatory-Global"}}]}}),
        encoding="utf-8")
    assert motor.evaluar(npm_test(), ctx).permitido


def test_la_plata_no_se_puede_preautorizar(home):
    # acunar de noche SIEMPRE se estaciona, aunque alguien la escriba en la
    # lista del departamento: es de las que preguntan siempre
    (home / "permisos.json").write_text(json.dumps({
        "preautorizados": {"dep:atlas": [
            {"familia": "plata", "operacion": "acunar",
             "forma": {"subtipo": "capital", "destino": "tesoro",
                       "monto_mm": 500_000}}]}}), encoding="utf-8")
    ctx = Contexto("rutina", departamento="dep:atlas", corrida="c1")
    assert motor.evaluar(acunar(500_000), ctx).estado \
        == motor.ESTADO_ESTACIONADA


def test_un_departamento_con_lista_vacia_no_hereda_el_default(home):
    (home / "permisos.json").write_text(
        json.dumps({"preautorizados": {"dep:atlas": []}}), encoding="utf-8")
    assert almacen.preautorizados("dep:atlas") == []
    assert almacen.preautorizados("dep:otro") == almacen.PREAUTORIZADO_DEFECTO


def test_lo_estacionado_termina_la_corrida(home):
    ctx = Contexto("rutina", departamento="dep:atlas", corrida="corr-1")
    r = motor.evaluar(acunar(500_000), ctx)
    # cualquier cosa de la MISMA corrida, aunque sea de nivel directo, no
    # pasa: la corrida termino
    directa = Accion("comando", "allowlist", {"id": "git_status"})
    r2 = motor.evaluar(directa, ctx)
    assert r2.estado == motor.ESTADO_ESTACIONADA
    assert r2.solicitud["id"] == r.solicitud["id"]
    intentos = almacen.obtener(r.solicitud["id"])["intentos"]
    assert any(i["que"] == "rodeo de corrida" for i in intentos)


def test_lo_estacionado_no_se_rodea_por_otro_departamento(home):
    a = acunar(500_000)
    r = motor.evaluar(a, Contexto("rutina", departamento="dep:atlas",
                                  corrida="c1"))
    r2 = motor.evaluar(a, Contexto("rutina", departamento="dep:mercado",
                                   corrida="c2"))
    assert r2.estado == motor.ESTADO_ESTACIONADA
    assert r2.solicitud["id"] == r.solicitud["id"]  # la misma pared
    intentos = almacen.obtener(r.solicitud["id"])["intentos"]
    assert any("otro origen" in i["que"] for i in intentos)


def test_lo_pendiente_tampoco_se_rodea_desde_otro_chat(home):
    a = acunar(500_000)
    r = motor.evaluar(a, Contexto("chat", chat="c1"))
    r2 = motor.evaluar(a, Contexto("chat", chat="c2"))
    assert r2.estado == motor.ESTADO_PENDIENTE
    assert r2.solicitud["id"] == r.solicitud["id"]
    assert almacen.obtener(r.solicitud["id"])["intentos"]


def test_subir_el_techo_no_suelta_lo_que_ya_estaba_esperando(home):
    r = motor.evaluar(acunar(500_000), Contexto("pedro"))
    almacen.poner_techo("plata_mm", 900_000)
    r2 = motor.evaluar(acunar(500_000), Contexto("pedro"))
    assert r2.estado == motor.ESTADO_PENDIENTE
    assert r2.solicitud["id"] == r.solicitud["id"]


def test_la_rutina_retoma_en_su_proxima_corrida(home):
    a = acunar(500_000)
    r = motor.evaluar(a, Contexto("rutina", departamento="dep:atlas",
                                  corrida="c1"))
    motor.responder(r.solicitud["id"], "si")
    # una estacionada aprobada NO se ejecuta al contestar: la retoma la
    # rutina, con una corrida nueva
    assert motor.aprobadas_para("dep:atlas")
    r2 = motor.evaluar(a, Contexto("rutina", departamento="dep:atlas",
                                   corrida="c2"))
    assert r2.permitido
    # y una sola vez: la tercera vuelve a preguntar
    r3 = motor.evaluar(a, Contexto("rutina", departamento="dep:atlas",
                                   corrida="c3"))
    assert r3.estado == motor.ESTADO_ESTACIONADA
    assert r3.solicitud["id"] != r.solicitud["id"]


def test_una_aprobada_sin_ejecutar_sobrevive_a_la_regla(home):
    """D4: el corte va DESPUES del consumo de aprobadas. Pedro aprobo esa
    solicitud concreta antes; la regla gobierna lo que venga.

    `desatendido` no es un parametro de `Contexto`: es una propiedad
    derivada de `origen not in ORIGENES_ATENDIDOS` (`acciones.py:108-110`,
    y los atendidos son "chat" y "pedro"). El molde de un contexto de
    rutina es el de `test_lo_estacionado_termina_la_corrida`. Y la segunda
    corrida lleva OTRO id a proposito: es lo que hace de verdad la rutina
    -- "la retoma en su proxima corrida" -- y ademas evita la pared de
    corrida, que es un corte anterior y taparia lo que este test mide.
    """
    ctx = Contexto("rutina", departamento="dep:atlas", corrida="corr-1")
    r = motor.evaluar(acunar(150_000), ctx)
    assert r.estado == motor.ESTADO_ESTACIONADA
    motor.responder(r.solicitud["id"], "si")
    almacen.anotar_regla(acunar(150_000), Contexto("pedro"), "x",
                         siempre_pregunta=True, efecto="denegar")

    proxima = Contexto("rutina", departamento="dep:atlas", corrida="corr-2")
    r2 = motor.evaluar(acunar(150_000), proxima)
    assert r2.estado == motor.ESTADO_PERMITIDO


# --------------------------------------------------------------------------
# Ejecucion: una accion irreversible no se hace dos veces
# --------------------------------------------------------------------------

def test_una_aprobada_se_ejecuta_una_sola_vez(home):
    hechos = []
    motor.registrar_ejecutor("plata", "acunar",
                             lambda a: hechos.append(a.forma["monto_mm"]) or
                             {"ok": True})
    r = motor.evaluar(acunar(500_000), Contexto("pedro"))
    salida = motor.responder(r.solicitud["id"], "si")
    assert salida["ejecucion"]["ejecutada"] is True
    assert hechos == [500_000]
    # un segundo intento de ejecutar la misma solicitud no acuna de nuevo
    assert motor.ejecutar(r.solicitud)["ejecutada"] is False
    assert hechos == [500_000]


def test_un_ejecutor_que_revienta_deja_la_solicitud_fallida(home):
    def explota(a):
        raise RuntimeError("el libro no abrio")
    motor.registrar_ejecutor("plata", "acunar", explota)
    r = motor.evaluar(acunar(500_000), Contexto("pedro"))
    salida = motor.responder(r.solicitud["id"], "si")
    assert salida["ejecucion"]["ejecutada"] is False
    assert almacen.obtener(r.solicitud["id"])["estado"] == "fallida"


def test_sin_ejecutor_no_se_pierde_la_solicitud(home):
    r = motor.evaluar(acunar(500_000), Contexto("pedro"))
    salida = motor.responder(r.solicitud["id"], "si")
    assert salida["ejecucion"]["ejecutada"] is False
    assert "sin ejecutor" in salida["ejecucion"]["motivo"]


# --------------------------------------------------------------------------
# Persistencia y rastro
# --------------------------------------------------------------------------

def test_la_escritura_no_deja_temporales(home):
    motor.evaluar(acunar(500_000), Contexto("pedro"))
    almacen.poner_techo("plata_mm", 1_000)
    sobrantes = [p.name for p in home.rglob("*.tmp*")]
    assert sobrantes == []


def test_permisos_json_ilegible_no_concede_nada(home):
    (home / "permisos.json").write_text("{ roto", encoding="utf-8")
    assert almacen.concedidos() == []
    assert almacen.techos()["plata_mm"] == 100_000
    # el lado seguro es preguntar de mas
    assert motor.evaluar(npm_test(), Contexto("chat")).estado \
        == motor.ESTADO_PENDIENTE


def test_solicitudes_ilegibles_niegan_todo(home):
    (home / "permisos").mkdir(parents=True, exist_ok=True)
    (home / "permisos" / "solicitudes.json").write_text("{ roto",
                                                        encoding="utf-8")
    # sin poder leer lo estacionado no se puede garantizar que esto no sea
    # un rodeo: se niega, incluso una accion de nivel directo
    directa = Accion("comando", "allowlist", {"id": "git_status"})
    assert motor.evaluar(directa, Contexto("pedro")).estado \
        == motor.ESTADO_NEGADO


def test_todo_deja_rastro_se_haya_preguntado_o_no(home):
    motor.evaluar(acunar(1_000), Contexto("pedro"))          # directo
    motor.evaluar(acunar(500_000), Contexto("pedro"))        # pregunta
    motor.evaluar(Accion("archivo", "leer", {"ruta": str(home / "token")}),
                  Contexto("pedro"))                          # nunca
    reg = almacen.registro()
    estados = [l["estado"] for l in reg if "estado" in l]
    assert estados == ["permitido", "pendiente", "negado"]
    assert all(l["ts"] for l in reg)


def test_la_vista_de_fabrica_trae_las_tres_cosas(home):
    motor.evaluar(acunar(500_000), Contexto("pedro"))
    motor.evaluar(npm_test(), Contexto("rutina", departamento="dep:a",
                                       corrida="c9"))
    r = motor.evaluar(npm_test("/otro"), Contexto("chat"))
    motor.responder(r.solicitud["id"], "si_siempre")
    v = motor.vista()
    assert len(v["pendientes"]) == 1
    assert len(v["estacionadas"]) == 1
    assert len(v["concedidos"]) == 1
    assert v["techos"]["plata_mm"] == 100_000
    assert v["error"] is None


def test_el_home_se_resuelve_en_cada_llamada(home, tmp_path, monkeypatch):
    # la trampa de CALIPSO_HOME congelado al importar: si el modulo lo
    # hubiera cacheado, cambiarlo aca no haria nada y el archivo caeria en
    # el home viejo
    otro = tmp_path / "otro-home"
    otro.mkdir()
    monkeypatch.setenv("CALIPSO_HOME", str(otro))
    almacen.poner_techo("plata_mm", 42)
    assert (otro / "permisos.json").exists()
    assert not (home / "permisos.json").exists()
