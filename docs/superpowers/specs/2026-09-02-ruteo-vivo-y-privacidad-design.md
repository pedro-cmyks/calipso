# El ruteo vivo y la privacidad

**Fecha:** 2026-09-02
**Estado:** aprobado por Pedro seccion por seccion, listo para plan
**Origen:** una corte mixta de seis jueces-corrida (cuatro Claude, dos Codex
headless en solo-lectura) audito el ruteo del chat. Veredicto unanime: esta
mal. Cada hallazgo de este documento fue verificado leyendo el codigo, no
tomado del resumen de un juez.

## 1. Por que existe, y que se rompio

Calipso promete tres cosas sobre a donde van los datos de Pedro (CLAUDE.md y la
memoria del proyecto):

1. **Suscripcion antes que API paga antes que local.**
2. **Nunca escalar en silencio a API paga.**
3. **Lo privado no sale de la maquina.**

Las tres se rompen en el camino vivo del chat. El camino: un mensaje llega por
WebSocket, `_decide` (`server.py:1455`) llama a `dispatch.extract_features` y a
`capabilities.choose` (`server.py:1481`), que rankea modelos; el ganador se
ejecuta con `_chunks_for` (`server.py:1986`).

**La fuga central, verificada eslabon por eslabon:**

- Un prompt marcado privado hace que `score_model` (`capabilities.py:255-258`)
  descarte todo modelo sin `private_ok`. Los unicos con `private_ok: True` son
  los `local:*` (`capabilities.py:42-56`).
- Gana `route: "local"`.
- Pero `local_up = False` esta **hardcodeado en dos lugares**
  (`server.py:1435` y `:1782`), con el comentario "sin Ollama".
- La ejecucion streaming de la ruta local, `_local_via_sub`
  (`server.py:2008-2019`), corre `subprocess.run(["claude", "-p", user_msg])`.
- El dato privado va a Anthropic.

O sea: **el unico caso que existe para proteger la privacidad -- que un prompt
se marque privado -- es exactamente el que la manda a la nube.** Y de yapa,
`_local_via_sub` tira el `system` (el closure solo usa `user_msg`) y no pasa
`--model`, asi que ni siquiera es el modelo que la UI reporta.

**Dos fugas mas, del mismo tronco:**

- **La orquestacion saltea el filtro.** Si el prompt privado es largo o
  complejo, `_should_orchestrate` (`server.py:1520`, llamado en `:2475`)
  dispara el equipo dinamico, que reparte a backends de suscripcion y API **sin
  pasar por `private_ok`**. La regla se rompe por un segundo camino.
- **Los adjuntos no se miran.** El marcador `private` sale de una regex sobre el
  texto del prompt (`dispatch.extract_features`). Un archivo adjunto con datos
  personales (`attachments`, `server.py:523+`) no dispara nada.

**La escalada silenciosa a API paga:**

El freno declarado, `api_only_when_forced`, **solo vive en el CLI muerto**
`dispatch.py:274`. En el camino vivo no existe -- verificado por grep sobre
`server.py`, `capabilities.py`, `connectors.py`. Lo unico que frena la API es la
penalizacion blanda de costo. Si las suscripciones se bloquean por cuota y el
proxy pago esta arriba, `choose` devuelve `route: "api"` **sin pedir
confirmacion**.

**Y los libros mienten los dos.** La UI reporta `qwen2.5:7b / local`
(`server.py:1511`, `_route_model_name` en `:1265`), `costs` registra el turno en
$0, mientras `_cobrar_turno` (`server.py:5948`) debita una unidad de
suscripcion. Pedro ve "gratis y local"; se gasto suscripcion y salio a la nube.

**No hay muro tecnico.** El streaming desde Ollama ya esta escrito
(`dispatch._ollama_chat_chunks`, `dispatch.py:450`) y el mismo repo lo usa en el
camino no-streaming (`_run_backend_text`, `server.py:1606`, que si postea al
Ollama real). La ruta local del chat es un stub perezoso, no un obstaculo.

## 2. Que decidio Pedro, y como se parte el trabajo

Pedro eligio: **que "local" sea local de verdad** -- arreglar la ejecucion, no
solo el cartel. Y pidio que Calipso, ademas, **aprenda a juzgar que es privado y
como degrada**, con redaccion. Es un spec que abarca las dos cosas, en dos
fases con un orden que no es negociable:

- **Fase 1 -- cerrar la fuga.** La ruta local ejecuta en Ollama; lo privado que
  no se puede atender local **falla cerrado**; se enforce "no API en silencio";
  la orquestacion respeta el filtro; y los tres libros (ruteo, UI, costos)
  dejan de mentir. Al terminar la Fase 1, **ninguna de las tres reglas de Pedro
  se rompe**. Es la parte de seguridad y se puede construir y verificar entera.

- **Fase 2 -- juzgar y redactar.** Un clasificador que decide no solo *si* algo
  es privado sino *que* trozos lo son, y una capa que los tapa antes de mandar a
  la nube y los repone localmente al mostrar. Es lo que permite que un prompt
  con un dato sensible **igual reciba ayuda de la nube** sin que el dato salga.
  Es mas grande, tiene una apuesta que hay que medir, y **no arranca hasta que
  la Fase 1 este cerrada** -- porque redactar mal y despues fugar es peor que
  fallar cerrado.

La Fase 2 no se escribe en detalle de implementacion hasta que la Fase 1
aterrice; este documento fija su diseño y su criterio de medicion.

## 3. Fase 1 -- la ruta local ejecuta en Ollama

`_chunks_for("local", ...)` (`server.py:1986`) deja de correr `claude -p` y pasa
a transmitir desde el Ollama que ya corre, con el streamer que ya existe
(`dispatch._ollama_chat_chunks`). Toma el `system`, el historial y el `model`
del veredicto -- las tres cosas que el stub de hoy tira.

**`local_up` deja de estar hardcodeado.** Los dos `local_up = False`
(`server.py:1435`, `:1782`) pasan a leer la salud real de Ollama, por el mismo
camino que ya usa el jefe de un departamento para saber si el modelo local
responde. Un Ollama vivo se ve vivo; uno caido, caido.

**Que se conserva:** el jefe de un departamento sigue usando `CONFIG["local"]`
directo (`_pensar_local`), que ya es Ollama y no se toca. Lo que se arregla es
el chat, que era el unico que ejecutaba "local" como claude.

## 4. Fase 1 -- el privado que no se puede atender local falla cerrado

Con la ejecucion arreglada, un prompt privado se rutea a Ollama y se contesta en
la maquina. Queda el caso de borde: **Ollama caido + prompt privado.**

**Falla cerrado.** Calipso no manda el dato a la nube: contesta con un mensaje
claro -- "no puedo procesar esto en privado ahora mismo: el modelo local no esta
disponible" -- y no ejecuta nada remoto. La promesa de privacidad se cumple
**sin excepcion silenciosa**, que es exactamente lo que hoy no pasa.

El costo de esta decision se paga en disponibilidad, no en privacidad: ante un
prompt privado sin modelo local, Pedro se queda sin respuesta hasta que levante
Ollama. Es el lado correcto para una promesa de privacidad, y es reversible: la
Fase 2 le agrega una salida (la redaccion) que hoy no existe.

**Nunca degrada un privado a la nube en la Fase 1.** El "degradar avisando" es
tentador pero su seguridad entera depende de que el aviso no se pueda ignorar, y
un aviso que se puede clickear sin leer no es una garantia. La Fase 1 no lo
incluye. La respuesta buena a "quiero que igual me conteste" es la redaccion de
la Fase 2, no un aviso.

## 5. Fase 1 -- no escalar a API paga en silencio

La regla `api_only_when_forced` deja de vivir solo en el CLI muerto y se enforce
en el camino vivo: en `_decide`, un veredicto `route: "api"` se **descarta del
ranking salvo que Pedro lo haya forzado explicitamente** (`/api` o el
equivalente en directivas). Asi "no escalar en silencio" deja de depender de que
la penalizacion de costo alcance, y se sostiene aunque las suscripciones se
caigan.

Si no queda ningun candidato no-API y el usuario no forzo API, el sistema lo
dice -- "las suscripciones no estan disponibles; deci `/api` si queres usar la
API paga" -- en vez de gastar sin preguntar. Es la misma forma que el fallo
cerrado de privacidad: cuando la unica salida viola una regla, se para y se
avisa, no se cruza la regla en silencio.

## 6. Fase 1 -- la orquestacion respeta el filtro

`_should_orchestrate` (`server.py:1520`) puede sacar un prompt privado por
backends de suscripcion o API sin pasar por `private_ok`. Se cierra: **un prompt
marcado privado no dispara orquestacion**, o la orquestacion se restringe a
backends locales. Un prompt privado tiene un solo camino -- local o fallo
cerrado -- y ni la longitud ni la complejidad lo sacan de ahi.

## 7. Fase 1 -- los tres libros dejan de mentir

- **El scorer.** Las etiquetas `cost: 0` y `private_ok: True` de los modelos
  `local:*` (`capabilities.py:42-56`) pasan a ser ciertas, porque tras la Fase 1
  la ejecucion local **es** local. `discover` (`capabilities.py:170-185`), que
  hoy propaga `private_ok: route == "local"` a todo Ollama descubierto, queda
  correcto por el mismo motivo. No hay que cambiar las etiquetas: hay que hacer
  que la ejecucion las cumpla, que es lo que hacen las secciones 3 a 6.
- **La UI.** El meta que ve Pedro (`server.py:1502`, `:1511`,
  `_route_model_name` en `:1265`) reporta el modelo que **de verdad** contesto.
  Si contesto Ollama, dice Ollama; si por un fallo cerrado no contesto nadie, lo
  dice. Nunca mas "qwen2.5:7b" sobre una respuesta de Claude.
- **Los costos.** `costs.log_usage` registra `local` como $0 **solo cuando de
  verdad fue local**. El doble libro -- $0 en la UI contra un debito de
  suscripcion en `_cobrar_turno` -- se elimina porque ya no hay una ruta que sea
  local en un libro y suscripcion en el otro.

## 7b. Fase 1 -- el CLI muerto deja de mentir

`dispatch.py` tiene su propio ruteo (`decide_by_rules`, `route`,
`decide_by_model`) que **el chat no usa** -- solo lo alcanza el entrypoint
`python dispatch.py "..."`. Pero su docstring promete "lo privado -> local" y su
rama PRIVATE se justifica con `why: "suscripcion local sin API"`, que es falso:
suscripcion manda a la nube. Un comentario falso sobre privacidad es peligroso
aunque el camino este frio, porque el proximo que lo lea le va a creer. La Fase 1
corrige esos comentarios y la docstring del modulo para que describan lo que el
codigo hace hoy (todo va a suscripcion; el clasificador es un stub; no hay boca
local viva en ese CLI), o borra el codigo muerto. `SAFE_FALLBACK` -- definido,
sin usar, y con el valor contrario a su comentario -- se elimina o se cablea.

Es limpieza, no seguridad: el CLI muerto no fuga porque nadie lo llama. Pero
entra en la Fase 1 porque es el mismo defecto -- una promesa de ruteo que el
codigo no cumple -- y arreglarlo mientras el tema esta fresco cuesta menos que
dejarlo para que muerda a otro.

## 8. Fase 2 -- juzgar que es privado

Hoy `private` es un booleano de una regex debil (`privado|confidencial|secreto|
contrasena|password|personal|sensible|no comparta`). No agarra DNI, cedula,
pasaporte, tarjeta, cuenta bancaria, telefono, direccion, email, historia
clinica, diagnostico, salario, token, clave SSH, ni un adjunto con cualquiera de
esas cosas. La Fase 2 lo reemplaza por un **juez de privacidad** que decide dos
cosas:

1. **Que trozos del prompt (y del adjunto) son sensibles**, no solo si el prompt
   entero lo es. La salida no es un `bool`: es una lista de tramos, cada uno con
   su tipo (identidad, credencial, salud, ubicacion, financiero, contacto) y sus
   posiciones.
2. **Que nivel de manejo pide** cada tramo: los que nunca pueden salir de la
   maquina (credenciales, claves) y los que pueden salir tapados.

**Quien juzga.** El modelo local (`CONFIG["local"]`, Ollama), no la nube -- seria
absurdo mandar el dato afuera para preguntar si el dato puede ir afuera. Un
prompt con un modelo local caido cae al fallo cerrado de la Fase 1, igual que
cualquier otro privado sin local.

**Esto NO es la regex de hoy con mas palabras.** La regex se conserva como un
piso barato -- un primer filtro rapido -- pero el juez es el que decide el
manejo. La distincion importa porque el juez tiene que atrapar lo que ninguna
lista de palabras atrapa: "mi numero es 3865-..." no dice "privado" y es un
telefono.

## 9. Fase 2 -- redactar y reponer

La idea que Pedro trajo -- "partirla para que no este completa en un lado" -- no
se implementa repartiendo entre vendors, porque eso no protege: un prompt de
razonamiento no se corta en pedazos que sean a la vez inofensivos por separado y
utiles juntos, y repartir entre Anthropic y OpenAI es exponerse en dos lados en
vez de uno. La version que **si** protege es partir en la **frontera de la
maquina**:

1. El juez (seccion 8) marca los tramos sensibles.
2. Los tramos que **nunca salen** (credenciales, claves): si el prompt los
   necesita para responder, cae al fallo cerrado -- eso se contesta local o no
   se contesta.
3. Los tramos que **pueden salir tapados**: se reemplazan por marcadores
   estables (`[PERSONA_1]`, `[TELEFONO_1]`, ...) antes de mandar a la nube. La
   nube razona sobre el texto tapado.
4. La respuesta vuelve, y Calipso **repone los valores reales localmente** antes
   de mostrarla. Lo sensible nunca estuvo en el trafico de salida.

**El limite honesto, que va escrito en el spec y en la UI:** la redaccion
protege el *contenido* de los tramos, no el *hecho* de que Pedro tiene un dato de
ese tipo. Mandar "el DNI de [PERSONA_1] es [ID_1], es valido?" le dice a la nube
que hay una persona y un DNI, aunque no cuales. Para lo que exige que ni siquiera
eso salga, la respuesta es local o nada. La redaccion es un tercer nivel entre
"todo local" y "fallar cerrado", no un reemplazo de ninguno de los dos.

**El degradado avisado, ahora si, tiene lugar** -- pero como consecuencia de la
redaccion, no como un aviso suelto: cuando un prompt tiene tramos que se van a
tapar, Calipso muestra **que** se tapo y **que** viajo, antes de mandar. El
usuario ve la version redactada real, no una casilla de "acepto". Es informacion
verificable, no un boton.

## 10. Fase 2 -- la apuesta que hay que medir

Que un modelo local de 7b sepa marcar los tramos sensibles de un texto libre
**no esta probado**, y este proyecto ya aprendio a no construir sobre una
apuesta sin medirla. Antes de cablear la redaccion al camino vivo:

- Un banco de prompts sinteticos con datos sensibles conocidos (posiciones
  marcadas a mano), y una medicion de cuantos tramos el juez local **agarra**
  (no dejar pasar un dato es lo que importa) y cuantos **inventa** (tapar de mas
  arruina la respuesta). Es el mismo metodo del experimento de la carta: barato,
  local, corrido varias veces porque el modelo no es determinista.
- El criterio duro: **ningun falso negativo sobre credenciales y salud** es
  aceptable -- si el juez deja pasar una clave sin tapar, la redaccion es peor
  que el fallo cerrado, porque promete proteger y no protege. Si el 7b no llega
  a ese piso, la Fase 2 usa un modelo local mas grande o se queda en el fallo
  cerrado de la Fase 1 hasta que exista uno que llegue.

Un resultado negativo de esta medicion es un resultado util: dice que la
redaccion todavia no se puede confiar, y Calipso se queda con la seguridad
completa de la Fase 1, que ya cumple las tres reglas.

## 11. Invariantes que no se tocan

- **El jefe de un departamento no se toca.** Ya usa `CONFIG["local"]` (Ollama) y
  ya tiene su `num_ctx`. Esto arregla el chat.
- **Ningun dato marcado privado sale de la maquina sin tapar.** Es la regla que
  todo el spec sirve. En la Fase 1 significa local-o-nada; en la Fase 2, ademas,
  tapado-o-nada.
- **Ninguna ruta a API paga se toma sin gesto explicito de Pedro.**
- **El juez de privacidad corre local.** Preguntar si un dato puede salir nunca
  puede ser una razon para que el dato salga.
- **Los tres libros dicen la verdad.** El modelo que la UI reporta es el que
  contesto; el costo que registra es el que se gasto.

## 12. Lo que queda abierto

1. **La deteccion de tipo del adjunto.** Un PDF o una imagen con datos
   personales necesita que el juez mire el adjunto, no solo el texto. La Fase 2
   lo incluye para adjuntos de texto; imagenes (OCR) queda para despues y se
   dice.
2. **El costo de latencia del juez.** Correr el juez local antes de cada prompt
   privado suma una llamada a Ollama. Para el chat interactivo puede notarse. La
   medicion de la seccion 10 tiene que reportar cuanto tarda, no solo cuanto
   acierta.
3. **La estabilidad de los marcadores entre turnos.** Si `[PERSONA_1]` es Pedro
   en un turno y otra persona en el siguiente, la nube pierde el hilo. La Fase 2
   fija los marcadores por conversacion, no por turno; el detalle es de plan.
4. **Que hace un prompt mixto** -- parte trivial, parte privada -- que hoy se
   rutea entero por una sola via. Con redaccion, la parte privada se tapa y el
   resto viaja; sin ella (Fase 1), el prompt entero es privado y va local o
   falla. Es correcto que la Fase 1 sea conservadora aca.

## 13. Como se verifica que funciona

**Fase 1, sin modelo:**

- Un prompt privado con Ollama disponible se ejecuta contra Ollama y **no**
  contra claude -- verificado espiando el subproceso, no el meta.
- Un prompt privado con Ollama caido **falla cerrado**: no hay llamada remota, y
  el mensaje lo dice.
- Un veredicto `route: "api"` sin `force_route == "api"` **no se ejecuta**: se
  descarta o se pide el gesto explicito.
- Un prompt privado **no dispara orquestacion**.
- El meta reportado y el costo registrado coinciden con lo que de verdad
  ejecuto, en las tres rutas.
- `local_up` refleja la salud real de Ollama, no una constante.

**Fase 1, con el servidor:** un prompt marcado privado, con Ollama vivo,
contesta local; con Ollama apagado, falla cerrado. Ninguno de los dos toca la
nube. Verificado mirando el trafico o el subproceso, no la pantalla.

**Fase 2, la medicion de la seccion 10**, antes de cablear nada: el juez local
sobre el banco sintetico, con el piso de cero falsos negativos en credenciales y
salud. Y despues, con la redaccion puesta: un prompt con un dato sensible viaja
**tapado** -- verificado leyendo lo que sale, no lo que se muestra -- y vuelve
repuesto.
