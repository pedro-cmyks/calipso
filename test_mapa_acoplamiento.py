"""Tests del acoplamiento mapa <-> chat (spec seccion 8)."""
import json

import pytest

import calipso.server as srv
from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import pagador as pag
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.mapa import ficha

TS = "2026-08-25T10:00:00"
W = "2026-W35"


EDIFICIO = {"id": "dep:atlas", "nombre": "atlas", "zona": "fabrica",
            "estado": "activo", "saldo_mm": 1_148_000,
            "gasto_ciclo_mm": 320_000, "ventas_ventana_mm": 900_500,
            "eficiencia_pormil": 124, "actividad": 2,
            "trabajos": ["t1", "t2"], "compuertas": 1}


def test_la_cuenta_pagadora_sale_del_id_del_edificio():
    assert ficha.cuenta_pagadora("dep:atlas") == "dep:atlas"
    # `personal:` COLAPSA a `personal`, no se queda como esta: la zona
    # personal no compra capacidad ni API de la fabrica (invariante 12), asi
    # que un cargo a `personal:finanzas` lo rechaza `Mercado._politica` y
    # queda pendiente para siempre. `personal` es la cuenta que el camino de
    # reserva personal espera.
    assert ficha.cuenta_pagadora("personal:finanzas") == ficha.CUENTA_PERSONAL
    # la casa de Pedro no es un departamento: su gasto queda fuera del libro
    # de la fabrica, que es donde lo lleva calipso/costs.py
    assert ficha.cuenta_pagadora("cuenta_pedro") == ficha.CUENTA_PERSONAL
    assert ficha.cuenta_pagadora(None) == ficha.CUENTA_PERSONAL
    assert ficha.cuenta_pagadora("") == ficha.CUENTA_PERSONAL
    # y nada de cuentas inventadas desde el cliente: el paquete del chat
    # llega de afuera y "tesoro" no puede pagar un chat
    assert ficha.cuenta_pagadora("tesoro") == ficha.CUENTA_PERSONAL


def test_el_edificio_se_busca_por_id_en_el_modelo():
    modelo = {"edificios": [EDIFICIO, {**EDIFICIO, "id": "dep:mercado"}]}
    assert ficha.edificio_de(modelo, "dep:mercado")["id"] == "dep:mercado"
    assert ficha.edificio_de(modelo, "dep:nada") is None
    assert ficha.edificio_de(None, "dep:atlas") is None


def test_el_bloque_lleva_los_numeros_en_monedas_y_dice_quien_paga():
    """El libro guarda milimonedas; el que lee el prompt lee monedas. Un
    bloque que dijera 1148000 haria que Calipso hable de millones."""
    texto = ficha.bloque(EDIFICIO)
    assert "atlas" in texto
    assert "1148.00" in texto and "320.00" in texto and "900.50" in texto
    assert "12.4%" in texto
    assert "dep:atlas" in texto.split("paga la cuenta")[1]
    assert "1148000" not in texto


def test_el_bloque_no_miente_cuando_no_hay_eficiencia():
    texto = ficha.bloque({**EDIFICIO, "eficiencia_pormil": None})
    assert "sin dato" in texto
    assert "0.0%" not in texto


@pytest.fixture
def economia(tmp_path, monkeypatch):
    """Una fabrica chica con un departamento con techo de API y plata.

    El `emitir_semana` no es decorativo: sin PT emitido, la semana no es
    operativa y `gastar_api` no encuentra el ciclo. Mismo armado que usa
    `test_economia_pagador.py`."""
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=1_000_000))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    k.acunar(TS, W, "dep:atlas", 50_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    return eco


def saldo(eco, cuenta):
    return pag.Pagador(eco).leer_kernel().saldo(cuenta)


def test_el_turno_de_api_lo_paga_el_departamento_en_foco(economia):
    """Un millon de tokens de entrada de deepseek son 270 milimonedas: el
    precio esta en PRECIOS_API_MM_POR_MTOK y no se redondea a cero."""
    antes = saldo(economia, "dep:atlas")
    cobrado = srv._cobrar_turno("dep:atlas", "api", None, "deepseek-chat",
                                {"prompt_tokens": 1_000_000,
                                 "completion_tokens": 0})
    assert cobrado == 270
    assert saldo(economia, "dep:atlas") == antes - 270


def test_sin_departamento_no_se_toca_el_libro(economia):
    antes = saldo(economia, "dep:atlas")
    assert srv._cobrar_turno(ficha.CUENTA_PERSONAL, "api", None,
                             "deepseek-chat",
                             {"prompt_tokens": 1_000_000}) == 0
    assert saldo(economia, "dep:atlas") == antes


def test_la_ruta_local_consume_suscripcion_igual(economia):
    # no hay Ollama: `_chunks_for` resuelve la ruta local con `_local_via_sub`,
    # que corre `claude -p` — una unidad de suscripcion, no un modelo gratis.
    antes = saldo(economia, "dep:atlas")
    # devuelve cero milimonedas igual: la suscripcion se cobra en unidades de
    # capacidad, y lo que sale del saldo lo pone el precio de esa unidad
    assert srv._cobrar_turno("dep:atlas", "local", None, "qwen2.5:7b",
                             {"prompt_tokens": 9_000_000}) == 0
    p = pag.Pagador(economia)
    asientos = p.leer_kernel().libro.asientos()
    assert cap.consumo_fabrica(asientos, "claude_max", [W]) == 1
    assert saldo(economia, "dep:atlas") < antes
    assert p.pendientes() == []


def test_el_fallback_local_le_cobra_al_departamento_en_foco(economia):
    """El fallback local es el camino comun de cualquier falla de ruta, y
    llega con el `client` de la ruta que fallo. Corre `claude` igual, asi que
    la unidad que consume es la de `claude`, no la del cliente del verdict."""
    srv._cobrar_turno("dep:atlas", "local", "codex", "qwen2.5:7b", {})
    p = pag.Pagador(economia)
    compras = [a for a in p.leer_kernel().libro.asientos()
               if (a.detalle or {}).get("suscripcion")]
    assert [a.detalle["suscripcion"] for a in compras] == ["claude_max"]


def test_el_borrador_del_chat_cobra_su_unidad_de_suscripcion(economia,
                                                            monkeypatch):
    """`_run_chat_draft` llama a `_run_subscription_text("claude", ...)`: una
    unidad de suscripcion de verdad, que hasta ahora no le cobraba a nadie.

    El cobro va en un hilo porque toma el candado del libro, y el borrador
    corre en el event loop con `ensure_future`."""
    import asyncio

    monkeypatch.setattr(srv, "EL_PULSO", None)
    monkeypatch.setattr(srv, "PENDING_CHANGES", {})
    monkeypatch.setattr(srv.goals, "active", lambda raiz: None)
    monkeypatch.setattr(srv.developer, "chat_draft_brief",
                        lambda *a, **k: {"job": {"id": "j1"}, "system": "s",
                                         "user_msg": "u"})
    monkeypatch.setattr(srv, "_run_subscription_text",
                        lambda *a, **k: "linea nueva\n")
    monkeypatch.setattr(srv.jobs, "write_artifact", lambda *a, **k: None)
    monkeypatch.setattr(srv.jobs, "update", lambda *a, **k: None)

    class _WSFalso:
        def __init__(self):
            self.enviados = []

        async def send_json(self, payload):
            self.enviados.append(payload)

    ws = _WSFalso()
    antes = saldo(economia, "dep:atlas")
    asyncio.run(srv._run_chat_draft(ws, "cambia algo", "no-existe.py",
                                    "chat:abc:borrador", "dep:atlas"))
    # la propuesta sigue llegando: el cobro es contabilidad, no la respuesta
    assert ws.enviados[-1]["type"] == "proposal"
    p = pag.Pagador(economia)
    asientos = p.leer_kernel().libro.asientos()
    assert cap.consumo_fabrica(asientos, "claude_max", [W]) == 1
    assert saldo(economia, "dep:atlas") < antes
    assert p.pendientes() == []


def test_el_borrador_sin_departamento_no_le_cobra_a_nadie(economia,
                                                          monkeypatch):
    """Sin edificio tocado el borrador es gasto personal, que queda fuera del
    libro de la fabrica igual que el turno."""
    import asyncio

    monkeypatch.setattr(srv, "EL_PULSO", None)
    monkeypatch.setattr(srv, "PENDING_CHANGES", {})
    monkeypatch.setattr(srv.goals, "active", lambda raiz: None)
    monkeypatch.setattr(srv.developer, "chat_draft_brief",
                        lambda *a, **k: {"job": {"id": "j1"}, "system": "s",
                                         "user_msg": "u"})
    monkeypatch.setattr(srv, "_run_subscription_text",
                        lambda *a, **k: "linea nueva\n")
    monkeypatch.setattr(srv.jobs, "write_artifact", lambda *a, **k: None)
    monkeypatch.setattr(srv.jobs, "update", lambda *a, **k: None)

    class _WSFalso:
        async def send_json(self, payload):
            pass

    antes = saldo(economia, "dep:atlas")
    asyncio.run(srv._run_chat_draft(_WSFalso(), "cambia algo", "no-existe.py",
                                    "chat:abc:borrador", None))
    assert saldo(economia, "dep:atlas") == antes
    assert pag.Pagador(economia).pendientes() == []


def test_un_cobro_que_no_entra_queda_pendiente_y_no_voltea_el_chat(tmp_path,
                                                                  monkeypatch):
    """Techo de API en cero: el mercado rechaza el gasto. El turno tiene que
    terminar igual y el cargo esperar en cargos_pendientes.jsonl."""
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=0))
    (eco / "suscripciones.json").write_text("{}", encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    k.acunar(TS, W, "dep:atlas", 50_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    srv._cobrar_turno("dep:atlas", "api", None, "deepseek-chat",
                      {"prompt_tokens": 1_000_000, "completion_tokens": 0})
    pendientes = pag.Pagador(eco).pendientes()
    assert len(pendientes) == 1 and pendientes[0]["cuenta"] == "dep:atlas"


def test_el_turno_de_equipo_dinamico_tambien_le_cobra_al_departamento(economia):
    """`used_route` vale "orchestrator" cuando corre el equipo dinamico. Si
    eso llega crudo a `_cobrar_turno`, los agentes gastan y el departamento
    no paga nada — que es justo lo contrario del criterio de exito del spec."""
    antes = saldo(economia, "dep:atlas")
    # lo que el llamador normaliza: orchestrator no es una ruta cobrable
    ruta = "api"      # verdict["route"] del turno
    cobrado = srv._cobrar_turno("dep:atlas", ruta, None, "deepseek-chat",
                                {"prompt_tokens": 1_000_000,
                                 "completion_tokens": 0})
    assert cobrado == 270 and saldo(economia, "dep:atlas") == antes - 270
    # y la ruta cruda no cobra nada, que es el bug que la normalizacion evita
    assert srv._cobrar_turno("dep:atlas", "orchestrator", None,
                             "deepseek-chat",
                             {"prompt_tokens": 1_000_000}) == 0


def test_el_pagador_se_valida_contra_el_registro_y_no_contra_la_ciudad(
        economia, monkeypatch):
    """Son dos preguntas distintas y solo una de las dos puede degradar el cobro.

    `_ciudad_modelo` lee el libro entero y el libro se repara truncando, asi
    que leerlo puede reventar. Que eso pase tiene que degradar la FICHA a "sin
    ficha" y nada mas: mandar el cobro a `personal` justo cuando el libro esta
    a medio reparar es dejar de asentar el gasto cuando menos se quiere."""
    def revienta():
        raise RuntimeError("libro a medio reparar")

    monkeypatch.setattr(srv, "_ciudad_modelo", revienta)
    bloque, cuenta = srv._ficha_y_cuenta("dep:atlas")
    assert cuenta == "dep:atlas"      # el departamento existe: sigue pagando
    assert bloque == ""               # la ficha si degrada


def test_un_departamento_inventado_degrada_a_personal_sin_derivar_la_ciudad(
        economia, monkeypatch):
    """El id sale del paquete del WebSocket. Validarlo contra el registro es
    ademas gratis: un id inventado ya no paga derivar la ciudad entera bajo el
    candado del libro."""
    derivaciones = []
    monkeypatch.setattr(srv, "_ciudad_modelo",
                        lambda: derivaciones.append(1))
    assert srv._ficha_y_cuenta("dep:inventado") == ("", ficha.CUENTA_PERSONAL)
    assert srv._ficha_y_cuenta("tesoro") == ("", ficha.CUENTA_PERSONAL)
    assert derivaciones == []


def test_con_el_departamento_en_el_registro_la_ficha_sale_del_libro(economia):
    bloque, cuenta = srv._ficha_y_cuenta("dep:atlas")
    assert cuenta == "dep:atlas"
    assert "Departamento en foco" in bloque and "atlas" in bloque


def test_sin_departamento_tocado_no_hay_ficha_ni_pagador(economia):
    assert srv._ficha_y_cuenta(None) == ("", ficha.CUENTA_PERSONAL)
    assert srv._ficha_y_cuenta("") == ("", ficha.CUENTA_PERSONAL)


def test_la_zona_personal_tiene_ficha_pero_paga_por_afuera(tmp_path,
                                                           monkeypatch):
    """Un departamento de zona personal existe en el registro -o sea que no es
    un id inventado- pero su cuenta colapsa a `personal` (invariante 12)."""
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    (eco / "suscripciones.json").write_text("{}", encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    bloque, cuenta = srv._ficha_y_cuenta("personal:finanzas")
    assert cuenta == ficha.CUENTA_PERSONAL
    assert "finanzas" in bloque


def test_el_modelo_de_ciudad_se_deriva_una_sola_vez_y_sin_coordenadas(economia):
    """El chat necesita la ficha, no el dibujo: el urbanismo, que es la
    mitad cara, no corre cuando no hay mapa que pintar."""
    modelo = srv._ciudad_modelo()
    assert modelo is not None
    edificio = ficha.edificio_de(modelo, "dep:atlas")
    assert edificio["saldo_mm"] == 50_000
    assert "x" not in edificio and "y" not in edificio
    # y el endpoint sigue entregando las coordenadas
    from fastapi.testclient import TestClient
    c = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    cuerpo = c.get("/api/mapa/ciudad").json()
    assert cuerpo["activa"] is True
    assert all("x" in e for e in cuerpo["ciudad"]["edificios"])


def test_un_cargo_a_un_departamento_inventado_no_se_aplica_nunca(economia):
    """Por que el turno degrada a `personal` cuando el edificio no existe.

    El id del departamento llega del paquete del WebSocket, o sea de afuera.
    Un cargo a una cuenta sin departamento detras lo rechaza el mercado, el
    pagador lo apila, y ningun reintento lo va a aplicar: una linea por turno
    en cargos_pendientes.jsonl, sin techo."""
    srv._cobrar_turno("dep:inventado", "api", None, "deepseek-chat",
                      {"prompt_tokens": 1_000_000, "completion_tokens": 0})
    p = pag.Pagador(economia)
    assert len(p.pendientes()) == 1
    assert p.reintentar_pendientes() == 0
    assert len(p.pendientes()) == 1   # y sigue ahi despues del reintento


def test_la_zona_personal_no_le_paga_a_la_fabrica(tmp_path, monkeypatch):
    """Invariante 12, ejecutada: un departamento de zona personal no compra
    capacidad. Es lo que hace que `cuenta_pagadora` tenga que colapsar
    `personal:` antes de que el cargo llegue al mercado."""
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    p = pag.Pagador(eco)
    p.cargar_suscripcion(TS, W, "personal:finanzas", "claude_max")
    assert len(p.pendientes()) == 1
    assert p.reintentar_pendientes() == 0   # la invariante lo prohibe siempre
    # y por eso el turno nunca manda una cuenta `personal:` al pagador
    assert ficha.cuenta_pagadora("personal:finanzas") == ficha.CUENTA_PERSONAL


def test_el_foco_es_pegajoso_por_conexion_y_no_por_paquete():
    """Pedro interrumpe con el edificio todavia tocado en pantalla: ese turno
    tiene que seguir en el mismo departamento.

    La vuelta que consume `pending` saltea el parseo del paquete, asi que si
    `departamento` se reiniciara en cada vuelta del bucle de turnos, un turno
    encolado por steering iria sin ficha y sin cobrarle a nadie. Se afirma
    sobre el AST porque la propiedad ES el alcance de la variable: manejar un
    turno encolado de verdad pide el WebSocket, los probes de ruteo y un
    modelo respondiendo."""
    import ast
    import inspect

    def reinicia_departamento(cuerpo) -> bool:
        """Solo las sentencias DIRECTAS del cuerpo: la reasignacion desde el
        paquete vive anidada en el `try`/`if` del parseo y no cuenta."""
        return any(isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "departamento"
                           for t in n.targets)
                   for n in cuerpo)

    fn = ast.parse(inspect.getsource(srv.ws_chat)).body[0]
    assert reinicia_departamento(fn.body), (
        "`departamento` tiene que declararse en el cuerpo de ws_chat, afuera "
        "del bucle de turnos: es estado de la conexion, como _last_verdict")
    for bucle in [n for n in ast.walk(fn) if isinstance(n, ast.While)]:
        assert not reinicia_departamento(bucle.body), (
            "`departamento` se reinicia en cada vuelta de un bucle: el turno "
            "que consume `pending` perderia el foco que Pedro tiene tocado")
