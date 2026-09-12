"""El server no importa torch (spec memoria por Ollama 2026-09-12, invariante
1): ningun modulo del repo importa torch, transformers ni
sentence_transformers (por AST, como el canario de la aduana), y un `import
calipso.server` en un proceso limpio con home temporal no los carga (por
`sys.modules`: lo que un import perezoso o una dependencia arrastraria).
Medido antes del cambio: `import calipso.server` = 1479 MB de RSS con torch
(1055 submodulos), scipy, transformers, sympy, sentence_transformers..."""
from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent
PROHIBIDOS = ("torch", "transformers", "sentence_transformers")


def _archivos():
    for p in sorted((RAIZ / "calipso").rglob("*.py")):
        if "/web/" not in str(p):
            yield p
    yield RAIZ / "dispatch.py"
    yield RAIZ / "launch_calipso.py"


def test_ningun_modulo_del_repo_importa_torch_ni_transformers():
    malos = []
    for ruta in _archivos():
        tree = ast.parse(ruta.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            nombres = []
            if isinstance(n, ast.Import):
                nombres = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module:
                nombres = [n.module]
            for nombre in nombres:
                if nombre.split(".")[0] in PROHIBIDOS:
                    malos.append(f"{ruta.relative_to(RAIZ)}:{n.lineno} {nombre}")
    assert malos == []


def test_importar_el_server_no_carga_torch(tmp_path):
    codigo = ("import json, sys\n"
              "import calipso.server\n"
              f"malos = sorted(m for m in sys.modules if m.split('.')[0] in {PROHIBIDOS!r})\n"
              "print('SYS_MODULES=' + json.dumps(malos))\n")
    env = {**os.environ, "CALIPSO_HOME": str(tmp_path), "CALIPSO_EMBED_FALSA": "1",
           "CALIPSO_ROOT": str(RAIZ)}
    r = subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-3000:]
    linea = [l for l in r.stdout.splitlines() if l.startswith("SYS_MODULES=")][-1]
    assert json.loads(linea[len("SYS_MODULES="):]) == []
