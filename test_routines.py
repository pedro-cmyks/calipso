#!/usr/bin/env python3
"""
test_routines.py - rutinas/timers: persistencia, vencimiento y ejecucion.

Aisla CALIPSO_HOME en un dir temporal.
"""
from __future__ import annotations

import datetime
import os
import tempfile

os.environ["CALIPSO_HOME"] = tempfile.mkdtemp(prefix="calipso_rt_")

from calipso import routines  # noqa: E402
from calipso import backup  # noqa: E402


def check(name: str, cond: bool, fails: list[str]) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def main() -> int:
    fails: list[str] = []
    now = datetime.datetime(2026, 6, 16, 12, 0, 0)

    # seed inicial: 3 rutinas, todas deshabilitadas
    seeded = routines.load()
    check("seed crea 3 rutinas", len(seeded) == 3, fails)
    check("seed todas deshabilitadas", all(not r["enabled"] for r in seeded), fails)
    check("kinds esperados", {r["kind"] for r in seeded} == {"reflect", "learn", "backup"}, fails)

    # rutina deshabilitada nunca vence
    check("deshabilitada no vence", routines.due(routines.load(), now) == [], fails)

    # habilitar reflect -> vence (nunca corrio)
    reflect = next(r for r in seeded if r["kind"] == "reflect")
    routines.update(reflect["id"], {"enabled": True, "interval_minutes": 60})
    due_now = routines.due(routines.load(), now)
    check("habilitada sin last_run vence ya", len(due_now) == 1 and due_now[0]["id"] == reflect["id"], fails)

    # ejecutar via run_due con handler que cuenta
    calls = []
    ran = routines.run_due(now, {"reflect": lambda r: calls.append(r["id"])})
    check("run_due ejecuta la vencida", len(ran) == 1 and ran[0]["status"] == "ok", fails)
    check("handler fue llamado", calls == [reflect["id"]], fails)

    # tras correr, no vuelve a vencer hasta pasar el intervalo
    after = routines.get(reflect["id"])
    check("last_run registrado", after["last_run"] is not None and after["last_status"] == "ok", fails)
    soon = now + datetime.timedelta(minutes=30)
    check("no vence antes del intervalo", routines.due(routines.load(), soon) == [], fails)
    later = now + datetime.timedelta(minutes=61)
    check("vence pasado el intervalo", len(routines.due(routines.load(), later)) == 1, fails)

    # handler que lanza no rompe; registra error
    routines.mark_run(reflect["id"], now - datetime.timedelta(hours=5), "ok")  # forzar vencido
    ran2 = routines.run_due(now, {"reflect": _boom})
    check("error de handler se captura", ran2 and ran2[0]["status"].startswith("error"), fails)

    # add/remove
    extra = routines.add("backup", "Backup manual", 720, enabled=True)
    check("add crea rutina", routines.get(extra["id"]) is not None, fails)
    check("remove borra rutina", routines.remove(extra["id"]) and routines.get(extra["id"]) is None, fails)

    # kind invalido
    try:
        routines.add("hackear", "x", 10)
        check("kind invalido rechazado", False, fails)
    except ValueError:
        check("kind invalido rechazado", True, fails)

    # backup: crea zip con contenido y lo lista; excluye carpeta backups
    res = backup.create_backup(stamp="20260616-120000")
    check("backup crea zip", res["ok"] and res["path"].endswith(".zip"), fails)
    check("backup incluye routines.json", res["files"] >= 1, fails)
    listed = backup.list_backups()
    check("backup listado", any(b["name"] == "calipso-backup-20260616-120000.zip" for b in listed), fails)
    res2 = backup.create_backup(stamp="20260616-130000")
    check("segundo backup no anida backups previos", res2["ok"], fails)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: rutinas/timers verificable")
    return 0


def _boom(_r):
    raise RuntimeError("kaboom")


if __name__ == "__main__":
    raise SystemExit(main())
