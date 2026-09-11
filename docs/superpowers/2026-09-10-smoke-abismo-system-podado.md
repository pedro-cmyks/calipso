# Smoke en vivo: el system local podado y la letra con senales (2026-09-10)

Server desechable (`uvicorn calipso.server:app` en 127.0.0.1:8773, `CALIPSO_HOME` temporal, token aleatorio,
`CALIPSO_NO_TOTP=1`, codigo de la rama `feat/abismo-system-podado` HEAD `1b2d734`), Ollama real con
`qwen2.5:7b`. Home sembrado como en el smoke del 1b: `catastro.json` copiado del real (2 repos: calipso,
Observatory-Global), `global/core/pedro-perfil.md` con tres lineas, `chats.json` con tres conversaciones
viejas ("Libros de agosto": El nombre de la rosa; "Charla con Mariana": Mariana Quintero presto el libro
rosa; "Presupuesto del taller": techo de 120 dolares, revisar en octubre). Cliente: un script ws que manda
cada mensaje y registra los eventos `abismo` (pondering / pescado / fallo), la ruta y el texto.

Ocho mensajes, todos con `/local`: seis positivos (2 memoria, 2 chats, 2 proyecto) y dos negativos
("buen dia! como va todo?", "explicame en dos lineas que es un websocket"). Dos pasadas: **con historial**
(los ocho en el mismo chat, como conversa Pedro) y **con chat nuevo por turno** (sin historial, como mide el
banco). El server real no se toco.

## La pregunta del smoke: el 7b emite la marca solo?

En el smoke del 1b (2026-09-08), con el system de produccion viejo: **0 marcas en 6 turnos naturales**.

| turno | con historial | chat nuevo por turno |
|---|---|---|
| "hola, que libro te conte que empece?" | **3 marcas** memoria (las tres `vacio`) | **1 marca** memoria, pescado |
| "che, quien me presto el libro rosa? no me acuerdo" | 0 | **1 marca** memoria, pescado |
| "en que quedamos la otra vez con el presupuesto del taller?" | 0 | **1 marca** memoria, pescado |
| "retoma lo que dejamos sobre mariana, la charla de agosto" | **1 marca** chats, **pescado y contestado con el bloque** | 0 (el dato ya venia en los recuerdos del system: ver abajo) |
| "como viene el repo de calipso, en que rama esta y que se toco ultimo?" | 0: el turno se fue al ORQUESTADOR (362 s) | 0: idem (335 s) |
| "dame el detalle del proyecto mapa-ciudad" | **1 marca** proyecto (`error`: el repo no esta en el catastro sembrado; correcto) | 0 |
| "buen dia! como va todo?" (negativo) | 0 | 0 |
| "explicame ... websocket" (negativo) | 0 | 0 |

**PASA lo que el aterrizaje promete:** el 7b emite la marca por su cuenta en turnos naturales (5 de 12
positivos-turno marcaron, contra 0 de 6 antes), rutea bien la fuente en cada caso (memoria para "te conte",
chats para "lo que dejamos... charla de agosto", proyecto para "detalle del proyecto"), no marca en los
negativos (0 de 4), y **la pesca de punta a punta funciono sin pedirsela**: "retoma lo que dejamos sobre
Mariana" corto el stream, pesco 294 bytes de `chats.json` y contesto con el fragmento real de la charla.
La marca jamas llego a disco (`⟦` cero veces en `chats.json`; "Lo que subio" cero veces en chats y telemetria).

## Lo que el smoke encontro y NO es del cambio de hoy (queda para Pedro)

1. **h06, el mas importante: la fuente `memoria` del abismo le devuelve al modelo SUS PROPIAS RESPUESTAS
   anteriores como recuerdos.** Cada turno se guarda como un episodio `"Pedro pregunto: ... / Calipso
   respondio: ..."` (`server.py:4024-4028`) y `fuentes.memoria` hace recall sobre esos episodios
   (`fuentes.py:110-118`). Verificado con `Memory.recall` sobre el home del smoke: para "quien me presto el
   libro rosa" los cinco primeros hits son turnos de este mismo smoke, encabezados por "Calipso respondio:
   Entiendo. No tengo registros de quien te presto...". En la segunda pasada el 7b consulto memoria, recibio
   eso como bloque, y repitio "no tengo registros" **con la consulta hecha**; en el turno 1 fresco construyo
   una confabulacion ("un libro de ciencia ficcion que comenzamos a leer juntos") sobre su propia respuesta
   anterior. Es la misma enfermedad que el smoke del 1b vio como "copio VERBATIM la respuesta de opus que la
   memoria episodica le puso en el prompt", y afecta tambien a los 4 "Recuerdos relevantes" del system de
   cada turno. Cuanto mas falla, mas fallos recuerda. **Decision de modelo para Pedro:** que las respuestas
   de Calipso no sean memoria consultable (solo las palabras de Pedro entran al episodio, o el episodio se
   guarda partido y el recall del abismo y del system solo devuelven la parte de Pedro). No es de este
   cambio ni del plan de la aduana.
2. **El orquestador secuestra las preguntas sobre repos** ("como viene el repo de calipso, en que rama
   esta...") por la heuristica de complejidad: 335-362 s de equipo dinamico que termina en "No pude
   completar la sintesis automatica", sin que el abismo llegue a intervenir. Ya paso en el smoke del 1b
   (3.3). Es del ruteo, no del abismo.
3. **Un recuerdo con el dato apaga la consulta, y esta bien:** en la segunda pasada, "retoma lo que
   dejamos sobre Mariana" no marco porque el turno de la primera pasada (que si pesco) quedo como episodio y
   el recall lo puso en el system; el modelo contesto desde ahi. La consulta es el regimen del medio, no un
   reflejo: si el dato ya esta en el prompt, no hace falta pedirlo.
4. **Memoria vacia = tres marcas seguidas a la misma fuente** (turno 1 con historial: memoria `vacio` x3
   hasta el tope). El tope de 3 por turno funciona; que el modelo reintente la misma fuente vacia en vez de
   cambiar de fuente es una mejora posible de la letra o de la reentrada ("memoria no tenia nada: proba
   chats") que NO se midio y no entra hoy.

## Veredicto

El aterrizaje queda validado en vivo para lo que se midio y prometio (emision de la marca en turnos
naturales, ruteo, cero espurias, pesca de punta a punta sin pedirsela). El h06 es lo que decide cuanto vale
la consulta a `memoria` de aca en adelante, y es de Pedro.
