# El compositor aprende de lo que Pedro edita

**Fecha:** 2026-09-03
**Estado:** brainstorming cerrado con Pedro; listo para su revision
**Origen:** el smoke del compositor (2026-09-02) mostro que los borradores salen neutros porque el corpus de voz de Pedro son casi puras ordenes a Calipso, no texto suyo escrito para una persona. Pedro pidio que el compositor "aprenda hablando conmigo" -- que aprenda su voz real de lo que el corrige, no de un acento inventado ni de ejemplos que haya que sembrar a mano.

## 1. Por que existe

El compositor (`/redacta`, ya en main) escribe en la voz de Pedro imitando ejemplos de sus mensajes. Pero sus mensajes reales son casi todos ordenes ("dibujame un SVG", "que proyectos tengo"), no como le escribe a una persona -- asi que el modelo tiene poco de donde sacar su voz y arranca neutro (correcto: mejor neutro que un acento inventado).

Esta feature cierra el lazo: cuando Pedro **edita** un borrador (lo corrige y manda su version final), esa version es su voz de verdad para ese registro. Si Calipso la guarda, con el uso el corpus deja de ser puras ordenes y se vuelve texto real de Pedro escrito para personas. Ahi el borrador pasa de neutro a sonar a el -- porque aprendio de lo que el corrigio.

## 2. Que decidio Pedro (brainstorming, 2026-09-03)

1. **Un gesto en el chat**, sin UI nueva: Pedro pega su version final con **`/mia <texto>`** y Calipso la guarda como ejemplo fuerte de su voz. (Descartado: editar inline en /fabrica -UI nueva, difierida-; y "automatico despues de /redacta" -fragil-.)
2. **Se guarda en un almacen propio**, local, aparte de los chats.
3. **`voz` prioriza estos ejemplos** sobre los mensajes-orden de los chats: con pocos, los combina; a medida que se juntan, el corpus se vuelve puro-Pedro y las ordenes dejan de ensuciar.
4. **Sin etiqueta por registro** (amigo/cliente) en el MVP -- refinamiento. Sin listar/borrar ejemplos todavia.

## 3. El gesto `/mia`

`/mia` es una directiva nueva del chat (junto a `/redacta`, `/nube`...). Uso:

- **`/mia <texto>`**: Calipso guarda `<texto>` como un ejemplo de la voz de Pedro y confirma ("guardado como ejemplo de tu voz"). NO corre un turno de chat normal (no le responde, no rutea, no cobra).
- **`/mia` solo** (sin texto): Calipso avisa "pega tu version despues de /mia" y no guarda nada.

El texto es la version FINAL de Pedro -- la que de verdad mando, ya editada. Calipso redacta y no manda (ver invariantes), asi que Pedro es quien trae de vuelta su version; el gesto es explicito y de una linea.

## 4. El almacen de ejemplos de voz

Un archivo local en `CALIPSO_HOME` (p.ej. `voz_ejemplos.json`), una lista de `{texto, ts}`. Modulo chico (`calipso/compositor/ejemplos.py`) con:
- `guardar(texto: str) -> None`: appendea `{texto, ts}` (dedup: si el texto ya esta, no lo duplica).
- `cargar() -> list[dict]`: devuelve los ejemplos guardados.

Es del usuario y local: no se comparte entre proyectos ni sale de la maquina. No se toca en `/nube` (los ejemplos de estilo van crudos si Pedro pide la nube, como ya decidido para el compositor, pero eso es del slice de `/redacta /nube`, no de este).

## 5. Como `voz` los usa (prioridad)

`voz.ejemplos_de_voz` pasa a considerar dos fuentes y **prioriza los guardados**:
- Firma nueva: `ejemplos_de_voz(chats_data: dict, guardados: list = (), n: int = 6) -> list[str]`.
- Devuelve primero los `guardados` (los `/mia`, mas recientes por `ts`), y **rellena** hasta `n` con los mensajes de Pedro de los chats (recientes, sin triviales), sin duplicar.
- Asi: sin ningun `/mia`, se comporta igual que hoy (solo mensajes de chat). Con `/mia`, esos ejemplos van primero y, cuando hay `n` o mas, el corpus es puro-`/mia` y las ordenes ya no entran.

`preparar_borrador` (lo que corre el chat en `/redacta`) carga las dos fuentes (`chats._load()` + `ejemplos.cargar()`) y se las pasa a `voz`.

## 6. Invariantes

- **Calipso REDACTA, no manda.** Sigue igual: `/mia` solo GUARDA texto que Pedro trae; Calipso no manda nada por el.
- **Los ejemplos de voz son de Pedro y locales.** El almacen vive en `CALIPSO_HOME`, no sale de la maquina, no se comparte entre proyectos.
- **Sin `/mia` ni `/redacta`, el chat es identico a hoy.** La directiva nueva no cambia ningun turno normal.
- **El almacen no se corrompe.** `guardar` es append con dedup; un texto vacio no se guarda.

## 7. Lo que NO hace (fuera del MVP)

- **Etiqueta por registro** (`/mia amigo: ...`): refinamiento; por ahora todos los ejemplos son "voz de Pedro" a secas.
- **Listar/borrar ejemplos** (`/mias` para gestionarlos): despues.
- **Editar el borrador inline en /fabrica** (la otra opcion del brainstorming): descartada para este MVP.
- **Capturar la edicion automaticamente** (sin gesto): descartado por fragil.
- **Recuperacion semantica por registro** de los ejemplos: el MVP prioriza por recencia, no por parecido al hilo. Refinamiento.

## 8. Como se verifica que funciona

- **`/mia <texto>`** guarda el texto en el almacen y confirma; un `/redacta` posterior lo usa como ejemplo (verificado: el `system` del borrador contiene ese texto, y va ANTES que los mensajes-orden).
- **`/mia` solo** avisa y no guarda; el almacen no crece.
- **Prioridad:** con varios `/mia` guardados (>= n), `ejemplos_de_voz` devuelve solo esos (los mensajes-orden de los chats ya no entran). Con pocos, los combina, `/mia` primero.
- **Sin `/mia`,** `ejemplos_de_voz` se comporta identico a hoy (solo mensajes de chat).
- **Local:** el almacen vive en `CALIPSO_HOME`, no hay ninguna llamada de red al guardar.
- **Efecto real (smoke, con el server y Ollama vivos):** tras guardar un par de `/mia` con la voz real de Pedro, un `/redacta` produce un borrador que suena mas a el que el neutro de arranque.
