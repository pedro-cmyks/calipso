#!/usr/bin/env python3
"""
test_streaming.py — Verifica los parsers de streaming SIN necesitar Ollama/LiteLLM.

Levanta un servidor HTTP local que emula:
  - /sse     -> stream estilo OpenAI/LiteLLM (data: {json}\\n\\n ... data: [DONE])
  - /ndjson  -> stream estilo Ollama (una línea JSON por token, 'done': true al final)

Y comprueba que _sse_text_chunks() y _ollama_text_chunks() reconstruyen el texto.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import dispatch

PIECES = ["Hola", ", ", "mundo", "!"]
EXPECTED = "".join(PIECES)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencio
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)  # descarta el body
        if self.path == "/sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for p in PIECES:
                obj = {"choices": [{"delta": {"content": p}}]}
                self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
        elif self.path == "/ndjson":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for i, p in enumerate(PIECES):
                obj = {"response": p, "done": i == len(PIECES) - 1}
                self.wfile.write((json.dumps(obj) + "\n").encode())
                self.wfile.flush()
        else:
            self.send_response(404)
            self.end_headers()


def main() -> int:
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    failures = []

    # 1) SSE (ruta API)
    got = "".join(dispatch._sse_text_chunks(f"{base}/sse", {"x": 1}, {}))
    print(f"[sse]    got={got!r}")
    if got != EXPECTED:
        failures.append(f"SSE: esperaba {EXPECTED!r}, obtuve {got!r}")

    # 2) NDJSON (ruta local)
    got = "".join(dispatch._ollama_text_chunks(f"{base}/ndjson", {"x": 1}))
    print(f"[ndjson] got={got!r}")
    if got != EXPECTED:
        failures.append(f"NDJSON: esperaba {EXPECTED!r}, obtuve {got!r}")

    # 3) _emit devuelve 0 con un iterador OK
    rc = dispatch._emit(iter(PIECES), "test")
    if rc != 0:
        failures.append(f"_emit OK: esperaba rc=0, obtuve {rc}")

    # 4) _emit devuelve 1 si el iterador revienta
    def boom():
        yield "x"
        raise RuntimeError("kaboom")
    rc = dispatch._emit(boom(), "test")
    if rc != 1:
        failures.append(f"_emit error: esperaba rc=1, obtuve {rc}")

    srv.shutdown()

    if failures:
        print("\n".join("FAIL: " + f for f in failures))
        return 1
    print("\nOK: todos los tests de streaming pasaron")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
