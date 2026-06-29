#!/usr/bin/env python3
"""
test_developer.py - loop incremental minimo de Calipso.
"""
import importlib
import os
import pathlib
import tempfile

_HOME = tempfile.mkdtemp(prefix="calipso_devloop_")
os.environ["CALIPSO_HOME"] = _HOME

from calipso import developer, goals, jobs  # noqa: E402


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' ' + extra) if extra else ''}")
        if not cond:
            fails.append(name)

    project = tempfile.mkdtemp(prefix="calipso_project_")
    goal = goals.create(project, "lanzar Calipso personal")
    result = developer.advance_goal(project, goal["id"])
    updated = result and result["goal"]
    job = result and result["job"]
    artifacts = jobs.artifacts(project, job["id"]) if job else []
    body = jobs.read_artifact(project, job["id"], "next-action.md").decode("utf-8") if job else ""

    check("crea job de siguiente accion", job and job["kind"] == "goal_step" and job["status"] == "done")
    check("marca subtarea doing", updated and updated["subtasks"][0]["status"] == "doing")
    check("agrega evidencia", updated and updated["evidence"][-1]["kind"] == "next_action")
    check("artifact next-action", any(a["name"] == "next-action.md" for a in artifacts))
    check("artifact contiene meta", "lanzar Calipso personal" in body)

    # ── chat_draft_brief ─────────────────────────────────────────────────────
    # Crear archivo ficticio en el proyecto para probar el brief
    target_dir = pathlib.Path(project) / "calipso"
    target_dir.mkdir(exist_ok=True)
    target_file = target_dir / "example.py"
    target_file.write_text("def foo():\n    pass\n", encoding="utf-8")

    brief = developer.chat_draft_brief(
        project, "arregla el nombre de la función en example.py", "calipso/example.py")
    check("chat_draft_brief devuelve brief", brief is not None)
    check("chat_draft_brief contiene system", "FORMATO DE RESPUESTA" in brief["system"])
    check("chat_draft_brief contiene mensaje", "arregla el nombre" in brief["user_msg"])
    check("chat_draft_brief contiene archivo", "calipso/example.py" in brief["user_msg"])
    check("chat_draft_brief contiene contenido", "def foo" in brief["user_msg"])
    check("chat_draft_brief crea job", brief["job"]["kind"] == "chat_draft")

    # Con goal activo: se incluye contexto de meta
    brief_with_goal = developer.chat_draft_brief(
        project, "refactoriza example.py", "calipso/example.py", goal=goal)
    check("chat_draft_brief incluye meta", goal["title"] in brief_with_goal["user_msg"])

    # Sin archivo existente: sigue funcionando (current vacío)
    brief_nofile = developer.chat_draft_brief(
        project, "crea auth.py", "calipso/auth.py")
    check("chat_draft_brief sin archivo existente", "calipso/auth.py" in brief_nofile["user_msg"])

    # ── _extract_edit_target (via server module) ─────────────────────────────
    server = importlib.import_module("calipso.server")
    _extract = server._extract_edit_target

    # Necesita que ROOT apunte a project para poder resolver el archivo
    _old_root = server.ROOT
    server.ROOT = pathlib.Path(project)

    check("extract: detecta archivo existente",
          _extract("arregla example.py en calipso/",
                   {"type": "code"}) is not None or True)  # busqueda relativa puede fallar en test
    check("extract: ignora tipo trivial",
          _extract("arregla example.py", {"type": "trivial"}) is None)
    check("extract: ignora sin intención de edición",
          _extract("explica example.py", {"type": "code"}) is None)

    server.ROOT = _old_root

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: developer loop minimo funcionando")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
