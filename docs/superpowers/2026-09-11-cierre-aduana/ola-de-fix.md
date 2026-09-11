# Ola de fix del cierre (una sola; despues una re-review acotada)

Rama feat/aduana, HEAD cd4ee5d. Arreglar TODO lo de abajo en commits chicos con rutas explicitas (uno por
tema esta bien), TDD (test que falla -> codigo -> pasa), suite completa verde antes de cada commit.
Los hallazgos vienen de la revision final, tres lentes con sondas y Codex; el spec
(docs/superpowers/specs/2026-09-10-aduana-design.md) es la autoridad.

## Importantes (codigo)

1. **Perdida silenciosa de cruces por contencion entre HILOS del mismo proceso** (`calipso/aduana.py:_escribir`):
   el candado no bloqueante con 3 x 50 ms fue pedido para el flock AJENO (otro proceso: fail-hang), pero
   `candado(no_bloquear=True)` tambien levanta ErrorCandado al instante si OTRO HILO del proceso tiene el
   RLock, y con dos cruces simultaneos del threadpool el segundo puede perderse (sin_libro). Arreglo: un
   `threading.Lock()` de modulo que serializa `_escribir` entre hilos (una escritura son microsegundos:
   bloquear entre hilos no cuelga nada) ANTES de tomar el candado; el candado no bloqueante con reintento
   queda solo para el proceso ajeno. Test: N hilos escribiendo a la vez -> N lineas, sin_libro.n == 0.
2. **`proyecto` vacio con ROOT=/** (`Quien.__post_init__` levanta ValueError('proyecto vacio') y `quien_turno`
   se construye en TODO turno antes del try: el websocket se cae en cada mensaje; los endpoints dan 500).
   Arreglo: un helper `_proyecto() -> str` en server.py (`ROOT.name or str(ROOT)`) usado en TODOS los sitios
   que hoy ponen `proyecto=ROOT.name` (_quien_http, _declarar_arranque, quien_turno en ws_chat, el handler
   _reflect del ticker, _calentar_probes). Test con `monkeypatch.setattr(srv, "ROOT", pathlib.Path("/"))`:
   `_quien_http` no revienta y el proyecto es "/".
3. **`_declarar_modelos_fuera` sin fail-open** (`server.py` ~2118-2132): `urllib.parse.urlsplit(url).hostname`
   sin try; un base_url malformado (`http://[::1:11434/x`) levanta ValueError: en el arranque se pierden en
   silencio la declaracion de la memoria/probes y `_backend_availability`; en PUT /api/config el 500 sale
   DESPUES de guardar la config. Arreglo: `try/except ValueError` -> tratar el host como no parseable y
   declararlo como "modelo fuera de la maquina" con destino=url (la aduana lo sanea) y motivo "base_url no
   parseable"; test: PUT /api/config con ese base_url devuelve 200 y `_calentar_probes` termina. Ademas
   separar el try de `_startup_warm` para que un fallo de `discovery.discover` no se lleve `_calentar_probes`.
4. **El saneo de argv no cubre URLs con query/fragmento** (`aduana._carga` para list/tuple aplica solo
   `_tapar_lexicas`): un `gh api 'https://x/y?token=abc'` guarda la query entera. Arreglo: en la rama de
   lista, cada token que sea URL http(s) pasa por `sanear_url` (userinfo/query/fragmento tapados) y el resto
   por las lexicas. Fila en el banco del saneo.

## Menores que los revisores pidieron cerrar ANTES del merge

5. **`leer()` revienta con una linea JSON valida cuyo `ts` no es str o cuyo `destino`/`quien` no es dict**
   (GET /api/aduana da 500 por UNA linea editada a mano; el spec 9 promete que las lineas rotas se cuentan).
   Arreglo: validar tipos dentro del try que cuenta `ilegibles` (ts str, quien dict, destino dict o None).
   Test: una linea `{"ts": 123, "quien": {}}` y otra con destino str cuentan como ilegibles y el endpoint
   sigue en 200.
6. **`proposito`, `motivo` y `quien.gesto` van al libro crudos** (aduana.py `_registro`/`declarar`): pasarlos
   por `_tapar_lexicas` (y `sanear_url` si son URL) al armar el registro; `proposito` ademas acotado a 120
   chars. Filas en el banco (`declarar(..., motivo="http://u:p@host/x")` -> userinfo tapado; `/model ghp_...`
   en gesto -> tapado).
7. **`ultimo_error` y el `error=` de telemetria llevan la ruta absoluta del disco** (OSError.filename,
   la ruta del .lock): componer el error sin la ruta (`f"{type(exc).__name__}: {getattr(exc, 'strerror', None) or ''}"`
   y para ErrorCandado solo el nombre de la clase). Ajustar el test de permisos para afirmar que la ruta NO
   aparece.
8. **La query sin `=` no se sanea** (`_tapar_valores` solo reemplaza `=([^&]*)`): un token pelado en la
   query (`?ghp_...`, `?a=1&deadbeef...`) va entero. Arreglo: sobre cada segmento de la query sin `=`,
   aplicar las lexicas (o taparlo entero si no es alfanumerico corto). Fila en el banco.
9. **`before_after_capture` "loopback por construccion" sin verificar** (`browser.py`): la excepcion del
   canario descansa en eso. Arreglo: al entrar, si el host de la URL no es loopback, `raise ValueError(
   "before_after_capture solo captura loopback")` (es un guard de programador, no un cruce). Test.
10. **El motivo de la excepcion del canario para `discovery._get_json`** dice "loopback por construccion"
    pero `discover_ollama(base=...)`/`discover_litellm(base=...)` aceptan cualquier base. Arreglo minimo y
    honesto: cambiar el motivo a "loopback por config: `base` viene de CONFIG en los llamadores de produccion
    (discover); un llamador con otro host no cruza: limite conocido" y que `test_las_excepciones_apuntan_...`
    siga verde. (No agregar cruce: es un declarado del arranque el que cubre el modelo fuera de la maquina.)
11. **El motivo de la excepcion `calipso/tools/commands.py`** es impreciso: la allowlist incluye `test_memory`,
    que corre `test_memory.py`, que construye `Memory()` (huggingface.co) y llama `reflect` (`claude -p`) desde
    un subproceso. Arreglo: precisar el motivo ("subprocesos de la allowlist: git local y tests; `test_memory`
    sale a la red desde OTRO proceso, fuera de la aduana: limite conocido, como los CLIs agentes").

## Trampa del entorno que mordio DURANTE este cierre (arreglar aca, es de una linea)

12. **`test_chat_live.py` ejecuta `asyncio.run(main())` AL IMPORTAR** y lee el token real de `~/.calipso/token`:
    un `pytest -q test_chat_live.py` (o cualquier import) le manda el mensaje "-q" al SERVER REAL en el puerto
    8000 y deja un turno basura ("-q" / "Nada.") en chats.json, un episodio en la memoria y una fila en
    costs.jsonl de Pedro. Paso hoy a las 01:42 durante la revision (un agente lo corrio), y es el origen de
    los recuerdos "-q" con acentos rotos que la medicion del abismo encontro. Arreglo: envolver la ejecucion
    en `if __name__ == "__main__":` (el script sigue sirviendo a mano) y una linea en su docstring que lo
    diga. Sin test (es un script manual); verificar que `pytest --collect-only -q test_chat_live.py` no
    dispare nada (0 collected, sin conexion).

## Lo que NO se toca en esta ola (parkeado con ruling del controlador, esta en el ledger)

- El detector completo en destino `afuera` corta el bloque del abismo ante un SHA de 40 hex o una URL de
  alta entropia (ruling 9: misma conducta que /nube; afinar el detector es otra tanda con banco).
- `leer()` bajo candado bloqueante; la lista negra de git (ratificada); `pr` con titulo + 2 lineas; el recorte
  del tablero mas ancho que la enumeracion literal; `/web/` excluido por substring en el canario; la
  duplicacion de la derivacion de destino en dos ramas; `entro()` sin try; contadores sin lock (los cubre el
  Lock del punto 1 si se usa tambien para SIN_LIBRO/_DECLARADOS: hacelo, es gratis).
