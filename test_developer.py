#!/usr/bin/env python3
"""
test_developer.py - loop incremental minimo de Calipso.
"""
import os
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

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: developer loop minimo funcionando")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
