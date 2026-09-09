"""La consulta en la ruta one-shot (spec seccion 4, "Regla de las rutas"): no
hay stream que cortar, el detector lee el texto entero, la reentrada re-invoca
el CLI (dos invocaciones reales, declaradas) y el preview se congela en la
primera marca. Y la ruta orquestador, que queda fuera: sus marcas se retiran
con aviso."""
import asyncio
import json
import pathlib
import sys
import textwrap

import pytest

import calipso.server as srv
from calipso import jobs
from calipso.mapa import pulso as p
from test_abismo_chat import chat, de_tipo, texto_visible  # noqa: F401  (fixture + helpers)
from test_abismo_chat import _sembrar_chat_viejo


@pytest.fixture
def cli_falso(tmp_path, monkeypatch):
    """Un CLI de suscripcion de mentira: sigue un guion por invocacion (partes
    con pausa entre ellas, asi el preview de 2 s alcanza a verlas llegar) y
    anota el system y el prompt que recibio en llamada-N.json."""
    carpeta = tmp_path / "cli"
    carpeta.mkdir()
    script = carpeta / "claude_falso.py"
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''
        import json, pathlib, sys, time
        base = pathlib.Path(__file__).parent
        n = len(list(base.glob("llamada-*.json")))
        args = sys.argv[1:]
        sistema = ""
        if "--append-system-prompt-file" in args:
            ruta = args[args.index("--append-system-prompt-file") + 1]
            sistema = pathlib.Path(ruta).read_text(encoding="utf-8")
        prompt = args[args.index("-p") + 1] if "-p" in args else ""
        (base / f"llamada-{n}.json").write_text(
            json.dumps({"sistema": sistema, "prompt": prompt}), encoding="utf-8")
        guion = json.loads((base / "guion.json").read_text(encoding="utf-8"))
        paso = guion[min(n, len(guion) - 1)]
        for parte in paso["partes"]:
            sys.stdout.write(parte)
            sys.stdout.flush()
            time.sleep(paso.get("pausa", 0))
    '''), encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr(srv, "_subscription_command", lambda c: str(script))

    class CLI:
        def guion(self, pasos):
            (carpeta / "guion.json").write_text(json.dumps(pasos), encoding="utf-8")

        def llamadas(self):
            return [json.loads(f.read_text(encoding="utf-8"))
                    for f in sorted(carpeta.glob("llamada-*.json"))]
    return CLI()


def test_en_suscripcion_la_marca_corta_congela_el_preview_y_reinvoca(chat, cli_falso):
    _sembrar_chat_viejo(["empece El nombre de la rosa, es un libro alucinante"])
    # pausa 3.5: el bucle del preview tica a los 3.0 y 6.0 s (avisa cada 2 s
    # sobre un sleep de 1.5), asi que hay UN tic antes de la marca (parcial
    # "Dejame ver", sin espacio final por el strip de _read_partial) y UNO
    # despues (congelado en "Dejame ver "). Con 2.5 el unico tic caia a 0.45 s
    # de la segunda escritura y una maquina cargada lo dejaba en rojo.
    cli_falso.guion([{"partes": ["Dejame ver ", "⟦abismo:chats libro⟧ esto no se ve"], "pausa": 3.5},
                     {"partes": ["y sigo con contexto"], "pausa": 0}])
    eventos = chat.turno("/claude que libro lei")
    tipos = [e["type"] for e in eventos]
    assert texto_visible(eventos) == "Dejame ver y sigo con contexto"
    assert tipos.count("done") == 1
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"]
    # el preview: avanza hasta la marca y ahi se congela; nunca muestra lo
    # que despues se descarta, ni la marca
    parciales = [e["partial"] for e in de_tipo(eventos, "process") if e.get("action") == "running"]
    assert parciales and any(pp == "Dejame ver " for pp in parciales)
    assert not any("esto no se ve" in pp or "⟦" in pp for pp in parciales)
    # dos invocaciones reales: la segunda lleva el bloque en el system y el
    # "venias diciendo" en el prompt
    llamadas = cli_falso.llamadas()
    assert len(llamadas) == 2
    assert "=== Lo que subio del abismo (fuente: chats) ===" in llamadas[1]["sistema"]
    assert "El nombre de la rosa" in llamadas[1]["sistema"]
    assert "Venias diciendo: Dejame ver " in llamadas[1]["prompt"]
    assert "Lo que subio" not in llamadas[0]["sistema"]
    # declaradas en telemetry
    eventos_abismo = [f["evento"] for f in chat.telemetria("abismo")]
    assert eventos_abismo == ["consulta", "reinvocacion_suscripcion"]
    # los artefactos de los dos jobs no llevan la marca
    for ev in de_tipo(eventos, "process"):
        if ev.get("action") == "start":
            ruta = jobs.artifact_path(str(srv.ROOT), ev["job_id"], "output.txt")
            assert ruta.exists() and "⟦" not in ruta.read_text(encoding="utf-8")
    # y la persistencia sigue siendo un solo par, sin marca ni bloque
    assert [(m["role"], m["text"]) for m in chat.mensajes()] == [
        ("user", "/claude que libro lei"), ("assistant", "Dejame ver y sigo con contexto")]


def test_en_suscripcion_una_pesca_vacia_no_reinvoca_y_el_texto_posterior_vale(chat, cli_falso):
    """Spec seccion 8.4 aplicado al one-shot: sin bloque no hay reentrada;
    lo que el CLI escribio despues de la marca vale, sin marcas."""
    cli_falso.guion([{"partes": ["Dejame ver ⟦abismo:chats zzzz⟧ y sigo sin contexto"], "pausa": 0}])
    eventos = chat.turno("/claude hola")
    assert texto_visible(eventos) == "Dejame ver  y sigo sin contexto"
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "fallo"]
    assert de_tipo(eventos, "abismo")[1]["motivo"] == "vacio"
    assert len(cli_falso.llamadas()) == 1


def test_un_stop_durante_el_cli_no_pesca_ni_reinvoca(chat, cli_falso):
    """El gesto mas fuerte de Pedro (invariante 8): un /stop mata el CLI y NO
    dispara la pesca ni una segunda invocacion, aunque el parcial que el CLI
    alcanzo a escribir tenga una marca valida. Lo que alcanzo a escribir
    vale, sin la marca, con el "(proceso interrumpido)" de siempre."""
    _sembrar_chat_viejo(["un libro"])
    cli_falso.guion([{"partes": ["Dejame ver ⟦abismo:chats libro⟧", " tarde"], "pausa": 4.0}])
    with chat.cliente.websocket_connect("/ws/chat") as ws:
        ws.send_text(chat.paquete("/claude que libro lei"))
        primero = []
        while not any(e.get("type") == "process" and e.get("action") == "start" for e in primero):
            primero.append(ws.receive_json())      # thinking, meta, ..., process/start
        ws.send_text("/stop")                      # con el CLI vivo (lo atiende el tic de 1.5 s)
        eventos = primero + chat.recibir(ws)
    assert de_tipo(eventos, "abismo") == []
    assert len(cli_falso.llamadas()) == 1
    assert [e["type"] for e in eventos].count("done") == 1
    visible = texto_visible(eventos)
    assert visible.startswith("Dejame ver ") and "(proceso interrumpido)" in visible
    assert "⟦" not in visible and "tarde" not in visible
    assert [f["momento"] for f in chat.telemetria("abismo") if f["evento"] == "abortada_por_steer"] == ["cli"]


def test_en_suscripcion_la_cuarta_marca_no_corta(chat, cli_falso):
    """El tope en one-shot (spec seccion 4): la cuarta marca se retira con
    aviso, sin reinvocar, y el texto posterior vale."""
    _sembrar_chat_viejo(["un libro"])
    cli_falso.guion([{"partes": ["a ⟦abismo:chats libro⟧"], "pausa": 0}] * 3
                    + [{"partes": ["d ⟦abismo:chats libro⟧ e"], "pausa": 0}])
    eventos = chat.turno("/claude libros")
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"] * 3
    assert texto_visible(eventos) == "a a a d  e" and len(cli_falso.llamadas()) == 4
    retiradas = [f for f in chat.telemetria("abismo") if f["evento"] == "retirada"]
    assert [f["clase"] for f in retiradas] == ["sin_corte"]


def test_en_suscripcion_un_prefijo_abierto_antes_de_la_marca_no_traga_la_reentrada(chat, cli_falso):
    """La sonda A del cierre (h01): `cortar_en_marca` corta en la primera
    valida y el tramo queda terminado en un `⟦abismo:` abierto; el filtro lo
    RETENIA a traves de la pesca y la reinvocacion, la continuacion se
    pegaba detras y `cerrar()` descartaba todo como `abierta`: dos
    invocaciones reales pagadas para no mostrar nada. En one-shot el texto
    llega entero: la tuberia se vuelca en cada tramo (el prefijo abierto se
    descarta con aviso ahi mismo) y el "venias diciendo" no lleva la marca a
    medias."""
    _sembrar_chat_viejo(["un libro"])
    cli_falso.guion([{"partes": ["x ⟦abismo:zzz ⟦abismo:chats libro⟧ fin"], "pausa": 0},
                     {"partes": ["y sigo"], "pausa": 0}])
    eventos = chat.turno("/claude libro")
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"]
    assert texto_visible(eventos) == "x y sigo"
    assert [e["type"] for e in eventos].count("done") == 1
    llamadas = cli_falso.llamadas()
    assert len(llamadas) == 2
    assert "Venias diciendo: x \n" in llamadas[1]["prompt"]
    assert "⟦" not in llamadas[1]["prompt"]
    assert chat.mensajes()[-1] == chat.mensajes()[-1] | {"role": "assistant", "text": "x y sigo"}
    retiradas = [f for f in chat.telemetria("abismo") if f["evento"] == "retirada"]
    assert [(f["clase"], f["largo"]) for f in retiradas] == [("abierta", len("⟦abismo:zzz "))]


def test_en_suscripcion_una_marca_que_solo_ve_la_tuberia_se_retira_sin_cortar(chat, cli_falso):
    """S11a del cierre (h01): PATRON no admite corchetes en el cuerpo, asi que
    el detector one-shot no ve la marca; el filtro de foco saca el
    `⟦foco:atlas⟧` de adentro y el del abismo veia una VALIDA y cortaba por
    su cuenta, sin que nadie consumiera la marca: el resto se tragaba mudo
    (sin senal, sin fila). En one-shot el corte lo decide SOLO el detector:
    la tuberia retira con aviso y el texto posterior vale."""
    cli_falso.guion([{"partes": ["Dejame ver ⟦abismo:chats libro ⟦foco:atlas⟧ x⟧ y esto sigue"], "pausa": 0},
                     {"partes": ["NO deberia reinvocar"], "pausa": 0}])
    eventos = chat.turno("/claude libro")
    assert de_tipo(eventos, "abismo") == []
    assert texto_visible(eventos) == "Dejame ver  y esto sigue"
    assert len(cli_falso.llamadas()) == 1
    assert [f["clase"] for f in chat.telemetria("abismo")] == ["sin_corte"]
    assert chat.mensajes()[-1]["text"] == "Dejame ver  y esto sigue"


def test_en_suscripcion_una_marca_abierta_al_final_no_se_vuelca(chat, cli_falso):
    """Seccion 11 en one-shot: el texto del CLI pasa por el mismo Emisor, asi
    que una marca abierta al final se descarta con aviso y no se vuelca."""
    cli_falso.guion([{"partes": ["termino asi ⟦abismo:chats sin cie"], "pausa": 0}])
    eventos = chat.turno("/claude hola")
    assert texto_visible(eventos) == "termino asi "
    assert de_tipo(eventos, "abismo") == [] and len(cli_falso.llamadas()) == 1
    assert [f["clase"] for f in chat.telemetria("abismo")] == ["abierta"]


def test_los_archivos_temporales_de_las_dos_invocaciones_se_borran(chat, cli_falso, monkeypatch):
    """El bloque pescado viaja a la reinvocacion en el archivo del system
    (`--append-system-prompt-file`, un `.md` en el tmpdir del sistema), no en
    el `.prompt.md` de ROOT (que solo existe con prompts de mas de 7000
    chars): `_cleanup_subscription_files` los borra en el finally, en las
    DOS invocaciones. Es un sumidero del bloque; el smoke lo re-mira."""
    creados = []
    real = srv.tempfile.NamedTemporaryFile

    def espia(*a, **k):
        f = real(*a, **k)
        creados.append(f.name)
        return f
    monkeypatch.setattr(srv.tempfile, "NamedTemporaryFile", espia)
    _sembrar_chat_viejo(["un libro"])
    cli_falso.guion([{"partes": ["a ⟦abismo:chats libro⟧"], "pausa": 0},
                     {"partes": ["b"], "pausa": 0}])
    chat.turno("/claude libro")
    sistemas = [n for n in creados if n.endswith(".md")]
    assert len(sistemas) == 2, creados            # un archivo de system por invocacion
    assert not any(pathlib.Path(n).exists() for n in creados)


def test_el_agente_de_equipo_no_publica_la_marca_del_abismo_al_pulso(monkeypatch):
    """La ruta orquestador queda FUERA (spec seccion 4): la marca que emita un
    agente se retira via _retirar_con_aviso + _limpiar_marcas y se ignora
    CON aviso (fila en telemetry). El molde de test_mapa_foco.py:139-176,
    con la marca del abismo."""
    pu = p.Pulso()
    monkeypatch.setattr(srv, "EL_PULSO", pu)
    monkeypatch.setattr(srv, "_plan_dynamic_team", lambda *a, **k: {"plan": 1})
    monkeypatch.setattr(srv, "_backend_availability", lambda *a, **k: {})
    monkeypatch.setattr(srv.sessions, "active", lambda *a, **k: None)
    monkeypatch.setattr(srv.orchestrator, "build_team", lambda *a, **k: {
        "agents": [{"role": "scout", "task": "mira", "model": "sonnet",
                    "persona": "explorador", "route": "api"}],
        "synthesis": ""})
    monkeypatch.setattr(srv.orchestrator, "agent_system", lambda *a, **k: "s")
    monkeypatch.setattr(srv.orchestrator, "synthesis_prompt", lambda *a, **k: "u")
    filas = []
    monkeypatch.setattr(srv.telemetry, "log_event",
                        lambda kind, **k: filas.append({"kind": kind, **k}))
    monkeypatch.setattr(srv, "_run_backend_text", lambda *a, **k: "listo")

    async def _agente(ws, inbox, agent, system, task):
        return "vamos a ⟦abismo:chats x⟧ mirar", None
    monkeypatch.setattr(srv, "_run_agent_text", _agente)

    class WSFalso:
        def __init__(self):
            self.enviados = []

        async def send_json(self, dato):
            self.enviados.append(dato)

    final, _, _ = asyncio.run(srv._run_dynamic_team(
        WSFalso(), asyncio.Queue(), "hace algo", {}, "base",
        {"route": "api", "client": None, "model": "m"}, departamento="dep:atlas"))
    assert final == "listo"
    razonado = "".join(e.get("texto", "") for e in pu.desde(0)[1] if e["evento"] == "razonando")
    assert razonado == "vamos a  mirar" and "⟦" not in razonado
    # "se ignoran CON aviso": una fila por retiro, con la cantidad
    retiradas = [f for f in filas if f["kind"] == "abismo" and f.get("evento") == "retirada"]
    assert [(f["clase"], f["cantidad"]) for f in retiradas] == [("agente", 1)]
