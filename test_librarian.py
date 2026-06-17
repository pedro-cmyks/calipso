#!/usr/bin/env python3
"""
test_librarian.py - inbox de memoria y bibliotecario activo.
"""
import importlib
import os
import pathlib
import tempfile

_HOME = tempfile.mkdtemp(prefix="calipso_librarian_home_")
_ROOT = tempfile.mkdtemp(prefix="calipso_librarian_root_")
os.environ["CALIPSO_HOME"] = _HOME
os.environ["CALIPSO_ROOT"] = _ROOT

from fastapi.testclient import TestClient  # noqa: E402
from calipso import chronology  # noqa: E402
from calipso import librarian  # noqa: E402

server = importlib.import_module("calipso.server")  # noqa: E402


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' ' + extra) if extra else ''}")
        if not cond:
            fails.append(name)

    proposal = librarian.propose(
        _ROOT, "Calipso debe proponer memoria antes de promoverla",
        scope="project", target="aprendido", rationale="test")
    check("crea propuesta", proposal["status"] == "pending")
    updated = librarian.update(_ROOT, proposal["id"], text="Calipso usa inbox de memoria")
    check("edita propuesta", updated and updated["text"] == "Calipso usa inbox de memoria")
    accepted = librarian.accept(_ROOT, proposal["id"])
    core = pathlib.Path(_ROOT) / ".calipso" / "core" / "aprendido.md"
    check("acepta propuesta", accepted and accepted["status"] == "accepted")
    check("promueve a core", core.exists() and "Calipso usa inbox" in core.read_text(encoding="utf-8"))
    discarded = librarian.propose(_ROOT, "ruido temporal", scope="project")
    discarded = librarian.discard(_ROOT, discarded["id"], "ruido")
    check("descarta propuesta", discarded and discarded["status"] == "discarded")
    check("log eventos", {e["action"] for e in librarian.events(_ROOT)} >= {"proposed", "accepted", "discarded"})
    suggestions = librarian.suggest_from_text(
        _ROOT, "Recordar: Pedro prefiere avances con pruebas visibles")
    check("sugiere desde texto", suggestions and suggestions[0]["scope"] == "global")

    client = TestClient(server.app)
    client.cookies.set(server.COOKIE, server.TOKEN)
    made = client.post("/api/memory/inbox/proposals", json={
        "text": "Este proyecto usa bibliotecario activo",
        "scope": "project",
        "target": "aprendido",
    })
    check("endpoint propone", made.status_code == 200)
    pid = made.json()["proposal"]["id"]
    listed = client.get("/api/memory/inbox").json()
    check("endpoint lista", any(p["id"] == pid for p in listed["proposals"]))
    edited = client.put(f"/api/memory/inbox/proposals/{pid}", json={
        "text": "Este proyecto tiene inbox de memoria",
    })
    check("endpoint edita", edited.status_code == 200 and "inbox" in edited.json()["proposal"]["text"])
    accepted_api = client.post(f"/api/memory/inbox/proposals/{pid}/accept")
    check("endpoint acepta", accepted_api.status_code == 200 and accepted_api.json()["proposal"]["status"] == "accepted")
    core_view = client.get("/api/memory/core")
    check("endpoint core", core_view.status_code == 200 and "global" in core_view.json())
    chronology_view = client.get("/api/memory/chronology")
    check("endpoint cronologia", (
        chronology_view.status_code == 200
        and chronology_view.json()["chronology"]["stem"] == chronology.FILENAME))
    chronology_proposal = client.post("/api/memory/chronology/proposals", json={
        "text": "Pedro esta validando memoria cronologica",
        "topic": "Calipso",
        "date": "2026-06-16",
    })
    chrono_json = chronology_proposal.json()
    check("propone cronologia", (
        chronology_proposal.status_code == 200
        and chrono_json["proposal"]["scope"] == "global"
        and chrono_json["proposal"]["target"] == chronology.FILENAME
        and "2026-06-16 | Calipso" in chrono_json["proposal"]["text"]))

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: bibliotecario activo funcionando")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
