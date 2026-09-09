# El contrato del abismo dentro del system de produccion: la posicion no alcanza

**Fecha:** 2026-09-08, cierre de la rama `feat/abismo-1b` (hallazgo h05 del smoke: `qwen2.5:7b` por la ruta
local no emite la marca por su cuenta -- 0 marcas en 6 turnos naturales, una confabulacion, un pedido de permiso).
**Hipotesis del hallazgo:** el contrato vive como cuarta de diez secciones y no al final del system, como en el
banco que midio su letra. **Metodo:** el protocolo del porton (banco v2 de 30 items, temp 0, `/api/generate`, un
prompt sin historial) sobre el system de PRODUCCION armado por `_build_context` con una copia del home del smoke
(catastro real de 3 repos, core y chats sembrados; `num_ctx` 8192, el de produccion), en tres posiciones del
bloque -letra byte-identica- mas el control del banco. N=2 por item (screening; el porton definitivo es N=6).
Script: `consulta_abismo_posicion.py`; cache crudo: `consulta_abismo_posicion_produccion.jsonl`.

## La tabla

| Variante | memoria | chats | proyecto | espurias | ruteo | copia literal del molde | latencia mediana |
|---|---|---|---|---|---|---|---|
| banco | 10/12 (83%) PASA | 12/12 (100%) PASA | 12/12 (100%) PASA | 2/24 (8%) | 32/34 | 22/34 | 3089 ms |
| actual | 2/12 (17%) NO | 6/12 (50%) NO | 2/12 (17%) NO | 0/24 (0%) | 9/10 | 5/10 | 5235 ms |
| final | 5/12 (42%) NO | 5/12 (42%) NO | 2/12 (17%) NO | 0/24 (0%) | 12/12 | 6/12 | 6318 ms |
| primero | 4/12 (33%) NO | 8/12 (67%) NO | 4/12 (33%) NO | 0/24 (0%) | 14/16 | 12/16 | 5264 ms |

Piso del porton: >= 5/6 por fuente en positivos, espurias <= 1/6, ruteo >= 90% de las legibles.

## Por item (corridas con marca legible, de 2)

| item | banco | actual | final | primero |
|---|---|---|---|---|
| cha-agosto | 2/2 | 2/2 | 2/2 | 2/2 |
| cha-decision | 2/2 | 0/2 | 0/2 | 0/2 |
| cha-idea | 2/2 | 0/2 | 0/2 | 0/2 |
| cha-link | 2/2 | 2/2 | 1/2 | 2/2 |
| cha-nombre | 2/2 | 2/2 | 2/2 | 2/2 |
| cha-receta | 2/2 | 0/2 | 0/2 | 2/2 |
| mem-fecha | 2/2 | 0/2 | 0/2 | 0/2 |
| mem-gustos | 0/2 | 0/2 | 0/2 | 0/2 |
| mem-libro | 2/2 | 0/2 | 1/2 | 0/2 |
| mem-medico | 2/2 | 0/2 | 0/2 | 2/2 |
| mem-pref | 2/2 | 0/2 | 2/2 | 0/2 |
| mem-rutina | 2/2 | 2/2 | 2/2 | 2/2 |
| pro-brief | 2/2 | 2/2 | 2/2 | 2/2 |
| pro-commit | 2/2 | 0/2 | 0/2 | 0/2 |
| pro-detalle | 2/2 | 0/2 | 0/2 | 0/2 |
| pro-estado | 2/2 | 0/2 | 0/2 | 0/2 |
| pro-rama | 2/2 | 0/2 | 0/2 | 0/2 |
| pro-ultimo | 2/2 | 0/2 | 0/2 | 2/2 |

## Que dice

1. **El entorno reproduce el porton v2 hoy.** El control (`banco`) da memoria 83%, chats 100%, proyecto 100%,
   espurias 8%: los mismos numeros del 2026-09-07. No cambio el modelo ni Ollama; cambio lo que rodea al contrato.
2. **Dentro del system de produccion la letra medida no se sostiene, en NINGUNA posicion.** Como esta (`actual`):
   memoria 17%, chats 50%, proyecto 17% -- los numeros de la linea base v1 (534c) que NO PASO, o sea que el system
   de produccion le borra al contrato la mejora entera. Al final (`final`, la hipotesis de h05): 42 / 42 / 17.
   Al principio (`primero`): 33 / 67 / 33. Ninguna se acerca al piso de 5/6. Las espurias quedan en 0 en las tres:
   el 7b bajo el system de produccion no marca de mas; casi no marca.
3. **Lo que compite no es la posicion, es el resto del system** (7.4k chars contra 687 del banco): la Constitucion
   (3000), la memoria nucleo, las otras diez instrucciones del "Contrato interno" ("Traduce el pedido natural de
   Pedro a una tarea clara antes de responder", "Usa memoria como contexto probabilistico", ...), proyectos,
   economia. En los positivos fallidos el 7b pide detalles ("cuentame mas sobre tu hermana"), contesta que no
   tiene el dato ("No tengo registros especificos sobre tu ultima rutina", la confabulacion de ausencia que el
   contrato prohibe) o sigue OTRA instruccion al pie de la letra (en `final`/mem-medico arranca un JSON con
   `"tipoDeTarea": "chat", "traduccion": ...` y se pasa al chino). Ver `salida` en el JSONL.
4. **Hallazgo lateral sobre la metrica del porton:** de las 34 marcas legibles del control, 22 son la COPIA LITERAL
   del molde del contrato (`⟦abismo:memoria pregunta⟧`, `⟦abismo:chats palabras, opcional desde:...⟧`,
   `⟦abismo:proyecto nombre⟧`). Son marcas VALIDAS para `marca.parsear` (fuente conocida, resto no vacio) y en
   produccion dispararian una pesca por la palabra "pregunta" o "palabras". El porton mide "emite una marca
   legible", no "emite una marca util": el 83/100/100 del v2 esta inflado por el loro. Las no literales son
   pocas y buenas (`⟦abismo:proyecto atlas⟧`, `⟦abismo:chats desde:2026-08 hasta:2026-09⟧`).

## Que NO se hizo, y por que

No se movio el bloque de lugar: la medicion no lo justifica (chats empeora al final, nada llega al piso) y mover
algo medido sin que los numeros lo pidan es churn. El cableado del 1b esta bien; la promesa "ante la duda,
CONSULTA" no se sostiene en la ruta local con el system de produccion. Es la bifurcacion que el spec (seccion 12)
reserva para Pedro con los numeros en la mano: refinar el indice (o el system entero: podar lo que compite,
re-medir el porton SOBRE el system de produccion y no sobre el del banco), cablear la consulta solo en rutas
grandes (suscripcion/API, donde Opus la emitio sola en el primer turno del smoke), o aceptar el regimen actual
(la consulta local funciona cuando Pedro la pide con todas las letras) hasta la rebanada 2. Y una cuarta cosa
para el porton, sea cual sea la salida: contar como legible SOLO la marca que no copia el molde.
