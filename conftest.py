"""conftest raiz — el ~/.calipso real de Pedro queda fuera de la suite.

Varios modulos congelan `CALIPSO_HOME` en una constante AL IMPORTARSE
(`librarian.py`, `memory.py`, `chats.py`, `sessions.py`, `jobs.py`,
`backup.py`, `server.py`), y `memory.Scope.__init__` hace `mkdir` y abre un
`chromadb.PersistentClient` en cuanto se construye. O sea que un simple
`import calipso.server` —lo que hace, entre otros, test_economia_server.py—
ya escribe en el home REAL: `global/chroma/`, `global/core/*.md`,
`projects/<slug>/chroma/`. Verificado: el md5 del arbol de ~/.calipso
cambiaba al correr la suite.

La aislacion archivo por archivo (`os.environ["CALIPSO_HOME"] = ...` arriba
de cada test) no alcanza por dos razones: no la tienen todos los archivos, y
el primero que importe el modulo gana — en una corrida completa,
test_economia_server.py importa `calipso.server` antes de que
test_librarian.py fije su home, y a partir de ahi la constante ya quedo
ligada al home real y el fixture de los otros es un no-op.

Por eso se fija ACA: pytest importa el conftest de la raiz antes de
recolectar cualquier test, asi que la variable ya esta puesta cuando se
importa el primer modulo de calipso. Se pisa siempre, incluso si venia del
entorno: una variable exportada apuntando al home real convertiria la suite
en un `rm` lento sobre las notas de Pedro.

Es red de seguridad, no permiso para escribir en el home: cada test sigue
debiendo usar `tmp_path`. Lo que esto garantiza es que un descuido cueste un
directorio temporal y no la memoria del asistente.

HASTA DONDE LLEGA, dicho con precision porque el agujero se pisa solo:
pytest importa este archivo solo cuando el test que recolecta esta DEBAJO de
este directorio. Un archivo de prueba en /tmp que importe `calipso.*` -aunque
lo lance este mismo interprete- no lo carga, y entonces `memory.Scope` abre
chroma sobre el ~/.calipso REAL. Lo mismo un `python -c "import
calipso.server"` suelto. Medido: `pytest /tmp/sonda.py` desde afuera deja
`CALIPSO_HOME` sin fijar. No hay forma de cubrirlo desde aca -no hay gancho
que corra antes de un import que no pasa por pytest-, asi que la regla para
cualquier script fuera del arbol es exportar `CALIPSO_HOME` a mano. Lo que si
se cerro fueron los caminos del paquete que ignoraban la variable aun estando
puesta: `server._TOKEN_FILE` y `server._TOTP_SECRET_FILE` (ver
`_home_calipso`), que ademas ESCRIBEN la primera vez.
"""
import os
import pathlib
import tempfile

_HOME_SUITE = pathlib.Path(tempfile.mkdtemp(prefix="calipso_suite_home_"))
os.environ["CALIPSO_HOME"] = str(_HOME_SUITE)
# El clon y la carpeta de trabajo de cada goal viven FUERA de ~/.calipso
# (goals.raiz_trabajo: ~/.local/share/calipso/goals por defecto, porque
# ~/.calipso es DENY_READ del sandbox y PROTEGIDA del hook). Misma red de
# seguridad: un temporal junto al home, para que ningun test siembre
# carpetas en el ~/.local/share real de Pedro.
_TRABAJO_SUITE = pathlib.Path(tempfile.mkdtemp(prefix="calipso_suite_trabajo_"))
os.environ["CALIPSO_GOALS_TRABAJO"] = str(_TRABAJO_SUITE)
# La memoria embebe por Ollama (spec 2026-09-12, ruling 8.10): en la suite
# NADIE llama a Ollama. Con esta variable `memory.Memory()` construye
# `memoria_embed.EmbedFalsa` (hash determinista, 1024 dims, sin red), y tiene
# que estar puesta ANTES del primer import de calipso por la misma razon que
# CALIPSO_HOME: varios tests importan `calipso.server` a nivel de modulo y
# eso construye `Memory()` en el acto. Se pisa siempre: un `0` exportado en
# la shell convertiria la suite en 200 POSTs a Ollama.
os.environ["CALIPSO_EMBED_FALSA"] = "1"


def home_de_la_suite() -> pathlib.Path:
    """El CALIPSO_HOME desechable de esta corrida (para los tests que lo miran)."""
    return _HOME_SUITE
