#!/usr/bin/env python3
"""
test_ui.py - verificacion ligera de la UI web de Calipso.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parent
HTML = ROOT / "calipso" / "web" / "index.html"


def check(name: str, cond: bool, fails: list[str]) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def carga_los_chats_tras_el_dom(text: str) -> bool:
    """La carrera de la PWA al arrancar (smoke de los canarios, hallazgo 3):
    `loadChats()` suelto en el parseo pintaba el historial antes de que el
    `<script type="module">` colgara `window.Canarios`, y las marcas
    guardadas en `meta.canarios` no se veian hasta re-abrir el chat. Los
    module scripts sin async corren antes de DOMContentLoaded: la carga del
    historial se cuelga de ahi."""
    suelta = re.search(r"^loadChats\(\);\s*$", text, re.M)
    diferida = 'document.addEventListener("DOMContentLoaded", () => loadChats());' in text
    return suelta is None and diferida


def test_la_pwa_carga_los_chats_tras_el_domcontentloaded():
    assert carga_los_chats_tras_el_dom(HTML.read_text(encoding="utf-8"))


def main() -> int:
    fails: list[str] = []
    text = HTML.read_text(encoding="utf-8")
    check("index.html existe", HTML.exists(), fails)
    check("chat presente", 'id="messages"' in text and 'id="input"' in text, fails)
    check("acciones de adjuntos", all(x in text for x in (
        "attachSelection", "attachOpenFile", "attachFolder")), fails)
    check("panel memoria", all(x in text for x in (
        "memoryBtn", "memoryPanel", "memoryCreate", "memoryList", "memoryCore",
        "memoryChronology", "/api/memory/core", "/api/memory/chronology")), fails)
    check("controles de cuota/conectores", all(x in text for x in (
        "cfgApiBudget", "cfgBlockClaude", "cfgBlockCodex", "harnessStatus")), fails)
    check("checklist lanzamiento", "launchChecklist" in text and "/api/launch/checklist" in text, fails)
    check("panel github", all(x in text for x in (
        "githubPanel", "githubRefresh", "loadGithub", "/api/github/overview")), fails)
    check("panel rutinas", all(x in text for x in (
        "routinesPanel", "loadRoutines", "/api/routines", "backupNow", "/api/backup")), fails)
    check("rama del abismo", all(x in text for x in (
        "startAbismo", "stopAbismo", 'm.type === "abismo"', "addDetalleViaje",
        "abismoEl")), fails)
    check("loadChats espera al DOMContentLoaded", carga_los_chats_tras_el_dom(text), fails)
    scripts = re.findall(r"<script>([\s\S]*?)</script>", text)
    check("scripts inline encontrados", bool(scripts), fails)
    node = shutil.which("node")
    check("node disponible", bool(node), fails)
    if node and scripts:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            tmp = pathlib.Path(f.name)
            f.write("\n".join(scripts))
        try:
            result = subprocess.run(
                [node, "--check", str(tmp)], cwd=str(ROOT), text=True,
                capture_output=True, encoding="utf-8", errors="replace", timeout=30)
            check("javascript valido", result.returncode == 0, fails)
            if result.returncode != 0:
                print(result.stderr or result.stdout)
        finally:
            tmp.unlink(missing_ok=True)
    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: UI web verificable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
