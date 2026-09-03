# El jefe aprende de mis reacciones en la mesa

**Fecha:** 2026-09-03
**Estado:** brainstorming cerrado con Pedro; listo para su revision
**Origen:** item 3 de la cola de specs de la fabrica ("el no_siempre de la mesa"). La gramatica de proponer (la ficha tipada) es su prerequisito y ya esta en main. Ver [[project_calipso]].

## 1. Por que existe, y como cambio el modelo

El jefe de cada departamento propone trabajo a la mesa; Pedro financia o descarta. Hoy la mesa tiene **botones mudos**: `descartar` marca la propuesta terminada y escribe `descartadas_semana`, una senal blanda que (a) no frena nada en `jefe._puede` y (b) **se evapora cada semana** (`situacion.py` la filtra por `semana_descartada == semana`). El jefe no se entera del *por que* ni de *que queria* Pedro, y a la semana ya la olvido.

El planteo original de este item era un **veto tipado duro** que frenara en `jefe._puede`, espejando el `no_siempre` de permisos. Pedro lo reencuadro en el brainstorming: **no es ponerle reglas fijas, es que el jefe lo entienda y aprenda** — el jefe ya tiene contexto (Pedro, el proyecto, el departamento, de donde sale la idea), asi que puede aprender del feedback. El feedback es natural: desde "no me gusta" o "otro angulo" hasta "no mas".

Honestidad de ingenieria que fijo el diseno: el jefe corre en el **modelo local chico** (qwen 7b/3b) y la medicion de la Fase 1 mostro que **no es tan determinista** — una instruccion en el prompt se le puede olvidar en una generacion mala. Entonces "aprender del contexto" alcanza para el gusto general, pero para un **"no mas" definitivo** Pedro quiere garantia. De ahi el diseno de dos capas: aprendizaje (blando) + un piso determinista solo para el "no mas".

Que es "aprender" aca, dicho con precision: el jefe **no tiene memoria propia entre turnos** (es un modelo sin estado; no hay pesos que se actualicen). "Aprende" = su reaccion queda escrita como **contexto durable que el jefe lee cada vez que decide**. La calidad del aprendizaje depende de que tan bien quede escrita la reaccion y de cuanto contexto tenga.

## 2. Que decidio Pedro (brainstorming, 2026-09-03)

1. **Dos reacciones, las dos con palabras** (no botones mudos): `descartar` (blando, aprendizaje) y `no mas` (duro, el tema para). Pedro elige el boton; no se infiere la intensidad de sus palabras.
2. **Captura en la mesa** (no por chat): las palabras van atadas exacto a la propuesta y su forma. (Descartado por fragil: adivinar por chat a cual propuesta se refiere.)
3. **Identidad del "no mas" = el tema (`clave`), para el departamento que reacciono, ignorando `promete`/`tarda`.** Reencuadrar la promesa o el plazo esquiva el `descartar` blando (eso es la competencia), pero NO el `no mas` duro. (Descartado: la ficha exacta, que se esquiva cambiando "medir" por "acelerar".)
4. **El piso del "no mas" es un chequeo determinista por `clave`**, no un motor de reglas: la propuesta que sale se cae antes del bus si su `clave` coincide con algo vetado en ese departamento. (Descartado: solo-registro sin chequeo, porque el modelo chico se olvida.)
5. **Sin inferencia de intensidad, sin captura por chat, sin veto global entre departamentos, sin resumen/olvido del registro** en el MVP.

## 3. Arquitectura

Cuatro piezas, cada una testeable por separado:

- **El registro de reacciones** (`calipso/plantel/reacciones.py`, nuevo): almacen durable por departamento con lo que Pedro reacciono.
- **La captura** (endpoints de la mesa en `server.py`): `descartar` y una reaccion nueva `no mas`, las dos llevando texto; y `financiar` con texto opcional.
- **El uso** (`decision.py` / `situacion.py`): el jefe lee el registro en su prompt; reemplaza a `descartadas_semana`.
- **El piso** (la costura de decision del jefe, `jefe.py`): chequeo determinista por `clave` para lo vetado con "no mas".
- **La UI** (`calipso/web/fabrica/`): campo de texto en la reaccion + boton "no mas".

La `forma` tipada (`{sobre, clave, promete, tarda}`, donde `clave = ficha.normalizar(sobre)`) ya existe, se valida al escribir (`bus.alta`), se persiste por propuesta y ya llega tanto al jefe (`situacion["descartadas_semana"][i]["forma"]`) como a la mesa (`server.py` fila con `forma`). Este diseno la consume; no la reinventa.

## 4. El registro de reacciones (`calipso/plantel/reacciones.py`)

Almacen por departamento, al lado de la `carta.md`: `~/.calipso/memoria/departamento/<clave_dep>/reacciones.json`. Es una lista JSON (no JSONL) para poder reescribir atomico; el volumen es bajo (Pedro no reacciona mil veces).

Cada entrada:

```json
{
  "ts": "2026-09-03T10:00:00",
  "reaccion": "descarto | no_mas | financio",
  "forma": {"sobre": "...", "clave": "...", "promete": "...", "tarda": "..."},
  "palabras": "otro angulo, muy caro",
  "propuesta_id": "taller-1a2b3c4d"
}
```

API del modulo (puro respecto del dominio; solo toca su archivo):

- `anotar(dep: str, reaccion: str, forma: dict, palabras: str, propuesta_id: str) -> None`: appendea una entrada. `reaccion` en `{"descarto", "no_mas", "financio"}`. Escritura **atomica** (tmp + `os.replace`, via el escritor compartido `calipso/economia/candado.py`), nunca `write_text` pelado.
- `leer(dep: str) -> list[dict]`: las entradas del departamento, mas recientes al final. `[]` si el archivo no existe. **Fallo cerrado si esta corrupto** (present-but-illegible NO es lista vacia): levanta, para no perder un "no mas" y para no reescribir el archivo entero con una config vacia (el mismo pozo que el memory documenta en `librarian._save`/`config()`). Distinguir AUSENTE de ILEGIBLE, como `permisos._leer_solicitudes`, no como `permisos.config()`.
- `vetado(dep: str, clave: str) -> bool`: True si hay alguna entrada `reaccion == "no_mas"` con esa `clave` en ese departamento. Es el piso del punto 7.

**Disciplina de escritura (invariante de dominio que ya mordio dos veces):** `write_text` trunca en el lugar y el memory lo marca como trampa; se usa el escritor atomico compartido. Un archivo corrupto no cae a lista vacia en la lectura del piso (fallo cerrado), asi la siguiente escritura no se lo lleva por delante.

## 5. La captura (endpoints de la mesa)

En `calipso/server.py`, donde Pedro reacciona (hoy `api_eco_bus_descartar` y `api_eco_bus_financiar`):

- **Descartar con palabras:** `POST /api/economia/bus/{id}/descartar` gana un campo opcional `palabras` en el body. Sigue marcando la propuesta `descartada` en el bus (terminal, como hoy) y **ademas** llama `reacciones.anotar(dep, "descarto", forma, palabras, id)`, tomando `forma` de `bus.datos(id)["forma"]` y `dep` del departamento de la propuesta.
- **No mas (nuevo):** `POST /api/economia/bus/{id}/no-mas` con `palabras` opcional. Marca la propuesta `descartada` en el bus (terminal, igual que descartar: la propuesta puntual muere) y llama `reacciones.anotar(dep, "no_mas", forma, palabras, id)`. La diferencia con descartar es el tipo `no_mas`, que es lo que arma el piso.
- **Financiar con palabras:** `POST /api/economia/bus/{id}/financiar` gana `palabras` opcional; si viene, `reacciones.anotar(dep, "financio", forma, palabras, id)` ademas de financiar. Es senal positiva para el aprendizaje; opcional.

Guardas: si la propuesta no tiene `forma` (el pre-seed escribe con titulo de prosa y sin forma, a proposito), la reaccion se anota con `forma` vacia o `null` y el piso simplemente no la puede vetar por `clave` (no rompe). Los guardas de estado que ya existen (no descartar una financiada, etc.) se mantienen.

## 6. El uso: el jefe lee sus reacciones

`decision.prompt` (via `situacion()`) pasa a incluir un bloque nuevo con las reacciones durables del departamento, **reemplazando** la linea `descartadas_semana` de hoy:

- Se rinde honesto como *"Pedro reacciono asi a tus propuestas:"* seguido de las entradas (tema + tu palabra + el tipo). Es la **voz de Pedro**, no una conclusion del jefe: por eso el registro vive afuera del `core/` (adentro le llegaria bajo el titulo "Lo que aprendiste antes", una instruccion de Pedro rotulada como conclusion propia — el mismo motivo por el que la carta vive afuera del core).
- Las tres clases se muestran distinto: un `no_mas` se rinde como "NO MAS: <tema> (<palabras>)"; un `descarto` como "descarto: <tema> (<palabras>) -- proba otro angulo o soltalo"; un `financio` como "financio: <tema> (<palabras>)".
- `descartadas_semana` (la senal semanal que se evapora) se retira: el registro durable la subsume. Esto toca `situacion.py` (deja de armar `descartadas_semana`) y `decision.py` (lee el registro en vez de esa lista). Los tests que verifican la linea semanal se actualizan a la durable.
- Cuanto se muestra: las entradas del departamento, acotadas a las N mas recientes por reaccion si crecen mucho (poda simple por recencia; el resumen semantico es refinamiento posterior). Los `no_mas` se muestran siempre (son el piso; conviene que el jefe los tenga delante para no gastar turnos).

## 7. El piso del "no mas" (chequeo determinista)

En la costura de decision del jefe (`jefe.tic` / `jefe._puede`, donde la ficha ya se parseo a `forma` y una ilegible ya se desvio), cuando `accion == "proponer"`:

- Se toma la `clave` de la `forma` recien parseada.
- Si `reacciones.vetado(dep, clave)` es True, la propuesta **se cae antes de llegar al bus**: no hay `alta`. El jefe recibe una razon "eso lo vetaste, proba otra cosa" (por el mismo canal que las otras razones de `_puede`).
- Es un solo chequeo por **igualdad de `clave`** (ignora `promete`/`tarda`), reusando la identidad que ya calcula `ficha.normalizar`. No es un motor de reglas ni una config de Pedro: es un candado sobre lo que marco a proposito.

Es la garantia de "pare lo que sea": no depende de que el modelo honre el prompt. Reencuadrar la promesa o el plazo no lo esquiva, porque la `clave` sale solo del `sobre`.

**Fallo cerrado del piso:** si `reacciones.leer(dep)` no puede leer el archivo (corrupto), el chequeo del piso trata la decision como bloqueada para ese tic (el jefe no propone, se anota la corrupcion) en vez de dejar pasar sin poder confirmar que el tema no esta vetado. Es el lado seguro, como "un no ilegible niega todo" en permisos.

## 8. La UI en `/fabrica`

La mesa (cliente en `calipso/web/fabrica/`) gana, en cada fila de propuesta:

- Un **campo de texto** opcional para las palabras de la reaccion.
- El boton **"no mas"** junto a los de descartar/financiar. Descartar y no mas mandan `palabras` en el body; no mas pega a `/no-mas`.
- Feedback minimo al reaccionar (la fila desaparece de la mesa como hoy al descartar/financiar).

Sin panel nuevo de "ver/editar reacciones" en el MVP (eso seria el equivalente al `/mias` del compositor: refinamiento).

## 9. Invariantes

- **El "no mas" para de verdad.** El piso es determinista (igualdad de `clave`); no depende del humor del modelo local.
- **Reencuadrar esquiva el blando, no el duro.** El `descartar` invita a otro angulo; el `no mas` frena el tema en cualquier forma (identidad por `clave`, sin `promete`/`tarda`).
- **El feedback se muestra como voz de Pedro**, no como conclusion del jefe (vive afuera del `core/`).
- **El registro no se corrompe ni se pierde.** Escritura atomica; lectura que distingue AUSENTE de ILEGIBLE y falla cerrado ante corrupto (no reescribe con vacio, no pierde un veto).
- **El veto es por el departamento que reacciono**, no global (en la competencia, otro departamento puede intentar el tema).
- **Sin "no mas" ni reaccion con palabras, la fabrica se comporta como hoy** salvo que `descartadas_semana` pasa a ser el registro durable (misma senal, ahora persistente).

## 10. Lo que NO hace (fuera del MVP)

- **Inferir la intensidad** de las palabras de Pedro: el vota con el boton (descartar vs no mas).
- **Captura por chat** ("esa del taller no me convence"): solo la mesa.
- **Veto global** entre departamentos: el "no mas" es por el departamento que reacciono.
- **Resumen/olvido/poda semantica** del registro: crece; poda por recencia simple si hace falta, lo demas es refinamiento.
- **Panel de ver/editar/revocar reacciones** en `/fabrica`: como el `/mias` del compositor, va despues. (Nota: sin revocacion en UI, deshacer un "no mas" errado es editar el JSON a mano; se anota como el primer refinamiento.)
- **PvP** (item 4 de la cola): el registro de reacciones es insumo suyo, pero el scoring competitivo no entra aca.

## 11. Como se verifica que funciona

- **Captura:** `POST .../descartar` con `palabras` marca descartada Y escribe una entrada `descarto` con la `forma` y las palabras. `POST .../no-mas` escribe `no_mas`. `POST .../financiar` con `palabras` escribe `financio`. Una propuesta sin `forma` (pre-seed) no rompe la anotacion.
- **Registro:** `anotar` appendea; `leer` devuelve en orden; `leer` sobre archivo ausente da `[]`; `leer` sobre archivo corrupto **levanta** (no da `[]`); la escritura es atomica (no `write_text` pelado).
- **Uso:** `decision.prompt` incluye el bloque "Pedro reacciono asi" con las tres clases rendidas distinto; `descartadas_semana` ya no arma la linea vieja; los `no_mas` aparecen siempre.
- **Piso:** una propuesta cuya `clave` fue vetada con `no_mas` en ese departamento se cae antes del bus y el jefe recibe la razon; una `clave` distinta (mismo tema reencuadrado con otra promesa) NO se cae por el blando pero SI por el duro (misma `clave`); otra `clave` real pasa; un tema vetado en otro departamento NO frena a este; con el registro corrupto el piso falla cerrado (el jefe no propone ese tic).
- **UI:** la fila de la mesa muestra el campo de texto y el boton "no mas"; descartar/no mas mandan las palabras; los tests de cliente (`node --test`) cubren el armado del body.
- **No regresion:** la suite completa (`.venv/bin/python -m pytest -q`) queda verde; sin reaccionar, la fabrica corre igual.
