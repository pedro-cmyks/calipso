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
"""
import os
import pathlib
import tempfile

_HOME_SUITE = pathlib.Path(tempfile.mkdtemp(prefix="calipso_suite_home_"))
os.environ["CALIPSO_HOME"] = str(_HOME_SUITE)


def home_de_la_suite() -> pathlib.Path:
    """El CALIPSO_HOME desechable de esta corrida (para los tests que lo miran)."""
    return _HOME_SUITE
