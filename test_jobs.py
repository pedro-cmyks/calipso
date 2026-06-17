#!/usr/bin/env python3
"""
test_jobs.py - registro persistente de trabajos largos.
"""
import os
import tempfile

_HOME = tempfile.mkdtemp(prefix="calipso_jobs_")
os.environ["CALIPSO_HOME"] = _HOME

from calipso import jobs  # noqa: E402


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' ' + extra) if extra else ''}")
        if not cond:
            fails.append(name)

    project = tempfile.mkdtemp(prefix="calipso_project_")
    job = jobs.start("test", "Trabajo largo", project_root=project, model="demo")
    check("crea job", job["id"].startswith("job_") and job["status"] == "running")
    jobs.event(project, job["id"], "running", elapsed=5)
    jobs.update(project, job["id"], status="done", elapsed=8)
    artifact = jobs.write_artifact(project, job["id"], "salida.txt", "resultado listo")
    artifact_json = jobs.write_artifact(project, job["id"], "../meta.json", {"ok": True})
    loaded = jobs.load(project, job["id"])
    evs = jobs.events(project, job["id"])
    arts = jobs.artifacts(project, job["id"])
    raw = jobs.read_artifact(project, job["id"], "salida.txt").decode("utf-8")
    listed = jobs.list_jobs(project)
    check("carga job actualizado", loaded and loaded["status"] == "done")
    check("eventos persistidos", len(evs) >= 4 and evs[-1]["action"] == "artifact")
    check("artifact texto", artifact["name"] == "salida.txt" and raw == "resultado listo")
    check("artifact sanitizado", artifact_json["name"] == "meta.json")
    check("lista artifacts", any(a["name"] == "salida.txt" for a in arts))
    check("lista jobs", listed and listed[0]["id"] == job["id"])

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: jobs persistentes funcionando")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
