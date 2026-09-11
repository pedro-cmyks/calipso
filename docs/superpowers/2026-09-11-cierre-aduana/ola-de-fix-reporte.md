# Reporte de la ola de fix del cierre (feat/aduana)

Rama `feat/aduana`. base_sha `cd4ee5dc4c9490e2c0b8c2bb22912d5af656dbe5` -> head_sha
`db8860269ee86c616f1470f9a1e0fddb712e79eb`. Nueve commits, uno por tema o grupo afin, TDD (test rojo ->
codigo -> verde), suite completa verde antes de cada uno. Sin push, sin tocar main ni ~/.calipso, sin server
real, sin Ollama. Los cambios de docs que ya estaban sin commitear en el arbol (AGENTS.md, los dos specs, el
estado del proyecto, el smoke) no son mios y quedaron intactos (git add con rutas explicitas).

Suite final: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?` ->
`1645 passed, 4 warnings in 112.84s`, `EXIT=0` (base: 1612 passed; +33 tests). No se toco `calipso/web/`.

## Commits

| sha | tema |
|---|---|
| `b3675e0` | aduana: serializar `_escribir` entre hilos con un Lock de modulo (punto 1) |
| `969be4e` | aduana: el error del hueco sin la ruta absoluta del disco (punto 7) |
| `05f2a01` | aduana: saneo de argv con URL, de proposito/motivo/gesto y de la query sin `=` (puntos 4, 6, 8) |
| `a3a28bf` | aduana: `leer()` cuenta como ilegible el JSON valido con tipos raros (punto 5) |
| `d08ba53` | server: `_proyecto()` para que ROOT=/ no deje el proyecto vacio (punto 2) |
| `437525e` | server: `_declarar_modelos_fuera` fail-open y el arranque con un try por paso (punto 3) |
| `9ae9e03` | browser: `before_after_capture` verifica que la URL sea loopback (punto 9) |
| `b38d2e7` | canario: motivos honestos para `discovery._get_json` y `tools/commands.run` (puntos 10, 11) |
| `db88602` | test_chat_live: correr solo bajo `__main__`, nunca al importar (punto 12) |

## Por punto

### 1. Perdida de cruces por contencion entre hilos (`aduana._escribir`)

Cambio (`calipso/aduana.py`): `_ENTRE_HILOS = threading.Lock()` de modulo; `_escribir` lo toma ANTES del
bucle de `candado(no_bloquear=True)` con 3 x 50 ms, que queda solo para el flock ajeno. El mismo Lock cubre
los contadores de modulo (lo parkeado que el punto 1 permitia): `sin_libro()`, `_reset_para_tests()`,
`_contar_hueco()` (ahora devuelve el n bajo el Lock, y `_anotar` lo usa para el aviso sin releer el
contador afuera) y la bandera de `declarar_una_vez` (check + add bajo el Lock; el `declarar` queda afuera:
el Lock no es reentrante y `_escribir` lo vuelve a tomar). `leer()` NO lo toma, a proposito: bajo el
candado bloqueante, un `.lock` ajeno colgado dejaria colgados a los escritores (fail-hang).

Test: `test_aduana.py::test_n_hilos_escribiendo_a_la_vez_dejan_n_lineas_sin_hueco` (4 hilos con barrera y
un `_append` que tarda 0.2 s, mas que los 3 x 50 ms: antes del fix perdia 3 de 4 -> `sin_libro.n == 3`;
ahora 4 lineas y `n == 0`, sin `aduana_sin_libro`) y
`test_aduana.py::test_declarar_una_vez_desde_n_hilos_declara_una_sola` (6 hilos, una sola linea).
Rojo antes del fix: `1 failed, 1 passed` (el de la bandera ya pasaba: con el GIL la carrera no se ve; es
guardia de regresion). Verde despues: `44 passed`.

### 2. `proyecto` vacio con ROOT=/ (server)

Cambio (`calipso/server.py`): helper `_proyecto() -> str` (`ROOT.name or str(ROOT)`), UNICO sitio que
deriva el proyecto de ROOT; lo usan `_quien_http`, `_declarar_arranque`, `quien_turno` en `ws_chat`, el
handler `_reflect` del ticker y `_calentar_probes`. `grep proyecto=ROOT.name calipso/server.py` -> nada.

Test: `test_aduana_api.py::test_con_root_en_la_raiz_el_proyecto_no_queda_vacio`
(`monkeypatch.setattr(srv, "ROOT", pathlib.Path("/"))`: `_proyecto() == "/"`, `_quien_http` no revienta y
el proyecto es "/"; `_declarar_arranque` y `_calentar_probes` tampoco revientan y sus lineas llevan
proyecto "/"; con un ROOT normal sigue siendo el nombre) y
`test_aduana_api.py::test_ningun_sitio_del_server_deriva_el_proyecto_por_su_cuenta` (guardia de texto:
`proyecto=ROOT.name` no vuelve; `proyecto=_proyecto()` aparece >= 5 veces). Rojo antes
(`AttributeError: no attribute '_proyecto'`), verde despues.

### 3. `_declarar_modelos_fuera` sin fail-open + `_startup_warm`

Cambio (`calipso/server.py`): `urlsplit(url).hostname` dentro de `try/except ValueError`; el host no
parseable se trata como fuera de la maquina y se declara con `destino=url` (la aduana lo sanea: `url:
"[SECRETO]"`, `host: None`) y `motivo="<boca>: base_url no parseable"` (conserva la boca, que era el
motivo original). Un `base_url` vacio se saltea antes (como antes, por el `or ""`). `_startup_warm` con
un try por `to_thread`: `discovery.discover` y `_calentar_probes` separados.

Tests: `test_aduana_api.py::test_un_base_url_no_parseable_se_declara_como_fuera_sin_reventar` (classifier
`http://[::1:11434/x?pwd=abc` -> 1 declarado, destino `{host: None, url: "[SECRETO]"}`, motivo
`classifier: base_url no parseable`, "abc" no esta en el libro; las dos loopback no declaran),
`test_put_config_con_base_url_malformado_devuelve_200_y_declara` (PUT /api/config -> 200, una linea
`gesto`), `test_calentar_probes_termina_con_un_base_url_malformado` (termina y declara memoria + fuera +
probes, devuelve `_backend_availability()`), `test_un_fallo_de_discover_no_se_lleva_los_probes`
(`discover` levanta RuntimeError; `_calentar_probes` corre igual). Rojo antes: `ValueError: Invalid IPv6
URL` x3 y `assert [] == ['probes']`. Verde despues: `46 passed` en test_aduana_api.py.

### 4. El saneo de argv no cubre URLs con query/fragmento

Cambio (`calipso/aduana.py`): `_texto_de_sitio(texto)` (URL http(s) -> `sanear_url`; lo que urlsplit no
parsea -> `[SECRETO]` entero; el resto -> lexicas). En `_carga`, la rama list/tuple aplica
`_texto_de_sitio` a CADA token y los une; la rama str reusa el mismo helper para URL/no parseable y sigue
con el detector completo para la frase de Pedro.

Test: `test_aduana.py::test_un_argv_con_url_sanea_la_url_y_deja_el_resto_lexico` (4 filas: `gh api
'https://api.github.com/repos/x/y?token=abc&per_page=5'` -> valores tapados, nombres conservados;
fragmento `#access_token=abc` tapado; `git fetch 'http://[::1/x?pwd=abc'` -> `[SECRETO]`; `git push <url>
<sha40>` intacto). `test_un_argv_de_gh_tapa_solo_lo_lexico` ahora afirma el resultado exacto
`git clone https://[SECRETO]@github.com/x/y.git` (antes `_CONN` se llevaba la URL entera). Rojo antes
(4 fallos), verde despues.

### 5. `leer()` revienta con JSON valido de tipos raros

Cambio (`calipso/aduana.py`): dentro del try que suma `ilegibles`, se exige `c` dict, `ts` str, `quien`
dict, `destino` dict o None (ausente/None sigue legible, cuenta como "?").

Tests: `test_aduana.py::test_leer_cuenta_como_ilegible_una_linea_json_valida_con_tipos_raros` (siete
formas: ts int, destino str, quien str, sin quien, lista, numero, null -> `ilegibles == 7`, la linea buena
sigue; `destino: null` legible) y
`test_aduana_api.py::test_una_linea_editada_a_mano_con_tipos_raros_no_tumba_el_endpoint` (GET /api/aduana
-> 200, `ilegibles == 3`). Rojo antes (`TypeError: '<' not supported between instances of 'int' and
'str'`), verde despues.

### 6. `proposito`, `motivo` y `quien.gesto` crudos

Cambio (`calipso/aduana.py`): `_texto_seguro(texto, tope=None)` (None queda None; el resto por
`_texto_de_sitio`, recorte DESPUES de sanear). `_registro` lo aplica a `proposito` con `PROPOSITO_MAX =
120` y a `quien.gesto` (sobre el dict de `a_dict()`, el Quien no se toca); `declarar` a `motivo` (sin tope:
el hallazgo solo acota proposito).

Tests: `test_aduana.py::test_un_motivo_con_url_va_saneado_y_uno_normal_queda`
(`motivo="http://u:p@host/x?k=v"` -> `http://[SECRETO]@host/x?k=[SECRETO]`; `all-MiniLM-L6-v2` intacto;
un motivo no parseable -> `[SECRETO]`), `test_un_gesto_con_token_va_tapado` (`/model ghp_...` ->
`/model [SECRETO]`, el resto del Quien intacto), `test_un_proposito_pasa_por_las_lexicas_y_se_acota_a_120`
(JWT tapado; 320 chars -> 120; un proposito URL saneado). Rojo antes (3 fallos), verde despues.

### 7. `ultimo_error` con la ruta absoluta del disco

Cambio (`calipso/aduana.py`): `_error_sin_ruta(exc)`: ErrorCandado -> solo el nombre de la clase; OSError
-> `Clase: strerror` (o solo la clase si no hay strerror); el resto -> `Clase: mensaje`. `_anotar` lo usa
para el contador y para `error=` de telemetria.

Tests ajustados: `test_aduana.py::test_sin_permisos_es_fail_open_con_aviso` (`ultimo_error ==
"PermissionError: Permission denied"` y `str(cerrado)` NO esta ni en el contador ni en la telemetria),
`test_candado_tomado_por_otro_proceso_es_fail_open_con_aviso` (`== "ErrorCandado"`, la ruta del `.lock`
no esta en los avisos), `test_enospc_simulado...` y `test_un_fallo_del_libro_no_reemplaza...` afirman el
texto exacto; `test_aduana_api.py::test_sin_libro_viene_de_memoria_sin_tocar_el_disco` usa un
`OSError(errno.ENOSPC, "disco lleno", ruta)` como uno real (antes era `OSError("disco lleno")` sin errno)
y afirma que la ruta del libro no aparece. Rojo antes (5 fallos), verde despues.

### 8. La query sin `=` no se sanea

Cambio (`calipso/aduana.py`): `_tapar_valores` recorre los segmentos por `&`: con `=` como antes (nombre
conservado, valor tapado); vacio se deja; sin `=` pasa por las lexicas y, si no es alfanumerico corto
(`_SUELTO_CORTO = [A-Za-z0-9_\-]{1,12}`: `?raw`, `?v2`, `?download`), se tapa entero. Vale tambien para
el fragmento con `=` (usa el mismo helper); un fragmento sin `=` sigue siendo un valor entero (`#readme`
-> `#[SECRETO]`, fila que ya estaba).

Filas nuevas en `test_aduana.py::test_positivos_tapados_en_la_url`: `?ghp_...` -> `?[SECRETO]`;
`?a=1&deadbeef...(32 hex)` -> `?a=[SECRETO]&[SECRETO]`; `?eyJ...&q=1` -> `?[SECRETO]&q=[SECRETO]`;
`?raw&v2&q=hola` -> `?raw&v2&q=[SECRETO]`; `?p%40ss.w0rd` -> `?[SECRETO]`; `#a=1&deadbeef...` ->
`#a=[SECRETO]&[SECRETO]`. Los falsos positivos del banco siguen intactos. Rojo antes (5 filas), verde
despues.

### 9. `before_after_capture` "loopback por construccion" sin verificar

Cambio (`calipso/browser.py`): `_es_loopback(url)` (http(s) a `localhost` o a una IP con `is_loopback`;
no parseable, sin host u otro esquema -> False). Al entrar: `raise ValueError("before_after_capture solo
captura loopback")` antes de tocar deps o playwright; docstring actualizado.

Tests: `test_aduana_enchufes.py::test_before_after_capture_rechaza_lo_que_no_es_loopback` (6 URLs:
example.com, 192.168.1.66, `http://[::1:8000/x`, `ftp://localhost/x`, `localhost:8000` sin esquema, vacia;
`deps.is_ready` es una bomba y no se toca; libro vacio) y `test_before_after_capture_acepta_loopback`
(localhost, 127.0.0.1, `[::1]`, https://localhost). Rojo antes (6 fallos), verde despues; el canario
sigue verde.

### 10. Motivo de la excepcion del canario para `discovery._get_json`

Sondeado antes de escribir: `discover()` llama `discover_ollama()` y `discover_litellm()` SIN argumentos
(`base` por defecto, localhost hardcodeado), y `resource_dispatcher.ollama_installed_models()` tambien usa
el default. Es decir: el `base` NO viene de CONFIG como decia el hallazgo; viene del default. El motivo
nuevo lo dice tal cual ("loopback por default: los llamadores de produccion (...) llaman con el `base` por
defecto (localhost); un llamador con otro `base` no cruza: limite conocido (el modelo fuera de la maquina
lo cubre el declarado del arranque)"). El docstring de `_get_json` acompana y el titulo de la seccion de
EXCEPCIONES dice "por config, por default o por construccion". Sin cruce nuevo.

Test: `test_aduana_canario.py::test_las_excepciones_apuntan_a_sitios_que_existen_y_que_no_cruzan_ya` y
`test_toda_salida_del_proceso_cruza_o_se_declara` siguen verdes (`12 passed`).

### 11. Motivo de la excepcion `calipso/tools/commands.py:run`

Verificado: `ALLOWLIST["test_memory"]` corre `test_memory.py`, que construye `memory.Memory(...)` (linea
24: SentenceTransformer -> huggingface.co) y llama `m.reflect(...)` (linea 58: `claude -p`). Motivo nuevo:
"subprocesos de la allowlist: git local y tests; `test_memory` sale a la red desde OTRO proceso
(test_memory.py construye Memory() -> huggingface.co y llama reflect -> `claude -p`), fuera de la aduana:
limite conocido, como los CLIs agentes". Mismo test que el punto 10.

### 12. `test_chat_live.py` ejecutaba al importar

Cambio: `asyncio.run(main(...))` y la resolucion de `MSG` bajo `if __name__ == "__main__":`; la lectura
del token real (`~/.calipso/token`) tambien sale del nivel de modulo (`_token()`, solo se llama desde el
guard: importar el archivo ya no lee nada de ~/.calipso). `main(TOKEN, MSG)` recibe ambos por parametro. El
docstring dice que es un script manual y que paso.

Verificacion (SIN correr el collect-only antes del fix, que habria disparado el mensaje):
`HOME=/nonexistent CALIPSO_TOKEN=bogus .venv/bin/python -c "import httpx, websockets; httpx.AsyncClient=None;
websockets.connect=None; import test_chat_live"` -> `importado sin correr` (si `main()` corriera,
reventaria con TypeError); `HOME=/nonexistent CALIPSO_TOKEN=bogus .venv/bin/python -m pytest
--collect-only -q test_chat_live.py` -> `no tests collected in 0.07s`, EXIT=5 (codigo de pytest para
"nada recolectado"). Sin conexion.

## Lo parkeado, tal cual quedo

No se toco: el detector completo en destino `afuera`, `leer()` bajo candado bloqueante, la lista negra de
git, `pr` con titulo + 2 lineas, el recorte del tablero, `/web/` en el canario, la duplicacion de la
derivacion de destino, `entro()` sin try. De "contadores sin lock" se hizo lo que el punto 1 permitia
(SIN_LIBRO y _DECLARADOS bajo `_ENTRE_HILOS`).

## Concerns para la re-review

- Punto 10: el hallazgo proponia el texto "loopback por config: `base` viene de CONFIG"; el codigo no lo
  sostiene (es el default hardcodeado en `discover` y en `resource_dispatcher`), asi que escribi el motivo
  honesto ("por default"). Si el controlador queria que `discover` leyera CONFIG, eso es un cambio de
  conducta que NO hice (el hallazgo pedia "arreglo minimo y honesto" sin cruce nuevo).
- Punto 8: el umbral "alfanumerico corto" quedo en `[A-Za-z0-9_\-]{1,12}`; es una eleccion mia (el
  hallazgo no fijo el numero). Un token pelado de 13+ chars o con `%`/`.` se tapa entero.
- Punto 6: `motivo` se sanea pero no se acota (el hallazgo acota solo `proposito` a 120); los motivos de
  hoy son nombres de modelo y de boca.
- Punto 7: el `test_sin_libro_viene_de_memoria_sin_tocar_el_disco` paso de `OSError("disco lleno")` a un
  OSError con errno/strerror/filename: con un OSError de un solo argumento (sin strerror) el texto queda
  solo "OSError", que es lo que la formula del hallazgo da.
- Punto 1: `test_declarar_una_vez_desde_n_hilos_declara_una_sola` ya pasaba antes del fix (con el GIL la
  ventana entre el check y el add no se ve en la practica): queda como guardia de regresion, no como
  reproduccion.
