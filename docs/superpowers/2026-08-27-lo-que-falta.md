# Lo que falta — lista consolidada

Fecha: 2026-08-27. Rama `feat/mesa-de-pedro`. Cinco lectores barrieron docs y codigo;
esto es una sola lista, deduplicada y verificada contra el arbol. Cada item tiene
`archivo:linea`. Lo que ya esta hecho no aparece.

Convencion de tamano: **chico** = unas horas, **mediano** = un dia, **grande** = varios dias.

---

## 1. Lo que bloquea todo lo demas

**La economia de Pedro nunca se sembro.** `/home/pedro/.calipso/economia/` no existe
(verificado con `ls`). Sin ese directorio `_EcoPagador.desde_entorno` devuelve `None`
(`calipso/economia/pagador.py:58`), `_economia()` devuelve `None`
(`calipso/server.py:3497`), los quince endpoints `/api/economia/*` contestan
`{"activa": false}`, la rutina del jefe sale por el early return
(`calipso/server.py:2681`) y el brief del chat sigue diciendo "apagada".

**No falta codigo.** El sembrado esta construido y probado: `POST /api/economia/sembrar`
(`calipso/server.py:3856`) con boton en la mesa (`calipso/web/fabrica/app.js:449`).
Falta el acto de Pedro: la lista de departamentos, el capital inicial y los numeros de
las suscripciones (ver seccion 4, pregunta 1).

Todo el bloque 2, todo el bloque 3, la mitad de la seccion "construido y apagado" y las
dos vistas de la seccion 6 estan aguas abajo de esto. Mientras no se siembre, cualquier
cosa que se construya en economia se puede escribir pero no se puede ver funcionar.

---

## 2. Bloques de trabajo

Ordenados por lo que le sirve a Pedro. Cada uno se puede empezar y terminar.

### B1 — La tira de permisos en `/fabrica` (5.9)
**Falta:** una pantalla. `grep permiso calipso/web/` da un solo acierto y es un
comentario sin relacion (`calipso/web/index.html:2510`).
**Que hay:** los cuatro endpoints listos y probados — `GET /api/permisos`
(`calipso/server.py:4088`), responder (`:4102`), revocar (`:4119`), techo (`:4130`) —
y dos ejecutores registrados (`:4083`, `:4085`).
**Por que primero:** hoy el techo de plata es un **muro, no una pregunta**.
`_permisos_puerta` (`calipso/server.py:3983`) corta con 409 y le dice a Pedro
"contestala en /api/permisos", y ese lugar no existe en pantalla. Por encima del techo,
acunar y mover el banco personal son imposibles salvo por `curl`. El propio codigo lo
admite: "la tira de 5.9 se construye despues" (`calipso/server.py:3990`).
**Tamano:** chico. **Desbloquea:** el techo de plata deja de ser un bloqueo duro, y con
el la puerta para enchufar terminal/archivos/apps. **Depende de:** nada.

### B2 — Enchufar el motor de permisos a terminal, archivos y apps
**Falta:** llamadores. `permisos.evaluar` tiene **un solo** consumidor, `_permisos_puerta`,
usado dos veces y las dos de plata (`calipso/server.py:4162` movimiento personal,
`:4242` acunar). Concretamente faltan cuatro cosas:
- ningun camino de escritura pasa por el motor: ni `/api/file`, ni `POST /api/commands/run`
  (`calipso/server.py:3385`);
- no hay ejecutores fuera de plata: sin ellos un "si" de Pedro sobre un comando devuelve
  `{"ejecutada": False, "motivo": "sin ejecutor para comando/correr"}`
  (`calipso/permisos/motor.py:236`);
- no existe el canal por el que el agente **pide** permiso (5.8): no hay
  `POST /api/permisos/pedir`;
- no hay forma de editar `preautorizados`: `almacen.preautorizados` lee del JSON
  (`calipso/permisos/almacen.py:179`) y solo `poner_techo` escribe (`:165`).
**Que hay:** el motor entero, y esta bien. Las cuatro familias clasifican
(`calipso/permisos/acciones.py:243-402`), `es_irreversible` mira git push/clean/amend/
reset --hard y rm -rf elemento por elemento (`acciones.py:308-347`), la subsuncion por raiz
(`acciones.py:436`), el estacionamiento y la pared anti-rodeo (`calipso/permisos/motor.py:113-200`).
El motor **sabe preguntar por un `rm -rf` y no sabe hacerlo despues del si.**
**Tamano:** mediano. **Depende de:** B1 (sin pantalla, un permiso pedido no se puede conceder).

### B3 — El registro de proyectos
**Falta el subsistema entero.** `grep proyectos.json` → 0. No hay
`calipso/economia/proyectos.py`. La cuenta `proyecto:<slug>` solo existe como validacion
de forma en la frontera de acunacion (`calipso/server.py:4213-4226`), que por eso admite
**cualquier slug** — su propio docstring lo dice (`calipso/server.py:4174-4179`).
Contenido minimo: `~/.calipso/economia/proyectos.json` con `nombre`, `zona`, `repo_path`,
`departamentos`, `abierto_en`, y una clase `Registro` con la misma disciplina que
`calipso/economia/departamentos.py:48-81` (configuracion, nunca estado); alta desde la
mesa; presupuesto `tesoro -> proyecto:<slug>` con motivo `presupuesto_proyecto`; cierre.
**Ojo con dos acoples reales:**
- `direccion.asignado_semana` (`calipso/economia/direccion.py:25-30`) suma solo
  `motivo == "presupuesto"` contra `dep_cuenta`: un `presupuesto_proyecto` no acumularia
  contra `UMBRAL_MANDATO_MM` (`direccion.py:18`) sin ampliar ese pliegue;
- el cierre de proyecto es el **primer llamador** de `Kernel.liquidar`
  (`calipso/economia/kernel.py:141`), hoy con cero llamadores de produccion. Y `liquidar`
  **no ve** la plata que el proyecto puso en un `trabajo:<id>` vivo (esta en la cuenta del
  trabajo, `calipso/economia/bus.py:133`), asi que `evaluar_y_liquidar_muertos`
  (`bus.py:180`) la devolveria semanas despues a una cuenta cerrada. **Cerrar un proyecto
  exige matar o reasignar sus trabajos primero.**
**Tamano:** grande. **Desbloquea:** B4, B5, B6, y las dos vistas. **Depende de:** el sembrado
(seccion 1) para poder verlo funcionar.

### B4 — Las dos compuertas: que un proyecto pueda pagar
Son **las dos unicas invariantes que el spec dice que se tocan**, y no se toco ninguna:
- `mercado._politica` (`calipso/economia/mercado.py:76`) sigue con
  `if pagador.startswith("trabajo:")`, y el `else` (`:82`) hace `dep_por_cuenta(pagador)`,
  que revienta con cualquier cuenta fuera del Registro (`mercado.py:44-48`);
- `bus.financiar` (`calipso/economia/bus.py:118-123`) exige un departamento de fabrica.
El trabajo real es **separar "quien puede pagar" de "contra quien se evaluan las politicas"**;
hoy estan confundidas en `mercado.py:82-87`.
**Tamano:** mediano (es un rediseno chico escrito en dos lugares). **Depende de:** B3.

### B5 — El nexo: quien lo hizo y para que proyecto
**Falta:** `dueno` se estampa solo cuando el pagador empieza con `trabajo:` — tres
ocurrencias literales, `calipso/economia/mercado.py:76`, `:110` (`comprar_capacidad`),
`:152` (`gastar_api`); tiene que estamparse **siempre que el pagador no sea `dep:*` ni
`personal:*`**. Lo mismo con `ref` forzado a la cuenta pagadora (`mercado.py:114`, `:155`).
Falta la clave `proyecto` en el evento `alta` del bus (`calipso/economia/bus.py:70-73`
apila nueve claves y ninguna es esa) y los dos pliegues puros
(`proyecto_de_gasto`, `departamento_de_gasto`; grep → 0).
**Lo que se rompe si esto se hace y no se acompana** — el spec dice que van en el mismo
movimiento:
- `costo_api_directo` (`calipso/economia/eficiencia.py:92`) pliega por `a.origen`; tiene
  que plegar por `detalle["dueno"]` o **la eficiencia de todos los departamentos se va a
  cero y el mapa pinta todos los edificios iguales**. El molde correcto ya existe al lado:
  `mercado.gasto_api_ciclo` (`mercado.py:29-33`). **Cuidado con el doble conteo:** si se
  pliega por `dueno` sin excluir `origen` que empieza con `trabajo:`, el mismo asiento se
  cuenta dos veces.
- **Y el numerador queda en cero igual.** `eficiencia_departamento`
  (`eficiencia.py:104-115`) cuenta ventas via `ventas_por_trabajo`, que exige
  `a.detalle.get("trabajo")` (`eficiencia.py:15-24`). Una venta de proyecto sin trabajo no
  le atribuye eficiencia a nadie. Falta el pliegue venta→proyecto→departamentos **y la
  regla de reparto**: si Atlas vende y tiene cinco departamentos habilitados, como se
  divide. Eso no es una linea, es una decision (seccion 4, pregunta 4).
- `cierre_departamento` (`calipso/economia/cierre.py:137-142`) se retira y pasa a ser
  `cierre_proyecto`.
- `situacion` (`calipso/plantel/situacion.py:89-108`, quince claves, ninguna de proyectos)
  gana la lista de proyectos que habilitan al departamento con su disponible;
  `dec.prompt` los ofrece (`calipso/plantel/decision.py:72-80`) y `jefe._puede` valida la
  referencia (`calipso/plantel/jefe.py:47-49`).
- el presupuesto de la propuesta pasa a `min(tope de agresividad, disponible del proyecto)`
  (`calipso/server.py:4413-4415`) y el freno deja de ser del departamento
  (`jefe.py:62-63`, `if s["disponible_mm"] <= 0`) — **con la plata en el proyecto, un
  departamento de apoyo queda congelado para siempre**.
**Tamano:** grande. **Depende de:** B3 + B4.

### B6 — La mezcla: quien paga vs. quien es dueno (spec 9.3)
**Falta, y es la decision de diseno mas grande de la economia.** Hoy `_cuenta_en_foco`
(`calipso/server.py:4632-4643`) deriva **quien paga** del edificio en foco via
`ficha.cuenta_pagadora`; `_ficha_y_cuenta` (`:4645-4677`) devuelve `(bloque, cuenta)` sin
concepto de proyecto ni de dueno; `_cobrar_turno` (`:4679`) recibe una sola `cuenta`.
Aguas abajo tampoco hay donde poner el dueno: ni `Pagador.cargar_api`
(`calipso/economia/pagador.py:148`) ni `cargar_suscripcion` (`:162`) lo aceptan, y
`Pagador._dueno_de` (`:119-123`) solo lo resuelve para `trabajo:` via bus.
El destino: paga el proyecto del chat, el dueno es el departamento en foco del mapa; el
foco deja de cambiar quien paga.
**Tamano:** grande. **Depende de:** B3 + B4 + B5.

### B7 — El freno cuando se acaba la plata
**Falta:** la politica que Pedro decidio hoy (la suscripcion sigue; la API pierde plata y
encola una carta) quedo **en el spec, no en el codigo**. `_apilar_pendiente`
(`calipso/economia/pagador.py:86-89`) apila y hace un `print` a stderr, nada mas.
`_cobrar_turno` (`calipso/server.py:4679`) tiene un `except Exception` que devuelve 0
(`:4710-4715`), y su docstring lo declara: "Nunca voltea el chat".
**Acople real:** `Pagador` no conoce la cola — sus rutas son libro/registro/suscripciones/
bus/pendientes (`pagador.py:52-56`) y el modulo no importa `cola`. Hay que agregarle
`<eco>/cola.jsonl` (la convencion esta en `calipso/server.py:3504`).
**Nota:** la carta no sirve de nada si no se drena `pendientes`, y eso lo hace
`Pagador.reintentar_pendientes`, que solo corre desde el cierre semanal (ver A1 abajo).
**Tamano:** chico. **Depende de:** A1 para tener efecto completo.

### B8 — Las perillas de un departamento son de solo lectura de por vida
**Falta:** un endpoint. `Registro.ajustar` (`calipso/economia/departamentos.py:77`) tiene
**cero** llamadores (`grep '\.ajustar('` → 0) y no existe `/api/economia/departamentos`
ni `/perilla`. `POST /api/economia/sembrar` las fija al crear y se niega a correr dos
veces (`calipso/server.py:3897`).
**Por que importa ahora mas que antes:** las perillas si las lee alguien —
`calipso/plantel/jefe.py:73` usa `agresividad_pct` como tope de gasto semanal y `:101`
usa `explorar_explotar_pct` para el sesgo del jefe. O sea: **la perilla que gobierna
cuanto gasta el jefe se fija una unica vez, en el sembrado, y despues solo se cambia
editando el JSON a mano.**
**Tamano:** chico. **Depende de:** nada (pero rinde solo despues del sembrado).

### B9 — Contabilidad que subestima
Tres cosas independientes, todas chicas:
- **El equipo dinamico gasta cinco veces y cobra una.** Hasta tres agentes corren via
  `_run_agent_text`/`_run_backend_text` (`calipso/server.py:1634`, `:1641`), mas la
  sintesis (`:1694`), contra un unico `_cobrar_turno` (`:2567`).
- **La suscripcion no llega a la barra de costo.** `cargar_suscripcion`
  (`calipso/economia/pagador.py:162`) devuelve `None`: cobra en el libro y descarta el monto.
- **Tokens inventados.** `mango.tokens(len(agent_system) // 4, len(output) // 4, 0)`
  (`calipso/server.py:1661`).
**Tamano:** chico cada uno. **Depende de:** el sembrado.

### B10 — Tres tablas de precio desincronizadas
`calipso/capabilities.py:39` (ordinal 0/1/3), `calipso/costs.py:30-34` (tres modelos),
`calipso/economia/pagador.py:28` (`{"deepseek-chat": (270, 1100)}` mas
`PRECIO_DESCONOCIDO = (3000, 15000)`). `api:claude-fable-5` esta en `capabilities.py:95`
y ausente de `costs.PRICING`. Todo lo que no sea deepseek cae en el precio conservador,
que sobreestima por cuatro. Y ninguna rutina revisa precios (`calipso/routines.py:29`).
**Tamano:** chico. **Depende de:** nada.

### B11 — Excepciones de dominio que suben 500 crudo
Ya tienen `except _eco_errores_economicos`: `calipso/server.py:3685`, `:3720`, `:3754`,
`:4057`. Siguen crudos: rechazar (`:3773`), reloj/in (`:3786`), reloj/out (`:3799`),
cierre (`:3812`), abrir (`:3830`), conciliar (`:3844`).
**Tamano:** chico. **Depende de:** nada.

### B12 — Infraestructura que quedo en Windows
`CREATE_NEW_CONSOLE` en `calipso/server.py:1127`, `:1144`, `:1164`: **los tres botones de
conectores devuelven 500 en Linux**. `calipso/config.py:32-33` sigue con `claude.cmd` /
`codex.cmd` (y `~/.calipso/config.json` tambien), asi que `dispatch.py` como CLI sale 127.
El checklist de arranque cuenta lanzadores de Windows y no ve `calipso.sh`
(`calipso/server.py:2815`). `RUNBOOK.md` integro de Windows. Sin `requirements.txt`.
**Tamano:** chico. **Depende de:** nada. Es la unica cosa de esta lista que rompe algo
que Pedro ve todos los dias.

### B13 — El mapa esta congelado
`traer()` se llama solo al arrancar y al volver online (`calipso/web/fabrica/app.js:672`,
`:50`). La mesa y las perillas refrescan cada 60 s (`:695`, `:698`); **la ciudad no**.
Ademas: el mapa no dibuja `eficiencia` (grep en `calipso/web/fabrica/mapa.js` → 0), dpr
redondeado a entero (`mapa.js:80`), y `PISO_DE_TESTS = 90` contra 163 que pasan
(`test_fabrica_js.py:21`).
**Tamano:** chico. **Depende de:** nada.

### B14 — Las dos vistas de proyecto
- **Vista A:** `#lista-chats` en secciones por proyecto, con seccion explicita "sin
  proyecto" y el disponible al lado del nombre. Hoy `pintarChats`
  (`calipso/web/fabrica/app.js:642-648`) pinta una lista plana. **El dato ya llega**:
  `calipso/chats.py:42` incluye `project_path` y `calipso/server.py:1019` lo expone.
  Solo necesita el campo `repo_path` del registro.
- **Vista B:** al tocar un edificio, una fila **por proyecto** que usa ese departamento,
  con gasto del ciclo, trabajos vivos y ultima actividad. Lo que hay es otra cosa:
  `mesa.textoDeMesa` (`calipso/web/fabrica/mesa.js:83-110`) filtra **propuestas del bus**
  por `p.departamento === filtro` (`:89`). Necesita el pliegue
  `proyectos_de_departamento` y un `GET /api/economia/departamento/{cuenta}`
  (grep `economia/departamento` → 0).
**Tamano:** vista A chica, vista B mediana. **Depende de:** B3 (+ B5 para la vista B).

### B15 — La bandeja (spec de manos, seccion 6)
No existe nada: `routines.KINDS` (`calipso/routines.py:29`) es
`("reflect", "learn", "backup", "departamento", "catastro")` y no hay handler
(`calipso/server.py:2709`); no hay endpoint ni fila en ninguna UI; no existen los dos
botones de 6.3.
**Precondicion que tampoco esta:** la marca de procedencia (8.3.1). `attachments.create`
sigue aceptando `source` opaco (`calipso/attachments.py:70, 93-94`) sin clave `origen`, y
el renderizador ramifica por `path` (`attachments.py:327-328`). No hay marco de documento
no confiable, y **8.3.2 no esta en ningun lado**: `motor.evaluar`
(`calipso/permisos/motor.py:113-200`) no consulta ninguna senal de contexto no confiable,
ni `Contexto` (`calipso/permisos/acciones.py:97-124`) tiene el campo. Hoy un permiso
permanente aplica igual con un documento hostil adentro.
**Tamano:** mediano. **Depende de:** B2.

### B16 — Catastro: el hueco que queda
El catastro esta hecho y en contexto. Falta **una sola cosa**: no hay forma de que Pedro
escriba la etiqueta `departamento`. El escaneo la preserva (`calipso/catastro.py:471`)
pero nadie la escribe: solo hay dos GET (`calipso/server.py:993`, `:1002`), ningun
POST/PUT. Hoy siempre es `None`.
**Tamano:** chico. **Depende de:** nada.

---

## 3. Construido y apagado

Trabajo ya pagado que no rinde. Prenderlo es barato y es lo de mejor relacion
esfuerzo/resultado de toda la lista.

### A1 — El cierre semanal: una raiz muerta que arrastra trece funciones
`POST /api/economia/cierre` (`calipso/server.py:3812`) **no tiene ningun llamador**.
Verificado: no esta en `calipso/web/` (grep `economia/cierre` → 0), no es un `kind` de
rutina (`_routine_handlers` devuelve exactamente `reflect, learn, backup, catastro,
departamento`, `calipso/server.py:2709`; `routines.DEFAULTS` tampoco), no esta en
`dispatch.py` ni `calipso.sh`, no hay cron. Unico ejercicio: `test_economia_server.py:96`.

Es el unico llamador de `cerrar_semana_operativa` y detras cuelga todo esto, todo muerto:

| Muerta por transitividad | Que se pierde |
|---|---|
| `operacion.cerrar_semana_operativa` (`calipso/economia/operacion.py:46`) | el orquestador |
| `cierre.cerrar_semana_economia` (`calipso/economia/cierre.py:52`) y `cerrar_ciclo` (`:158`) | el cierre y el breaker de dos rojos |
| `pt.cerrar_semana` (`calipso/economia/pt.py:182`), `pt.expirar_pools` (`:98`) | **los PT nunca expiran** |
| `cola.expirar_semana` (`calipso/economia/cola.py:169`) | las compuertas nunca caducan |
| `bus.evaluar_y_liquidar_muertos` (`calipso/economia/bus.py:180`) | un trabajo financiado que no rinde **nunca muere ni devuelve el escrow** |
| `departamentos.declarar_quiebra` (`calipso/economia/departamentos.py:100`) | **nadie congela nunca a nadie**: `es_congelado` (`:84`) tiene ocho llamadores vivos y en produccion devuelve siempre `False` |
| `direccion.asignar_presupuesto` (`calipso/economia/direccion.py:33`) | la direccion **nunca reparte presupuesto semanal** |
| `eficiencia.eficiencia_suscripcion` (`calipso/economia/eficiencia.py:72`) + `atribucion_por_suscripcion:50`, `costo_api_directo:86`, `ventas_por_trabajo:15`, `costos_de_trabajo:27` | media `eficiencia.py` corre solo en tests |
| `capacidad.recaudacion` (`calipso/economia/capacidad.py:109`) | "esta suscripcion no se paga sola" |
| `Pagador.reintentar_pendientes` (`calipso/economia/pagador.py:98`) | **los cargos fallidos nunca se reintentan** |

**Un `kind: "cierre"` en `_routine_handlers` mas su entrada en `DEFAULTS` enciende las
trece de una vez.** Es la linea de codigo mas rentable del repo. **Tamano:** chico.

### A2 — La cola: completa, testeada y sin una sola entrada
`Cola.encolar` (`calipso/economia/cola.py:67`) tiene **cero llamadores de produccion**.
Valida tipo, carril sesion/goteo, escrow al tipo de cambio vigente, recargo y tope; tests
densos en `test_economia_frontera.py:153-224`.
Consecuencia verificada: `Cola.pendientes()` (`cola.py:129`) **si** esta vivo — lo llama
`calipso/mapa/ciudad.py:268` en cada refresco — pero como nadie encola, `avisos()`
(`ciudad.py:248`) devuelve siempre lista vacia. **Los globitos de aviso sobre los
edificios son decorado inerte.** Y `pintarAvisos` (`calipso/web/fabrica/app.js:232-241`)
pinta `<span class="aviso">` sin `data-id` ni handler: aunque hubiera algo, no se puede
tocar. `atender` (`calipso/server.py:3759`) y `rechazar` (`:3773`) no tienen llamador de UI.
Quedan sin uso: `atender_carta` (`cola.py:152`), `rechazar` (`:145`), `servir` (`:182`).
**Tamano:** chico (un llamador + los handlers de la barra).

### A3 — El reloj: tres endpoints huerfanos
`POST /api/economia/reloj/in` (`calipso/server.py:3786`), `/out` (`:3799`), `/conciliar`
(`:3844`) — ninguno tiene llamador. Arrastran `Reloj.clock_in`/`clock_out`/`conciliar`
(`calipso/economia/reloj.py:57, 78, 125`), `pt.consumir_personal`
(`calipso/economia/pt.py:83`) y `Cola.servir`.
**Efecto medible:** `Reloj.minutos_por_categoria` devuelve siempre `{}`, asi que
`linea_empleo_mm_por_hora` (`calipso/economia/personal.py:63`) cae siempre en la rama
teorica `sueldo // 173`. **El numero de "linea de empleo" que la mesa le muestra a Pedro
nunca es real.** Aparte, `Reloj.huerfanos` (`reloj.py:119`) no lo llama nadie, ni siquiera
`conciliar`: nadie detecta un `clock_in` que quedo abierto de la semana pasada.

### A4 — `calipso/economia/cuenta_pedro.py`: el modulo entero esta muerto
Su docstring dice que son "las UNICAS formas tipadas de sacar plata" de la cuenta.
Cero llamadores las cuatro: `retirar` (`:13`), `reinyectar` (`:17` — Pedro no puede
devolver plata al tesoro), `financiar_personal` (`:22`), `rescatar` (`:31`).
`rescatar` duele doble: `es_congelado` (`calipso/economia/departamentos.py:84`) **lee** la
marca de rescate para descongelar, o sea que el camino de vuelta esta implementado en el
lector y no existe en el escritor. **Rescatar un departamento congelado hoy exige un REPL.**
`POST /api/economia/personal/movimiento` (`calipso/server.py:4145`) no cubre esto: escribe
en `personal.jsonl` y, textual, "nunca toca el libro de la fabrica".

### A5 — Sueltas
- `Mercado.vender_servicio` (`calipso/economia/mercado.py:162`), cero llamadores: **el
  comercio entre departamentos no existe.** La unica plata que se mueve entre cuentas es
  la que baja de la direccion o entra por la frontera.
- `direccion.pagar_carta_sistema` (`calipso/economia/direccion.py:73`) y
  `adelantar_obligatoria` (`:79`), cero llamadores. `adelantar_obligatoria` es el unico
  otro llamador posible de `Kernel.registrar_acreencia`, cuyas acreencias solo las cobra
  `Kernel.liquidar` — tambien muerta. **Circuito cerrado y apagado entero.**
- `_Mango.herramienta` (`calipso/mapa/pulso.py:105`), cero productores. El cliente sabe
  pintarlo (`calipso/web/fabrica/pulso.js:76-77`, y `"herramienta"` esta en `CONOCIDOS`,
  `:35`) pero el servidor solo emite `diff` (`calipso/server.py:629`), `razonando` (`:1660`)
  y `tokens` (`:1661`). **En el mapa nunca se ve que herramienta esta usando un agente.**
- `motor.aprobadas_para` (`calipso/permisos/motor.py:284`) y `motor.cerrar` (`:246`), cero
  llamadores: **una solicitud desatendida que Pedro aprueba queda parada para siempre**,
  porque ninguna rutina la retoma. `_departamento` (`calipso/server.py:2675-2707`) arma un
  `Contexto` de plantel, no de permisos, y nunca llama a `evaluar`.
- `trabajar` sigue siendo no-op declarado (`calipso/server.py:4394-4397`): **una propuesta
  financiada no produce trabajo.** Esta fuera de alcance a proposito, pero conviene tenerlo
  presente cuando se mire el bus y no pase nada.

### A6 — Restos superados: borrar, no llamar
`interruptor.anotar_tic` (`calipso/plantel/interruptor.py:134`) y `hay_cuerda` (`:144`) los
reemplazo `tomar_tic` (`:150`), que hace las dos cosas bajo candado y documenta la carrera
que la version separada tenia. Aca no falta un llamador: falta la baja.

### A7 — Endpoints huerfanos fuera de la economia
Superficie que no rinde. Por lo que cuesta que este apagada:
`GET /api/resources` (`calipso/server.py:3299`, sin llamador **y sin tests**),
`GET /api/telemetry` (`:3160`, idem), `GET /api/costs` (`:3041`, idem),
`POST /api/github/contribute/plan` (`:879`) y `/run` (`:888`) — el flujo de contribucion
entero sin UI, `GET /api/verify/recommend` (`:3360`) mientras su hermano `/run` si se usa,
`POST /api/discover` (`:2644`), `POST /api/memory/chronology/proposals` (`:3114`) y
`/inbox/suggest` (`:3128`), `GET /api/connectors/health` (`:1082`), `GET /setup` (`:285`,
sin enlace desde ninguna pagina).
Redundantes, no perdidos: `GET/POST /api/commands*` (`:3342`, `:3385` — la capacidad vive
en proceso via `calipso/tools/commands.py`), `GET /api/catastro*` (`:993`, `:1002` — el
catastro llega al chat por `catastro.cargar()` en `calipso/prompt_compiler.py:305`),
`POST /api/reflect` (`:2637`) y `/learn` (`:2957` — corren por el ticker),
`GET /api/deps` (`:2787`) y `POST /api/deps/install` (`:2868` — **el que se blindo hoy es
un endpoint que nadie invoca**).

---

## 4. Lo que decide Pedro y nadie mas

**1. La lista de departamentos del arranque y cuanto capital entra al tesoro.**
Nombraste cerebro/direccion, market research, legal, I&D; y para Atlas publicar, testing,
marketing, research, development. Tres preguntas concretas: "market research" y "research",
uno o dos? "publicar" es un departamento o es la frontera de salida? Y el numero del primer
capital, mas la regla: **el neto del banco acuna solo, hay tope semanal, o es un acto manual
cada vez?** Se suma un dato que quedo explicitamente sin inventar: la `capacidad_ciclo` de
cada suscripcion — cuantas unidades da cada plan por ciclo — hoy con un default de 1.000
marcado como estimacion (`calipso/server.py:3559-3562`). Ese numero decide cuando la fabrica
se queda sin cuota.
*Por que cambia el trabajo:* **es lo unico que separa a Pedro de tener economia.** Sin esto,
la seccion 1 sigue bloqueada y todo el bloque 2 se puede escribir pero no ver.

**2. Que es un entregable de un proyecto, y si "como va Atlas?" tiene pantalla.**
Hoy un proyecto es una billetera con nombre de carpeta: no hay `objetivo`, ni fecha de
cierre, ni entregables, y no hay ninguna pantalla donde mirar un proyecto — se lo ve como
encabezado de una seccion de chats y como fila dentro de la mesa de un departamento.
*Por que cambia el trabajo:* define el JSON de B3 y decide si B14 son dos vistas o tres.

**3. Como se reparte la eficiencia de una venta entre los departamentos de un proyecto.**
Si Atlas vende y tiene cinco departamentos habilitados, quien se lleva el credito.
*Por que cambia el trabajo:* sin regla de reparto, B5 arregla el denominador y deja el
numerador en cero — la eficiencia sigue rota y el mapa sigue pintando todos los edificios
iguales. No es una linea de codigo, es una decision.

**4. Los skills de terceros: entran ahora o no.**
Un spec dice "decidido: se cargan por archivo"; el otro dice "no se abre esa puerta hasta
que la seccion 8 este construida y verificada". **Un spec decide lo que el otro veta, en
silencio.** Hoy `calipso/skills.py:12` es un dict hardcodeado sin un solo import de I/O.
*Por que cambia el trabajo:* si entran, es un subsistema con superficie de ejecucion de
terceros; si no, se saca de los dos documentos.

**5. Que hace `_subscription_invocation` con los permisos (ver seccion 6, S5).**
`--allowedTools` no es "el agente contratado": esa funcion es **el chat de Pedro**
(llamadores en `calipso/server.py:597, 1497, 1523, 1654, 2372, 2427, 3163`). Ponerle
banderas cambia lo que Calipso puede hacer contestandole a Pedro.
*Por que cambia el trabajo:* es la diferencia entre acotar al agente y mutilar el chat.

---

## 5. Lo que yo sacaria del alcance

**La agencia de navegador.** Ya esta excluida a proposito, pero conviene decir por que
sigue afuera: depende del piso de procedencia (8.3.1) y del marco de documento no
confiable, que no existen (`calipso/attachments.py:327`). Construirla antes es abrir una
superficie de ejecucion sin la defensa que la justifica.

**`Cola.encolar` para el reloj y los PT, antes que para las cartas de cierre.**
Prender A1 llena la cola sola con cartas reales. Encolar a mano primero es escribir un
llamador que A1 vuelve redundante en una semana.

**Los endpoints huerfanos de A7 que son duplicados** — `/api/commands*`, `/api/catastro*`,
`/api/reflect`, `/api/learn`, `/api/deps*`. No hay que darles UI: hay que **borrarlos**.
Cada uno es superficie autenticada que nadie ejerce y que hay que blindar cuando aparece un
hallazgo. Blindar `POST /api/deps/install` fue trabajo bien hecho sobre un endpoint que no
existe para nadie.

**`interruptor.anotar_tic` y `hay_cuerda`** (A6): borrarlas. Tienen tests que hoy protegen
codigo superado, y la version que quedo documenta la carrera que ellas tenian.

**La vista que suma el gasto mensual de las cuatro fuentes** (suscripciones + precios API +
`costs.py` + la caja de direccion). Es un numero lindo que exige cruzar cuatro fuentes que
hoy **no coinciden** (B10). Primero sincronizar precios; el numero unico despues, si sigue
haciendo falta.

**El resto del catalogo de specs futuros** — frontera de salida, senales externas,
conectores bancarios, escrow, tarifas diferenciadas, copiadores y curiosos, ASD-STE100,
hooks deterministas, MCP, multi-PC federado, sensores nativos, Tailscale, estado `pausado`,
franjas laborales, sueldo en el libro personal. Verificado: cero modulos, cero greps
positivos. No es deuda; es una lista de deseos y conviene que se lea como tal.

---

## 6. Riesgos de seguridad vivos

Los tres de hoy estan cerrados y verificados (login sin token, `deps/install` con 403 en
`calipso/server.py:2884`, screenshot con `UrlNoPermitida` en `:2896`). Quedan estos:

**S2 — El token viaja en el query string y uvicorn lo loguea entero. El mas grave.**
`auth_guard` acepta `request.query_params.get("token")` (`calipso/server.py:250`) y para
`/api` o metodos que no son GET planta la cookie y sigue de largo sin redirigir (`:251-255`).
`uvicorn.run(app, host="0.0.0.0", port=8000)` sin `log_config` (`:4795`): el access log
escribe la query completa. El banner sigue imprimiendo el token dentro de una URL (`:4793`).
Y la cascara Tauri lo reinyecta en cada arranque: `format!("http://127.0.0.1:8000/?token={tok}")`
(`src-tauri/src/lib.rs:118`). Rotar el token no arregla el patron: **cada arranque escribe
el token nuevo en los logs.**

**S4b — `_safe` no tiene denylist de rutas sensibles.**
La mitad (a) esta hecha y bien: el techo vive en `_switch_project`, el unico lugar que
reasigna `ROOT`, y corta con 400 fuera de las raices declaradas (`calipso/server.py:968-990`).
La mitad (b) falta: `_safe` son cuatro lineas que solo comparan contra `ROOT`
(`calipso/server.py:299-304`). Como el home es raiz del catastro,
`_switch_project("~/.calipso")` pasa el techo, y desde ahi `/api/file?path=token` no tiene
quien lo pare. La prueba de aceptacion "`_safe` sobre `~/.calipso/token` da 400" hoy no pasa.
Lo mismo cubre `personal.jsonl`, el libro privado de Pedro.

**S5 y S6 — El agente hereda el CLI y el entorno enteros.**
`cmd += ["--append-system-prompt-file", temp_name, "-p", prompt]`
(`calipso/server.py:2007`): sin `--allowedTools`, sin `--add-dir`, sin `--permission-mode`.
Igual para codex (`:2009-2018`). Y `env = os.environ.copy()` con dos `pop` solo para claude
(`:2019-2022`): **`CALIPSO_TOKEN` sigue viajando**, lo que deja en letra muerta el "nunca"
de las credenciales por la otra puerta.
*Advertencia antes de tocar:* `--allowedTools` **agrega** a la allowlist, no la reemplaza;
los settings del repo abierto siguen aplicando ademas de las banderas; y una regla `deny`
sobre `Read` no cubre `Bash` (`cat ~/.ssh/id_rsa` es Bash). **El criterio de salida es un
test que intente leer `~/.ssh/id_rsa` desde el agente y falle.** Si ese test no se puede
escribir, es una UI y hay que decirlo. Existe ademas `_run_subscription_text_live`
(`calipso/server.py:2001-2006`), la version streaming, que ningun spec nombra.

**S3 — `CALIPSO_NO_TOTP` sin atar al origen.**
`_TOTP_DISABLED` sale del entorno sin mirar quien pide (`calipso/server.py:269`) y
`login_page` pinta "TOTP desactivado — ingresa cualquier codigo" a cualquiera (`:263-266`).
Falta atarlo a `127.0.0.1`.

**S7 — El volcado de prompts largos cae dentro del repo.**
`dir=str(ROOT)` (`calipso/server.py:1986`). No existe `~/.calipso/tmp/`. Un prompt de mas de
7000 caracteres — con lo que tenga adentro — queda como archivo en el proyecto abierto.

**WS sin chequeo de `Origin`.** `ws_chat` (`calipso/server.py:2227`) y el de mapa/pulso
(`:4469`) autentican solo por cookie; ninguno mira el header. Corrijo un reporte previo:
`ws_mapa` **ya no** acepta token por query.

**CSP de la cascara con `unsafe-inline` y `unsafe-eval` en `script-src`.**
`src-tauri/tauri.conf.json:21`. `style-src` ya esta separado, asi que el arreglo es solo
endurecer `script-src`. **Agravante:** `src-tauri/` sigue sin trackear (`git status`:
`?? Cargo.lock`, `?? Cargo.toml`, `?? src-tauri/`) — la CSP que hay que arreglar no esta en
git y un `git clean -fd` la borra. Hoy no es explotable porque la cascara no compila desde
aca, pero la UI ya renderiza SVG del modelo (`calipso/web/index.html:1694`,
`calipso/web/fabrica/svg.js:7-10`): el iframe sandbox aguanta solo, sin capa de CSP detras.

**Un solo token global, sin sujeto** (`calipso/server.py:152-153`). No hay identidad: todo
lo que entra es "Pedro". Cualquier registro de permisos anota siempre al mismo actor.

**`CALIPSO_HOME` congelado al importar, en dieciseis modulos.**
`backup.py:17`, `attachments.py:27`, `config.py:9`, `chronology.py:18`, `discovery.py:21`,
`librarian.py:20`, `chats.py:9`, `routines.py:26`, `capabilities.py:26`, `costs.py:24`,
`jobs.py:18`, `goals.py:20`, `memory.py:38`, `telemetry.py:9`, `sessions.py:23`. Solo
`catastro.py` esta arreglado. **El decimosexto es el peor y no estaba anotado en ningun
inventario:** `_ECO_BASE` (`calipso/server.py:3488`) es la raiz de la economia entera —
libro, registro, suscripciones, cola, bus, personal y el `base` del interruptor del plantel.
No es un agujero explotable; es una bomba de tests y de entornos que se desactiva sola en
cuanto alguien mueva `CALIPSO_HOME` en caliente.

---

## 7. Documentacion, en una linea

`AGENTS.md` tiene **cero** menciones de economia, departamento, mapa o fabrica (grep
verificado): el documento que lee un agente al entrar no sabe que existe la mitad del
sistema. `calipso/doclinks.py:18` sigue sin `DESIGN.md` ni `docs/superpowers/`. Diecisiete
lineas de mojibake en `calipso/server.py`. `calipso/tools/commands.py:190` sigue diciendo
que `test_memory.py` requiere Ollama con bge-m3. Y la fabrica sigue en cyan
(`calipso/web/fabrica/estilo.css:8`, `--acento: #66d9ff`) contra lo que dice `DESIGN.md`.

---

## 8. Una trampa que no existe — no la "arreglen"

El jefe del plantel piensa contra Ollama directo (`calipso/server.py:4352-4356`), **no** por
la ruta "local" que ejecuta `claude -p`. Esta bien resuelto y parece un bug cuando se lee
rapido. Queda anotado para que nadie lo rompa.
