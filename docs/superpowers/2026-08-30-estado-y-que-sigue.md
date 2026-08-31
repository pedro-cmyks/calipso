# Estado al cierre del 2026-08-30

Todo lo de abajo esta en `main` y en GitHub (`0208b82`). 759 tests de python y 325 de
cliente, verdes, corridos sobre un clon limpio de `main` antes de pushear.

**Pero la fabrica no esta viva.** Ver la seccion "Lo que falta para que funcione", que es
lo unico que importa manana.

---

## Lo que entro hoy

**Seguridad, tres agujeros cerrados y verificados.** El token de Pedro estaba hardcodeado
en el HTML de `/login`, que es la unica ruta que `auth_guard` deja pasar sin autenticar
(se rota y se saca; comprobado con `curl` que ya no aparece). `POST /api/deps/install`
llamaba a `pip install` con lo que le mandaran — RCE, cerrado con 403. Y `screenshot()`
aceptaba cualquier URL, incluida la metadata de la nube: ahora hay `exigir_url_publica`,
llamada desde la funcion y no solo desde el endpoint.

**El cristal, tercera divisa del libro.** `Divisa` tenia `MONEDA` y `PT`; ahora tambien
`CRISTAL`, con sus tres verbos, copiando el patron del pedro-token. Mide capacidad de
suscripcion, que no es plata: hasta hoy un cargo de suscripcion de la fabrica terminaba en
una transferencia de monedas, asi que sin saldo lanzaba `SinSaldo`, caia en
`cargos_pendientes.jsonl` y se reintentaba para siempre sin aplicarse. **La suscripcion se
consumia y el libro anotaba cero.** El razonamiento completo esta en
`2026-08-27-lo-que-falta.md` y en la pagina publicada de la decision.

`cristal.py` **todavia no tiene un solo llamador de produccion**: es reversible del todo.
El paso siguiente es que `pagador._aplicar` lo llame, y eso mueve tambien los filtros de
`eficiencia.py` — si no se mueven juntos, la eficiencia se va a cero en silencio.

**La rutina de cierre.** `cerrar_semana_operativa` no lo disparaba nadie, y detras colgaban
doce funciones muertas: los PT no expiraban, los trabajos que no rinden no morian ni
devolvian el escrow, los cargos fallidos no se reintentaban, y `es_congelado` **no podia
devolver `True` jamas en produccion** — todo el mecanismo de quiebra existia y no podia
activarse. Ahora es el sexto `kind` de rutina. **Nace apagada**: encenderla significa que
la economia expira y liquida sola mientras Pedro duerme, y esa es su decision.

Una salvedad: el handler pasa `presupuesto_direccion_mm=0`, porque ese monto no tiene
perilla. Los presupuestos semanales de cada departamento si se reparten.

**La cara del motor de permisos.** Cuatro endpoints probados sin una sola pantalla, que
convertian el techo de plata en un muro en vez de una pregunta. Ahora hay una tercera
pestaña en la mesa, con aviso numerado. La frase que Pedro lee sale de `accion.forma` —el
mismo objeto que el motor compara— y hay un desplegable con el JSON exacto: nada escondido
detras de un resumen. Todo escapado, porque `accion.titulo` y el contexto los puede
escribir un departamento, o sea un modelo.

Para plata no aparece "si y no me preguntes mas": acuñar por encima del techo tiene
`siempre_pregunta`. La pantalla lo **dice** en vez de dibujar un boton que devolveria 400.

**El probe pasivo de consumo.** Claude y Codex ya escriben su uso real en disco, gratis:
Claude deja el `usage` por turno en el jsonl de sesion, y Codex deja `rate_limits` con el
**porcentaje de cuota usado** en dos ventanas (5 horas y semanal) con su `resets_at`. El
probe lee eso; no llama a nadie. Se midio que preguntarle al CLI su propio estado consume
cuota real (7,0% a 9,0% con dos llamadas triviales), asi que el diseño pasivo no es solo
mas barato: es el unico correcto.

Nacio **encendida**, y esta bien: solo hace `stat` y lectura sobre archivos ajenos, sin
red, sin subprocesos, sin modelos. Y tiene un test que siembra una frase en cinco lugares
del contenido —incluida una linea de JSON roto y una clave inventada— y revisa **byte a
byte todos los archivos** bajo `CALIPSO_HOME`, mas stdout y stderr. Con un segundo test
para que una excepcion tampoco pueda citarla.

Lo que midio sobre los archivos reales: 25 dias de Claude, 10.886 turnos, 11,6M tokens de
salida — inferencia por ritmo, ~12.000 unidades por ciclo. Codex al 9% de la ventana de 5
horas: 22 por ventana, 200 por semana, y **eso si es medicion**, no inferencia.

**La ronda pre-seed.** Los departamentos piden su capital de arranque por el bus y Pedro
elige en la mesa. Habia dos frenos que lo hacian imposible: el de saldo estaba antes de la
rama de `proponer`, asi que un departamento sin plata no podia ni pedir plata; y el de
agresividad, con `presupuesto_semanal_mm = 0`, frenaba para siempre por un motivo que no
era agresividad. Ninguno se borro: se movieron a la accion correcta.

El monto se recorta a una perilla, no lo inventa el modelo — hay una regla escrita en
`_contratar_para` sobre eso, y esta medido que el 3b alucina.

Dos techos: **por pedido** y **acumulado sobre una ventana deslizante** de 4 semanas
operativas. La ventana empezo siendo fija y eso permitia meter 2x el techo en dos semanas
de calendario seguidas, en el borde. Ahora la demora cae siempre del lado conservador:
tardar en abrir el lunes **aprieta** el techo, nunca lo afloja, porque la ventana rueda
cuando Pedro abre una semana, no cuando pasa el tiempo. Y la pantalla dice cuando vuelve
cupo y cuanto.

**La bandeja se limpia sola.** Un pedido sin responder apretaba al departamento para
siempre. Ahora vence, y el vencimiento **no lo dispara nadie**: es una funcion pura del
libro, recalculada en cada lectura. Sin disparador no hay nada que encender ni que quede
apagado. Vive exactamente la ventana en la que nacio, que es lo que dura su
financiabilidad. Y la pantalla de Plata dice por que un departamento esta callado, con el
texto byte por byte que recibio el jefe.

**La configuracion dejo de ser de escritura unica.** `Registro.ajustar` tiene su primer
llamador de produccion, y `capacidad_ciclo` se puede corregir con lo que mida el probe.
Repreciar una suscripcion pasa por el motor de permisos; una perilla no —se deshace
escribiendola de nuevo y no mueve un milimon—.

---

## Lo que falta para que funcione

Verificado hoy al cerrar:

```
~/.calipso/economia/     -> NO existe
servidor en :8000        -> sin respuesta
unit de systemd          -> no hay
rutinas                  -> todas apagadas
```

**La economia nunca se sembro.** Sin ese directorio los quince endpoints
`/api/economia/*` contestan `{"activa": false}`, no hay un solo departamento, nadie puede
pedir una ronda, no se consume un cristal y el mapa no tiene que dibujar. Nada de lo de
arriba esta haciendo nada.

El orden:

1. **Levantar el servidor**, y dejarlo correr un rato antes de sembrar: la rutina del
   probe nacio encendida, asi que va a medir el consumo real. Sembrar despues, con un
   `capacidad_ciclo` medido en vez del 1000 marcado "estimacion a ajustar".
2. **Sembrar.** Departamentos acordados: `cerebro`, `research` (incluye market research),
   `development`, `testing`, `marketing`, mas **`finanzas` en zona personal, con ese nombre
   exacto** — esta hardcodeado en `pagador.py` y sin el todo cargo personal se apila
   pendiente para siempre. Falta el numero: cuanto paga Pedro por mes por cada suscripcion.
3. **Poner las perillas.** Los dos techos de pre-seed nacen en cero y **cero frena**: recien
   sembrado, ningun departamento puede pedir nada.
4. **Decidir si se enciende la rutina de cierre.**

---

## Decisiones que quedaron abiertas

- **Taller / I+D**: Pedro lo quiere. Quedo como departamento de fabrica, con la linea de
  que el taller hace I+D para proyectos y mejorar a Calipso mismo sigue siendo personal.
  Se puede dar vuelta antes de sembrar; despues no, porque `Registro` no tiene baja.
- **Legal**: afuera hasta que pueda facturar sus dictamenes (`vender_servicio` no tiene
  llamador de produccion).
- **Que el "no" de Pedro pese.** Hoy descartar le devuelve el cupo entero al jefe, y eso es
  una decision de spec con test propio que cita la seccion 8. Si Pedro quiere que un
  rechazo tenga costo, **es un cambio de spec, no un bug fix**.
- **El contexto selectivo.** Observacion de Pedro, sin resolver: `context_sections` tiene
  hoy dos regimenes sin nombre —briefs siempre encendidos y truncados a lo bruto contra
  `recall()`, que se enciende por necesidad— y el estado de la fabrica esta en el grupo
  equivocado. Con doce departamentos, truncar decide por Pedro que sabe Calipso. Falta el
  regimen del medio: que Calipso pueda **pedir** el detalle en vez de tenerlo todo encima.

---

## Fuera de este repo

**El skin del e-reader** se trabaja aparte, en `/var/home/pedro/calipso-lector/BRIEF.md`,
en su propia sesion. Tres piezas: un plugin de KOReader (Lua) para la lectura, una APK
(launcher + WebView + `ACTION_PROCESS_TEXT`) para la fabrica, y el gesto de asistente como
puente. El plugin va primero.

De ahi vuelven dos cosas a este repo, y **no antes de que el lector acepte su primer
permiso**: la red privada (Tailscale, que ya figura como plan) y la **identidad de
dispositivo** — hoy hay un solo token global sin sujeto, asi que todo lo que entra es
"Pedro" y el registro no puede decir desde donde se aprobo algo.

---

## Lo que sigue abierto en seguridad

La revision que Pedro pidio aparte no se hizo. Lo mas grave inventariado:

- **El token viaja en el query string y uvicorn loguea la query entera.** Rotarlo no
  arregla el patron: cada arranque escribe el token nuevo en los logs, y la cascara Tauri
  lo reinyecta.
- **`_safe` solo compara contra `ROOT`**, asi que abriendo `~/.calipso` como proyecto se
  puede leer el token y el libro personal por `/api/file`.
- **El agente hereda el CLI y el entorno enteros**, con `CALIPSO_TOKEN` adentro. El
  criterio de salida es un test que intente leer `~/.ssh/id_rsa` desde el agente y falle.
- **`server.py` resuelve `~/.calipso/token` sin pasar por `CALIPSO_HOME`**, asi que la
  suite lee el token real a memoria y en una maquina sin el archivo lo crearia.

El inventario completo, con `archivo:linea` por item, esta en
`2026-08-27-lo-que-falta.md`.
