#!/usr/bin/env python3
"""
Prueba de chat en vivo contra el servidor corriendo.
Autentica via token, abre WebSocket, manda un mensaje y muestra la respuesta.
"""
import asyncio
import json
import sys
import httpx
import websockets

import os, pathlib
# el token NO se escribe aca: este archivo esta en git
TOKEN = (os.environ.get("CALIPSO_TOKEN")
         or pathlib.Path.home().joinpath(".calipso/token")
                        .read_text(encoding="utf-8").strip())
BASE   = "http://localhost:8000"
WS     = "ws://localhost:8000/ws/chat"
MSG    = sys.argv[1] if len(sys.argv) > 1 else "hola, di solo 'Calipso operativo en Linux' y nada mas"


async def main():
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


asyncio.run(main())
