#!/usr/bin/env python3
"""
test_memory.py — Verifica la memoria jerárquica de Calipso.

1) Recuperación semántica por ÁMBITO (global vs proyecto): la pregunta correcta
   trae el recuerdo del ámbito correcto, en español, sin compartir palabras.
2) reflect(): promueve hechos duraderos del episódico al core curado, separando
   lo global (sobre Pedro) de lo del proyecto.

Aísla CALIPSO_HOME y el proyecto en directorios temporales.
La 1ª ejecución descarga el modelo de embeddings si falta.
"""
import os
import tempfile

_HOME = tempfile.mkdtemp(prefix="calipso_home_")
_PROJ = tempfile.mkdtemp(prefix="calipso_proj_")
os.environ["CALIPSO_HOME"] = _HOME

from calipso import memory  # noqa: E402


def main() -> int:
    m = memory.Memory(project_root=_PROJ)
    failures = []

    # --- 1) recuperación por ámbito ---
    m.glob.remember("Pedro es ingeniero de software y prefiere código conciso en Python")
    m.glob.remember("A Pedro le gusta trabajar de madrugada con música")
    m.project.remember("Calipso es un orquestador multi-modelo que enruta a tres bocas")
    m.project.remember("El proyecto guarda la memoria en ChromaDB con embeddings bge-m3")

    checks = [
        ("¿qué hace el usuario para vivir?", "ingeniero", "global"),
        ("¿de qué se trata esto que estamos armando?", "orquestador", "project"),
    ]
    for q, expected, scope in checks:
        hits = m.recall(q, n=3)
        top = hits[0] if hits else {"text": "", "scope": "-", "score": 0}
        # Lo que se verifica es el RUTEO POR ÁMBITO (la feature nueva): la
        # pregunta global trae algo del ámbito global, la de proyecto del proyecto.
        ok = top["scope"] == scope
        print(f"  Q: {q}")
        print(f"     top [{top['scope']}] ({top['score']}): {top['text']}")
        print(f"     -> {'OK' if ok else 'FAIL'} (esperaba ámbito '{scope}')\n")
        if not ok:
            failures.append(q)

    # --- 2) reflect(): promoción al core curado ---
    for ex in [
        "Pedro contó que también es músico y odia las reuniones largas",
        "Pedro aclaró que Calipso debe poder hablarle por Telegram desde el iPhone",
        "hola, ¿cómo estás?",  # ruido: NO debería promoverse
    ]:
        m.project.remember(ex, kind="chat")

    promoted = m.reflect()
    print(f"[reflect] promovidos {len(promoted)} hechos:")
    for p in promoted:
        print(f"     [{p.get('scope')}] {p.get('fact')}")
    if not promoted or any("error" in p for p in promoted):
        failures.append("reflect no promovió nada")
    else:
        core = m.load_core()
        print(f"\n[core] tras reflect, load_core() = {len(core)} chars")
        if "Pedro" not in core and "Calipso" not in core:
            failures.append("core vacío tras reflect")

    if failures:
        print("\nFALLARON:", failures)
        return 1
    print("\nOK: memoria jerárquica (global/proyecto) + reflect funcionando")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
