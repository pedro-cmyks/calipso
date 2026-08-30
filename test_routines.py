#!/usr/bin/env python3
"""
test_routines.py - rutinas/timers: persistencia, vencimiento y ejecucion.

Aisla CALIPSO_HOME en un dir temporal.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
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

    # seed inicial: 6 rutinas. Las tres viejas y "cierre" nacen
    # deshabilitadas; "catastro" y "consumo" nacen habilitadas a proposito
    # (ver el comentario de routines.DEFAULTS): son las que existen para
    # que Pedro no tenga que acordarse de prenderlas -- ninguna de las dos
    # gasta nada ni toma una decision economica. "cierre" es la excepcion
    # opuesta: nace apagada porque encender el cierre automatico de la
    # economia es decision de Pedro, no del codigo.
    seeded = routines.load()
    check("seed crea 6 rutinas", len(seeded) == 6, fails)
    habilitadas_por_defecto = {"catastro", "consumo"}
    deshabilitadas_por_defecto = [r for r in seeded if r["kind"] not in habilitadas_por_defecto]
    check("las cuatro deshabilitadas por defecto (viejas + cierre) nacen apagadas",
         all(not r["enabled"] for r in deshabilitadas_por_defecto), fails)
    catastro_rt = next((r for r in seeded if r["kind"] == "catastro"), None)
    check("catastro nace habilitada",
         catastro_rt is not None and catastro_rt["enabled"] is True, fails)
    consumo_rt = next((r for r in seeded if r["kind"] == "consumo"), None)
    check("consumo nace habilitada",
         consumo_rt is not None and consumo_rt["enabled"] is True, fails)
    check("kinds esperados",
         {r["kind"] for r in seeded} ==
         {"reflect", "learn", "backup", "catastro", "cierre", "consumo"},
         fails)

    # el resto de esta prueba ejercita el vencimiento de UNA rutina
    # puntual (reflect); catastro y consumo nacen habilitadas y por lo
    # tanto "vencen" desde el primer load() (nunca corrieron), lo que
    # interferiria con esas aserciones. Ya quedo probado arriba que nacen
    # habilitadas -- se apagan aca para el resto del escenario.
    routines.update(catastro_rt["id"], {"enabled": False})
    routines.update(consumo_rt["id"], {"enabled": False})

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

    # C2 (revision de la rama): save() no deja un temporal huerfano si
    # os.replace falla a mitad de camino (disco lleno, permisos)
    home = pathlib.Path(os.environ["CALIPSO_HOME"])
    ruta_routines = home / "routines.json"
    _replace_real = os.replace

    def _replace_roto(*_a, **_k):
        raise OSError("disco lleno (simulado)")

    os.replace = _replace_roto
    try:
        propago = False
        try:
            routines.save(routines.load())
        except OSError:
            propago = True
    finally:
        os.replace = _replace_real
    check("save con os.replace roto propaga el error (no lo esconde)", propago, fails)
    temporales = list(home.glob(f"{ruta_routines.name}.tmp*"))
    check("save no deja temporales si el replace falla", temporales == [], fails)

    # C2: un routines.json PRESENTE pero corrupto no se pisa con el seed.
    # Antes de esta ronda, add/update/remove/mark_run eran load->modify->save:
    # un lector que agarraba el archivo a medio escribir (el ticker en su
    # hilo, un endpoint en el threadpool) leia el seed y lo guardaba encima,
    # perdiendo TODAS las rutinas de Pedro -incluida la de departamento con
    # su `cuenta`- por una escritura que un instante despues iba a terminar
    # bien.
    antes_de_corromper = routines.load()
    ruta_routines.write_text("esto no es json valido {{{", encoding="utf-8")
    crudo_roto = ruta_routines.read_bytes()
    check("load no revienta con el archivo corrupto",
         isinstance(routines.load(), list), fails)
    check("load no persiste el seed encima del archivo corrupto",
         ruta_routines.read_bytes() == crudo_roto, fails)
    check("update se niega a escribir sobre un archivo corrupto",
         routines.update(reflect["id"], {"enabled": False}) is None, fails)
    check("update no toco el archivo corrupto",
         ruta_routines.read_bytes() == crudo_roto, fails)
    check("remove se niega a escribir sobre un archivo corrupto",
         routines.remove(reflect["id"]) is False, fails)
    check("remove no toco el archivo corrupto",
         ruta_routines.read_bytes() == crudo_roto, fails)
    routines.mark_run(reflect["id"], now, "ok")
    check("mark_run no toco el archivo corrupto",
         ruta_routines.read_bytes() == crudo_roto, fails)
    try:
        routines.add("backup", "no deberia crearse", 60)
        add_se_nego = False
    except routines.ErrorRutinas:
        add_se_nego = True
    check("add se niega a escribir sobre un archivo corrupto", add_se_nego, fails)
    check("add no toco el archivo corrupto",
         ruta_routines.read_bytes() == crudo_roto, fails)

    # el mismo archivo, pero JSON valido con la forma equivocada (un objeto,
    # no una lista): tambien es "no se pudo leer", no "no hay rutinas"
    ruta_routines.write_text(json.dumps({"no": "es una lista"}), encoding="utf-8")
    check("update se niega con json valido pero forma invalida",
         routines.update(reflect["id"], {"enabled": False}) is None, fails)

    # reparar a mano, como haria Pedro (o el propio Pedro restaurando un
    # backup): save() SI puede escribir encima de un archivo corrupto
    routines.save(antes_de_corromper)
    check("save repara el archivo corrupto a mano",
         routines.get(reflect["id"]) is not None, fails)

    # C2: un routines.json AUSENTE (no confundir con "presente pero
    # corrupto", el caso de arriba) sigue dando el seed, como siempre
    ruta_routines.unlink()
    reseed = routines.load()
    reseed_viejas = [r for r in reseed if r["kind"] not in ("catastro", "consumo")]
    check("archivo ausente sigue dando el seed",
         len(reseed) == 6 and all(not r["enabled"] for r in reseed_viejas),
         fails)

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
