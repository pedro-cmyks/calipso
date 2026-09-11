#!/usr/bin/env python3
"""
Prueba de chat en vivo contra el servidor corriendo.
Autentica via token, abre WebSocket, manda un mensaje y muestra la respuesta.

Es un SCRIPT MANUAL, no un test de la suite: solo corre bajo
`if __name__ == "__main__"`. Importarlo (o que pytest lo recolecte) no
manda nada: antes, `asyncio.run(main())` corria al importar y un
`pytest -q test_chat_live.py` le mandaba "-q" al server REAL de Pedro,
dejando un turno basura en chats.json, un episodio en la memoria y una fila
en costs.jsonl (paso el 2026-09-11 durante la revision de la aduana).
"""
import asyncio
import json
import sys
import httpx
import websockets

import os, pathlib

BASE   = "http://localhost:8000"
WS     = "ws://localhost:8000/ws/chat"


def _token() -> str:
    # el token NO se escribe aca: este archivo esta en git. Se lee solo al
    # correr a mano, nunca al importar.
    return (os.environ.get("CALIPSO_TOKEN")
            or pathlib.Path.home().joinpath(".calipso/token")
                           .read_text(encoding="utf-8").strip())


async def main(TOKEN: str, MSG: str):
    # 1. Autenticar con el token para obtener la cookie de sesion
    async with httpx.AsyncClient() as http:
        r = await http.get(f"{BASE}/?token={TOKEN}", follow_redirects=True)
        cookie = r.cookies.get("calipso_token")
        if not cookie:
            # buscar en el historial de redirects
            for resp in r.history:
                cookie = resp.cookies.get("calipso_token")
                if cookie:
                    break
        if not cookie:
            print("[ERROR] No se obtuvo cookie de sesion")
            sys.exit(1)
        print(f"[auth] cookie obtenida")

    # 2. Conectar WebSocket con la cookie
    headers = {"Cookie": f"calipso_token={cookie}"}
    print(f"[ws]   conectando a {WS}")
    print(f"[msg]  enviando: {MSG!r}\n")
    print("─" * 60)

    async with websockets.connect(WS, additional_headers=headers) as ws:
        await ws.send(json.dumps({"text": MSG}))

        full_response = []
        async for raw in ws:
            try:
                pkt = json.loads(raw)
            except Exception:
                continue

            t = pkt.get("type", "")

            if t == "chunk":
                chunk = pkt.get("text", "")
                print(chunk, end="", flush=True)
                full_response.append(chunk)

            elif t == "meta":
                route  = pkt.get("route", "?")
                model  = pkt.get("model", "?")
                persona = pkt.get("persona", "")
                print(f"\n[ruta: {route} / {model}" + (f" / {persona}" if persona else "") + "]", flush=True)

            elif t == "cost":
                print(f"\n[costo: {pkt.get('tokens')} tokens, ${pkt.get('cost_usd', 0):.4f}]")

            elif t == "done":
                print("\n" + "─" * 60)
                print("[done] respuesta completa recibida")
                break

            elif t == "error":
                print(f"\n[ERROR] {pkt.get('text','?')}")
                break

            elif t in ("goal", "plan", "agent_start", "agent_done", "skill"):
                # telemetria interna — mostrar resumida
                print(f"\n[telemetria:{t}] {json.dumps(pkt)[:120]}", flush=True)


if __name__ == "__main__":
    MSG = sys.argv[1] if len(sys.argv) > 1 else "hola, di solo 'Calipso operativo en Linux' y nada mas"
    asyncio.run(main(_token(), MSG))
