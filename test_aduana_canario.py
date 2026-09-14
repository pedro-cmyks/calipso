"""El canario de la aduana (spec seccion 8, regla invertida): TODA llamada de
red y TODO subprocess del arbol se marca por AST, sin mirar argv ni host (por
AST son indecidibles), y un hallazgo se salva solo si (a) la funcion que lo
contiene -o un closure anidado, o una funcion que la envuelve- tiene un Call
a `aduana.cruzar` / `aduana.declarar` / `aduana.declarar_una_vez`, o (b)
`archivo:funcion` esta en EXCEPCIONES con motivo, una por linea, para que
sumar una sea un diff visible. Una excepcion `helper: <archivo:funcion>`
exige que ESE llamador tenga el Call.

Se marca tanto el Call directo (`subprocess.run(cmd)`) como la salida pasada
por referencia, sin llamarla, en un argumento o keyword de otro Call
(`asyncio.to_thread(subprocess.run, cmd)`, `loop.run_in_executor(None,
urlopen, url)`, `functools.partial(subprocess.run, ...)`): es el idioma que
empuja la invariante 8 (nunca en el loop) y sin esto seria un escape.

Limite honesto: no ve lo que sale desde adentro de una libreria (chromadb,
sentence_transformers, el SDK de Anthropic) ni `page.goto` de Chromium. Para
eso estan `declarar` y la tabla de la seccion 7 del spec. Tampoco resuelve un
rebinding a variable (`run = subprocess.run; run(cmd)`) ni las formas fuera
de la lista del spec (`os.system`, `asyncio.create_subprocess_*`,
`http.client`, `socket.socket()`); hoy ninguna existe en el arbol (sondeado
por grep el 2026-09-10) y si aparece una, se suma a la regla, no a
EXCEPCIONES.
"""
from __future__ import annotations

import ast
import pathlib
import textwrap

RAIZ = pathlib.Path(__file__).resolve().parent

# archivo:funcion -> motivo. `helper: archivo:funcion` nombra al llamador que
# lleva el Call (se verifica). Archivo relativo a la raiz del repo; funcion
# anidada como `externa:interna`; nivel de modulo como `<modulo>`.
EXCEPCIONES: dict[str, str] = {
    # --- modelos: la aduana no conoce a los modelos (invariante 7) ---
    "calipso/server.py:_run_subscription_text": "modelo: CLI de suscripcion, lo mide la telemetria y la economia",
    "calipso/server.py:_run_subscription_text_live": "modelo: CLI de suscripcion en vivo, idem",
    "calipso/goals_manos.py:_correr_cabeza": "modelo: la cabeza sin herramientas del goal (la propuesta y el revisor; claude -p --restricted --tools '' / codex exec -s read-only): CLI de suscripcion, lo mide el ledger del goal (golpes.jsonl) y la economia",
    "calipso/plugins.py:install": "modelo: `claude -p` para instalar un plugin; CLI agente",
    "dispatch.py:run_subscription": "modelo: el CLI suelto de dispatch.py no mide",
    "dispatch.py:_http_post_json": "modelo: LiteLLM/Ollama por config; base_url no loopback se DECLARA al cargar la config",
    "dispatch.py:_http_post_stream": "modelo: idem, stream",
    # --- loopback por config, por default o por construccion ---
    "calipso/server.py:_http_up": "loopback: salud de Ollama/LiteLLM, corre en el LOOP",
    "calipso/discovery.py:_get_json": "loopback por default: el llamador de produccion (`discover`) llama a discover_ollama/discover_litellm con el `base` por defecto (localhost); un llamador con otro `base` no cruza: limite conocido (el modelo fuera de la maquina lo cubre el declarado del arranque). `_npm_latest` no pasa por aca (tiene su propio urlopen con el Call)",
    "calipso/discovery.py:_cli_version": "local: `<cli> --version`, sin red",
    "calipso/carga.py:_ollama_get": "loopback: Ollama (/api/ps del sensor de la carga, 0,5 s)",
    "calipso/carga.py:ollama_evict": "loopback: Ollama (keep_alive 0 del vigia)",
    "calipso/memoria_embed.py:_post_embed": "loopback: Ollama (/api/embed del embedder de la memoria, bge-m3; spec memoria por Ollama 2026-09-12). La memoria ya no sale a huggingface.co",
    "calipso/attachments.py:_vision_ollama": "loopback: Ollama en localhost:11434",
    "launch_calipso.py:_port_open": "loopback: el lanzador espera al propio server",
    "launch_calipso.py:_wait_ready": "loopback: idem",
    "launch_calipso.py:main": "local: lanza uvicorn/el navegador, no sale a internet",
    "calipso/memoria_reindex.py:_server_prendido": "loopback: el reindex (acto de Pedro, fuera del server) pregunta si el server escucha en CALIPSO_PORT antes de recorrer el chroma; no sale de la maquina",
    # --- git local ---
    "calipso/catastro.py:_git": "git local: rev-parse/log/status sobre el catastro",
    "calipso/server.py:_git": "git local: /api/git/* sobre ROOT",
    "calipso/github.py:git_local": "git local: el clon del goal (clone de una ruta, checkout -b, diff --stat, fetch de una ruta local; spec goals 2026-09-13, ruling 15.4). Sin remoto: nunca sale de la maquina",
    "calipso/tools/commands.py:run": "subprocesos de la allowlist: git local y tests; `test_memory` habla con Ollama en loopback desde OTRO proceso (test_memory.py construye Memory() -> POST /api/embed) y llama reflect -> `claude -p`, fuera de la aduana: limite conocido, como los CLIs agentes",
    # --- muertos en Linux ---
    "calipso/server.py:api_connector_action": "muerto en Linux: Popen con CREATE_NEW_CONSOLE (solo Windows); cuando se arregle cruza como gesto",
    "calipso/server.py:api_subscription_install": "muerto en Linux: idem",
    "calipso/server.py:api_subscription_login": "muerto en Linux: idem",
    # --- probes declarados en otro lugar ---
    "calipso/server.py:_subscription_probe": "helper: calipso/server.py:_calentar_probes -- se alcanza desde el loop via _harness_context; el declarado vive en el arranque",
}

_RED = {"urlopen", "urlretrieve"}
_SUBPROCESS = {"run", "Popen", "check_output", "check_call", "call"}
_MODULOS_RED = {"requests", "httpx", "aiohttp"}
_ADUANA = ("aduana.cruzar", "aduana.declarar", "aduana.declarar_una_vez")


def _archivos() -> list[pathlib.Path]:
    return (sorted(p for p in RAIZ.glob("calipso/**/*.py") if "/web/" not in str(p))
            + [RAIZ / "dispatch.py", RAIZ / "launch_calipso.py"])


def _alias(tree: ast.AST) -> dict[str, str]:
    """nombre local -> nombre canonico. `import urllib.request as _ur` ->
    {_ur: urllib.request}; `from calipso import aduana` -> {aduana:
    calipso.aduana}; `import subprocess` -> {subprocess: subprocess}."""
    al: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.asname:
                    al[a.asname] = a.name
                else:
                    raiz = a.name.split(".")[0]
                    al[raiz] = raiz
        elif isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                al[a.asname or a.name] = f"{n.module}.{a.name}"
    return al


def _canon(func: ast.AST, al: dict[str, str]) -> str | None:
    partes: list[str] = []
    while isinstance(func, ast.Attribute):
        partes.append(func.attr)
        func = func.value
    if not isinstance(func, ast.Name):
        return None
    partes.append(al.get(func.id, func.id))
    return ".".join(reversed(partes))


def _es_salida(canon: str | None) -> bool:
    if not canon:
        return False
    ultimo = canon.rsplit(".", 1)[-1]
    if ultimo in _RED and canon.startswith("urllib"):
        return True
    if canon == "socket.create_connection":
        return True
    if canon.startswith("subprocess.") and ultimo in _SUBPROCESS:
        return True
    if canon.split(".")[0] in _MODULOS_RED:
        return True
    return canon == "websockets.connect"


def _tiene_aduana(nodo: ast.AST, al: dict[str, str]) -> bool:
    for n in ast.walk(nodo):
        if isinstance(n, ast.Call):
            c = _canon(n.func, al)
            if c and c.endswith(_ADUANA):
                return True
    return False


def _funciones(tree: ast.AST) -> dict[str, ast.AST]:
    """`externa:interna` -> nodo, para verificar los `helper:`."""
    out: dict[str, ast.AST] = {}

    def visitar(n, pila):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pila = pila + [n.name]
            out[":".join(pila)] = n
        for h in ast.iter_child_nodes(n):
            visitar(h, pila)
    visitar(tree, [])
    return out


def hallazgos_de(ruta: pathlib.Path, raiz: pathlib.Path = RAIZ) -> list[dict]:
    """Toda salida sin aduana en `ruta`: [{sitio, linea, llamada, salvado}]."""
    tree = ast.parse(ruta.read_text(encoding="utf-8"))
    al = _alias(tree)
    rel = str(ruta.relative_to(raiz)) if raiz in ruta.parents else ruta.name
    out: list[dict] = []

    def marcar(n: ast.Call, pila: list[ast.AST]) -> None:
        nombre = ":".join(f.name for f in pila) or "<modulo>"
        out.append({
            "sitio": f"{rel}:{nombre}", "linea": n.lineno,
            "llamada": ast.unparse(n)[:120],
            "salvado": any(_tiene_aduana(f, al) for f in pila)})

    def visitar(n, pila: list[ast.AST]):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pila = pila + [n]
        if isinstance(n, ast.Call):
            if _es_salida(_canon(n.func, al)):
                marcar(n, pila)
            else:
                # la salida pasada por referencia, sin llamarla:
                # `to_thread(subprocess.run, cmd)`, `partial(urlopen, url)`,
                # `algo(runner=subprocess.run)`. Se marca el Call que la recibe.
                pasados = list(n.args) + [k.value for k in n.keywords]
                if any(isinstance(a, (ast.Name, ast.Attribute))
                       and _es_salida(_canon(a, al)) for a in pasados):
                    marcar(n, pila)
        for h in ast.iter_child_nodes(n):
            visitar(h, pila)
    visitar(tree, [])
    return out


def _sin_aduana(archivos, excepciones: dict[str, str], raiz=RAIZ) -> list[str]:
    """Las lineas que la suite reporta: `archivo:linea  funcion  llamada`."""
    por_archivo = {}
    fallas: list[str] = []
    for ruta in archivos:
        tree = ast.parse(ruta.read_text(encoding="utf-8"))
        por_archivo[ruta] = (tree, _alias(tree), _funciones(tree))
    for ruta in archivos:
        for h in hallazgos_de(ruta, raiz):
            if h["salvado"]:
                continue
            motivo = excepciones.get(h["sitio"])
            if motivo is None:
                fallas.append(f"{h['sitio'].split(':')[0]}:{h['linea']}  "
                              f"{h['sitio'].split(':', 1)[1]}  {h['llamada']}")
                continue
            if motivo.startswith("helper:"):
                llamador = motivo[len("helper:"):].split("--")[0].strip()
                arch, _, func = llamador.partition(":")
                tree_l = next(((t, a, fs) for r, (t, a, fs) in por_archivo.items()
                               if str(r.relative_to(raiz)) == arch), None)
                if tree_l is None or func not in tree_l[2] \
                        or not _tiene_aduana(tree_l[2][func], tree_l[1]):
                    fallas.append(f"{h['sitio']}: la excepcion dice que el cruce "
                                  f"esta en {llamador}, y ahi no hay Call a la aduana")
    return list(dict.fromkeys(fallas))      # sin repetir (tres calls, un aviso)


def _excepciones_viejas(hallazgos: list[dict], excepciones: dict[str, str]) -> list[str]:
    """Las excepciones que sobran (decision 13): las huerfanas (ningun hallazgo
    con ese sitio) y las que cubren un sitio que YA tiene el Call a la aduana
    (un `pendiente:` que sobrevivio a su task). Una `helper:` no sobra por eso:
    el cruce que declara vive en el llamador, no en el sitio."""
    sitios = {h["sitio"] for h in hallazgos}
    salvados = {h["sitio"] for h in hallazgos if h["salvado"]}
    viejas = [f"{s}  sin sitio: ningun hallazgo matchea (borrarla)"
              for s in sorted(set(excepciones) - sitios)]
    viejas += [f"{s}  ya cruza: el sitio tiene el Call a la aduana (borrarla)"
               for s in sorted(set(excepciones) & salvados)
               if not excepciones[s].startswith("helper:")]
    return viejas


def test_toda_salida_del_proceso_cruza_o_se_declara():
    fallas = _sin_aduana(_archivos(), EXCEPCIONES)
    assert not fallas, "salidas sin aduana:\n" + "\n".join(fallas)


def test_las_excepciones_apuntan_a_sitios_que_existen_y_que_no_cruzan_ya():
    """Una excepcion que ya no matchea nada es vieja: se borra. Y una sobre
    un sitio que YA tiene el Call a la aduana tambien sobra (un `pendiente`
    que sobrevivio a su task): se borra, para que sumar o dejar una
    excepcion sea siempre un diff visible y nunca un verde por inercia
    (decision 13: sin este guardia, la lista de pendientes deja el canario
    verde sobre main sin un solo enchufe)."""
    hallazgos = [h for ruta in _archivos() for h in hallazgos_de(ruta)]
    viejas = _excepciones_viejas(hallazgos, EXCEPCIONES)
    assert not viejas, "excepciones viejas (borrarlas):\n" + "\n".join(viejas)


# --- controles positivos ------------------------------------------------------

def _archivo(tmp_path, nombre, codigo) -> pathlib.Path:
    p = tmp_path / nombre
    p.write_text(textwrap.dedent(codigo), encoding="utf-8")
    return p


def test_control_positivo_urlopen_sin_aduana(tmp_path):
    p = _archivo(tmp_path, "suelto.py", """
        import urllib.request as _ur
        def traer(url):
            with _ur.urlopen(url) as r:
                return r.read()
    """)
    fallas = _sin_aduana([p], {}, raiz=tmp_path)
    assert fallas and "suelto.py:4" in fallas[0] and "traer" in fallas[0]


def test_control_positivo_subprocess_con_cmd_variable(tmp_path):
    p = _archivo(tmp_path, "suelto.py", """
        import subprocess
        def correr(cmd):
            return subprocess.run(cmd, capture_output=True)
    """)
    fallas = _sin_aduana([p], {}, raiz=tmp_path)
    assert fallas and "suelto.py:4" in fallas[0]


def test_un_cruce_en_la_funcion_o_en_el_closure_salva(tmp_path):
    p = _archivo(tmp_path, "con_aduana.py", """
        import subprocess
        import urllib.request
        from calipso import aduana
        def runner(quien):
            def run(args):
                with aduana.cruzar(quien, "gh", "api.github.com", carga=args):
                    return subprocess.run(args)
            return run
        def traer(url, quien):
            with aduana.cruzar(quien, "leer", url, carga=url) as c:
                with urllib.request.urlopen(url) as r:
                    return r.read()
    """)
    assert _sin_aduana([p], {}, raiz=tmp_path) == []


def test_una_excepcion_helper_exige_el_call_en_el_llamador(tmp_path):
    p = _archivo(tmp_path, "helper.py", """
        import subprocess
        from calipso import aduana
        def probe():
            return subprocess.run(["x", "--version"])
        def calentar(quien):
            aduana.declarar(quien, "probes", None)
            return probe()
        def sin_nada():
            return probe()
    """)
    assert _sin_aduana([p], {"helper.py:probe": "helper: helper.py:calentar"},
                       raiz=tmp_path) == []
    fallas = _sin_aduana([p], {"helper.py:probe": "helper: helper.py:sin_nada"},
                         raiz=tmp_path)
    assert fallas and "no hay Call" in fallas[0]


def test_el_alias_local_de_urllib_se_resuelve(tmp_path):
    """`import urllib.request as _ur` (attachments.py:290) no puede
    esconder un urlopen."""
    p = _archivo(tmp_path, "alias.py", """
        def f(req):
            import urllib.request as _ur, json as _j
            with _ur.urlopen(req, timeout=60) as r:
                return _j.loads(r.read())
    """)
    assert len(_sin_aduana([p], {}, raiz=tmp_path)) == 1


def test_control_positivo_referencia_pasada_a_to_thread(tmp_path):
    """La salida pasada como referencia, sin llamarla (`to_thread(subprocess.run,
    cmd)`, `run_in_executor(None, urlopen, url)`, un keyword), es el idioma que
    empuja la invariante 8 (nunca en el loop): se marca igual que el Call."""
    p = _archivo(tmp_path, "suelto.py", """
        import asyncio
        import subprocess
        import urllib.request
        async def correr(cmd):
            return await asyncio.to_thread(subprocess.run, cmd, capture_output=True)
        async def traer(loop, url):
            return await loop.run_in_executor(None, urllib.request.urlopen, url)
        def con_runner(cmd):
            return _ejecutar(cmd, runner=subprocess.run)
    """)
    fallas = _sin_aduana([p], {}, raiz=tmp_path)
    assert len(fallas) == 3, fallas
    assert "suelto.py:6" in fallas[0] and "correr" in fallas[0] and "subprocess.run" in fallas[0]
    assert "suelto.py:8" in fallas[1] and "traer" in fallas[1] and "urlopen" in fallas[1]
    assert "suelto.py:10" in fallas[2] and "con_runner" in fallas[2]


def test_una_referencia_pasada_tambien_se_salva_con_el_cruce(tmp_path):
    p = _archivo(tmp_path, "con_aduana.py", """
        import asyncio
        import subprocess
        from calipso import aduana
        async def correr(quien, cmd):
            with aduana.cruzar(quien, "gh", "api.github.com", carga=cmd):
                return await asyncio.to_thread(subprocess.run, cmd)
    """)
    assert _sin_aduana([p], {}, raiz=tmp_path) == []


# --- controles positivos del guardia de la decision 13 -------------------------

def test_una_excepcion_sin_sitio_es_huerfana(tmp_path):
    p = _archivo(tmp_path, "x.py", """
        import subprocess
        def algo(cmd):
            return subprocess.run(cmd)
    """)
    viejas = _excepciones_viejas(hallazgos_de(p, raiz=tmp_path),
                                 {"x.py:nada": "pendiente: Task 9"})
    assert len(viejas) == 1 and "x.py:nada" in viejas[0] and "sin sitio" in viejas[0]


def test_una_excepcion_sobre_un_sitio_que_ya_cruza_sobra(tmp_path):
    """Un `pendiente:` que sobrevivio a su task: el sitio ya tiene el Call y la
    excepcion tiene que caer, para que el verde nunca sea por inercia."""
    p = _archivo(tmp_path, "x.py", """
        import subprocess
        from calipso import aduana
        def algo(quien, cmd):
            aduana.declarar(quien, "probes", None)
            return subprocess.run(cmd)
    """)
    hallazgos = hallazgos_de(p, raiz=tmp_path)
    viejas = _excepciones_viejas(hallazgos, {"x.py:algo": "pendiente: Task 9"})
    assert len(viejas) == 1 and "x.py:algo" in viejas[0] and "ya cruza" in viejas[0]
    # una `helper:` sobre ese sitio no sobra: el cruce que declara vive en el llamador
    assert _excepciones_viejas(hallazgos, {"x.py:algo": "helper: x.py:otro"}) == []


def test_no_quedan_pendientes():
    """Los `pendiente: Task N` fueron el andamio de las Tasks 2-6 (decision
    13): al cerrar la Task 6 no queda ninguno, y la lista es la de la
    seccion 8 del spec."""
    pendientes = sorted(s for s, m in EXCEPCIONES.items() if m.startswith("pendiente"))
    assert not pendientes, f"sitios que el spec exige enchufar y siguen exceptuados: {pendientes}"
