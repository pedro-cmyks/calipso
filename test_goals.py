#!/usr/bin/env python3
"""
test_goals.py - Goal Mode persistente minimo.
"""
import os
import tempfile

_HOME = tempfile.mkdtemp(prefix="calipso_goals_")
os.environ["CALIPSO_HOME"] = _HOME

from calipso import goals  # noqa: E402


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' ' + extra) if extra else ''}")
        if not cond:
            fails.append(name)

    project = tempfile.mkdtemp(prefix="calipso_project_")
    detected = goals.detect("meta: dejame Calipso listo para usarlo desde el iPhone.")
    check("detecta meta natural", detected == "dejame Calipso listo para usarlo desde el iPhone")

    goal = goals.create(project, detected)
    check("crea meta activa", goal["id"].startswith("goal_") and goal["status"] == "active")
    check("criterios propuestos", len(goal["criteria"]) >= 3 and "dispositivo" in goal["criteria"][0]["text"].lower())
    check("subtareas propuestas", len(goal["subtasks"]) >= 3)

    active = goals.active(project)
    listed = goals.list_goals(project)
    check("recupera activa", active and active["id"] == goal["id"])
    check("lista metas", listed and listed[0]["id"] == goal["id"])

    goals.add_evidence(project, goal["id"], "job", "Proceso terminado", job_id="job_demo")
    goals.set_criterion(project, goal["id"], "c1", True, "Abre en smoke visual")
    goals.set_subtask(project, goal["id"], "t1", "done")
    updated = goals.load(project, goal["id"])
    evs = goals.events(project, goal["id"])
    check("evidencia persistida", updated and any(e.get("job_id") == "job_demo" for e in updated["evidence"]))
    check("criterio marcado", updated and updated["criteria"][0]["done"] is True)
    check("subtarea marcada", updated and updated["subtasks"][0]["status"] == "done")
    check("eventos persistidos", evs and evs[-1]["action"] == "subtask")

    goals.update(project, goal["id"], status="blocked", blocker="falta Tailscale")
    blocked = goals.active(project)
    check("bloqueo mantiene activa", blocked and blocked["status"] == "blocked")

    goals.update(project, goal["id"], status="complete")
    check("complete limpia activa", goals.active(project) is None)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: Goal Mode persistente funcionando")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
