#!/usr/bin/env python3
"""
test_proposals.py - propuestas aplicadas como jobs/evidencia.
"""
import importlib
import os
import tempfile

_HOME = tempfile.mkdtemp(prefix="calipso_proposals_home_")
_ROOT = tempfile.mkdtemp(prefix="calipso_proposals_root_")
os.environ["CALIPSO_HOME"] = _HOME
os.environ["CALIPSO_ROOT"] = _ROOT

from fastapi.testclient import TestClient  # noqa: E402
from calipso import goals, jobs  # noqa: E402

server = importlib.import_module("calipso.server")  # noqa: E402


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' ' + extra) if extra else ''}")
        if not cond:
            fails.append(name)

    client = TestClient(server.app)
    client.cookies.set(server.COOKIE, server.TOKEN)

    goal = goals.create(_ROOT, "probar aplicacion de propuestas")
    proposed = client.post("/api/proposals", json={
        "path": "nota.txt",
        "content": "hola laboratorio\n",
        "source": "test",
    })
    check("crea propuesta", proposed.status_code == 200)
    change_id = proposed.json()["id"]
    applied = client.post(f"/api/proposals/{change_id}/apply")
    data = applied.json()
    check("aplica propuesta", applied.status_code == 200 and data["ok"])
    check("archivo escrito", os.path.exists(os.path.join(_ROOT, "nota.txt")))
    job = data.get("job")
    check("job propuesta", job and job["kind"] == "proposal_apply" and job["status"] == "done")
    arts = jobs.artifacts(_ROOT, job["id"]) if job else []
    check("artifacts diff/contenido", {"proposal.diff", "applied-content.txt"}.issubset({a["name"] for a in arts}))
    updated = goals.load(_ROOT, goal["id"])
    check("evidencia en meta", updated and updated["evidence"][-1]["kind"] == "proposal")

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: propuestas aplicadas con evidencia")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
