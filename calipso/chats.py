from __future__ import annotations

import datetime
import json
import os
import pathlib
import uuid

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
CHAT_FILE = CALIPSO_HOME / "chats.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load() -> dict:
    if not CHAT_FILE.exists():
        return {"active": None, "chats": {}}
    try:
        data = json.loads(CHAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"active": None, "chats": {}}
    data.setdefault("active", None)
    data.setdefault("chats", {})
    return data


def _save(data: dict) -> None:
    CALIPSO_HOME.mkdir(parents=True, exist_ok=True)
    CHAT_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def list_chats() -> list[dict]:
    data = _load()
    chats = list(data["chats"].values())
    chats.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return [
        {k: c.get(k) for k in ("id", "title", "project_path", "project_name",
                               "created_at", "updated_at")}
        | {"messages": len(c.get("messages", []))}
        for c in chats
    ]


def todos() -> list[dict]:
    """Todos los chats completos (con mensajes). Para la fuente `chats` del
    abismo: la busqueda lexica necesita el texto, no el conteo de list_chats."""
    return list(_load()["chats"].values())


def get(chat_id: str | None) -> dict | None:
    if not chat_id:
        return None
    return _load()["chats"].get(chat_id)


def active() -> dict | None:
    data = _load()
    return data["chats"].get(data.get("active"))


def active_id() -> str | None:
    return _load().get("active")


def set_active(chat_id: str) -> dict:
    data = _load()
    chat = data["chats"].get(chat_id)
    if not chat:
        raise KeyError(chat_id)
    data["active"] = chat_id
    _save(data)
    return chat


def create(project_path: str, title: str | None = None) -> dict:
    p = pathlib.Path(project_path)
    now = _now()
    chat_id = uuid.uuid4().hex[:12]
    chat = {
        "id": chat_id,
        "title": title or "Nueva conversacion",
        "project_path": str(p),
        "project_name": p.name,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    data = _load()
    data["chats"][chat_id] = chat
    data["active"] = chat_id
    _save(data)
    return chat


def append(chat_id: str | None, role: str, text: str, meta: dict | None = None) -> dict | None:
    if not chat_id:
        return None
    data = _load()
    chat = data["chats"].get(chat_id)
    if not chat:
        return None
    chat.setdefault("messages", []).append({
        "role": role,
        "text": text,
        "meta": meta or {},
        "ts": _now(),
    })
    if role == "user" and (chat.get("title") == "Nueva conversacion"):
        chat["title"] = text.strip()[:70] or chat["title"]
    chat["updated_at"] = _now()
    _save(data)
    return chat

