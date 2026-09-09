# Cierre de la rama feat/abismo-1b (2026-09-08)

El ritual de cierre de rama (plan `docs/superpowers/plans/2026-09-08-abismo-1b-cableado.md`, Task 13),
con los informes tal cual los produjeron los agentes:

- `revision-final.md`: la revision de merge de la rama entera contra el spec, con el triage de los minors
  diferidos por task (tres "deben cerrarse antes del merge", el resto "pueden esperar").
- `adversaria-eficacia.md`: 35 sondas contra las nueve invariantes del spec (las 18 obligatorias del brief
  mas las que el codigo sugirio). Cedieron tres cosas Important, todas cerradas en la ola de fix: el filtro
  con estado en la ruta one-shot truncaba en silencio; una reinvocacion del CLI que fallaba cerraba el turno
  con el tramo a medias; la fuente `chats` pescaba el chat activo y la propia pregunta.
- `adversaria-regresiones.md`: 10 sondas sobre lo que ya funcionaba (steer sin marcas byte a byte, /redacta,
  /team, fallbacks, goals, adjuntos, /nube sin marcas, /stop). Nada roto.
- `adversaria-completitud.md`: tabla promesa por promesa del spec y del plan. Ninguna promesa falta.
- `ola-de-fix.md` y `re-review.md`: los ocho commits `35ef0d4..7011b9b` que cerraron h01-h04 y los tres
  must-fix (entre ellos h02: una marca ilegible anidada dentro de otra armaba, al retirarse, una marca VALIDA
  que salia visible y se persistia; el filtro ahora relee hasta punto fijo), y su verificacion acotada.
- `re-smoke.md`: el smoke abreviado tras la ola. El smoke completo esta en `../2026-09-08-smoke-abismo-1b.md`.
- `ledger.md`: la ejecucion entera, task por task: rulings del controlador, minors diferidos, rondas de fix.

Los 33 hallazgos crudos se unificaron en 25; los cinco Important pasaron por tres refutadores
independientes cada uno (ninguno cayo). Suite al cierre: 1470 passed; node 412.

## Lo que queda para Pedro

1. **h05, la decision de la seccion 12 del spec.** El 7b local (qwen2.5:7b, la ruta del dia a dia en la
   Ally) NO emite la marca del abismo por su cuenta con el system de PRODUCCION: cero marcas en seis turnos
   naturales del smoke, y en uno confabulo. El porton v2 (2026-09-07) midio el contrato SOLO, junto a una
   identidad de dos renglones; dentro del system real de ocho secciones el contrato no pasa en ninguna
   posicion (240 llamadas al 7b real, N=2, protocolo del porton). Ademas la metrica del porton contaba como
   legible la copia literal del molde (22 de 34 marcas legibles del control eran `⟦abismo:memoria pregunta⟧`
   textual). Evidencia en `experimentos/` (commit `7011b9b`). Con marca explicita en el mensaje, la pesca
   funciona de punta a punta (smoke 3.1 y 3.5); por suscripcion (/nube) el modelo de nube consulta solo
   (smoke 4.1). Opciones del spec: podar el system de produccion y re-medir el porton SOBRE ese system (con
   la exclusion de la copia literal), cablear la consulta solo en rutas grandes (suscripcion/API), o aceptar
   el regimen actual hasta la rebanada 2. Nada se rompe mientras tanto: sin marca, el filtro es transparente.
2. **h04, una politica de producto que el fix decidio y el spec no escribe:** en local, la fuente `chats` ya
   no pesca la ventana de 12 mensajes que el modelo ya tiene ni la pregunta actual, pero SI los mensajes mas
   viejos del chat activo; en /nube el chat activo queda fuera ENTERO (un turno local previo de la misma
   conversacion no viaja tapado por la puerta de atras del bloque). Confirmar o cambiar.
3. Residuales con nombre (park, en `ledger.md`): la divergencia streaming/one-shot ante un foco anidado en
   el cuerpo de la marca (streaming consulta, one-shot retira con aviso); `turno.retirar_marcas` de una
   sola pasada; tras una reinvocacion fallida el fallback local reempieza pegado al tramo (avisado);
   el filtro de foco cosecha focos del texto descartado tras el corte; `/nube /api` streamea marcadores sin
   reponer (preexistente); el hueco visual entre `pescado` y el primer chunk en la PWA; `pintarAbismo` no
   limpia el texto tapado anterior (invisible por `.oculto`).
4. El despliegue: reiniciar el server real con main. Sin rotar nada esta vez.
