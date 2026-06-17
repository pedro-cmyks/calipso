# Calipso - biblioteca y memoria

Este documento define donde vive cada tipo de conocimiento de Calipso, quien lo
lee y como crece. La idea central: Calipso necesita un bibliotecario, no solo una
pila de recuerdos. El bibliotecario decide que se queda como episodio, que se
promueve a memoria estable, que pertenece a la identidad y que pertenece al
handoff tecnico del proyecto.

## Mapa corto

```text
Pedro
  habla con Calipso

Calipso
  lee identidad + memoria + estado operativo
  usa modelos/herramientas/agentes internos
  asigna skills como musculos de trabajo
  responde con una sola voz

Bibliotecario
  clasifica lo aprendido
  promueve hechos duraderos
  evita mezclar identidad, handoff, preferencias y logs
```

## Documentos principales

### `CALIPSO.md`

Es la constitucion de Calipso: identidad, principios, tono, politica de modelos,
verificacion, memoria, telemetria y conectores.

Lo lee Calipso como contexto de identidad. Debe ser estable y pequeno. No debe
convertirse en changelog ni backlog tecnico.

Va aqui:

- que significa ser Calipso;
- como debe hablar con Pedro;
- como debe tratar a los modelos externos;
- reglas profundas de honestidad, verificacion y autonomia;
- principios que no cambian cada sesion.

No va aqui:

- detalles de ultimo commit;
- bugs puntuales;
- instrucciones largas de setup;
- tareas pendientes de una semana.

### `AGENTS.md`

Es el handoff tecnico para agentes de codigo: Codex, Claude Code u otro agente que
entre a trabajar en este repo.

Lo leen los agentes que modifican el proyecto. Calipso no deberia meterlo entero
en cada conversacion visible con Pedro, porque contiene ruido de ingenieria.

Va aqui:

- estado real del repo;
- que ya esta hecho y verificado;
- como arrancar y probar;
- decisiones tecnicas que no se deben relitigar;
- proximos pasos recomendados;
- gotchas operativos;
- rutas importantes.

No va aqui:

- preferencias globales de Pedro;
- identidad profunda de Calipso, salvo resumen;
- logs extensos;
- recuerdos episodicos.

### `LIBRARY.md`

Es el mapa de la biblioteca: explica que documento significa que, que lee quien,
y como se promueve conocimiento.

Lo leen agentes de codigo y, cuando sea relevante, Calipso para entender su propia
arquitectura de memoria.

Va aqui:

- taxonomia de memoria;
- reglas de promocion;
- donde guardar cada cosa;
- como evitar duplicar o mezclar capas;
- convenciones para nueva literatura.

### Core markdown global

Ruta:

```text
~/.calipso/global/core/
```

Es memoria estable sobre Pedro que sirve en cualquier proyecto.

Archivo inicial importante:

```text
~/.calipso/global/core/pedro-perfil.md
~/.calipso/global/core/pedro-cronologia.md
```

`pedro-perfil.md` es un seed curado importado desde memorias previas de Pedro.
Debe tratarse como base evolutiva: util para interpretar estilo, proyectos,
intereses y referencias comprimidas, pero corregible por Pedro. No es una regla
dura ni una biografia definitiva.

`pedro-cronologia.md` es la linea de tiempo curada: cambios de etapa,
actualizaciones fechadas, proyectos que pasan a primer plano y correcciones de
estado actual. Si algo viejo del perfil choca con una entrada nueva de la
cronologia, Calipso prioriza lo nuevo y lo marca como contexto actual.

Va aqui:

- preferencias personales duraderas;
- forma de trabajar;
- idioma y estilo;
- limites y sensibilidades;
- hechos personales que Pedro quiere que Calipso recuerde.
- cambios fechados o estado actual que corrige recuerdos viejos.

No va aqui:

- detalles tecnicos de este repo;
- decisiones de Calipso como producto;
- logs de una sesion.

### Core markdown del proyecto

Ruta:

```text
<repo>/.calipso/core/
```

Es memoria estable sobre este proyecto. Viaja con el repo.

Va aqui:

- decisiones tecnicas del proyecto;
- objetivos de producto;
- arquitectura local;
- convenciones propias del repo;
- hechos que ayudan a trabajar aqui despues.

No va aqui:

- preferencias globales de Pedro;
- secretos;
- tokens;
- ruido de ejecuciones puntuales.

### Memoria episodica

Rutas:

```text
~/.calipso/global/chroma/
~/.calipso/projects/<slug>/chroma/
```

Es el volumen: conversaciones, eventos, outputs, detalles que pueden servir por
busqueda semantica. No todo lo episodico merece volverse core.

### Telemetria

Rutas tipicas:

```text
~/.calipso/costs.jsonl
~/.dispatch/decisions.jsonl
```

Es experiencia operativa: rutas decididas/usadas, costos, latencia, fallbacks,
errores, aceptaciones o descartes.

La telemetria no es memoria narrativa. Sirve para aprender comportamiento y
mejorar ruteo.

## Reglas del bibliotecario

### 1. Clasificar antes de guardar

Antes de escribir conocimiento duradero, preguntar:

- Es identidad de Calipso? -> `CALIPSO.md`.
- Es handoff para agentes de codigo? -> `AGENTS.md`.
- Es regla de biblioteca/memoria? -> `LIBRARY.md`.
- Es preferencia de Pedro para todos los proyectos? -> core global.
- Es decision tecnica de este repo? -> core del proyecto o `AGENTS.md`.
- Es solo un evento util por si acaso? -> memoria episodica.
- Es metrica/resultado operativo? -> telemetria.

### 2. Promover solo lo durable

Un episodio se promueve si:

- probablemente seguira siendo verdadero en futuras sesiones;
- Pedro lo corrigio o lo enfatizo;
- evita repetir una decision ya tomada;
- reduce riesgo o costo;
- ayuda a otro agente a continuar sin adivinar.

No se promueve si:

- fue una prueba temporal;
- es un secreto;
- es una impresion vaga;
- depende de una condicion que cambiara pronto;
- se puede recuperar mejor como log.

### 3. Separar voz visible de proceso interno

Pedro habla con Calipso. Los agentes internos, modelos, rutas y herramientas
pueden aparecer en paneles de telemetria, pero la respuesta principal mantiene
una sola voz.

Los skills internos tambien son proceso interno. "Investigador", "editor de
codigo", "verificador" o "bibliotecario" son rutinas de trabajo, no identidades
separadas frente a Pedro.

### 3.5 Compilar contexto antes de llamar modelos

Calipso no debe mandar el mensaje crudo de Pedro como unica instruccion a cada
backend. Debe construir un contexto de trabajo:

- constitucion de Calipso;
- perfil/memoria global de Pedro;
- memoria del proyecto;
- recuerdos episodicos relevantes;
- meta activa;
- repo/adjuntos si aplican;
- herramientas y permisos;
- estado operativo de modelos/conectores;
- evidencia esperada.

`calipso/prompt_compiler.py` define este contrato v0. Es la capa que traduce
conversacion humana a brief interno para modelos/agentes. La memoria global de
Pedro aporta compresion: nombres como "Atlas", "Observatory" o "Mulspel" pueden
expandirse si estan curados; si no, el bibliotecario debe proponer una tarjeta.

### 4. Mantener documentos pequenos y vivos

Cada documento debe tener una funcion clara. Si empieza a crecer demasiado,
dividir:

```text
CALIPSO.md   -> identidad
AGENTS.md    -> handoff tecnico
LIBRARY.md   -> sistema de memoria
SPEC.md      -> contrato de producto y plan de ejecucion
ROADMAP.md   -> plan de producto
RUNBOOK.md   -> operacion/verificacion
DECISIONS.md -> decisiones historicas
```

No crear estos archivos por estetica. Crearlos cuando el contenido ya pida una
casa propia.

## Como se comunica todo

```text
Turno de Pedro
  |
  v
Calipso carga:
  - sistema base
  - CALIPSO.md
  - core global/proyecto
  - recuerdos episodicos relevantes
  - estado operativo
  |
  v
Router decide modelo/ruta/agentes
  |
  v
Orquestador asigna skills
  |
  v
Herramientas/modelos/agentes trabajan
  |
  v
Calipso sintetiza una respuesta
  |
  v
Memoria/telemetria registran experiencia
  |
  v
Bibliotecario decide si algo se promueve
```

## Estado actual del bibliotecario

Hoy existe parcialmente:

- `Memory.reflect()` promueve episodios a core con ayuda de un modelo local.
- `CALIPSO.md`, `AGENTS.md` y este `LIBRARY.md` separan identidad, handoff y mapa
  de memoria.
- La telemetria ya existe, pero todavia falta cerrar el ciclo de aprender de
  aceptar/descartar propuestas y rutinas periodicas.

Falta construir:

- una rutina periodica de reflexion;
- UI/inbox para revisar promociones importantes antes de escribirlas;
- logging claro de aceptar/descartar propuestas;
- reglas mas finas para decidir global vs proyecto;
- artifacts verificables unidos al plan ejecutado.
