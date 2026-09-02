# El compositor de voz -- Calipso escribe como Pedro

**Fecha:** 2026-09-02
**Estado:** brainstorming cerrado con Pedro; listo para su revision
**Origen:** Pedro pidio que Calipso, ademas de contestarle, le PROPONGA el proximo texto de su propia respuesta -- escrito en su voz, con contexto y considerando como habla.

## 1. Por que existe

Hoy Calipso contesta a Pedro. Esta feature invierte la direccion: Calipso **escribe como Pedro**, para que Pedro mande ese texto como suyo. Sirve para dos cosas, con un solo gesto:

- **Responder** un hilo que le llega (un mail, un mensaje, un chat que Pedro pega): Calipso propone la respuesta de Pedro, en su registro.
- **Redactar desde cero**: Pedro da la intencion cruda ("decile a Ana que no llego, reprogramamos") y Calipso la escribe como la diria el.

El valor no es "buen texto" -- es que **suene a Pedro**: sus muletillas, su largo de frase, que escribe sin tildes, su registro.

## 2. Que decidio Pedro (brainstorming, 2026-09-02)

1. **Un compositor general**: responde hilos ajenos Y redacta desde cero, en su voz en ambos casos.
2. **La voz se APRENDE de sus mensajes** (cero trabajo), no de una ficha que el escriba.
3. **El registro se adapta por CONTEXTO**: Calipso aprende su RANGO (no una sola voz) y elige el registro segun con quien habla y el tono del hilo (amigo != cliente != familia).
4. **Local por default, nube a pedido**: el borrador lo escribe el modelo local (privado, gratis); si queda flojo, Pedro pide `/nube` para ese borrador y la nube -mejor imitadora- lo reescribe.
5. **Vive como un gesto en el chat** (`/redacta`), no como una pantalla nueva. Reusa el chat, el WebSocket, la privacidad y el `/nube` que ya existen.

## 3. Como aprende la voz (recuperacion, no entrenamiento)

No hay un modelo entrenado. Calipso ya guarda los mensajes de Pedro (`role=="user"` en `chats.py`, verbatim) y ya sabe buscarlos por parecido semantico (los embeddings de `memory.py`, chromadb + SentenceTransformer). El compositor:

1. **Arma un corpus de voz** con los mensajes reales de Pedro. Fuente primaria: sus mensajes en los chats. Cada uno se puede indexar por embedding para recuperarlo por parecido.
2. **Al redactar, recupera un punado** (5-8) de mensajes de Pedro que calzan con el registro/tema que necesita, y los pone como ejemplos VIVOS ("asi escribis vos") en el prompt del que redacta. El modelo imita el estilo de esos ejemplos, no una descripcion abstracta.
3. **El registro sale del contexto**: para un hilo informal, recupera los mensajes informales de Pedro; para uno de trabajo, los mas neutros. El contexto (a quien responde, el tono del hilo) guia que se recupera.

**El riesgo honesto (Pedro lo marco dos veces):** casi todo el corpus de hoy son ordenes cortas a Calipso -- un registro angosto, distinto de como Pedro le escribiria a un amigo o en un mail. Mitigacion, sin romper el "cero trabajo": el default aprende de sus chats (captura igual sus habitos de superficie: sin tildes, muletillas, largo de frase). Y si Pedro quiere RANGO de verdad, le pega **un par de ejemplos reales** etiquetados por registro ("asi le escribo a un amigo", "asi un mail") que entran al corpus de voz con su etiqueta. Opcional, pero es el salto de calidad mas grande. La feature funciona sin ejemplos; mejora mucho con unos pocos.

## 4. El flujo -- el gesto `/redacta`

`/redacta` es una directiva nueva del chat (junto a `/nube`, `/api`, etc.). Dos formas:

- **`/redacta` con un hilo**: Pedro pega el mensaje que le llego y pone `/redacta`. Calipso lo trata como "algo a lo que responder" y propone la respuesta de Pedro.
- **`/redacta <intencion>`**: Pedro da que quiere decir. Calipso lo escribe desde cero en su voz.

Calipso **infiere el modo** (responder vs desde cero) del contenido -- un modelo distingue bien "un mensaje que me mandaron" de "una instruccion de que decir". No hay dos gestos distintos; uno solo y Calipso decide.

La salida es un **borrador**, marcado como tal (no es Calipso contestandole a Pedro: es el texto de Pedro). Pedro:
- lo edita y lo copia/manda por su cuenta (Calipso no manda nada por el -- solo redacta),
- o pide **`/otra`** para otra version (mismo hilo, otro intento),
- o pide un ajuste ("mas corto", "mas formal", "sacale el che").

## 5. Local por default, nube a pedido

El borrador lo escribe el **modelo local** (`CONFIG["local"]`, el 7b) por default: los ejemplos de voz de Pedro y el hilo nunca salen de la maquina. El 7b imita peor un estilo personal, asi que el borrador puede sonar menos a Pedro.

Si Pedro quiere mas calidad, combina `/redacta /nube`: la nube (mejor imitadora) recibe los ejemplos de voz + el hilo, con la maquinaria de la Fase 2:
- Los **datos sensibles del hilo** (un telefono, una direccion) van tapados por la redaccion, y la respuesta se repone.
- Los **ejemplos de estilo de Pedro NO se tapan** -- son justo lo que la nube tiene que imitar. Van crudos. Pedro lo acepto explicitamente: elige turno a turno cuando vale exponer su voz.
- Una **credencial** en el hilo hace fallar cerrado igual que en el chat: no se manda ni tapada.

Es coherente con la postura de todo el ruteo: local es el default seguro; la nube es un acto explicito.

## 6. La ficha de voz (refinamiento, no MVP)

Ademas del corpus recuperable, Calipso puede mantener una **ficha de voz** chica y editable: un puñado de rasgos extraidos de los mensajes de Pedro (escribe sin tildes; frases cortas; usa "che"/"dale"; nunca "estimado"; rango de registros observados). Sirve para (a) darle al modelo una guia estable ademas de los ejemplos, y (b) que Pedro corrija lo que no le suena. **No entra en el MVP**: el MVP es recuperacion-few-shot sola, que ya captura el estilo de los ejemplos. La ficha se agrega si los borradores no salen suficientemente "Pedro".

## 7. Invariantes y lo que reusa

- **Calipso no manda nada por Pedro.** El compositor REDACTA; Pedro copia/manda. Nunca se conecta a su mail/WhatsApp/nada. (Si algun dia se quiere, es otra feature con su propio gesto de autorizacion.)
- **Local por default; la voz no sale sin `/nube` explicito.** Misma regla que el chat.
- **Reusa todo lo que ya anda**: el `/ws/chat`, el reductor de eventos del cliente (`chat.js`), la redaccion/`/nube` de la Fase 2, la memoria y sus embeddings. Superficie nueva minima: una directiva, un modulo que arma el corpus+prompt, y el render del borrador.
- **El corpus de voz es de Pedro y local.** No se comparte entre proyectos ni sale de la maquina salvo `/nube`.

## 8. Lo que NO hace (fuera del MVP)

- **Mandar el mensaje** por Pedro (mail, chat, etc.). Solo redacta.
- **Un panel dedicado en `/fabrica`.** El MVP es el gesto en el chat; el panel es un posible parte 2.
- **Entrenar un modelo de la voz de Pedro.** Es recuperacion-few-shot; sin entrenamiento.
- **La ficha de voz explicita** (seccion 6): refinamiento posterior.
- **Deteccion automatica de "esto amerita un borrador"** -- Pedro lo pide con `/redacta`; Calipso no lo ofrece solo (todavia).

## 9. Como se verifica que funciona

- **Sin `/redacta`, el chat es identico a hoy.** La directiva nueva no cambia ningun turno normal.
- **`/redacta` sobre un hilo pegado** produce un borrador que (a) es una RESPUESTA al hilo, (b) usa el registro que calza, (c) suena a Pedro (sus habitos de superficie presentes). Verificado leyendo borradores reales, no solo que "salga texto".
- **`/redacta <intencion>`** produce el texto desde cero en su voz.
- **`/otra`** da una version distinta del mismo pedido.
- **Local por default:** un `/redacta` sin `/nube` no manda los ejemplos ni el hilo a la nube (verificado en el trafico, no en la pantalla). **`/redacta /nube`** manda el hilo tapado y los ejemplos crudos, y una credencial en el hilo falla cerrado.
- **La recuperacion trae mensajes de Pedro** (no de otro), y el corpus no sale de la maquina salvo `/nube`.
