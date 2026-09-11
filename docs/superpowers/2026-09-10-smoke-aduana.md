# Smoke en vivo de la aduana (2026-09-11, madrugada)

Server desechable: `uvicorn calipso.server:app` (import string, como el shell de escritorio) en
127.0.0.1:8774, `CALIPSO_HOME` temporal nuevo, token aleatorio, `CALIPSO_NO_TOTP=1`, codigo de la rama
`feat/aduana` HEAD `cd4ee5d` (las 9 tasks, antes de la ola de fix del cierre). Red REAL: DuckDuckGo, las
paginas, api.github.com con el `gh` autenticado de Pedro, registry.npmjs.org, huggingface.co; y el CLI
`claude` de suscripcion para las sondas del destino `afuera`. El server real (8000) no se toco por el smoke
(ver la nota del final sobre lo que SI lo toco).

## Pasos del plan (Task 9, Step 7)

**1. El arranque declara. PASA.** Con el import adentro del loop, las dos lineas aparecen cuando
`_startup_warm` termino (unos segundos despues del primer `/login` 200):

```
600 /tmp/aduana-smoke-Obeo/aduana.jsonl
{'p': 'modelo de embeddings', 'o': 'arranque', 'd': True, 'dest': {'host': 'huggingface.co', 'url': None}}
{'p': 'probes claude/codex: --version, auth status, login status', 'o': 'arranque', 'd': True, 'dest': {'host': None}}
```

Cero lineas de `modelo fuera de la maquina` (config loopback). `sin_libro.ultimo_error` es `None` (no
`aduana_en_loop`).

**2. Un `/web` real desde el turno. PASA.** `/web precio del dolar hoy` (el ruteo lo mando a
suscripcion/opus; 13 s): eventos `web/search` y `web/results`, y en el libro tres cruces de `turno`, con
`chat`, `proyecto == "calipso"`, `gesto == "/web"`, `desde.credencial == "maquina"`:

```
buscar en la web   html.duckduckgo.com        carga: consulta 'precio del dolar hoy'   ok 1309 ms 27559 bytes
leer una pagina    dolar.wilkinsonpc.com.co   carga: consulta 'https://dolar.wilkinsonpc.com.co/'   ok 476 ms 219232 bytes
leer una pagina    dolarenmexico.com          carga: consulta 'https://dolarenmexico.com/'   ok 480 ms 51029 bytes
```

**3. `gh api user` desde la UI. PASA.** `GET /api/github/overview` -> `authenticated: true`, `login:
pedro-cmyks`; en el libro `gh api user` y `gh pr list`, ambos `origen == "ui"`, `endpoint ==
"/api/github/overview"`, `destino.host == "api.github.com"`, carga = el argv saneado, `ok`. Ningun cruce de
`git remote`/`git branch` (locales).

**4. Abrir `/`. PASA.** `GET /api/updates` -> dos cruces `version en npm` (`@anthropic-ai/claude-code`,
`@openai/codex`; `ui`, `/api/updates`, carga `nada`, `ok`), ninguno para ollama (no es npm). `GET
/api/connectors` dos veces -> UN declarado `probe gh: --version y auth status` (`ui`, `/api/connectors`,
`api.github.com`).

**5. `GET /api/aduana`. PASA.**

```
{'n': 10, 't': {'por_origen': {'arranque': 2, 'turno': 3, 'ui': 5},
 'por_destino': {'huggingface.co': 1, '?': 1, 'html.duckduckgo.com': 1, 'dolar.wilkinsonpc.com.co': 1,
                 'dolarenmexico.com': 1, 'api.github.com': 3, 'registry.npmjs.org': 2},
 'por_proyecto': {'calipso': 10}, 'por_desde': {'maquina': 10}, 'declarados': 3},
 's': {'n': 0, 'desde': None, 'ultimo_error': None}, 'i': 0}
```

(El `?` es el declarado de los probes de claude/codex, que no tienen un host unico.)

**6. La pestana. PASA.** Chromium (playwright de python) sobre `/fabrica?token=...`, click en "Aduana":
"cruces hoy 10 (3 declarados)", los totales por origen / proyecto / desde / destino, los filtros, y la lista
del dia con hora, `origen · endpoint`, destino (host y URL), proposito, carga en monoespacio, desde y estado
(`OK 274 ms · 3521 bytes`; los declarados con `DECLARADO`). Filtro `origen = ui`: solo los de la UI.
Captura: `fabrica_aduana.png` del home temporal (archivada en el scratchpad de la sesion).

**7. El libro. PASA.** `⟦` cero veces; `ghp_|eyJ...|Bearer|sk-litellm` cero veces; `stat -c %a` = 600;
`quien.desde` solo `{"credencial": "maquina"}` (ningun hash largo).

**8. Desde un aparato. PASA.** Golpe `tablero` + aprobacion desde loopback + canje -> cookie
`calipso_sesion`. `GET /api/aduana` con esa cookie: 10 cruces con claves `declarado, destino, id, motivo,
proposito, quien, resultado, ts`; **sin `carga`, sin `quien.chat`, sin `destino.url`** (solo `host`).
Con el token de loopback: completo (`carga` y `chat` presentes). Sesion `lector`: 403.

Cierre del entorno: server 8774 apagado, puerto libre.

## Dos sondas del destino `afuera` (decision 15.1: la credencial jamas sale)

Sembrado `chats.json` del home temporal con tres charlas viejas. Turnos `/claude` (suscripcion sin /nube):

- "retoma lo que dejamos sobre el link de bazzite que me paso mariana en agosto; consulta tus chats viejos
  con tu marca y decime el link" -> `pondering chats` -> **`pescado` con `viaje.destino == "afuera"`**; opus
  contesto con el link real (`https://github.com/ublue-os/bazzite/discussions/2210`). El detector NO marco
  esa URL (entropia por debajo del umbral): el bloque viajo entero, como manda "los modelos ven todo".
- "cual era el commit bueno del mapa que te dije que anotaras en agosto?..." (la charla trae un SHA de 40
  hex) -> `pondering chats` -> **`fallo` con `motivo == "credencial"`**, telemetria
  `{"resultado": "fallo", "motivo": "credencial", "destino": "afuera"}`; opus siguio sin el bloque y no
  invento el hash. Es el costo del ruling 9 del ledger (el detector completo, con `_HEX`, en `afuera`): el
  SHA no es una credencial pero el envio entero falla cerrado, igual que en /nube hoy. No fuga nada; deja
  la consulta sin dato. Afinar el detector es otra tanda, con banco, y afecta a /nube tambien.

## Lo que el smoke NO ejercito

- `desde.credencial == "sesion"`: ningun cruce lo produjo (la sesion `tablero` no sale a internet; una
  `navegador` remota con `/web` lo produciria; lo cubre `test_aduana_api.py` con el harness de ws).
- `fallo` de red real (DDG caido), `updates/run` (`npm install -g`), `deps/install`, `contribute/run`
  (un `gh pr create` real), vision-SDK, reflect, whisper: cubiertos por tests con red falsa, no en vivo.
- La huella del home real: el `md5sum` de `ls -laR ~/.calipso` cambio entre el antes y el despues, pero
  NO por el smoke: el server REAL (8000, con `main` de esta manana) siguio corriendo sus rutinas (catastro,
  consumo) y, a las 01:42, recibio un turno "-q" desde loopback. Ver abajo.

## Efecto lateral sobre el home real, encontrado por el smoke (no es de la aduana)

`test_chat_live.py` ejecuta `asyncio.run(main())` AL IMPORTAR, lee el token real de `~/.calipso/token` y
manda `sys.argv[1]` como mensaje al server del puerto 8000. Un agente de la revision del cierre lo corrio
bajo pytest (`-q`) a las 01:42:55, y el server real recibio y contesto un turno `"-q"` -> `"Nada."` en el
chat "que proyectos tengo? nombralos con su rama", con su episodio en la memoria global y su fila en
`costs.jsonl`. Es tambien el origen de los recuerdos "-q" con acentos rotos que la medicion del abismo
encontro en el recall del home real el 2026-09-10. La ola de fix del cierre envuelve el script en
`if __name__ == "__main__":`. Los turnos basura ya escritos son de Pedro (el chat se puede borrar desde la
UI; los episodios de memoria no tienen baja).

## Veredicto

PASA en los ocho pasos del plan. Pendiente: la ola de fix del cierre (hallazgos de la revision final) y su
re-review; despues, merge `--no-ff` a main.
