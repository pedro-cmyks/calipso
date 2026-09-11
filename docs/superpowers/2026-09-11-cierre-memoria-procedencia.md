# Cierre de la memoria con procedencia (2026-09-11): el porton en vivo, el smoke y lo que queda

Rama `feat/memoria-procedencia` (HEAD de la Task 4: `74c88f6`), sobre main `279dfb0`. Spec:
`docs/superpowers/specs/2026-09-11-memoria-con-procedencia-design.md`; plan:
`docs/superpowers/plans/2026-09-11-memoria-procedencia.md`. Lo que dijo Calipso es contexto, no evidencia:
guardar todo, decidir al leer. Este documento cierra las Tasks 1-4 con la evidencia en vivo de la Task 5:
el porton (antes / A / B), el smoke de escritura y reindex, y lo que queda para Pedro.

**Resumen en tres lineas.** El porton NO dio la salida limpia del spec (seccion 5): `sin_dato` cae como se
esperaba (4 -> 1 -> 0 sobre 8 turnos), `eco` por el flag es 0 en A y en B, pero `confabula` se duplica en las
dos (2 -> 4 -> 4) y en A hay un eco PARAFRASEADO de la frase fija que el flag no atrapa. Por el ruling 6 del
plan el aterrizaje formal de la variante no lo toma el implementador: queda para el ruling (abajo, con las dos
lecturas). El codigo sigue con `VARIANTE_DEFAULT = "A"`. El smoke de escritura y reindex PASA en sus 4 puntos.

## 1. El porton en vivo (antes / A / B)

`experimentos/porton_memoria.py`; resultados en `experimentos/porton_memoria_resultados.md` (el informe que
escribe el script) y `experimentos/porton_memoria_resultados.jsonl` (los 24 turnos con el texto COMPLETO,
los eventos `abismo`, la ruta, los ms y el sha del codigo de cada condicion).

Protocolo: fixture `experimentos/fixtures/memoria_smoke_home` RESTAURADO por condicion y por pasada, las 4
preguntas de memoria/chats del smoke del 09-10, chat nuevo por turno, N=2, server desechable (`uvicorn
calipso.server:app` en 127.0.0.1:8776, `CALIPSO_HOME` temporal, token aleatorio, `CALIPSO_NO_TOTP=1`), Ollama
real con `qwen2.5:7b`. `antes` es MAIN EXACTO (ruling 11, tomado por Pedro): el server de esa condicion se
levanto desde un worktree de main (`git worktree add --detach /tmp/calipso-main-porton main`, sha `279dfb0`,
cwd y `CALIPSO_ROOT` en el worktree, borrado al terminar); `A` y `B` desde la rama (`74c88f6`) con
`MEMORIA_PRESENTAR=A|B`. Clases: `dato` (la respuesta trae la verdad sembrada), `sin_dato` (`clasificar` lo
dice), `confabula` (ni una ni otra). Flags: `consulto` (evento `abismo` en el ws), `eco` (la respuesta
contiene `no tenia el dato`). El server real (8000) y `~/.calipso` no se tocaron (seccion 3, punto 4).

### Totales por condicion (copiados de `experimentos/porton_memoria_resultados.md`)

| condicion | turnos | dato | sin_dato | confabula | consulto | eco |
|---|---|---|---|---|---|---|
| antes | 8 | 2 | 4 | 2 | 1 | 0 |
| A | 8 | 3 | 1 | 4 | 3 | 0 |
| B | 8 | 4 | 0 | 4 | 3 | 0 |

### Por pregunta (pasada 1 / pasada 2)

| pregunta | antes (main) | A | B |
|---|---|---|---|
| libro | confabula / confabula | confabula / confabula | confabula / confabula |
| libro_rosa | sin_dato / sin_dato | dato / dato (consulto memoria) | dato (consulto memoria) / dato |
| presupuesto | sin_dato (consulto chats x3) / sin_dato | confabula (consulto memoria x3) / confabula (consulto memoria x2) | confabula (consulto memoria x3) / confabula (consulto memoria x3) |
| mariana | dato / dato | sin_dato / dato | dato / dato |

### Lo que se lee

1. **`sin_dato` cae, como prometia el spec:** 4/8 en main, 1/8 en A, 0/8 en B. `libro_rosa` es el caso
   limpio: en main el modelo repite "No tengo registros de quién te prestó el libro rosa" (h06: sus propios
   no-saber le vuelven como recuerdo); en A y en B contesta "Mariana Quintero te prestó el libro rosa" las
   cuatro veces, porque el episodio del 09-10 que SI pesco el dato ahora se presenta como
   `Calipso contesto (local, 2026-09-10): ...` y los no-saber vecinos ya no lo tapan.
2. **`eco` por el flag es 0 en A y 0 en B.** Por la letra de la regla del spec ("B solo si A muestra eco y B
   no"), el script escribe "Se aterriza A".
3. **Pero en A hay un eco parafraseado que el flag no atrapa.** `A` pasada 1, `presupuesto`, texto completo:
   "No teníamos el dato del presupuesto del taller registrado en ese momento. ¿Necesitas que busque más
   información sobre este tema?". Lo que el modelo vio en el system de ese turno (reconstruido con
   `_build_context` sobre el home de esa pasada, seccion 4) fueron dos vinetas
   `Calipso no tenia el dato entonces (local, 2026-09-10).` y contesto la parafrasis. `hay_eco` busca el
   prefijo exacto `no tenia el dato` (ruling 8: el flag depende de ese prefijo) y "no teniamos el dato" no lo
   contiene; `clasificar` tampoco lo atrapa (`no tengo (ese|el|ningun) dato` es en primera persona del
   singular), asi que ese eco quedo GUARDADO como `dato` y en el turno siguiente ya se presentaba como
   `Calipso contesto (local, 2026-09-11): No teníamos el dato...`. Es exactamente el bucle que la frase fija
   queria cortar, en su version parafraseada. En B (sin el renglon de Calipso) no hay nada que parafrasear y
   no aparece.
4. **`confabula` se duplica en A y en B (2 -> 4 -> 4), y todo el aumento esta en `presupuesto`.** La verdad
   ("120 dolares", "revisar en octubre") vive SOLO en `chats.json` (charla "Presupuesto del taller"); en la
   memoria episodica del fixture hay solo no-saber sobre el presupuesto. En main el modelo pesco `chats`
   (818 bytes: la charla con el dato) tres veces seguidas y aun asi contesto "No tengo registros" (h04: tres
   marcas a la misma fuente; y el dato pescado no le sirvio). En A y en B el modelo pesco `memoria` (5 de 5
   turnos, `tamano` 2000 = `ABISMO_BLOQUE_MAX`: el sub-bloque `recuerdos` desborda y `etiquetar` corta el
   bloque entero, el hallazgo del ruling 2 del ledger) y contesto: A1 el eco parafraseado del punto 3; A2 un
   eco de la propia pregunta con la letra de la reentrada ("En que quedamos la otra vez con el presupuesto
   del taller? Segui exactamente desde ahi, sin repetir."); B1 y B2 inventos ("aún no hemos llegado a un
   acuerdo definitivo", "ajustarlos según las necesidades del proyecto `mapa-ciudad`"). Con N=2 son dos
   turnos por condicion: no alcanza para decir si es el modelo o la presentacion, pero la direccion es la
   misma en las dos variantes y es la contraria a la esperada.
5. **`libro` confabula en las 6 pasadas de las 3 condiciones:** el fixture trae la confabulacion del 09-10
   ("un libro de ciencia ficción... trilogía ambientada en un futuro distópico") como episodio, `clasificar`
   la etiqueta `dato` (ruling del spec: una confabulacion no se detecta sin modelo) y las tres condiciones la
   presentan; el modelo la repite. No cambia con la procedencia: es lo que el spec deja fuera (seccion 6).
6. **`mariana`:** main 2/2, A 1/2 (en la pasada 1 pregunta "¿Hay algo específico de esa charla que
   necesites revisar?" en vez de contestar), B 2/2. Un turno; no se lee nada de ahi.

### El aterrizaje: ruling 6, no lo toma el implementador

La regla del spec (seccion 5) y del plan (decision 12) es mecanica sobre el flag `eco`: A. La lectura de los
textos dice otra cosa: A muestra un eco (parafraseado, 1/8) y B no, y `confabula` sube en las dos. Las dos
salidas del ruling 6 del plan ("eco en las dos; sin_dato que no baja; confabula que sube claramente") se
tocan: `confabula` 2 -> 4 sobre 8 turnos. Por eso **no se aterriza nada por cuenta propia**: el codigo
queda con `VARIANTE_DEFAULT = "A"` (lo que ya tenia) y la decision es de Pedro / del controlador, con estas
dos preguntas:

- **Cuenta el eco parafraseado como "A muestra eco"?** Si si, por el espiritu del spec gana B (B 0/8 ecos
  y 0/8 `sin_dato`), y el aterrizaje es el Step 3 de la Task 5 (`VARIANTE_DEFAULT = "B"` + la linea del
  test). Si se lee por el flag tal como esta escrito, queda A y no se toca codigo.
- **`confabula` 2 -> 4 (todo en `presupuesto`, cuya verdad esta en `chats.json` y no en la memoria) es
  "sube claramente"?** Si si, el spec pide parar y mirar antes de mergear; lo que se ve en los textos es que
  la procedencia le quito al modelo el "no tengo registros" heredado y, sin dato en la memoria, invento (B)
  o parafraseo la frase fija (A). Tres cosas que este cierre NO hace porque son rulings: sumar un patron
  para la parafrasis (`no teniamos el dato`, ruling 1: hay que medirlo contra el banco), presupuestar el
  sub-bloque `recuerdos` del abismo (ruling 2), o cambiar la letra de la frase fija (ruling 8).

## 2. El smoke: la escritura real y el reindex sobre un home que un server real escribio

Server desechable nuevo sobre el fixture restaurado (`/tmp/memoria-smoke-yxfx`, catastro con la raiz del
repo), la variante del codigo (sin `MEMORIA_PRESENTAR`: `A`), un solo turno `/local che, quien me presto el
libro rosa? no me acuerdo` (10.5 s, ruta `local/qwen2.5:7b`, sin consulta): "Entendido. Según mis registros,
Mariana Quintero te lo prestó al finalizar tu charla en agosto...". Server apagado antes de los chequeos.

1. **El episodio nuevo lleva la pregunta limpia y la procedencia. PASA.** `count 17, 1 con procedencia`;
   meta `{'modelo': 'qwen2.5:7b', 'ruta': 'local', 'route': 'local', 'chat': 'f3408caa670c', 'kind': 'chat',
   'ts': '2026-09-11T10:49:12', 'procedencia': 1}`; documento
   `'Pedro pregunto: che, quien me presto el libro rosa? no me acuerdo\nCalipso respondio: Entendido...'`
   (sin `/local`).
2. **El reindex sobre ese home. PASA**, con una precision: el chequeo del puerto es `CALIPSO_PORT` (default
   8000) y en esta maquina el server REAL de Pedro esta prendido en el 8000, asi que `--aplicar` a secas se
   nego ("el server responde en el puerto 8000: apagalo (o --forzar)", exit 2) aunque el desechable estaba
   apagado: correcto para el home real, ruido para un home de prueba. Con `CALIPSO_PORT=8776` (el puerto del
   server que sirve ESE home):
   - `--vista`: `global: 17 episodios, 1 con procedencia, 17 parsean como chat, 0 kind=chat que NO parsean,
     0 no chat, 5 sin_dato, 0 basura, 0 raros -> 16 por reindexar` y
     `projects/var-home-pedro-calipso: 0 episodios ... -> 0 por reindexar`, exit 0.
   - `--aplicar`: `global: 16 episodios reindexados; count 17 -> 17`, exit 0.
   - `--vista` de nuevo: `17 con procedencia -> 0 por reindexar`. `--aplicar` de nuevo: `global: nada que
     escribir (ya reindexado o sin pares de chat)`, exit 0 (idempotente).
   - Un episodio viejo tras el reindex: `{'ts': '2026-09-10T20:58:05', 'kind': 'chat', 'procedencia': 1,
     'ruta': 'local', 'route': 'local'}` (merge: las claves viejas siguen; `chat` y `modelo` ausentes).
   - Con el server PRENDIDO en el 8776 y `CALIPSO_PORT=8776`: `--aplicar` -> "el server responde en el
     puerto 8776: apagalo (o --forzar)", exit 2; `--vista` sigue contando (exit 0): ruling 7 del ledger.
3. **Lo presentado en un turno real. PASA.** `_build_context('quien me presto el libro rosa?', ...)` sobre
   ese home, bloque `Recuerdos relevantes`: vinetas `- Pedro dijo (2026-09-11): che, quien me presto el
   libro rosa? no me acuerdo` / `  Calipso contesto (local, 2026-09-11): Entendido. Según mis registros,
   Mariana Quintero...`, dos `- Pedro dijo (2026-09-10): ...` / `  Calipso no tenia el dato entonces (local,
   2026-09-10).`, y la confabulacion del libro como `Calipso contesto (local, 2026-09-10): ...`. Ninguna
   `Pedro pregunto:`, ninguna `/local` en el system entero (`False False`).
4. **El home real intacto. PASA con la lectura correcta:** el md5 de `ls -laR ~/.calipso` cambio entre antes
   y despues, y el diff de los dos listados dice por que: `catastro.json`, `consumo_*.json[l]` y
   `routines.json` con mtime 10:48:22, exactamente una hora despues del mtime anterior (09:48:22) -- la
   rutina horaria del server REAL de Pedro, que siguio corriendo en el 8000. Nada en `global/`, `projects/`,
   `chats.json` ni en ningun chroma. Ni el porton ni el smoke abrieron `~/.calipso`.

## 3. El banco y la suite

- Banco: `experimentos/no_saber_banco.py` -> `no-saber: 26/27 atrapados (96%); datos: 0/24 falsos` (el que se
  escapa es `cha-decision`, declarado).
- Suite completa antes del commit de este cierre: ver el reporte de la Task 5 (`0 failed`, `EXIT=0`).

## 4. Lo que queda para Pedro

- **El aterrizaje de la variante** (seccion 1): la regla mecanica dice A; los textos dicen que A parafrasea
  la frase fija y B inventa. Decidir A o B (o re-medir con N mayor; el porton corre en ~25 min:
  `.venv/bin/python experimentos/porton_memoria.py`).
- **El reindex del home real (decision 3 del spec, acto de Pedro):** con el server apagado, desde la raiz del
  repo, `.venv/bin/python -m calipso.memoria_reindex --vista` (mira los numeros: los `kind=chat que NO
  parsean` deberian ser 0; los ambitos de proyecto traen lo de junio-agosto con acentos rotos, que `partir`
  entiende), y si cierran, `.venv/bin/python -m calipso.memoria_reindex --aplicar`. Sin `CALIPSO_HOME`
  exportado va al `~/.calipso` real: es lo que se quiere ESA vez. Segunda corrida: `nada que escribir`. El
  server puede volver a arrancar en cualquier momento (dos clientes no corrompen nada; el chequeo del puerto
  es por completitud del recorrido). `--vista` se puede correr con el server prendido (ruling 7).
- **Los hallazgos del porton que piden ruling** (seccion 1): la parafrasis del no-saber que los patrones no
  atrapan (`no teniamos el dato`; sumarla es tocar `PATRONES_FUERTES` y correr el banco), el sub-bloque
  `recuerdos` del abismo al techo de 2000 en 5 de 5 consultas a `memoria` (ruling 2), y el modelo que
  pesca `chats` con el dato adentro y lo ignora (main, `presupuesto`, 3 veces: h04 + un fallo de lectura).
- Los departamentos (`memoria/departamento/*/chroma`) no se reindexan (spec).
- `reflect`/`recent` siguen leyendo el documento crudo (fuera del alcance, spec seccion 6).

## 5. Como se reproduce

```bash
cd /var/home/pedro/calipso
curl -s http://127.0.0.1:11434/api/tags | jq '.models[].name'          # qwen2.5:7b
.venv/bin/python experimentos/porton_memoria.py                         # N=2, antes,A,B: 6 servers, 24 turnos, ~25 min
.venv/bin/python experimentos/porton_memoria.py --n 1 --condiciones A,B  # mas corto
```

El script levanta el worktree de main en `/tmp/calipso-main-porton` para `antes` y lo borra al terminar; se
niega si el directorio ya existe, si algo escucha en el 8776 o si Ollama no tiene el modelo. El smoke de la
seccion 2 son los comandos del Step 4 de la Task 5 del plan, con dos correcciones: el `catastro.json` del home
de prueba declara la raiz del repo (con `raices: []` ningun chat se puede crear: `POST /api/chats` pasa por
`_switch_project(ROOT)`, que exige una raiz), y el reindex se corre con `CALIPSO_PORT` en el puerto del server
desechable.
