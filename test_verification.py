#!/usr/bin/env python3
"""
test_verification.py - recomendador y runner de verificacion fuerte.
"""
import importlib
import os
import tempfile

_HOME = tempfile.mkdtemp(prefix="calipso_verification_home_")
os.environ["CALIPSO_HOME"] = _HOME
os.environ["CALIPSO_ROOT"] = os.getcwd()

from fastapi.testclient import TestClient  # noqa: E402
from calipso import goals, jobs, verification  # noqa: E402

server = importlib.import_module("calipso.server")  # noqa: E402


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' ' + extra) if extra else ''}")
        if not cond:
            fails.append(name)

    files = [
        {"path": "calipso/web/index.html", "status": "M"},
        {"path": "SPEC.md", "status": "M"},
        {"path": "calipso/attachments.py", "status": "M"},
    ]
    plan = verification.recommend(files, [])
    ids = [c["command_id"] for c in plan["commands"]]
    check("recomienda UI", "ui_syntax" in ids)
    check("recomienda docs", "docs_check" in ids)
    check("recomienda adjuntos", "test_attachments" in ids)
    check("tipos clasificados", {"frontend", "docs", "attachments"}.issubset(set(plan["change_types"])))

    client = TestClient(server.app)
    client.cookies.set(server.COOKIE, server.TOKEN)
    goal = goals.create(os.getcwd(), "verificacion fuerte")
    run = client.post("/api/verify/run", json={
        "goal_id": goal["id"],
        "files": [{"path": "calipso/web/index.html", "status": "M"}],
        "commands": [{"command_id": "ui_syntax", "title": "Verificar UI", "reason": "test"}],
    })
    data = run.json()
    check("endpoint corre plan", run.status_code == 200 and data["report"]["status"] == "done")
    job = data["job"]
    arts = jobs.artifacts(os.getcwd(), job["id"])
    check("job verification_plan", job["kind"] == "verification_plan")
    check("artifacts reporte", {"verification-report.json", "verification-report.md"}.issubset({a["name"] for a in arts}))
    updated = goals.load(os.getcwd(), goal["id"])
    check("evidencia verification", updated and updated["evidence"][-1]["kind"] == "verification")

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: verificacion fuerte funcionando")
    return 0


def test_tocar_permisos_corre_los_tests_de_permisos():
    """El motor de permisos aparecia solo dentro de la rama del inbox, asi
    que tocarlo corria test_inbox y no test_permisos; y el almacen no
    disparaba nada. Un corte que NIEGA antes de crear la solicitud es lo
    mas silencioso que hay en el motor: sin esta red, romperlo da verde."""
    for ruta in ("calipso/permisos/almacen.py", "calipso/permisos/motor.py",
                 "calipso/permisos/acciones.py"):
        plan = verification.recommend(files=[{"path": ruta}])
        ids = [c["command_id"] for c in plan["commands"]]
        assert "test_permisos" in ids, ruta


if __name__ == "__main__":
    raise SystemExit(main())
