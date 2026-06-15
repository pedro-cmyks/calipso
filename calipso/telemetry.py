from __future__ import annotations

import datetime
import json
import os
import pathlib
from typing import Any

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
LEDGER = CALIPSO_HOME / "telemetry.jsonl"


def log_event(kind: str, **data: Any) -> dict[str, Any]:
    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        **data,
    }
    try:
        CALIPSO_HOME.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry


def recent(limit: int = 100) -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
