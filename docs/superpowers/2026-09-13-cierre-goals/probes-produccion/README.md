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
