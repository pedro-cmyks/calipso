# El PvP — rendicion de cuentas de las promesas

**Fecha:** 2026-09-03
**Estado:** brainstorming cerrado con Pedro; listo para su revision
**Origen:** item 4 (el ultimo) de la cola de specs de la fabrica. La gramatica de proponer (item 1), que los departamentos propongan (item 2) y el no_siempre + el registro de reacciones (item 3) ya estan en main. Ver [[project_calipso]].

## 1. Por que existe, y el hueco que llena

La fabrica tiene departamentos con billetera, un jefe que propone trabajo a un bus, y una mesa donde Pedro financia o descarta. Una propuesta lleva una **ficha tipada** con `promete` (una de seis promesas, cada una con su METRICA) y `tarda` (el plazo). El item 4 —el PvP— es la competencia entre departamentos: prometer algo medible con plazo y que despues **se vea si cumplio**.

**El hueco, medido en el codigo (2026-09-03):** hoy NADA mide si un trabajo financiado cumplio su promesa.
- El unico evaluador de trabajo financiado, `bus.evaluar_y_liquidar_muertos` (`calipso/economia/bus.py:731-803`), lee SOLO el `criterio` (`gasto_max_mm`, `semanas_max`): un trabajo *muere* por pasarse de presupuesto o de plazo, y se liquida devolviendo el resto pro-rata. Nunca lee `forma`/`promete`.
- La METRICA de exito **no se guarda**: se deriva de `promete` cada vez que se muestra (`server.py:4301-4313`). Es prosa de pantalla.
- El propio bus lo dice (`bus.py:815-817`): *"vara y lugares van en None porque el PvP es otro plan, y porque hoy la mesa no tendria con que comparar: `retorno_mm` es una copia literal de `presupuesto_mm`"*. Y no hay ninguna **frontera de ejecucion** que produzca un resultado medible: el trabajo financiado solo retiene plata en `trabajo:<id>`, gasta, y se liquida por timeout.

O sea: **"ver si cumplio" es el hueco que el PvP llena.** Y como no hay medicion automatica de la entrega, el juez es Pedro.

## 2. Que decidio Pedro (brainstorming, 2026-09-03)

1. **Pedro juzga la entrega.** Cuando el plazo de una promesa vence, Calipso se la trae ("el taller prometio X, cumplio?") y Pedro marca **cumplio / no cumplio**. La rendicion de cuentas es HACIA PEDRO. (Descartado: medicion automatica de la METRICA -necesita una frontera de ejecucion que no existe, es otro proyecto-; y "solo por ser elegido en la mesa" -no juzga la entrega-.)
2. **El veredicto pesa como REPUTACION, no como plata.** Arma un standing por departamento (cumplio N de M). El jefe lo ve en su prompt (aprende a prometer lo que puede cumplir); Pedro lo ve en la mesa al lado de cada propuesta (financia con el historial a la vista). El premio/castigo es la proxima decision de plata de Pedro, informada. (Descartado en el MVP: mover plata sola -toca la solvencia, mas dientes pero mas riesgo-; y "solo un registro" -no cierra el lazo de competencia-.)
3. **Almacen nuevo `promesas.py`**, hermano de `reacciones.py`, no tipos nuevos en reacciones: es otro eje (la entrega, no el gusto sobre la propuesta), aunque copia sus disciplinas.
4. **Sin plata automatica, sin leaderboard/reordenar la mesa solo, sin medicion automatica, sin panel de revocar** en el MVP.

## 3. Arquitectura

Cinco piezas, cada una testeable por separado:

- **El almacen de veredictos** (`calipso/plantel/promesas.py`, nuevo): por departamento, al lado de la carta.
- **Detectar lo vencido** (`calipso/economia/bus.py` o un helper): un trabajo financiado con `forma`, cuyo plazo vencio, y sin veredicto todavia.
- **La superficie de juicio** (endpoints de la mesa en `server.py`): la seccion "por juzgar" y los endpoints `cumplio`/`no-cumplio`.
- **El standing** (`promesas.py` derivacion): "cumplio N de M", leido por el jefe (su prompt) y por la mesa (al lado de cada propuesta).
- **La UI** (`calipso/web/fabrica/`): la seccion "por juzgar" y el standing en la fila.

La `forma` tipada (`{sobre, clave, promete, tarda}`) ya existe y se persiste en el bus; el plazo sale de `ficha.SEMANAS_MAX[tarda]`; las semanas transcurridas de `bus.semanas_transcurridas(ops, semana_financiada, semana)`. Este diseno las consume; no las reinventa.

## 4. El almacen de veredictos (`calipso/plantel/promesas.py`)

Almacen por departamento, al lado de la carta y de las reacciones: `~/.calipso/memoria/departamento/<clave>/promesas.json`. Lista JSON, escritura atomica, lectura fallo cerrado. Mismas disciplinas que `reacciones.py` (y el mismo `_slug` que `memory._slug`, sin importar memory para no arrastrar chromadb al jefe).

Cada veredicto:

```json
{
  "ts": "2026-09-03T10:00:00",
  "propuesta_id": "atlas-1a2b3c4d",
  "forma": {"sobre": "...", "clave": "...", "promete": "medir", "tarda": "corto"},
  "cumplio": true,
  "palabras": "tarde pero cumplio"
}
```

API del modulo (puro respecto del dominio; solo toca su archivo):
- `anotar(nombre: str, propuesta_id: str, forma: dict, cumplio: bool, palabras: str) -> None`: appendea un veredicto. Atomico. Dedup por `propuesta_id` (un trabajo se juzga UNA vez; un segundo veredicto sobre el mismo id no duplica -- gana el primero, o se ignora el segundo).
- `leer(nombre: str) -> list[dict]`: los veredictos del depto, mas viejos primero; `[]` si ausente; **levanta `ErrorPromesas`** si corrupto.
- `juzgada(nombre: str, propuesta_id: str) -> bool`: True si ese trabajo ya tiene veredicto (para no volver a traerlo a "por juzgar").
- `standing(nombre: str) -> dict`: `{"cumplidas": int, "total": int}` derivado de los veredictos. `{"cumplidas": 0, "total": 0}` si no hay ninguno.

## 5. Detectar lo vencido (que entra a "por juzgar")

Un trabajo entra a "por juzgar" cuando, a la vez:
- es `tipo == "trabajo"` (no preseed) y tiene `forma` con `promete`/`tarda` (una promesa de verdad);
- **fue financiada** (fue elegida en la mesa): tiene `semana_financiada` en `bus.datos(id)`. Se pregunta por `semana_financiada` y NO por el estado actual A PROPOSITO, para que juzgar sea independiente de la liquidacion: un trabajo que ya paso a `liquidada` conserva su `semana_financiada` y sigue siendo juzgable; si se pidiera `estado == "financiada"`, correr el cierre lo sacaria de "por juzgar" y romperia el invariante de la seccion 9;
- **su plazo vencio**: `bus.semanas_transcurridas(ops, semana_financiada, semana_actual) >= ficha.SEMANAS_MAX[forma["tarda"]]`;
- **no tiene veredicto todavia**: `not promesas.juzgada(nombre, propuesta_id)`.

Esto se calcula al vuelo cuando se arma la mesa (como ya se calcula el estado de cada propuesta), y es INDEPENDIENTE de la liquidacion (que en la maquina de Pedro esta apagada: el trabajo no se auto-muere, pero su plazo igual vencio y se puede juzgar; y si el cierre se prendiera, el trabajo liquidado conserva `semana_financiada` y se sigue pudiendo juzgar). El nombre del departamento sale del `departamento` del bus SIN el prefijo `dep:` (igual que las reacciones y la carta: `dep.split(":",1)[1] if ":" in dep else dep`).

## 6. La superficie de juicio (endpoints de la mesa)

En `calipso/server.py`:
- **La mesa (`api_eco_bus`) gana una lista `por_juzgar`**: los trabajos vencidos sin veredicto (seccion 5), cada uno con su `id`, `departamento`, `titulo`, la `forma` y la METRICA (para que Pedro vea que se prometio).
- **`POST /api/economia/bus/{id}/cumplio`** y **`POST /api/economia/bus/{id}/no-cumplio`**, con body `{palabras?}` (espeja `MesaNoMasBody`). Cada uno deriva `nombre`/`forma` de `bus.datos(id)` y llama `promesas.anotar(nombre, id, forma, cumplio, palabras)`. Guarda: si el trabajo no esta vencido o ya tiene veredicto, 400 (no se juzga dos veces ni antes de tiempo). Un `promesas.ErrorPromesas` (registro corrupto) se surfacea como 400.
- El marcado NO toca el bus ni el libro: el trabajo sigue su ciclo de vida economico (financiada -> liquidada) por su lado; el veredicto es solo reputacion.

## 7. El standing: donde se ve

- **En el prompt del jefe** (`decision.py` via `jefe.tic`, como las reacciones): un renglon *"Tu historial de promesas: cumpliste N de M"* (de `promesas.standing(nombre)`), para que aprenda a prometer lo que puede cumplir. Se lee con fallo cerrado (si el registro esta corrupto, el jefe no propone ese tic, igual que con las reacciones). Se muestra como hechos, no como conclusion del jefe (afuera del `core`).
- **En la mesa** (`api_eco_bus`), al lado de cada propuesta: el `standing` del departamento que la propone (`{"cumplidas": N, "total": M}`), para que Pedro financie con el historial a la vista.

## 8. La UI en `/fabrica`

- La mesa gana la **seccion "por juzgar"**: cada trabajo vencido con lo que prometio (la METRICA) y dos botones **cumplio / no cumplio** + un campo de palabras opcional (mismo patron que las reacciones de la seccion anterior).
- En cada fila de propuesta, el **standing del departamento** ("3/5 cumplidas") al lado del nombre.
- Sin panel de ver/editar/revocar veredictos (refinamiento, como el `/mias` del compositor).

## 9. Invariantes

- **El veredicto no mueve plata.** Es reputacion; la liquidacion (presupuesto/tiempo) queda intacta y separada.
- **Un trabajo se juzga una vez.** Dedup por `propuesta_id`; no se juzga dos veces ni antes de que venza el plazo.
- **Los preseed no se juzgan.** No prometen nada (forma nula); nunca entran a "por juzgar".
- **El standing es la voz de los hechos, no del jefe.** Vive afuera del `core/` (como la carta y las reacciones).
- **El registro no se corrompe ni se pierde.** Atomico; lectura distingue AUSENTE de ILEGIBLE y falla cerrado.
- **Juzgar es independiente de la liquidacion.** El plazo vencido se calcula de las semanas, ande o no el cierre.
- **El nombre del departamento se deriva sin el prefijo `dep:`** (misma trampa que ya mordio en reacciones: el bus guarda con prefijo, la carta/registro sin).
- **Sin promesas juzgadas, la fabrica se comporta como hoy** (el standing es 0 de 0, el prompt no muestra el renglon, la mesa no tiene "por juzgar").

## 10. Lo que NO hace (fuera del MVP)

- **Mover plata por el veredicto** (premio/penalidad automatica): Pedro eligio reputacion; la plata queda como su decision informada. Refinamiento con mas dientes, despues.
- **Leaderboard / reordenar la mesa por standing**: el `vara`/`lugares` del bus siguen en None; Pedro compara los standings al decidir. Ordenar es refinamiento.
- **Medir la METRICA automaticamente**: no hay frontera de ejecucion; construirla es otro proyecto. Pedro juzga.
- **Panel de ver/editar/revocar veredictos** en `/fabrica`: despues.
- **Juzgar preseeds u otras cosas sin promesa**: solo trabajos con `forma`.

## 11. Como se verifica que funciona

- **Almacen:** `anotar` appendea; `leer` ausente da `[]`, corrupto **levanta**; `juzgada` es True tras anotar; `standing` cuenta cumplidas/total; dedup por `propuesta_id` (un segundo veredicto no duplica); escritura atomica (sin `.tmp` tirado).
- **Vencido:** un trabajo con `forma` financiado hace `SEMANAS_MAX[tarda]` semanas o mas, sin veredicto, entra a "por juzgar"; uno mas nuevo NO; un preseed NO; uno ya juzgado NO.
- **Endpoints:** `POST .../cumplio` anota `cumplio=True` con las palabras; `.../no-cumplio` anota `False`; juzgar un no-vencido o un ya-juzgado da 400; un registro corrupto da 400; el bus/libro no se tocan.
- **Standing:** `decision.prompt` incluye "cumpliste N de M" cuando hay veredictos y lo omite cuando no; la mesa (`api_eco_bus`) trae `standing` por propuesta y la lista `por_juzgar`.
- **UI:** la mesa muestra la seccion "por juzgar" con los botones y el campo, y el standing al lado de cada propuesta; los tests de cliente (`node --test`) cubren el render y el armado del body.
- **No regresion:** la suite completa (`.venv/bin/python -m pytest -q --ignore=test_chat_live.py`) queda verde, mas el cliente; sin juzgar nada, la fabrica corre como hoy.
