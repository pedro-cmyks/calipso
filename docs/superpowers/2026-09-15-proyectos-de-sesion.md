# Proyectos de sesion (para hacer con tiempo, uno por sesion)

Pedro, 2026-09-15: "dejar planteado lo del modelo propio como un proyecto por sesion, para hacerlo la
proxima semana con tiempo"; y "como va a ser la red de comunicacion de Calipso entre mis dispositivos, con
cuidado, consultado con diferentes inteligencias artificiales". Los dos quedan aca con lo que ya se sabe,
para arrancar cada uno con un brainstorm corto y el metodo de siempre.

## A. El modelo propio: Calipso con tu voz (LoRA sobre Qwen con tus chats)

**Que es.** Un adaptador LoRA (unos pocos millones de pesos nuevos sobre Qwen 2.5 3b o 7b) entrenado con
tus mensajes y tus correcciones, para que Calipso responda COMO vos sin depender del prompt del compositor.
Decision de Pedro: **primero la voz** (`/redacta`), que es lo medible; el criterio (proponer y juzgar
goals) y el ruteo despues, con mas ejemplos.

**Lo que hay que saber antes de empezar.**

- Un fine-tuning ensena estilo, habitos y criterio; NO ensena hechos ni razona mejor. Los hechos siguen en
  la memoria con procedencia (contexto). Un 3b con LoRA no le gana a Opus en nada dificil: es mas tuyo.
- Con ~50 ejemplos se nota el tono; con 500-2000 se nota el criterio.
- La Ally no tiene GPU utilizable para esto: QLoRA del 3b en CPU es posible pero lento (horas por epoca con
  pocos cientos de ejemplos); el 0.5b/1.5b sirven para el experimento primero. Alquilar una GPU es `gastar`
  (NUNCA para Calipso): lo haria Pedro a mano si vale la pena.
- Todo queda local: el dataset son tus conversaciones. Pasa por el detector de secretos antes de entrenar.

**Paso 0: exportar el historial (lo que Pedro pregunto).** Donde vive hoy:

| fuente | donde | tamano en la Ally | forma |
|---|---|---|---|
| Claude Code (esta maquina) | `~/.claude/projects/<slug-del-cwd>/*.jsonl` (una carpeta por directorio de trabajo: `-var-home-pedro`, `-var-home-pedro-calipso`, `-var-home-pedro-Observatory-Global`...) | 630 MB, 13 sesiones largas en `-var-home-pedro` + 147 en calipso | JSONL: una fila por mensaje (`user`/`assistant`), con las llamadas a herramientas |
| Claude Code (otras maquinas) | lo mismo, en cada una (`~/.claude/projects/`) | ? | igual |
| Calipso (la PWA) | `~/.calipso/chats.json` | 166 KB, 18 chats | JSON |
| claude.ai (web/app) | Configuracion -> Privacidad -> Exportar datos (llega un zip por correo) | ? | JSON |
| ChatGPT / Codex | ChatGPT: Settings -> Data controls -> Export; Codex CLI: `~/.codex/sessions/` | ? | JSON/JSONL |

Lo que hace el proyecto: `experimentos/historial_export.py` que lee esas fuentes, saca SOLO los mensajes de
Pedro (y el contexto inmediato al que responden), los pasa por `detector.detectar_secretos`, y arma un
`dataset.jsonl` local con pares (contexto, lo que Pedro dijo) mas las correcciones ("no, asi no"). De ahi:
un banco (el del compositor, `experimentos/`) que compara "LoRA" contra "prompt de /redacta" sobre las
mismas entradas, con Pedro juzgando a ciegas. Se aterriza solo lo que mide mejor.

**Orden sugerido para la sesion:** (1) brainstorm de 20 minutos (que fuentes, que se excluye, donde vive el
dataset, con que modelo base se prueba); (2) spec corto; (3) `historial_export.py` con tests; (4) un
LoRA de juguete con el 1.5b en CPU (`peft` + `torch` cpu, el venv que el goal de torch ya dejo armado) sobre
100 ejemplos; (5) el banco; (6) decidir si vale entrenar el 3b/7b.

## B. Calipso en varios dispositivos: la red entre lo tuyo (seguridad primero)

**Lo que Pedro quiere.** Calipso viviendo en varias computadoras suyas, viendo todos sus repos (unos en
esta, otros en otra), y comunicandose entre dispositivos. Y lo dijo con la advertencia justa: "un ataque
contra mi y entrarian a mi red; hay que pensarlo con cuidado y consultarlo con diferentes inteligencias
artificiales, porque cada una tiene distintos limites sobre lo que considera seguro".

**Lo que ya esta decidido (D3, 2026-08):** cada dispositivo se autentica una vez y cada tanto se le vuelve
a pedir; Pedro puede revocar desde otro dispositivo; **la Ally es la raiz de confianza** (tiene todos los
permisos sobre las cuentas). Falta el diseno: credencial por aparato, alta, vencimiento, revocacion.

**Lo que ya hay en la maquina:** Tailscale instalado (`/usr/bin/tailscale`): una red privada WireGuard con
identidad por dispositivo y ACLs, que es el transporte natural (nada de abrir puertos a internet). El
server de Calipso escucha solo en `127.0.0.1` (revision de seguridad del 2026-08-31: `CALIPSO_HOST`).

**Preguntas que el brainstorm tiene que contestar (con Pedro):**

1. Que se comparte y que no: la memoria (una sola, replicada, o por dispositivo con indice comun), los
   chats, los goals (un goal corre en UN dispositivo: donde esta el repo), los permisos y la aduana (el
   libro es por dispositivo; el tablero los junta).
2. Quien manda: la Ally como raiz de confianza; los otros como "aparatos" con credencial (el mismo modelo
   que ya tiene `/api/aparatos` para el lector).
3. El transporte: tailnet (recomendado) contra un relay propio; sin exposicion a internet en ningun caso.
4. El modelo de amenaza, escrito: un dispositivo comprometido (que puede leer/pedir), una laptop robada
   (cifrado en reposo, revocacion), un repo malicioso en una maquina (el escudo git ya existe), un modelo
   de suscripcion que recibe datos de todos los dispositivos (la aduana lo mide).
5. Que puede hacer un dispositivo sobre otro: leer el estado, mandar un `/goal` que corra alla, ver sus
   goals; y que NUNCA (tocar los permisos de la raiz, exportar la memoria entera).

**Como se consulta con varias inteligencias (el pedido de Pedro):** el mismo brief (este texto + el spec
borrador que salga del brainstorm) a tres lentes independientes y adversarias, cada una con la consigna
"encontra como entrar, que dato se filtra, que decision es imprudente": Claude (un workflow de lentes,
como en las tandas anteriores), Codex/GPT-5.5 (`codex exec` en solo lectura, como la revision adversaria
del hook) y DeepSeek u otro por API (la ruta `api` de Calipso; si hay que pagar, lo decide Pedro). Se
comparan los hallazgos (los que dos o mas lentes coinciden pesan mas; los que una sola ve se verifican) y
se incorporan como rulings numerados, como siempre. Lo que una IA considere "fuera de sus limites" lo
tapa otra: por eso tres.

**Orden sugerido:** (1) brainstorm con Pedro (las 5 preguntas); (2) spec v1; (3) las tres lentes; (4) spec
v2 con rulings; (5) plan; (6) SDD con smoke real entre la Ally y otra maquina de Pedro por la tailnet.
