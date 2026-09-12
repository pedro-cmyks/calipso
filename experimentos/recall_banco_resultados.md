# Banco de recall: MiniLM contra bge-m3 en tres variantes (spec memoria por Ollama, seccion 3)

Corrida: 2026-09-12 13:06. Consultas por condicion: 37 (24 positivas = 8 topicos x 3, 8 negativas, mas las reales). Score = coseno (= 1 - distancia de chroma). Los duplicados del fixture cuentan como UN acierto (por topico).

## Resumen por condicion

| condicion | docs | hit@1 | hit@4 | reales hit@1 | aciertos min/med/max | negativas min/med/max | margen | umbral sugerido | s docs | s consultas |
|---|---|---|---|---|---|---|---|---|---|---|
| minilm | 21 | 22/24 | 24/24 | 4/5 | (0.4057, 0.6597, 0.7637) | (0.0221, 0.2206, 0.3428) | 0.0629 | 0.374 | 0.36 | 0.12 |
| bge-m3:pregunta | 21 | 23/24 | 24/24 | 4/5 | (0.4591, 0.7843, 1.0) | (0.3147, 0.4117, 0.4627) | -0.0036 | None | 3.37 | 1.48 |
| bge-m3:pregunta+150 | 21 | 24/24 | 24/24 | 5/5 | (0.5537, 0.6654, 0.8181) | (0.2313, 0.346, 0.3987) | 0.155 | 0.476 | 7.41 | 1.53 |
| bge-m3:par | 21 | 24/24 | 24/24 | 5/5 | (0.5369, 0.6597, 0.8181) | (0.2313, 0.3656, 0.452) | 0.0849 | 0.494 | 16.96 | 1.55 |

## hit@1 por topico (de 3 consultas: literal, parafrasis de la pregunta, parafrasis del contenido)

| topico | minilm | bge-m3:pregunta | bge-m3:pregunta+150 | bge-m3:par |
|---|---|---|---|---|
| libro_empezado | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) |
| libro_rosa | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) |
| presupuesto_taller | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) |
| mariana_agosto | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) |
| repo_calipso | 1/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) |
| mapa_ciudad | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) |
| buen_dia | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) |
| websocket | 3/3 (hit@4 3/3) | 2/3 (hit@4 3/3) | 3/3 (hit@4 3/3) | 3/3 (hit@4 3/3) |

## Ruido intra-corpus: otro topico en el top-4 de las positivas

El margen se mide contra temas AUSENTES (las negativas); el ruido de siempre es OTRO episodio del mismo corpus. Por condicion: cuantos hits de otro topico hay en el top-4 de las consultas positivas (literal, parafrasis y reales), el max de sus scores y cuantos pasan el umbral sugerido de la condicion y los de referencia (0.476 el turno, 0.44 la consulta del abismo, 0.30 el viejo de MiniLM). Un umbral por margen no filtra este ruido: los umbrales siguen PROVISORIOS y se re-miden cuando el corpus crezca.

| condicion | hits de otro topico | max | pasan el sugerido | pasan 0.476 | pasan 0.44 | pasan 0.30 |
|---|---|---|---|---|---|---|
| minilm | 63 | 0.7011 | 26/63 (0.374) | 14/63 | 16/63 | 45/63 |
| bge-m3:pregunta | 64 | 0.6292 | - (sin umbral) | 26/64 | 35/64 | 64/64 |
| bge-m3:pregunta+150 | 63 | 0.6961 | 22/63 (0.476) | 22/63 | 32/63 | 63/63 |
| bge-m3:par | 63 | 0.6961 | 21/63 (0.494) | 22/63 | 36/63 | 63/63 |

## Regla de parada

- bge-m3:pregunta: margen -0.0036 (negativo o sin datos): PARAR y decirle a Pedro
- bge-m3:pregunta: hit@1 por debajo de MiniLM en ['websocket']: PARAR y decirle a Pedro

## Umbrales elegidos (a completar a mano al anotar: ver el plan, Task 3, Step 10)

- `RECALL_MIN_SCORE` (server.py): 0.476, el umbral sugerido de `bge-m3:pregunta+150` (punto medio entre el peor acierto 0.5537 y la peor negativa 0.3987; margen 0.155, el mayor de las tres variantes y 2,5 veces el de MiniLM). Antes 0.30 sobre MiniLM.
- `RECALL_UMBRAL` (abismo/fuentes.py): 0.44 = max(negativas) 0.3987 + 0.25 * margen 0.155 = 0.4375, a dos decimales (mas bajo que el del turno: la consulta la escribe el modelo). Antes 0.20 sobre MiniLM.
- variante aterrizada (`PALABRAS_RESPUESTA`): 150 (pregunta+150, la que ya estaba en produccion) porque separa mejor que `par` (margen 0.0849, y embebe 2,3 veces mas lento: 16.96 s contra 7.41 s por los 21 docs) y que `pregunta` (margen -0.0036 y 2/3 en websocket: la pregunta sola no separa, las negativas suben a 0.46). Las dos lineas PARADA son de `bge-m3:pregunta`, la variante descartada; la aterrizada iguala o supera a MiniLM en los 8 topicos (MiniLM 1/3 en repo_calipso y 4/5 en las reales: confunde la fila real de los proyectos con mapa_ciudad del fixture).

## Detalle: top-1 por consulta

| condicion | consulta | tipo | top-1 (topico, score) | mejor del topico | acierto@1 |
|---|---|---|---|---|---|
| minilm | libro_empezado/literal | literal | libro_empezado (0.6848) | 0.6848 | si |
| minilm | libro_empezado/pregunta | parafrasis_pregunta | libro_empezado (0.6147) | 0.6147 | si |
| minilm | libro_empezado/contenido | parafrasis_contenido | libro_empezado (0.7326) | 0.7326 | si |
| minilm | libro_rosa/literal | literal | libro_rosa (0.6687) | 0.6687 | si |
| minilm | libro_rosa/pregunta | parafrasis_pregunta | libro_rosa (0.6982) | 0.6982 | si |
| minilm | libro_rosa/contenido | parafrasis_contenido | libro_rosa (0.5629) | 0.5629 | si |
| minilm | presupuesto_taller/literal | literal | presupuesto_taller (0.6997) | 0.6997 | si |
| minilm | presupuesto_taller/pregunta | parafrasis_pregunta | presupuesto_taller (0.4788) | 0.4788 | si |
| minilm | presupuesto_taller/contenido | parafrasis_contenido | presupuesto_taller (0.4952) | 0.4952 | si |
| minilm | mariana_agosto/literal | literal | mariana_agosto (0.6494) | 0.6494 | si |
| minilm | mariana_agosto/pregunta | parafrasis_pregunta | mariana_agosto (0.5069) | 0.5069 | si |
| minilm | mariana_agosto/contenido | parafrasis_contenido | mariana_agosto (0.7334) | 0.7334 | si |
| minilm | repo_calipso/literal | literal | real:m4-2026-08-27T10:34:01 (0.4897) | 0.4283 | no |
| minilm | repo_calipso/pregunta | parafrasis_pregunta | real:m4-2026-08-27T10:34:01 (0.6212) | 0.57 | no |
| minilm | repo_calipso/contenido | parafrasis_contenido | repo_calipso (0.6119) | 0.6119 | si |
| minilm | mapa_ciudad/literal | literal | mapa_ciudad (0.747) | 0.747 | si |
| minilm | mapa_ciudad/pregunta | parafrasis_pregunta | mapa_ciudad (0.5394) | 0.5394 | si |
| minilm | mapa_ciudad/contenido | parafrasis_contenido | mapa_ciudad (0.6368) | 0.6368 | si |
| minilm | buen_dia/literal | literal | buen_dia (0.4057) | 0.4057 | si |
| minilm | buen_dia/pregunta | parafrasis_pregunta | buen_dia (0.408) | 0.408 | si |
| minilm | buen_dia/contenido | parafrasis_contenido | buen_dia (0.5258) | 0.5258 | si |
| minilm | websocket/literal | literal | websocket (0.6929) | 0.6929 | si |
| minilm | websocket/pregunta | parafrasis_pregunta | websocket (0.6625) | 0.6625 | si |
| minilm | websocket/contenido | parafrasis_contenido | websocket (0.6568) | 0.6568 | si |
| minilm | neg/tokio | negativa | buen_dia (0.3428) | None | no |
| minilm | neg/pan | negativa | presupuesto_taller (0.1161) | None | no |
| minilm | neg/rueda | negativa | repo_calipso (0.1912) | None | no |
| minilm | neg/waterloo | negativa | libro_empezado (0.1692) | None | no |
| minilm | neg/rodilla | negativa | repo_calipso (0.0221) | None | no |
| minilm | neg/alquiler | negativa | presupuesto_taller (0.2663) | None | no |
| minilm | neg/mongolia | negativa | mapa_ciudad (0.25) | None | no |
| minilm | neg/wifi | negativa | websocket (0.2941) | None | no |
| minilm | real/m0-2026-06-29T15:12:59/contenido | real_contenido | real:m0-2026-06-29T15:12:59 (0.7379) | 0.7379 | si |
| minilm | real/m3-2026-08-27T09:34:18/contenido | real_contenido | real:m3-2026-08-27T09:34:18 (0.7637) | 0.7637 | si |
| minilm | real/m4-2026-08-27T10:34:01/contenido | real_contenido | mapa_ciudad (0.7011) | 0.5803 | no |
| minilm | real/m5-2026-08-27T11:35:42/contenido | real_contenido | real:m5-2026-08-27T11:35:42 (0.6904) | 0.6904 | si |
| minilm | real/m41-2026-09-01T16:02:40/contenido | real_contenido | real:m41-2026-09-01T16:02:40 (0.7473) | 0.7473 | si |
| bge-m3:pregunta | libro_empezado/literal | literal | libro_empezado (1.0) | 1.0 | si |
| bge-m3:pregunta | libro_empezado/pregunta | parafrasis_pregunta | libro_empezado (0.8064) | 0.8064 | si |
| bge-m3:pregunta | libro_empezado/contenido | parafrasis_contenido | libro_empezado (0.6398) | 0.6398 | si |
| bge-m3:pregunta | libro_rosa/literal | literal | libro_rosa (1.0) | 1.0 | si |
| bge-m3:pregunta | libro_rosa/pregunta | parafrasis_pregunta | libro_rosa (0.9017) | 0.9017 | si |
| bge-m3:pregunta | libro_rosa/contenido | parafrasis_contenido | libro_rosa (0.6904) | 0.6904 | si |
| bge-m3:pregunta | presupuesto_taller/literal | literal | presupuesto_taller (1.0) | 1.0 | si |
| bge-m3:pregunta | presupuesto_taller/pregunta | parafrasis_pregunta | presupuesto_taller (0.7835) | 0.7835 | si |
| bge-m3:pregunta | presupuesto_taller/contenido | parafrasis_contenido | presupuesto_taller (0.4965) | 0.4965 | si |
| bge-m3:pregunta | mariana_agosto/literal | literal | mariana_agosto (1.0) | 1.0 | si |
| bge-m3:pregunta | mariana_agosto/pregunta | parafrasis_pregunta | mariana_agosto (0.8599) | 0.8599 | si |
| bge-m3:pregunta | mariana_agosto/contenido | parafrasis_contenido | mariana_agosto (0.6195) | 0.6195 | si |
| bge-m3:pregunta | repo_calipso/literal | literal | repo_calipso (1.0) | 1.0 | si |
| bge-m3:pregunta | repo_calipso/pregunta | parafrasis_pregunta | repo_calipso (0.7029) | 0.7029 | si |
| bge-m3:pregunta | repo_calipso/contenido | parafrasis_contenido | repo_calipso (0.4591) | 0.4591 | si |
| bge-m3:pregunta | mapa_ciudad/literal | literal | mapa_ciudad (1.0) | 1.0 | si |
| bge-m3:pregunta | mapa_ciudad/pregunta | parafrasis_pregunta | mapa_ciudad (0.7804) | 0.7804 | si |
| bge-m3:pregunta | mapa_ciudad/contenido | parafrasis_contenido | mapa_ciudad (0.6667) | 0.6667 | si |
| bge-m3:pregunta | buen_dia/literal | literal | buen_dia (1.0) | 1.0 | si |
| bge-m3:pregunta | buen_dia/pregunta | parafrasis_pregunta | buen_dia (0.7843) | 0.7843 | si |
| bge-m3:pregunta | buen_dia/contenido | parafrasis_contenido | buen_dia (0.594) | 0.594 | si |
| bge-m3:pregunta | websocket/literal | literal | websocket (1.0) | 1.0 | si |
| bge-m3:pregunta | websocket/pregunta | parafrasis_pregunta | websocket (0.8834) | 0.8834 | si |
| bge-m3:pregunta | websocket/contenido | parafrasis_contenido | real:m41-2026-09-01T16:02:40 (0.4866) | 0.4767 | no |
| bge-m3:pregunta | neg/tokio | negativa | buen_dia (0.4517) | None | no |
| bge-m3:pregunta | neg/pan | negativa | mapa_ciudad (0.3781) | None | no |
| bge-m3:pregunta | neg/rueda | negativa | presupuesto_taller (0.4125) | None | no |
| bge-m3:pregunta | neg/waterloo | negativa | websocket (0.3156) | None | no |
| bge-m3:pregunta | neg/rodilla | negativa | libro_rosa (0.4238) | None | no |
| bge-m3:pregunta | neg/alquiler | negativa | presupuesto_taller (0.411) | None | no |
| bge-m3:pregunta | neg/mongolia | negativa | mapa_ciudad (0.3147) | None | no |
| bge-m3:pregunta | neg/wifi | negativa | websocket (0.4627) | None | no |
| bge-m3:pregunta | real/m0-2026-06-29T15:12:59/contenido | real_contenido | real:m0-2026-06-29T15:12:59 (0.7482) | 0.7482 | si |
| bge-m3:pregunta | real/m3-2026-08-27T09:34:18/contenido | real_contenido | real:m3-2026-08-27T09:34:18 (0.6796) | 0.6796 | si |
| bge-m3:pregunta | real/m4-2026-08-27T10:34:01/contenido | real_contenido | real:m4-2026-08-27T10:34:01 (0.6655) | 0.6655 | si |
| bge-m3:pregunta | real/m5-2026-08-27T11:35:42/contenido | real_contenido | real:m5-2026-08-27T11:35:42 (0.8287) | 0.8287 | si |
| bge-m3:pregunta | real/m41-2026-09-01T16:02:40/contenido | real_contenido | real:m0-2026-06-29T15:12:59 (0.5213) | 0.3751 | no |
| bge-m3:pregunta+150 | libro_empezado/literal | literal | libro_empezado (0.784) | 0.784 | si |
| bge-m3:pregunta+150 | libro_empezado/pregunta | parafrasis_pregunta | libro_empezado (0.6579) | 0.6579 | si |
| bge-m3:pregunta+150 | libro_empezado/contenido | parafrasis_contenido | libro_empezado (0.582) | 0.582 | si |
| bge-m3:pregunta+150 | libro_rosa/literal | literal | libro_rosa (0.8146) | 0.8146 | si |
| bge-m3:pregunta+150 | libro_rosa/pregunta | parafrasis_pregunta | libro_rosa (0.7732) | 0.7732 | si |
| bge-m3:pregunta+150 | libro_rosa/contenido | parafrasis_contenido | libro_rosa (0.6597) | 0.6597 | si |
| bge-m3:pregunta+150 | presupuesto_taller/literal | literal | presupuesto_taller (0.7434) | 0.7434 | si |
| bge-m3:pregunta+150 | presupuesto_taller/pregunta | parafrasis_pregunta | presupuesto_taller (0.5972) | 0.5972 | si |
| bge-m3:pregunta+150 | presupuesto_taller/contenido | parafrasis_contenido | presupuesto_taller (0.5835) | 0.5835 | si |
| bge-m3:pregunta+150 | mariana_agosto/literal | literal | mariana_agosto (0.655) | 0.655 | si |
| bge-m3:pregunta+150 | mariana_agosto/pregunta | parafrasis_pregunta | mariana_agosto (0.5994) | 0.5994 | si |
| bge-m3:pregunta+150 | mariana_agosto/contenido | parafrasis_contenido | mariana_agosto (0.6092) | 0.6092 | si |
| bge-m3:pregunta+150 | repo_calipso/literal | literal | repo_calipso (0.7096) | 0.7096 | si |
| bge-m3:pregunta+150 | repo_calipso/pregunta | parafrasis_pregunta | repo_calipso (0.6418) | 0.6418 | si |
| bge-m3:pregunta+150 | repo_calipso/contenido | parafrasis_contenido | repo_calipso (0.6056) | 0.6056 | si |
| bge-m3:pregunta+150 | mapa_ciudad/literal | literal | mapa_ciudad (0.7568) | 0.7568 | si |
| bge-m3:pregunta+150 | mapa_ciudad/pregunta | parafrasis_pregunta | mapa_ciudad (0.6654) | 0.6654 | si |
| bge-m3:pregunta+150 | mapa_ciudad/contenido | parafrasis_contenido | mapa_ciudad (0.713) | 0.713 | si |
| bge-m3:pregunta+150 | buen_dia/literal | literal | buen_dia (0.5775) | 0.5775 | si |
| bge-m3:pregunta+150 | buen_dia/pregunta | parafrasis_pregunta | buen_dia (0.5537) | 0.5537 | si |
| bge-m3:pregunta+150 | buen_dia/contenido | parafrasis_contenido | buen_dia (0.6345) | 0.6345 | si |
| bge-m3:pregunta+150 | websocket/literal | literal | websocket (0.8181) | 0.8181 | si |
| bge-m3:pregunta+150 | websocket/pregunta | parafrasis_pregunta | websocket (0.7534) | 0.7534 | si |
| bge-m3:pregunta+150 | websocket/contenido | parafrasis_contenido | websocket (0.566) | 0.566 | si |
| bge-m3:pregunta+150 | neg/tokio | negativa | real:m4-2026-08-27T10:34:01 (0.3893) | None | no |
| bge-m3:pregunta+150 | neg/pan | negativa | buen_dia (0.3321) | None | no |
| bge-m3:pregunta+150 | neg/rueda | negativa | repo_calipso (0.3599) | None | no |
| bge-m3:pregunta+150 | neg/waterloo | negativa | real:m4-2026-08-27T10:34:01 (0.2313) | None | no |
| bge-m3:pregunta+150 | neg/rodilla | negativa | libro_empezado (0.3714) | None | no |
| bge-m3:pregunta+150 | neg/alquiler | negativa | presupuesto_taller (0.3233) | None | no |
| bge-m3:pregunta+150 | neg/mongolia | negativa | real:m4-2026-08-27T10:34:01 (0.2563) | None | no |
| bge-m3:pregunta+150 | neg/wifi | negativa | repo_calipso (0.3987) | None | no |
| bge-m3:pregunta+150 | real/m0-2026-06-29T15:12:59/contenido | real_contenido | real:m0-2026-06-29T15:12:59 (0.7385) | 0.7385 | si |
| bge-m3:pregunta+150 | real/m3-2026-08-27T09:34:18/contenido | real_contenido | real:m3-2026-08-27T09:34:18 (0.7019) | 0.7019 | si |
| bge-m3:pregunta+150 | real/m4-2026-08-27T10:34:01/contenido | real_contenido | real:m4-2026-08-27T10:34:01 (0.7853) | 0.7853 | si |
| bge-m3:pregunta+150 | real/m5-2026-08-27T11:35:42/contenido | real_contenido | real:m5-2026-08-27T11:35:42 (0.7858) | 0.7858 | si |
| bge-m3:pregunta+150 | real/m41-2026-09-01T16:02:40/contenido | real_contenido | real:m41-2026-09-01T16:02:40 (0.7243) | 0.7243 | si |
| bge-m3:par | libro_empezado/literal | literal | libro_empezado (0.784) | 0.784 | si |
| bge-m3:par | libro_empezado/pregunta | parafrasis_pregunta | libro_empezado (0.6579) | 0.6579 | si |
| bge-m3:par | libro_empezado/contenido | parafrasis_contenido | libro_empezado (0.582) | 0.582 | si |
| bge-m3:par | libro_rosa/literal | literal | libro_rosa (0.8146) | 0.8146 | si |
| bge-m3:par | libro_rosa/pregunta | parafrasis_pregunta | libro_rosa (0.7732) | 0.7732 | si |
| bge-m3:par | libro_rosa/contenido | parafrasis_contenido | libro_rosa (0.6597) | 0.6597 | si |
| bge-m3:par | presupuesto_taller/literal | literal | presupuesto_taller (0.7434) | 0.7434 | si |
| bge-m3:par | presupuesto_taller/pregunta | parafrasis_pregunta | presupuesto_taller (0.5972) | 0.5972 | si |
| bge-m3:par | presupuesto_taller/contenido | parafrasis_contenido | presupuesto_taller (0.5835) | 0.5835 | si |
| bge-m3:par | mariana_agosto/literal | literal | mariana_agosto (0.655) | 0.655 | si |
| bge-m3:par | mariana_agosto/pregunta | parafrasis_pregunta | mariana_agosto (0.5994) | 0.5994 | si |
| bge-m3:par | mariana_agosto/contenido | parafrasis_contenido | mariana_agosto (0.6092) | 0.6092 | si |
| bge-m3:par | repo_calipso/literal | literal | repo_calipso (0.6447) | 0.6447 | si |
| bge-m3:par | repo_calipso/pregunta | parafrasis_pregunta | repo_calipso (0.6264) | 0.6264 | si |
| bge-m3:par | repo_calipso/contenido | parafrasis_contenido | repo_calipso (0.5369) | 0.5369 | si |
| bge-m3:par | mapa_ciudad/literal | literal | mapa_ciudad (0.7568) | 0.7568 | si |
| bge-m3:par | mapa_ciudad/pregunta | parafrasis_pregunta | mapa_ciudad (0.6654) | 0.6654 | si |
| bge-m3:par | mapa_ciudad/contenido | parafrasis_contenido | mapa_ciudad (0.7328) | 0.7328 | si |
| bge-m3:par | buen_dia/literal | literal | buen_dia (0.5775) | 0.5775 | si |
| bge-m3:par | buen_dia/pregunta | parafrasis_pregunta | buen_dia (0.5537) | 0.5537 | si |
| bge-m3:par | buen_dia/contenido | parafrasis_contenido | buen_dia (0.6345) | 0.6345 | si |
| bge-m3:par | websocket/literal | literal | websocket (0.8181) | 0.8181 | si |
| bge-m3:par | websocket/pregunta | parafrasis_pregunta | websocket (0.7534) | 0.7534 | si |
| bge-m3:par | websocket/contenido | parafrasis_contenido | websocket (0.566) | 0.566 | si |
| bge-m3:par | neg/tokio | negativa | real:m4-2026-08-27T10:34:01 (0.3893) | None | no |
| bge-m3:par | neg/pan | negativa | buen_dia (0.3321) | None | no |
| bge-m3:par | neg/rueda | negativa | repo_calipso (0.3922) | None | no |
| bge-m3:par | neg/waterloo | negativa | real:m4-2026-08-27T10:34:01 (0.2313) | None | no |
| bge-m3:par | neg/rodilla | negativa | repo_calipso (0.3938) | None | no |
| bge-m3:par | neg/alquiler | negativa | repo_calipso (0.3419) | None | no |
| bge-m3:par | neg/mongolia | negativa | real:m4-2026-08-27T10:34:01 (0.2563) | None | no |
| bge-m3:par | neg/wifi | negativa | repo_calipso (0.452) | None | no |
| bge-m3:par | real/m0-2026-06-29T15:12:59/contenido | real_contenido | real:m0-2026-06-29T15:12:59 (0.7323) | 0.7323 | si |
| bge-m3:par | real/m3-2026-08-27T09:34:18/contenido | real_contenido | real:m3-2026-08-27T09:34:18 (0.7019) | 0.7019 | si |
| bge-m3:par | real/m4-2026-08-27T10:34:01/contenido | real_contenido | real:m4-2026-08-27T10:34:01 (0.7853) | 0.7853 | si |
| bge-m3:par | real/m5-2026-08-27T11:35:42/contenido | real_contenido | real:m5-2026-08-27T11:35:42 (0.7858) | 0.7858 | si |
| bge-m3:par | real/m41-2026-09-01T16:02:40/contenido | real_contenido | real:m41-2026-09-01T16:02:40 (0.7243) | 0.7243 | si |
