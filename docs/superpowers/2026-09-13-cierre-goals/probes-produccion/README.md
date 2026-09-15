# Probes en produccion (2026-09-15, pedidos por Pedro: "corre pruebas directas en Calipso")

Contra el server REAL (8000) con el token de Pedro y su suscripcion: lecturas (goals, carga, memoria,
aduana, inbox), turnos por el chat (`/help`, `/goal estado`, `/goal ...`, `/goal dale`, `/goal parar`,
`/goal no`) y goals reales chicos sobre repos temporales sin remoto (`/tmp/probe-calipso-repoN`, `tope: 3
golpes 8m`). Cuatro rondas; cada una encontro algo real que se arreglo, se mergeo y se desplego antes de la
siguiente (la ronda 4 quedo 16/0):

1. `ronda1.log` (18/13): el sistema no tiene pytest; el martillo creo el venv del clon y `pip install
   pytest` cayo en `deny network-outbound pypi.org`: la compuerta `instalar_en_goal` (directo) era
   imposible sin red a los indices. Ademas 5 de 14 Bash denegados por `&&`, `|`, `2>&1`, `python -c` y un
   commit con salto de linea. -> ruling 32 (indices de paquetes en la red del sandbox con
   instalar_en_goal directo; el contrato dice como usar Bash). El resto de los fallos: el script asumia
   `cumplido`.
2. `ronda2.log` (15/4): con pypi, el criterio paso confinado, pero el revisor codex dijo NO cumplido porque
   `pytest -q` a secas no existe fuera del venv (no sabia que el runner ya lo corrio) y el martillo pidio
   instalar pytest en el home. `git -C <clon>` denegado. -> ruling 33 (el revisor recibe el resultado del
   criterio y no lo rejuzga; git -C dentro del clon pasa). Los 2 fallos de la retoma: el script no
   esperaba el tick del runner.
3. `ronda3.log` (23/1): los dos goals de punta a punta (complete con la rama traida; parar -> retomar por
   el inbox con nota -> complete). Dos commits denegados por el `<noreply@anthropic.com>` de la firma
   entre comillas. -> ruling 34 (los operadores del shell se buscan fuera de las comillas). El fallo:
   `ultima_nota` se consume en el golpe siguiente (la nota SI llego: evento `nota_pedro`).
4. `ronda4.log` (16/0): un golpe de 39 s, 9 comandos, 0,23 USD, ventana de 5 h al 3 %; el unico deny del
   hook fue su propia sonda (`gh pr create --fill`); criterio confinado en verde, revisor codex
   `proveedor_distinto`, 40 cruces de aduana, complete con la rama en el origen y HEAD intacto.

Lo que dejan los probes en el home real: `~/.calipso/goals/<id>/` (siete goals, todos finales),
`~/.local/share/calipso/goals/<id>/repo` (los clones), y los chats `probe ...` en la PWA (se pueden
borrar). Nada fuera de eso; el server real se reinicio tres veces con main.

## Probe de capacidades del chat (2026-09-15, pedido de Pedro: "un turno que pruebe todas las capacidades")

`probes_capacidades.py` (un turno por capacidad en el chat real, mas un goal que instala torch) y los logs
`capacidades-vuelta1..6.log`. Cada vuelta encontro algo real que se arreglo, mergeo y desplego antes de la
siguiente:

- Vuelta 1 (14 turnos + goal): `/fast` sonnet, `/think` y `/ultrathink` opus, `/claude` honesto, `/codex`
  dice "soy Codex" (la identidad de Calipso no llega por esa ruta: pendiente), `/local` 7b honesto sin
  reloj, `/web` 3.14.7 con fuente, imagen honesta (no hay modelo; ofrece SVG), `/plan` >7 min (equipo),
  `/nube` bien. Bugs: `hoy` disparaba la busqueda web; el PDF fue al 7b que invento que lo hacia; python.org
  llegaba en gzip; el goal de torch murio como `hook inactivo` por un `sleep 60` que bloqueo el propio CLI,
  y `hasta: python verifica.py` caia en revisor (ruling 35).
- Vuelta 2: la RAM en 0. Dos causas: cada turno de chat por suscripcion lanzaba `claude -p` con TODOS los
  MCP/plugins/hooks/herramientas de Pedro (playwright = node + Chromium), y con el equipo de agentes en
  paralelo el swap se lleno y el kernel mato a Ollama; y `/tmp` (tmpfs = RAM) tenia 4,6 GB de homes de
  tests y experimentos filtrados (932 + 187 + 199 + 167 directorios). Arreglado: `--strict-mcp-config
  --setting-sources "" --tools ""` en el chat; la suite y los experimentos borran su home al salir.
- Vuelta 3: el PDF fue a sonnet pero narro "despues genero el PDF. Empecemos." (sin manos); el goal quedo
  `waiting compuerta` sin solicitud porque `web` es directo y el motor la concedio sin preguntar (ruling 37).
- Vuelta 4: el PDF contesta honesto y propone `/goal generar PDF ... hasta: archivo .pdf en ~/Descargas`;
  el goal de torch cerro de punta a punta (2 golpes + revisor codex, 2,6 min, 4 unidades, ~0,66 USD,
  `torch 2.14.0+cpu` en el venv del clon, `verifica.py` imprime el producto de dos tensores, rama traida).
  Ultimo hallazgo: el hook denegaba `.venv/bin/python` por ser symlink al sistema (ruling 38).

Pendientes que dejo el probe: la identidad de Calipso por la ruta Codex; la fecha y hora en el contexto del
modelo local; `/plan` tarda mas de 7 minutos; la regla de carga no mira el swap lleno (zram) al decidir si
carga el 7b; un goal para "instalar una app" pasa por `instalar_sistema` (pregunta) y no se probo.
