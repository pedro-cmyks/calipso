# Calipso

Un asistente personal que corre en la maquina de su dueno, no en la nube de nadie.

Calipso es un server Python (FastAPI) con una PWA de chat y un tablero web. El
usuario le habla siempre a Calipso, y ella decide por dentro a que modelo manda
cada pedido -- Claude o Codex por suscripcion, DeepSeek por API, o Qwen local por
Ollama -- segun el tipo de tarea, la privacidad, el costo y cuanta RAM queda
libre. Recuerda con procedencia (cada recuerdo dice de donde salio), se
autoaudita turno a turno, y ejecuta "goals": tareas con criterio medible que
corren solas en un clon del repo dentro de un sandbox, con el dueno aprobando
al final.

No es un producto ni una libreria: es de un usuario, en una maquina (Linux).
Esta publico para que se pueda leer, discutir y reusar lo que sirva.

## Por donde empezar

- [`CALIPSO.md`](CALIPSO.md) -- la identidad y las reglas de conducta.
- [`DOSSIER.md`](DOSSIER.md) -- que es, en que estado esta, que falta.
- [`SPEC.md`](SPEC.md) y [`DESIGN.md`](DESIGN.md) -- arquitectura y diseno.
- [`SETUP.md`](SETUP.md) y [`RUNBOOK.md`](RUNBOOK.md) -- instalar y operar.
- [`docs/superpowers/`](docs/superpowers/) -- especificaciones, planes y notas
  de cada etapa, con fecha.

## Como esta hecho

Python 3 + FastAPI, Tauri para la ventana de escritorio, Chroma para la
memoria, bwrap para el sandbox de los goals. Las pruebas viven en la raiz
(`test_*.py`) y corren con `pytest`.

## Licencia

[MIT](LICENSE).
