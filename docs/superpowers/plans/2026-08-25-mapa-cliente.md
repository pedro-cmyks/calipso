# Plan 2 del mapa RTS — el cliente

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que Pedro abra `/fabrica` en el teléfono o en el escritorio y vea su fábrica dibujada en pixel art —edificios con volumen, calles de comercio, unidades trabajando— y pueda recorrerla, tocar un edificio y leer su economía.

**Architecture:** Una app propia en `calipso/web/fabrica/`, servida en `/fabrica`, que consume el `GET /api/mapa/ciudad` del Plan 1. Módulos ES separados por responsabilidad. La lógica que se puede testear vive en funciones puras sin DOM (el sprite es una **matriz de índices de paleta**, no un canvas; la cámara es aritmética), y el canvas queda como una capa fina que pinta esas matrices. Los tests corren con el runner que Node trae de fábrica y se enganchan a `pytest` para que siga habiendo un solo comando.

**Tech Stack:** JavaScript ES2022 (módulos nativos, sin bundler, sin dependencias), Canvas 2D, CSS grid, `node --test` (Node 22, sin paquetes), FastAPI para la ruta, pytest para el puente.

**Spec:** `docs/superpowers/specs/2026-08-25-mapa-rts-design.md`

## Global Constraints

- **Cero archivos de imagen.** Los sprites se dibujan por código desde una paleta. Un departamento nuevo aparece dibujado sin que nadie haya hecho arte.
- **El servidor manda un modelo, no un dibujo.** Cómo se pinta es decisión exclusiva del cliente; ninguna tarea de este plan agrega lógica de dibujo al servidor.
- **El mapa nunca escribe en el libro por su cuenta.** Este plan es 100% lector: no agrega ningún endpoint que escriba.
- **Cero dependencias nuevas.** Ni npm, ni bundler, ni framework, ni CDN. Módulos ES nativos servidos tal cual. Python sigue en biblioteca estándar más lo que ya está instalado.
- **Nada de emojis** en código, tests, commits, documentos ni en la interfaz. Texto plano o símbolos tipográficos.
- **Español** en nombres, comentarios, mensajes de test y de commit. Sin tildes en los mensajes de commit (el repo ya viene así).
- **Escala entera** al pintar sprites: el pixel no se deforma nunca.
- **Determinismo del dibujo**: el mismo modelo produce el mismo bitmap. Nada de `Math.random()` ni de `Date.now()` dentro de la generación de sprites.
- Python 3.14. Correr los tests siempre con `/var/home/pedro/calipso/.venv/bin/python -m pytest` (nunca `pytest` a secas).
- La UI vieja (`/`, `calipso/web/index.html`) **no se toca**.

---

## Estructura de archivos

Todo nuevo salvo los tres últimos.

| archivo | responsabilidad |
|---|---|
| `calipso/web/fabrica/paleta.js` | los índices de la paleta y las rampas de color por zona y estado. Datos puros. |
| `calipso/web/fabrica/sprites.js` | de un edificio a una matriz de píxeles con perspectiva forzada. Puro, sin canvas. Más `pintar()`, que es la única función que toca un contexto. |
| `calipso/web/fabrica/camara.js` | paneo, zoom, `volarA` con easing, y las conversiones mundo↔pantalla. Aritmética pura. |
| `calipso/web/fabrica/ciudad.js` | traer el modelo, indexarlo, formatear la ficha de hover y resolver qué edificio hay bajo un punto. |
| `calipso/web/fabrica/mapa.js` | orden de pintado, geometría de calles y unidades (puro) y el bucle de dibujo sobre el canvas. |
| `calipso/web/fabrica/paneles.js` | qué disposición corresponde a cada ancho de pantalla, y el armado de la tarjeta de hover y la barra de avisos. |
| `calipso/web/fabrica/chat.js` | el reductor de eventos del `/ws/chat` que ya existe, más el cliente que lo alimenta. |
| `calipso/web/fabrica/app.js` | el pegamento: engancha eventos del DOM, corre el bucle de animación, arma la app. |
| `calipso/web/fabrica/index.html` | el esqueleto de las tres columnas, y el registro del service worker. |
| `calipso/web/fabrica/estilo.css` | la paleta de la interfaz y el layout. |
| `calipso/web/fabrica/manifest.json` | manifest propio de la fábrica, con `start_url` en `/fabrica`. El global arranca en `/` y abriría la UI vieja. |
| `calipso/web/fabrica/*.test.js` | uno por módulo puro. |
| `test_fabrica_js.py` | puente: `pytest` corre `node --test`. |
| `test_mapa_server.py` | **modificar**: se le suman los tests de la ruta `/fabrica`. |
| `calipso/server.py` | **modificar**: se le suma la ruta `/fabrica`. |
| `calipso/web/sw.js` | **modificar**: `/fabrica` entra en el shell cacheado. |

**Contrato de un edificio** (lo que el Plan 1 ya entrega, y de lo que este plan solo lee):
`{id, nombre, zona, orden, tamano, estado, saldo_mm, gasto_ciclo_mm, ventas_ventana_mm, eficiencia_pormil, actividad, trabajos, compuertas, x, y}` — `zona` es `"fabrica"` o `"personal"`, `estado` es `"activo"` o `"congelado"`, `tamano` va de 1 a 9, `actividad` de 0 a 3, `eficiencia_pormil` puede ser `null`, y `x`/`y` son enteros en coordenadas de mundo.
**Calle**: `{a, b, peso_mm, ancho, tipo}` con `ancho` de 1 a 4 y `tipo` en `"calle"` o `"cable"`.
**Unidad**: `{id, dueno, gastado_mm, hacia}` — `hacia` puede ser `null`.
**Aviso**: `{id, tipo, sobre, monedas_en_juego_mm}` — `sobre` puede ser `null`.

---

### Task 1: Paleta, sprites y el puente de tests

El primer entregable es el que decide todo lo demás: **un edificio es una matriz de números**, no un dibujo. Eso hace que el render sea testeable sin navegador y que la estética se pueda cambiar sin tocar la lógica.

**Files:**
- Create: `calipso/web/fabrica/paleta.js`
- Create: `calipso/web/fabrica/sprites.js`
- Create: `calipso/web/fabrica/sprites.test.js`
- Create: `test_fabrica_js.py`

**Interfaces:**
- Produces:
  - `paleta.js`: constantes `TRANSPARENTE=0, FRENTE=1, LATERAL=2, TECHO=3, VENTANA=4, PRENDIDA=5, BORDE=6, GRIETA=7`; `RAMPAS` (objeto: zona/estado → índice → color hex); `rampaDe(edificio) -> objeto de colores`.
  - `sprites.js`: `ANCHO=16`, `PROF=6`, `ALTO_BASE=6`, `ALTO_PISO=4`; `fnv1a(texto) -> number`; `alturaDe(tamano) -> number`; `medidas(edificio) -> {ancho, alto, altoFrente}`; `edificioSprite(edificio) -> {ancho, alto, pix: Uint8Array}`; `pintar(ctx, sprite, rampa, x, y, escala) -> void`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `calipso/web/fabrica/sprites.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";

import {FRENTE, LATERAL, TECHO, VENTANA, PRENDIDA, GRIETA, TRANSPARENTE,
        rampaDe, RAMPAS} from "./paleta.js";
import {edificioSprite, medidas, alturaDe, fnv1a, ANCHO, PROF} from "./sprites.js";

function edi(extra = {}) {
  return {id: "dep:atlas", nombre: "atlas", zona: "fabrica", tamano: 4,
          estado: "activo", actividad: 2, ...extra};
}

function cuenta(sprite, valor) {
  let n = 0;
  for (const v of sprite.pix) if (v === valor) n++;
  return n;
}

test("el mismo edificio da el mismo sprite", () => {
  const a = edificioSprite(edi());
  const b = edificioSprite(edi());
  assert.equal(a.ancho, b.ancho);
  assert.equal(a.alto, b.alto);
  assert.deepEqual(Array.from(a.pix), Array.from(b.pix));
});

test("la matriz mide exactamente lo que dicen sus medidas", () => {
  const e = edi({tamano: 7});
  const s = edificioSprite(e);
  const m = medidas(e);
  assert.equal(s.ancho, m.ancho);
  assert.equal(s.alto, m.alto);
  assert.equal(s.pix.length, m.ancho * m.alto);
});

test("el tamano manda en la altura y es monotono", () => {
  let previo = 0;
  for (let t = 1; t <= 9; t++) {
    const alto = alturaDe(t);
    assert.ok(alto > previo, `tamano ${t} no crecio`);
    previo = alto;
  }
});

test("hay volumen: techo, frente y lateral aparecen los tres", () => {
  const s = edificioSprite(edi());
  assert.ok(cuenta(s, FRENTE) > 0, "sin cara frontal");
  assert.ok(cuenta(s, LATERAL) > 0, "sin cara lateral");
  assert.ok(cuenta(s, TECHO) > 0, "sin techo");
});

test("el sprite tiene aire alrededor de la perspectiva", () => {
  // la esquina de abajo a la derecha queda fuera del cuerpo: el lateral se
  // corrio hacia arriba. Si no hay transparencia ahi, no hay perspectiva.
  const s = edificioSprite(edi());
  assert.equal(s.pix[(s.alto - 1) * s.ancho + (s.ancho - 1)], TRANSPARENTE);
});

test("mas actividad prende mas ventanas, y nunca menos", () => {
  let previo = -1;
  for (let a = 0; a <= 3; a++) {
    const n = cuenta(edificioSprite(edi({actividad: a})), PRENDIDA);
    assert.ok(n >= previo, `actividad ${a} prendio menos que la anterior`);
    previo = n;
  }
  assert.ok(cuenta(edificioSprite(edi({actividad: 3})), PRENDIDA) > 0,
            "con actividad 3 no prendio ninguna");
});

test("sin actividad no hay una sola ventana prendida", () => {
  const s = edificioSprite(edi({actividad: 0}));
  assert.equal(cuenta(s, PRENDIDA), 0);
  assert.ok(cuenta(s, VENTANA) > 0, "tampoco hay ventanas apagadas");
});

test("un congelado no prende luz y le salen grietas", () => {
  const vivo = edificioSprite(edi({estado: "activo", actividad: 3}));
  const muerto = edificioSprite(edi({estado: "congelado", actividad: 3}));
  assert.equal(cuenta(muerto, PRENDIDA), 0, "un congelado prendio una luz");
  assert.ok(cuenta(muerto, GRIETA) > 0, "un congelado sin grietas");
  assert.equal(cuenta(vivo, GRIETA), 0, "un edificio sano con grietas");
});

test("la grieta es una sola linea continua, no salpicadura", () => {
  const s = edificioSprite(edi({estado: "congelado"}));
  const filas = new Map();
  s.pix.forEach((v, i) => {
    if (v !== GRIETA) return;
    const y = Math.floor(i / s.ancho);
    filas.set(y, (filas.get(y) || 0) + 1);
  });
  for (const [y, n] of filas) assert.equal(n, 1, `la fila ${y} tiene ${n} grietas`);
  const ys = [...filas.keys()].sort((a, b) => a - b);
  for (let i = 1; i < ys.length; i++) {
    assert.equal(ys[i], ys[i - 1] + 1, "la grieta se corta");
  }
});

test("dos edificios distintos no prenden el mismo patron de ventanas", () => {
  const a = edificioSprite(edi({id: "dep:atlas"}));
  const b = edificioSprite(edi({id: "dep:mercado"}));
  assert.notDeepEqual(Array.from(a.pix), Array.from(b.pix));
});

test("cada zona tiene su rampa y el congelado pisa a la zona", () => {
  const f = rampaDe(edi({zona: "fabrica"}));
  const p = rampaDe(edi({zona: "personal"}));
  assert.notEqual(f[FRENTE], p[FRENTE], "fabrica y personal se ven igual");
  const congelado = rampaDe(edi({zona: "personal", estado: "congelado"}));
  assert.equal(congelado[FRENTE], RAMPAS.congelado[FRENTE]);
});

test("una zona desconocida cae en la de fabrica en vez de romper", () => {
  assert.equal(rampaDe(edi({zona: "marte"}))[FRENTE], RAMPAS.fabrica[FRENTE]);
});

test("el tamano se recorta a la escala 1-9 en vez de reventar", () => {
  assert.equal(alturaDe(0), alturaDe(1));
  assert.equal(alturaDe(99), alturaDe(9));
});

test("fnv1a es estable y distingue", () => {
  assert.equal(fnv1a("atlas"), fnv1a("atlas"));
  assert.notEqual(fnv1a("atlas"), fnv1a("mercado"));
  assert.ok(Number.isInteger(fnv1a("atlas")) && fnv1a("atlas") >= 0);
});
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: FALLA — `test_fabrica_js.py` todavía no existe.

- [ ] **Step 3: Escribir el puente de pytest**

Crear `test_fabrica_js.py` en la raíz del repo:

```python
"""
test_fabrica_js.py — Puente: pytest corre tambien los tests del cliente.

Los modulos de calipso/web/fabrica son JavaScript puro, sin DOM, y se
testean con el runner que Node trae de fabrica. Se corren desde aca para
que `pytest` siga siendo el unico comando que hay que saber.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

FABRICA = pathlib.Path(__file__).parent / "calipso" / "web" / "fabrica"


def node() -> str | None:
    """Node del PATH, o el que fnm haya instalado. None si no hay."""
    directo = shutil.which("node")
    if directo:
        return directo
    versiones = sorted(
        (pathlib.Path.home() / ".local/share/fnm/node-versions")
        .glob("v*/installation/bin/node"))
    return str(versiones[-1]) if versiones else None


def test_los_modulos_del_cliente_pasan_sus_tests():
    ejecutable = node()
    if ejecutable is None:
        pytest.skip("node no esta instalado: los tests del cliente NO corrieron")
    # el directorio va como cwd, NO como argumento: Node 22 trata un
    # argumento posicional como modulo de entrada y sale con
    # "Cannot find module <dir>" sin correr un solo test
    r = subprocess.run([ejecutable, "--test"], cwd=str(FABRICA),
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 4: Correr los tests para verificar que fallan por la razón correcta**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: FALLA, y **el texto del error tiene que nombrar `./paleta.js`** — no la carpeta `fabrica`.

Esa distinción importa: si el error dice `Cannot find module '<ruta de la carpeta>'`, significa que Node recibió el directorio como argumento y no corrió ningún test. Si dice `Cannot find module './paleta.js'`, entonces sí descubrió `sprites.test.js`, lo ejecutó, y falló por la razón correcta. Los dos fallos se parecen y solo uno es el bueno.

**Si en vez de fallar SALTA (`skipped`), pará**: significa que no encontró Node, y entonces ningún test del cliente va a correr en toda esta rama. Verificá a mano con `ls ~/.local/share/fnm/node-versions/` y arreglá `node()` antes de seguir. Un salto silencioso acá vuelve inútiles las seis tareas.

- [ ] **Step 5: Escribir la paleta**

Crear `calipso/web/fabrica/paleta.js`:

```js
/**
 * calipso/web/fabrica/paleta.js — Los colores de la ciudad.
 *
 * Un sprite es una matriz de estos indices, no de colores: la forma se
 * decide una vez y la estetica se puede cambiar entera tocando solo este
 * archivo. Cero imagenes: todo se dibuja por codigo.
 */

export const TRANSPARENTE = 0;
export const FRENTE = 1;
export const LATERAL = 2;
export const TECHO = 3;
export const VENTANA = 4;
export const PRENDIDA = 5;
export const BORDE = 6;
export const GRIETA = 7;

export const RAMPAS = {
  // la fabrica es acero frio; lo personal es calido y aparte
  fabrica: {
    [FRENTE]: "#3d4f63", [LATERAL]: "#26313d", [TECHO]: "#566e88",
    [VENTANA]: "#1b2430", [PRENDIDA]: "#ffd75f", [BORDE]: "#12181f",
    [GRIETA]: "#12181f",
  },
  personal: {
    [FRENTE]: "#5a4668", [LATERAL]: "#382a43", [TECHO]: "#78608a",
    [VENTANA]: "#241c2b", [PRENDIDA]: "#c9a3e0", [BORDE]: "#180f1d",
    [GRIETA]: "#180f1d",
  },
  // un departamento quebrado se ve quebrado: gris, sin luz, agrietado
  congelado: {
    [FRENTE]: "#3a3a3a", [LATERAL]: "#262626", [TECHO]: "#4d4d4d",
    [VENTANA]: "#1c1c1c", [PRENDIDA]: "#1c1c1c", [BORDE]: "#0f0f0f",
    [GRIETA]: "#0a0a0a",
  },
};

export function rampaDe(edificio) {
  if (edificio.estado === "congelado") return RAMPAS.congelado;
  return RAMPAS[edificio.zona] || RAMPAS.fabrica;
}
```

- [ ] **Step 6: Escribir el generador de sprites**

Crear `calipso/web/fabrica/sprites.js`:

```js
/**
 * calipso/web/fabrica/sprites.js — De un edificio a una matriz de pixeles.
 *
 * Perspectiva forzada: el volumen esta horneado en el sprite (cara
 * frontal, lateral oscurecido y techo aclarado), no armado con tiles
 * isometricos. La funcion es pura y devuelve datos, no dibujo: por eso se
 * puede testear sin navegador y por eso el mismo modelo da siempre el
 * mismo bitmap. Nada de Math.random ni de reloj aca adentro.
 */
import {TRANSPARENTE, FRENTE, LATERAL, TECHO, VENTANA, PRENDIDA, BORDE,
        GRIETA} from "./paleta.js";

export const ANCHO = 16;      // ancho de la cara frontal, en pixeles
export const PROF = 6;        // cuanto se corre la perspectiva
export const ALTO_BASE = 6;   // planta baja
export const ALTO_PISO = 4;   // cada piso que suma el tamano

const VENT_ANCHO = 3;
const VENT_ALTO = 2;
const VENT_COLS = 3;

/** FNV-1a de 32 bits. Estable entre navegadores y entre corridas. */
export function fnv1a(texto) {
  let h = 0x811c9dc5;
  for (let i = 0; i < texto.length; i++) {
    h ^= texto.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

function pisosDe(tamano) {
  return Math.max(1, Math.min(9, Math.trunc(tamano) || 1));
}

export function alturaDe(tamano) {
  return ALTO_BASE + pisosDe(tamano) * ALTO_PISO;
}

export function medidas(edificio) {
  const altoFrente = alturaDe(edificio.tamano);
  return {ancho: ANCHO + PROF, alto: altoFrente + PROF, altoFrente};
}

export function edificioSprite(edificio) {
  const {ancho, alto, altoFrente} = medidas(edificio);
  const pix = new Uint8Array(ancho * alto);   // arranca todo en TRANSPARENTE
  const en = (x, y, v) => {
    if (x >= 0 && x < ancho && y >= 0 && y < alto) pix[y * ancho + x] = v;
  };
  const congelado = edificio.estado === "congelado";
  const arriba = PROF;                        // primera fila de la cara frontal

  // cara frontal
  for (let y = arriba; y < arriba + altoFrente; y++)
    for (let x = 0; x < ANCHO; x++) en(x, y, FRENTE);

  // cara lateral: se corre un pixel arriba por cada pixel a la derecha
  for (let d = 1; d <= PROF; d++)
    for (let y = arriba; y < arriba + altoFrente; y++)
      en(ANCHO - 1 + d, y - d, LATERAL);

  // techo: el mismo corrimiento, apoyado en el borde de arriba del frente
  for (let d = 1; d <= PROF; d++)
    for (let x = 0; x < ANCHO; x++) en(x + d, arriba - d, TECHO);

  // ventanas: patron estable derivado del id, encendido segun la actividad
  const h = fnv1a(edificio.id);
  const act = congelado ? 0 : Math.max(0, Math.min(3, edificio.actividad || 0));
  const pisos = pisosDe(edificio.tamano);
  for (let p = 0; p < pisos; p++) {
    for (let c = 0; c < VENT_COLS; c++) {
      const sorteo = (h >>> ((p * VENT_COLS + c) % 29)) & 3;
      const v = (act > 0 && sorteo < act) ? PRENDIDA : VENTANA;
      const x0 = 2 + c * 5;
      const y0 = arriba + 2 + p * ALTO_PISO;
      for (let dy = 0; dy < VENT_ALTO; dy++)
        for (let dx = 0; dx < VENT_ANCHO; dx++) en(x0 + dx, y0 + dy, v);
    }
  }

  // contorno del frente, para que los edificios no se fundan entre si
  for (let x = 0; x < ANCHO; x++) {
    en(x, arriba, BORDE);
    en(x, arriba + altoFrente - 1, BORDE);
  }
  for (let y = arriba; y < arriba + altoFrente; y++) {
    en(0, y, BORDE);
    en(ANCHO - 1, y, BORDE);
  }

  // grieta: una sola linea que baja en zigzag por la cara frontal
  if (congelado) {
    let x = 3 + (h % (ANCHO - 6));
    for (let i = 0; i < altoFrente; i++) {
      en(x, arriba + i, GRIETA);
      x += (fnv1a(edificio.id + ":" + i) & 1) ? 1 : -1;
      x = Math.max(1, Math.min(ANCHO - 2, x));
    }
  }

  return {ancho, alto, pix};
}

/** La unica funcion del modulo que toca un canvas. Escala SIEMPRE entera. */
export function pintar(ctx, sprite, rampa, x, y, escala) {
  const e = Math.max(1, Math.round(escala));
  for (let j = 0; j < sprite.alto; j++) {
    for (let i = 0; i < sprite.ancho; i++) {
      const v = sprite.pix[j * sprite.ancho + i];
      if (v === TRANSPARENTE) continue;
      ctx.fillStyle = rampa[v];
      ctx.fillRect(x + i * e, y + j * e, e, e);
    }
  }
}
```

- [ ] **Step 7: Correr los tests para verificar que pasan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: PASA (no SALTA).

Correr también la suite dirigida completa para confirmar que no se rompió nada:
`/var/home/pedro/calipso/.venv/bin/python -m pytest -q --ignore=test_chat_live.py`
Esperado: los 212 de antes más el nuevo.

- [ ] **Step 8: Commit**

```bash
git add calipso/web/fabrica/paleta.js calipso/web/fabrica/sprites.js \
        calipso/web/fabrica/sprites.test.js test_fabrica_js.py
git commit -m "feat(fabrica): sprites por codigo — un edificio es una matriz de pixeles"
```

---

### Task 2: La cámara

Paneo libre en los dos ejes, zoom que respeta el punto que estás mirando, y un vuelo con easing que **converge exacto** para que el foco del Plan 3 aterrice donde dijo.

**Files:**
- Create: `calipso/web/fabrica/camara.js`
- Create: `calipso/web/fabrica/camara.test.js`

**Interfaces:**
- Produces: `ESCALA_MIN=0.25`, `ESCALA_MAX=6`; `crearCamara(x=0, y=0, escala=1) -> cam`; `aPantalla(cam, mundo, vista) -> {x,y}`; `aMundo(cam, pantalla, vista) -> {x,y}`; `arrastrar(cam, dx, dy) -> cam`; `acercar(cam, factor, punto, vista) -> cam`; `volarA(cam, destino, ms=600) -> cam`; `paso(cam, dt) -> boolean`; `suave(u) -> number`; `escalaEntera(cam) -> number`; `encuadrar(edificios, vista, margen=60) -> {x, y, escala}`. `vista` es `{ancho, alto}` en píxeles.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `calipso/web/fabrica/camara.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";

import {crearCamara, aPantalla, aMundo, arrastrar, acercar, volarA, paso,
        escalaEntera, encuadrar, ESCALA_MIN, ESCALA_MAX} from "./camara.js";

const VISTA = {ancho: 800, alto: 600};
const cerca = (a, b, tol = 1e-9) =>
  assert.ok(Math.abs(a - b) < tol, `${a} no esta cerca de ${b}`);

test("ida y vuelta entre mundo y pantalla", () => {
  const cam = crearCamara(120, -40, 2.5);
  const mundo = {x: 333, y: -17};
  const vuelta = aMundo(cam, aPantalla(cam, mundo, VISTA), VISTA);
  cerca(vuelta.x, mundo.x);
  cerca(vuelta.y, mundo.y);
});

test("el centro de la vista es la posicion de la camara", () => {
  const cam = crearCamara(120, -40, 3);
  const p = aPantalla(cam, {x: 120, y: -40}, VISTA);
  cerca(p.x, VISTA.ancho / 2);
  cerca(p.y, VISTA.alto / 2);
});

test("el punto bajo el cursor no se mueve al acercar", () => {
  const cam = crearCamara(0, 0, 1);
  const cursor = {x: 640, y: 130};
  const antes = aMundo(cam, cursor, VISTA);
  acercar(cam, 1.8, cursor, VISTA);
  const despues = aMundo(cam, cursor, VISTA);
  cerca(despues.x, antes.x, 1e-6);
  cerca(despues.y, antes.y, 1e-6);
});

test("la escala tiene tope arriba y abajo", () => {
  const cam = crearCamara(0, 0, 1);
  for (let i = 0; i < 50; i++) acercar(cam, 2, {x: 400, y: 300}, VISTA);
  assert.equal(cam.escala, ESCALA_MAX);
  for (let i = 0; i < 100; i++) acercar(cam, 0.5, {x: 400, y: 300}, VISTA);
  assert.equal(cam.escala, ESCALA_MIN);
});

test("arrastrar el dedo a la derecha trae el mundo a la derecha", () => {
  const cam = crearCamara(0, 0, 2);
  arrastrar(cam, 100, 0);
  assert.equal(cam.x, -50);          // 100 pixeles / escala 2
});

test("arrastrar tambien mueve el eje vertical", () => {
  const cam = crearCamara(0, 0, 1);
  arrastrar(cam, 0, 30);
  assert.equal(cam.y, -30);
});

test("volarA aterriza exacto y despues se apaga", () => {
  const cam = crearCamara(0, 0, 1);
  volarA(cam, {x: 500, y: -300, escala: 3}, 600);
  let vueltas = 0;
  while (paso(cam, 16)) {
    if (++vueltas > 1000) throw new Error("el vuelo no termina");
  }
  assert.equal(cam.x, 500);
  assert.equal(cam.y, -300);
  assert.equal(cam.escala, 3);
  assert.equal(cam.vuelo, null);
});

test("un paso mas largo que el vuelo aterriza igual, sin pasarse", () => {
  const cam = crearCamara(0, 0, 1);
  volarA(cam, {x: 500, y: 0}, 600);
  paso(cam, 5000);
  assert.equal(cam.x, 500);
  assert.equal(cam.vuelo, null);
});

test("el vuelo avanza de verdad en el medio del recorrido", () => {
  const cam = crearCamara(0, 0, 1);
  volarA(cam, {x: 1000, y: 0}, 600);
  paso(cam, 300);
  assert.ok(cam.x > 0 && cam.x < 1000, `quedo en ${cam.x}`);
});

test("volarA sin destino de escala conserva la que habia", () => {
  const cam = crearCamara(0, 0, 2.5);
  volarA(cam, {x: 10, y: 10}, 100);
  paso(cam, 100);
  assert.equal(cam.escala, 2.5);
});

test("tocar la camara cancela el vuelo en curso", () => {
  const cam = crearCamara(0, 0, 1);
  volarA(cam, {x: 500, y: 0}, 600);
  arrastrar(cam, 10, 0);
  assert.equal(cam.vuelo, null);
  assert.equal(paso(cam, 16), false);
});

test("paso sin vuelo no hace nada y lo dice", () => {
  const cam = crearCamara(7, 7, 1);
  assert.equal(paso(cam, 16), false);
  assert.equal(cam.x, 7);
});

test("un vuelo de cero milisegundos no divide por cero", () => {
  const cam = crearCamara(0, 0, 1);
  volarA(cam, {x: 42, y: 0}, 0);
  paso(cam, 16);
  assert.equal(cam.x, 42);
  assert.equal(cam.vuelo, null);
});

test("la escala de dibujo es entera y nunca baja de 1", () => {
  assert.equal(escalaEntera(crearCamara(0, 0, 0.25)), 1);
  assert.equal(escalaEntera(crearCamara(0, 0, 2.4)), 2);
  assert.equal(escalaEntera(crearCamara(0, 0, 2.6)), 3);
});

test("encuadrar centra la ciudad en el medio de la vista", () => {
  const e = encuadrar([{x: 0, y: 0}, {x: 200, y: 100}], VISTA);
  assert.equal(e.x, 100);
  assert.equal(e.y, 50);
});

test("encuadrar hace entrar toda la ciudad, con margen", () => {
  const edificios = [{x: -500, y: -200}, {x: 500, y: 200}];
  const e = encuadrar(edificios, VISTA, 60);
  const cam = crearCamara(e.x, e.y, e.escala);
  for (const b of edificios) {
    const p = aPantalla(cam, b, VISTA);
    assert.ok(p.x >= 0 && p.x <= VISTA.ancho, `se fue en x: ${p.x}`);
    assert.ok(p.y >= 0 && p.y <= VISTA.alto, `se fue en y: ${p.y}`);
  }
});

test("una ciudad ancha se encuadra por el lado que aprieta", () => {
  // 4000 de ancho contra 800 de vista aprieta mas que 100 de alto contra 600
  const e = encuadrar([{x: 0, y: 0}, {x: 4000, y: 100}], VISTA, 0);
  assert.ok(e.escala <= VISTA.ancho / 4000 + 1e-9, `escala ${e.escala}`);
});

test("encuadrar respeta los topes de escala", () => {
  const lejos = encuadrar([{x: 0, y: 0}, {x: 1e9, y: 1e9}], VISTA);
  assert.equal(lejos.escala, ESCALA_MIN);
  const juntos = encuadrar([{x: 0, y: 0}, {x: 1, y: 1}], VISTA);
  assert.equal(juntos.escala, ESCALA_MAX);
});

test("encuadrar un solo edificio lo pone en el centro sin dividir por cero", () => {
  const e = encuadrar([{x: 42, y: -7}], VISTA);
  assert.equal(e.x, 42);
  assert.equal(e.y, -7);
  assert.ok(Number.isFinite(e.escala) && e.escala > 0);
});

test("encuadrar una ciudad vacia no rompe", () => {
  const e = encuadrar([], VISTA);
  assert.ok(Number.isFinite(e.x) && Number.isFinite(e.y));
  assert.ok(Number.isFinite(e.escala) && e.escala > 0);
});
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: FALLA con `Cannot find module` de `./camara.js`.

- [ ] **Step 3: Escribir la cámara**

Crear `calipso/web/fabrica/camara.js`:

```js
/**
 * calipso/web/fabrica/camara.js — Paneo, zoom y vuelo.
 *
 * Aritmetica pura: ni canvas ni DOM, para que se pueda testear entera.
 * `cam.x` y `cam.y` son el punto del MUNDO que queda en el centro de la
 * vista. El vuelo converge exacto —al terminar, las coordenadas son las
 * del destino, no una aproximacion— porque el foco tiene que aterrizar
 * donde dijo que iba.
 */

export const ESCALA_MIN = 0.25;
export const ESCALA_MAX = 6;

export function crearCamara(x = 0, y = 0, escala = 1) {
  return {x, y, escala, vuelo: null};
}

export function aPantalla(cam, mundo, vista) {
  return {x: (mundo.x - cam.x) * cam.escala + vista.ancho / 2,
          y: (mundo.y - cam.y) * cam.escala + vista.alto / 2};
}

export function aMundo(cam, pantalla, vista) {
  return {x: (pantalla.x - vista.ancho / 2) / cam.escala + cam.x,
          y: (pantalla.y - vista.alto / 2) / cam.escala + cam.y};
}

export function arrastrar(cam, dx, dy) {
  cam.x -= dx / cam.escala;
  cam.y -= dy / cam.escala;
  cam.vuelo = null;               // la mano manda sobre el vuelo
  return cam;
}

export function acercar(cam, factor, punto, vista) {
  const antes = aMundo(cam, punto, vista);
  cam.escala = Math.max(ESCALA_MIN, Math.min(ESCALA_MAX, cam.escala * factor));
  const despues = aMundo(cam, punto, vista);
  cam.x += antes.x - despues.x;   // el punto bajo el dedo no se mueve
  cam.y += antes.y - despues.y;
  cam.vuelo = null;
  return cam;
}

export function volarA(cam, destino, ms = 600) {
  cam.vuelo = {
    desde: {x: cam.x, y: cam.y, escala: cam.escala},
    hasta: {x: destino.x, y: destino.y,
            escala: destino.escala === undefined ? cam.escala : destino.escala},
    ms, t: 0,
  };
  return cam;
}

/** Easing: arranca rapido y frena al llegar. */
export function suave(u) {
  const v = 1 - u;
  return 1 - v * v * v;
}

/** Avanza el vuelo `dt` milisegundos. Devuelve si habia algo que avanzar. */
export function paso(cam, dt) {
  const v = cam.vuelo;
  if (!v) return false;
  v.t = Math.min(v.ms, v.t + dt);
  const u = v.ms === 0 ? 1 : v.t / v.ms;
  const k = suave(u);
  cam.x = v.desde.x + (v.hasta.x - v.desde.x) * k;
  cam.y = v.desde.y + (v.hasta.y - v.desde.y) * k;
  cam.escala = v.desde.escala + (v.hasta.escala - v.desde.escala) * k;
  if (u >= 1) {
    cam.x = v.hasta.x;            // exacto, no "casi"
    cam.y = v.hasta.y;
    cam.escala = v.hasta.escala;
    cam.vuelo = null;
  }
  return true;
}

/** El pixel no se deforma: los sprites se pintan a escala entera. */
export function escalaEntera(cam) {
  return Math.max(1, Math.round(cam.escala));
}

/**
 * Donde poner la camara para que la ciudad entera entre en la vista.
 * Se llama cuando llega el modelo: el mundo que emite el urbanismo mide
 * lo que mida, y hardcodear una posicion inicial deja medio mapa afuera.
 */
export function encuadrar(edificios, vista, margen = 60) {
  if (!edificios.length) return {x: 0, y: 0, escala: 1};
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const e of edificios) {
    x0 = Math.min(x0, e.x); x1 = Math.max(x1, e.x);
    y0 = Math.min(y0, e.y); y1 = Math.max(y1, e.y);
  }
  const util = {ancho: Math.max(1, vista.ancho - margen * 2),
                alto: Math.max(1, vista.alto - margen * 2)};
  const ancho = x1 - x0, alto = y1 - y0;
  const cabe = Math.min(ancho > 0 ? util.ancho / ancho : ESCALA_MAX,
                        alto > 0 ? util.alto / alto : ESCALA_MAX);
  return {x: (x0 + x1) / 2, y: (y0 + y1) / 2,
          escala: Math.max(ESCALA_MIN, Math.min(ESCALA_MAX, cabe))};
}
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: PASA.

- [ ] **Step 5: Commit**

```bash
git add calipso/web/fabrica/camara.js calipso/web/fabrica/camara.test.js
git commit -m "feat(fabrica): camara — paneo en dos ejes, zoom anclado y vuelo exacto"
```

---

### Task 3: El modelo en el cliente

Traer la ciudad, indexarla, formatear la ficha que se ve al pasar por encima de un edificio, y resolver qué edificio hay bajo un punto de la pantalla.

**Files:**
- Create: `calipso/web/fabrica/ciudad.js`
- Create: `calipso/web/fabrica/ciudad.test.js`

**Interfaces:**
- Consumes: `medidas(edificio)` de `sprites.js`; `aPantalla(cam, mundo, vista)` y `escalaEntera(cam)` de `camara.js`.
- Produces: `cargarCiudad(buscar=fetch) -> Promise<{activa, ciudad?}>`; `indice(ciudad) -> {porId: Map, avisosPorId: Map}`; `monedas(mm) -> string`; `fichaDe(ciudad, id) -> objeto|null`; `ordenDePintado(edificios) -> array`; `enPunto(ciudad, cam, vista, px, py) -> string|null`; `centroDe(edificio) -> {x, y}`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `calipso/web/fabrica/ciudad.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";

import {crearCamara} from "./camara.js";
import {cargarCiudad, indice, monedas, fichaDe, ordenDePintado,
        enPunto} from "./ciudad.js";

const VISTA = {ancho: 800, alto: 600};

function edi(id, extra = {}) {
  return {id, nombre: id.split(":")[1] || id, zona: "fabrica", orden: 0,
          tamano: 4, estado: "activo", saldo_mm: 1_148_000,
          gasto_ciclo_mm: 22_500, ventas_ventana_mm: 900_000,
          eficiencia_pormil: 1234, actividad: 2, trabajos: [], compuertas: 0,
          x: 0, y: 0, ...extra};
}

function ciudadDePrueba() {
  return {
    semana: "2026-W35", tesoro_mm: 0, cuenta_pedro_mm: 0, direccion_mm: 0,
    tipo_cambio_mm: 5000, linea_empleo_mm: 14450,
    edificios: [edi("dep:atlas", {x: 0, y: 0}),
                edi("dep:mercado", {x: 400, y: 200, trabajos: ["radar"],
                                    compuertas: 2})],
    calles: [{a: "dep:atlas", b: "dep:mercado", peso_mm: 250_000, ancho: 3,
              tipo: "calle"}],
    unidades: [{id: "radar", dueno: "dep:mercado", gastado_mm: 12_000,
                hacia: "dep:atlas"}],
    avisos: [{id: "c1", tipo: "gasto", sobre: "dep:mercado",
              monedas_en_juego_mm: 50_000},
             {id: "c2", tipo: "gasto", sobre: "dep:mercado",
              monedas_en_juego_mm: 10_000},
             {id: "carta", tipo: "renovacion", sobre: null,
              monedas_en_juego_mm: 0}],
  };
}

test("el indice encuentra cada edificio por su id", () => {
  const {porId} = indice(ciudadDePrueba());
  assert.equal(porId.get("dep:atlas").nombre, "atlas");
  assert.equal(porId.get("dep:nadie"), undefined);
});

test("los avisos se cuentan por edificio y los sueltos no rompen", () => {
  const {avisosPorId} = indice(ciudadDePrueba());
  assert.equal(avisosPorId.get("dep:mercado"), 2);
  assert.equal(avisosPorId.get("dep:atlas"), undefined);
});

test("las monedas se leen como monedas, no como milimonedas", () => {
  assert.equal(monedas(1_148_000), "1.148");
  assert.equal(monedas(0), "0");
  assert.equal(monedas(1_500), "1,5");
});

test("la ficha trae lo que la tarjeta muestra", () => {
  const f = fichaDe(ciudadDePrueba(), "dep:mercado");
  assert.equal(f.nombre, "mercado");
  assert.equal(f.saldo, "1.148");
  assert.equal(f.eficiencia, "123,4%");
  assert.equal(f.trabajos, 1);
  assert.equal(f.compuertas, 2);
});

test("sin eficiencia la ficha lo dice en vez de inventar un cero", () => {
  const c = ciudadDePrueba();
  c.edificios[0].eficiencia_pormil = null;
  assert.equal(fichaDe(c, "dep:atlas").eficiencia, "sin dato");
});

test("la ficha de un edificio que no existe es nula", () => {
  assert.equal(fichaDe(ciudadDePrueba(), "dep:fantasma"), null);
});

test("se pinta de atras hacia adelante", () => {
  const orden = ordenDePintado([edi("b", {y: 500}), edi("a", {y: 100})]);
  assert.deepEqual(orden.map(e => e.id), ["a", "b"]);
});

test("el orden de pintado desempata estable", () => {
  const orden = ordenDePintado([edi("z", {y: 0}), edi("a", {y: 0})]);
  assert.deepEqual(orden.map(e => e.id), ["a", "z"]);
});

test("tocar encima de un edificio lo encuentra", () => {
  const c = ciudadDePrueba();
  const cam = crearCamara(0, 0, 1);
  // el edificio de atlas esta en el mundo (0,0), o sea el centro de la vista;
  // el sprite se apoya con su base ahi, asi que unos pixeles mas arriba cae
  // adentro del cuerpo
  assert.equal(enPunto(c, cam, VISTA, 400, 290), "dep:atlas");
});

test("tocar el vacio no devuelve nada", () => {
  const c = ciudadDePrueba();
  const cam = crearCamara(0, 0, 1);
  assert.equal(enPunto(c, cam, VISTA, 10, 10), null);
});

test("cuando dos se superponen gana el de adelante", () => {
  const c = ciudadDePrueba();
  c.edificios = [edi("dep:atras", {x: 0, y: 0}),
                 edi("dep:adelante", {x: 0, y: 6})];
  const cam = crearCamara(0, 3, 1);
  // 290 cae DENTRO de las dos cajas; 300 cae solo en una y entonces el test
  // pasaria igual con el bucle recorrido al reves, que es el error que este
  // test existe para atrapar
  const id = enPunto(c, cam, VISTA, 400, 290);
  assert.equal(id, "dep:adelante");
});

test("cargarCiudad pide el endpoint y devuelve el modelo", async () => {
  let pedido = null;
  const falso = async (url) => {
    pedido = url;
    return {ok: true, status: 200,
            json: async () => ({activa: true, ciudad: ciudadDePrueba()})};
  };
  const r = await cargarCiudad(falso);
  assert.equal(pedido, "/api/mapa/ciudad");
  assert.equal(r.activa, true);
  assert.equal(r.ciudad.edificios.length, 2);
});

test("cargarCiudad pasa la respuesta de economia inactiva tal cual", async () => {
  const falso = async () => ({ok: true, status: 200,
                              json: async () => ({activa: false})});
  const r = await cargarCiudad(falso);
  assert.equal(r.activa, false);
});

test("cargarCiudad avisa cuando el servidor contesta mal", async () => {
  const falso = async () => ({ok: false, status: 401, json: async () => ({})});
  await assert.rejects(() => cargarCiudad(falso), /401/);
});
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: FALLA con `Cannot find module` de `./ciudad.js`.

- [ ] **Step 3: Escribir el modelo del cliente**

Crear `calipso/web/fabrica/ciudad.js`:

```js
/**
 * calipso/web/fabrica/ciudad.js — El modelo, del lado del cliente.
 *
 * Trae la ciudad, la indexa y responde las dos preguntas que hace la
 * interfaz: que dice la ficha de este edificio, y que edificio hay debajo
 * de este punto de la pantalla. Nada de dibujo.
 */
import {medidas} from "./sprites.js";
import {aPantalla, escalaEntera} from "./camara.js";

// useGrouping "always" es obligatorio: sin el, esta locale devuelve "1148"
// en vez de "1.148" para los numeros de cuatro digitos.
const FORMATO = new Intl.NumberFormat("es", {maximumFractionDigits: 2,
                                             useGrouping: "always"});

export async function cargarCiudad(buscar = fetch) {
  const r = await buscar("/api/mapa/ciudad");
  if (!r.ok) throw new Error("no se pudo leer la ciudad: " + r.status);
  return await r.json();
}

export function indice(ciudad) {
  const porId = new Map();
  for (const e of ciudad.edificios) porId.set(e.id, e);
  const avisosPorId = new Map();
  for (const a of ciudad.avisos) {
    if (!a.sobre) continue;      // las cartas no cuelgan de ningun edificio
    avisosPorId.set(a.sobre, (avisosPorId.get(a.sobre) || 0) + 1);
  }
  return {porId, avisosPorId};
}

/** El libro guarda milimonedas; la gente lee monedas. */
export function monedas(mm) {
  return FORMATO.format(Math.round(mm) / 1000);
}

export function fichaDe(ciudad, id) {
  const e = ciudad.edificios.find(x => x.id === id);
  if (!e) return null;
  const efi = e.eficiencia_pormil;
  return {
    id: e.id, nombre: e.nombre, zona: e.zona, estado: e.estado,
    saldo: monedas(e.saldo_mm),
    gasto_ciclo: monedas(e.gasto_ciclo_mm),
    ventas_ventana: monedas(e.ventas_ventana_mm),
    // null no es cero: sin estado de suscripciones no hay eficiencia
    eficiencia: (efi === null || efi === undefined)
      ? "sin dato" : FORMATO.format(efi / 10) + "%",
    trabajos: e.trabajos.length,
    compuertas: e.compuertas,
  };
}

/** El sprite se apoya con su base en el punto del edificio. */
export function centroDe(edificio) {
  return {x: edificio.x, y: edificio.y};
}

/** De atras hacia adelante: el de mas abajo tapa al de mas arriba. */
export function ordenDePintado(edificios) {
  return [...edificios].sort((a, b) => (a.y - b.y) || (a.id < b.id ? -1 : 1));
}

export function enPunto(ciudad, cam, vista, px, py) {
  const esc = escalaEntera(cam);
  const orden = ordenDePintado(ciudad.edificios);
  for (let i = orden.length - 1; i >= 0; i--) {   // el de adelante primero
    const e = orden[i];
    const m = medidas(e);
    const p = aPantalla(cam, centroDe(e), vista);
    const x0 = p.x - (m.ancho * esc) / 2;
    const y0 = p.y - m.alto * esc;
    if (px >= x0 && px < x0 + m.ancho * esc &&
        py >= y0 && py < y0 + m.alto * esc) return e.id;
  }
  return null;
}
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: PASA. Los cuatro valores están verificados en este Node con `useGrouping: "always"`: `1.148`, `0`, `1,5` y `123,4`.

**Los tests de formato no se tocan.** Si alguno sale en rojo, el que está mal es el `Intl.NumberFormat` — revisá que lleve `useGrouping: "always"` antes de mirar cualquier otra cosa. La tarea 5 vuelve a afirmar estos mismos formatos desde el otro lado, así que aflojar un assert acá deja la 5 en rojo.

- [ ] **Step 5: Commit**

```bash
git add calipso/web/fabrica/ciudad.js calipso/web/fabrica/ciudad.test.js
git commit -m "feat(fabrica): el modelo en el cliente — indice, ficha y que hay bajo el dedo"
```

---

### Task 4: La ruta, el esqueleto y el mapa dibujado

La primera vez que se ve algo. Al terminar esta tarea, `/fabrica` muestra la ciudad y se puede recorrer con el mouse o el dedo.

**Files:**
- Create: `calipso/web/fabrica/mapa.js`
- Create: `calipso/web/fabrica/mapa.test.js`
- Create: `calipso/web/fabrica/index.html`
- Create: `calipso/web/fabrica/estilo.css`
- Create: `calipso/web/fabrica/manifest.json`
- Create: `calipso/web/fabrica/app.js`
- Modify: `calipso/server.py` (agregar las rutas `/fabrica` y `/fabrica/manifest.json` justo después de la de `/sw.js`, antes del comentario de estáticos de la línea 3499)
- Modify: `test_mapa_server.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: `mapa.js` exporta `puntosDeCalle(ciudad, cam, vista, idx=indice(ciudad)) -> array de {desde, hasta, ancho, tipo}`; `posicionDeUnidad(unidad, ciudad, cam, vista, fase, idx=indice(ciudad)) -> {x, y}|null`; `crearMapa(canvas) -> {dibujar(ciudad, cam, resaltado=null, fase=0), vista()}`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `calipso/web/fabrica/mapa.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";

import {crearCamara} from "./camara.js";
import {puntosDeCalle, posicionDeUnidad} from "./mapa.js";

const VISTA = {ancho: 800, alto: 600};

function ciudadDePrueba() {
  const base = {nombre: "x", zona: "fabrica", orden: 0, tamano: 4,
                estado: "activo", saldo_mm: 0, gasto_ciclo_mm: 0,
                ventas_ventana_mm: 0, eficiencia_pormil: null, actividad: 0,
                trabajos: [], compuertas: 0};
  return {
    edificios: [{...base, id: "dep:a", x: -100, y: 0},
                {...base, id: "dep:b", x: 100, y: 0}],
    calles: [{a: "dep:a", b: "dep:b", peso_mm: 1, ancho: 2, tipo: "calle"}],
    unidades: [{id: "u1", dueno: "dep:a", gastado_mm: 0, hacia: "dep:b"},
               {id: "u2", dueno: "dep:a", gastado_mm: 0, hacia: null}],
    avisos: [],
  };
}

test("cada calle da un segmento entre los dos edificios", () => {
  const c = ciudadDePrueba();
  const [s] = puntosDeCalle(c, crearCamara(0, 0, 1), VISTA);
  assert.equal(s.ancho, 2);
  assert.equal(s.tipo, "calle");
  assert.ok(s.desde.x < s.hasta.x, "el segmento no va de a hacia b");
});

test("una calle con un extremo que no existe se descarta sin romper", () => {
  const c = ciudadDePrueba();
  c.calles.push({a: "dep:a", b: "dep:fantasma", peso_mm: 1, ancho: 1,
                 tipo: "cable"});
  assert.equal(puntosDeCalle(c, crearCamara(0, 0, 1), VISTA).length, 1);
});

test("la unidad con destino camina de su casa al otro edificio", () => {
  const c = ciudadDePrueba();
  const cam = crearCamara(0, 0, 1);
  // la ida ocupa la primera mitad de la fase: 0 es la casa, 0.5 el destino
  const casa = posicionDeUnidad(c.unidades[0], c, cam, VISTA, 0);
  const medio = posicionDeUnidad(c.unidades[0], c, cam, VISTA, 0.25);
  const destino = posicionDeUnidad(c.unidades[0], c, cam, VISTA, 0.5);
  assert.ok(destino.x > casa.x, "el destino no quedo del otro lado");
  assert.ok(medio.x > casa.x && medio.x < destino.x,
            "la unidad se salio del tramo");
});

test("al completar la fase la unidad volvio a su casa", () => {
  const c = ciudadDePrueba();
  const cam = crearCamara(0, 0, 1);
  const casa = posicionDeUnidad(c.unidades[0], c, cam, VISTA, 0);
  const vuelta = posicionDeUnidad(c.unidades[0], c, cam, VISTA, 1);
  assert.ok(Math.abs(casa.x - vuelta.x) < 1e-6, "la vuelta no cierra");
});

test("la unidad sin destino orbita su casa en vez de irse al origen", () => {
  const c = ciudadDePrueba();
  const cam = crearCamara(0, 0, 1);
  const casa = puntosDeCalle(c, cam, VISTA)[0].desde;
  const p = posicionDeUnidad(c.unidades[1], c, cam, VISTA, 0.25);
  const d = Math.hypot(p.x - casa.x, p.y - casa.y);
  assert.ok(d > 0 && d < 60, `orbita rara: ${d}`);
});

test("una unidad huerfana no rompe el dibujo", () => {
  const c = ciudadDePrueba();
  const suelta = {id: "u3", dueno: "dep:fantasma", gastado_mm: 0, hacia: null};
  assert.equal(posicionDeUnidad(suelta, c, crearCamara(0, 0, 1), VISTA, 0), null);
});

test("la fase da la vuelta sin saltos", () => {
  const c = ciudadDePrueba();
  const cam = crearCamara(0, 0, 1);
  const a = posicionDeUnidad(c.unidades[1], c, cam, VISTA, 0);
  const b = posicionDeUnidad(c.unidades[1], c, cam, VISTA, 1);
  assert.ok(Math.abs(a.x - b.x) < 1e-6 && Math.abs(a.y - b.y) < 1e-6,
            "la orbita salta al completar la vuelta");
});
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: FALLA con `Cannot find module` de `./mapa.js`.

- [ ] **Step 3: Escribir el mapa**

Crear `calipso/web/fabrica/mapa.js`:

```js
/**
 * calipso/web/fabrica/mapa.js — El dibujo de la ciudad.
 *
 * La geometria (donde va cada calle, donde esta cada unidad) es pura y se
 * testea; el canvas queda como una capa fina encima. La `fase` de las
 * unidades entra por parametro en vez de leer el reloj adentro: asi el
 * dibujo sigue siendo una funcion de sus argumentos.
 */
import {aPantalla, escalaEntera} from "./camara.js";
import {centroDe, indice, ordenDePintado} from "./ciudad.js";
import {rampaDe} from "./paleta.js";
import {edificioSprite, pintar} from "./sprites.js";

const FONDO = "#0b0f14";
const CALLE = "#2a3038";
const CABLE = "#c9a3e0";
const UNIDAD = "#9ae6a4";
const AVISO = "#ffd75f";
const RESALTE = "#66d9ff";
const RADIO_ORBITA = 22;

// `idx` entra por parametro para que el bucle de dibujo lo calcule una sola
// vez por cuadro en vez de una vez por calle y por unidad.
export function puntosDeCalle(ciudad, cam, vista, idx = indice(ciudad)) {
  const {porId} = idx;
  const out = [];
  for (const c of ciudad.calles) {
    const a = porId.get(c.a), b = porId.get(c.b);
    if (!a || !b) continue;          // una punta que no existe no se dibuja
    out.push({desde: aPantalla(cam, centroDe(a), vista),
              hasta: aPantalla(cam, centroDe(b), vista),
              ancho: c.ancho, tipo: c.tipo});
  }
  return out;
}

/** `fase` va de 0 a 1 y vuelve a empezar. */
export function posicionDeUnidad(unidad, ciudad, cam, vista, fase,
                                 idx = indice(ciudad)) {
  const {porId} = idx;
  const casa = porId.get(unidad.dueno);
  if (!casa) return null;
  const p = aPantalla(cam, centroDe(casa), vista);
  const destino = unidad.hacia ? porId.get(unidad.hacia) : null;
  if (!destino) {
    // sin calle a donde ir, la unidad orbita su propia casa
    const a = fase * Math.PI * 2;
    return {x: p.x + Math.cos(a) * RADIO_ORBITA,
            y: p.y + Math.sin(a) * RADIO_ORBITA};
  }
  const q = aPantalla(cam, centroDe(destino), vista);
  // ida y vuelta, para que la unidad no teletransporte al llegar
  const u = fase <= 0.5 ? fase * 2 : (1 - fase) * 2;
  return {x: p.x + (q.x - p.x) * u, y: p.y + (q.y - p.y) * u};
}

export function crearMapa(canvas) {
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;     // pixel art: nada de interpolar
  const cache = new Map();               // sprites ya rasterizados

  function vista() {
    return {ancho: canvas.clientWidth, alto: canvas.clientHeight};
  }

  /**
   * DEUDA DECLARADA: el dpr se redondea a entero. Los aparatos de Pedro
   * (el Ally, el iPhone, el Mac) tienen todos dpr entero, y redondear
   * mantiene la escala de dibujo entera con un solo sistema de
   * coordenadas. En una pantalla con dpr fraccionario (Windows al 150%)
   * el navegador reescala el lienzo entero y el pixel art pierde nitidez.
   * El arreglo completo es pintar en pixeles fisicos, y cuesta manejar
   * dos sistemas de coordenadas a la vez.
   */
  function dpr() {
    return Math.max(1, Math.min(3, Math.round(window.devicePixelRatio || 1)));
  }

  // reasigna el bitmap SOLO si cambio de tamano: asignar canvas.width lo
  // borra entero y es caro, y aca se llama en cada cuadro
  function ajustar() {
    const d = dpr(), v = vista();
    const ancho = Math.round(v.ancho * d), alto = Math.round(v.alto * d);
    if (canvas.width === ancho && canvas.height === alto) return;
    canvas.width = ancho;
    canvas.height = alto;
    ctx.setTransform(d, 0, 0, d, 0, 0);
    ctx.imageSmoothingEnabled = false;
  }

  /** Un edificio se dibuja una vez por combinacion y despues se copia. */
  function rasterizar(e, esc) {
    const clave = `${e.id}|${e.zona}|${e.estado}|${e.tamano}|${e.actividad}|${esc}`;
    const guardado = cache.get(clave);
    if (guardado) return guardado;
    const sprite = edificioSprite(e);
    const fuera = document.createElement("canvas");
    fuera.width = sprite.ancho * esc;
    fuera.height = sprite.alto * esc;
    const octx = fuera.getContext("2d");
    octx.imageSmoothingEnabled = false;
    pintar(octx, sprite, rampaDe(e), 0, 0, esc);
    const listo = {lienzo: fuera, ancho: fuera.width, alto: fuera.height};
    if (cache.size > 300) cache.clear();   // techo simple; la ciudad es chica
    cache.set(clave, listo);
    return listo;
  }

  function dibujar(ciudad, cam, resaltado = null, fase = 0) {
    ajustar();
    const v = vista();
    ctx.fillStyle = FONDO;
    ctx.fillRect(0, 0, v.ancho, v.alto);
    const esc = escalaEntera(cam);
    const idx = indice(ciudad);            // una vez por cuadro, no por item
    const {avisosPorId} = idx;

    for (const s of puntosDeCalle(ciudad, cam, v, idx)) {
      ctx.strokeStyle = s.tipo === "cable" ? CABLE : CALLE;
      ctx.lineWidth = s.ancho * esc;
      ctx.setLineDash(s.tipo === "cable" ? [6 * esc, 4 * esc] : []);
      ctx.beginPath();
      ctx.moveTo(s.desde.x, s.desde.y);
      ctx.lineTo(s.hasta.x, s.hasta.y);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    for (const e of ordenDePintado(ciudad.edificios)) {
      const r = rasterizar(e, esc);
      const p = aPantalla(cam, centroDe(e), v);
      const x = Math.round(p.x - r.ancho / 2);
      const y = Math.round(p.y - r.alto);
      if (x + r.ancho < 0 || x > v.ancho ||
          y + r.alto < 0 || y > v.alto) continue;
      ctx.drawImage(r.lienzo, x, y);
      if (e.id === resaltado) {
        ctx.strokeStyle = RESALTE;
        ctx.lineWidth = 2;
        ctx.strokeRect(x - 2, y - 2, r.ancho + 4, r.alto + 4);
      }
      const avisos = avisosPorId.get(e.id) || 0;
      for (let i = 0; i < avisos; i++) {
        ctx.fillStyle = AVISO;
        ctx.fillRect(x + i * 5 * esc, y - 6 * esc, 3 * esc, 3 * esc);
      }
    }

    for (const u of ciudad.unidades) {
      const p = posicionDeUnidad(u, ciudad, cam, v, fase, idx);
      if (!p) continue;
      ctx.fillStyle = UNIDAD;
      ctx.fillRect(Math.round(p.x) - esc, Math.round(p.y) - esc,
                   2 * esc, 2 * esc);
    }
  }

  return {dibujar, vista};
}
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: PASA.

- [ ] **Step 5: Escribir el esqueleto y el estilo**

Crear `calipso/web/fabrica/index.html`:

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b0f14">
<title>Calipso — la fabrica</title>
<link rel="manifest" href="/fabrica/manifest.json">
<link rel="stylesheet" href="/static/fabrica/estilo.css">
</head>
<body>
<div id="app">
  <aside id="panel-chats" class="panel">
    <div class="titulo">Chats</div>
    <div id="lista-chats" class="lista"></div>
  </aside>

  <main id="panel-centro" class="panel">
    <div class="titulo">Calipso</div>
    <div id="conversacion" class="conversacion"></div>
    <form id="entrada" autocomplete="off">
      <input id="texto" type="text" placeholder="Escribi a Calipso">
      <button type="submit">Enviar</button>
    </form>
  </main>

  <section id="panel-mapa" class="panel">
    <div class="titulo">
      <span>La fabrica</span>
      <button id="expandir" type="button">Sobrevolar</button>
    </div>
    <div class="lienzo">
      <canvas id="mapa"></canvas>
      <div id="tarjeta" class="tarjeta oculto"></div>
      <div id="sin-fabrica" class="sin-fabrica oculto">
        Todavia no hay fabrica: la economia no esta activa.
      </div>
    </div>
  </section>

  <nav id="pestanas">
    <button data-pestana="chat" class="activa" type="button">Chat</button>
    <button data-pestana="mapa" type="button">Mapa</button>
  </nav>

  <div id="avisos" class="avisos"></div>
</div>
<script type="module" src="/static/fabrica/app.js"></script>
<script>
// misma linea que ya usa la UI vieja: sin esto el service worker nunca se
// registra desde /fabrica y toda la parte de PWA de la tarea 5 es inerte
if ("serviceWorker" in navigator) {
  window.addEventListener("load",
    () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
</script>
</body>
</html>
```

Crear también `calipso/web/fabrica/manifest.json`, propio de la fábrica. El manifest global tiene `start_url: "/"`, así que instalar desde `/fabrica` abriría la UI vieja:

```json
{
  "name": "Calipso — la fabrica",
  "short_name": "Fabrica",
  "description": "La consola de la fabrica de Calipso",
  "id": "/fabrica",
  "start_url": "/fabrica",
  "scope": "/",
  "display": "standalone",
  "background_color": "#0b0f14",
  "theme_color": "#0b0f14",
  "orientation": "any",
  "icons": [
    {
      "src": "/static/icon.svg",
      "sizes": "any",
      "type": "image/svg+xml",
      "purpose": "any maskable"
    }
  ]
}
```

Crear `calipso/web/fabrica/estilo.css`:

```css
/* calipso/web/fabrica/estilo.css — La consola de la fabrica. */
:root {
  --fondo: #0b0f14;
  --panel: #12161c;
  --linea: #222a33;
  --texto: #c9d1d9;
  --tenue: #6e7681;
  --acento: #66d9ff;
  --aviso: #ffd75f;
  --barra: 34px;
}

* { box-sizing: border-box; }

html, body {
  margin: 0; height: 100%; overflow: hidden;
  background: var(--fondo); color: var(--texto);
  font: 13px/1.5 ui-sans-serif, system-ui, sans-serif;
}

#app {
  display: grid; height: 100%;
  grid-template-columns: 220px minmax(0, 1fr) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr) var(--barra);
  grid-template-areas: "chats centro mapa" "avisos avisos avisos";
}

.panel {
  display: flex; flex-direction: column; min-width: 0; min-height: 0;
  border-right: 1px solid var(--linea); background: var(--panel);
}
#panel-chats { grid-area: chats; }
#panel-centro { grid-area: centro; }
#panel-mapa { grid-area: mapa; border-right: 0; }

.titulo {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; padding: 8px 10px; border-bottom: 1px solid var(--linea);
  color: var(--tenue); font-size: 11px; letter-spacing: .6px;
  text-transform: uppercase;
}
.titulo button {
  background: transparent; border: 1px solid var(--linea); color: var(--texto);
  border-radius: 4px; padding: 3px 8px; font-size: 11px; cursor: pointer;
}

.lista { overflow-y: auto; }
.lista .chat {
  padding: 7px 10px; border-bottom: 1px solid var(--linea);
  cursor: pointer; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis;
}
.lista .chat.activo { color: var(--acento); }

.conversacion { flex: 1; overflow-y: auto; padding: 10px; }
.conversacion .turno { margin-bottom: 12px; white-space: pre-wrap; }
.conversacion .turno.mio { color: var(--acento); }
.conversacion .turno.error { color: #ff7b72; }

#entrada { display: flex; gap: 6px; padding: 8px; border-top: 1px solid var(--linea); }
#entrada input {
  flex: 1; min-width: 0; background: var(--fondo); color: var(--texto);
  border: 1px solid var(--linea); border-radius: 4px; padding: 7px 9px;
  /* 16px o mas: por debajo, Safari de iPhone agranda la pagina al enfocar,
     y con overflow:hidden no hay scroll para volver */
  font-size: 16px;
}
#entrada button {
  background: var(--linea); color: var(--texto); border: 0;
  border-radius: 4px; padding: 7px 12px; cursor: pointer;
}

.lienzo { position: relative; flex: 1; min-height: 0; }
#mapa {
  display: block; width: 100%; height: 100%;
  touch-action: none;                  /* el paneo lo maneja la camara */
  image-rendering: pixelated;
  cursor: grab;
}
#mapa.arrastrando { cursor: grabbing; }

.tarjeta {
  position: absolute; pointer-events: none; max-width: 230px;
  background: #12161cf2; border: 1px solid var(--linea); border-radius: 5px;
  padding: 8px 10px; font-size: 12px;
}
.tarjeta .nombre { color: var(--acento); margin-bottom: 5px; }
.tarjeta .fila { display: flex; justify-content: space-between; gap: 12px; }
.tarjeta .fila span:first-child { color: var(--tenue); }
.tarjeta .congelado { color: #ff7b72; }

.sin-fabrica {
  position: absolute; inset: 0; display: flex;
  align-items: center; justify-content: center;
  color: var(--tenue); text-align: center; padding: 20px;
}

.avisos {
  grid-area: avisos; display: flex; align-items: center; gap: 10px;
  padding: 0 10px; overflow-x: auto; white-space: nowrap;
  border-top: 1px solid var(--linea); background: var(--panel);
  font-size: 12px;
}
.avisos .nada { color: var(--tenue); }
.avisos .aviso { color: var(--aviso); }

#pestanas { display: none; }
.oculto { display: none !important; }

/* Mapa a pantalla completa, para sobrevolar. */
#app.mapa-entero { grid-template-areas: "mapa mapa mapa" "avisos avisos avisos"; }
#app.mapa-entero #panel-chats,
#app.mapa-entero #panel-centro { display: none; }

/* Telefono: dos pestanas, con la barra de avisos siempre a la vista. */
@media (max-width: 820px) {
  #app {
    grid-template-columns: minmax(0, 1fr);
    /* el viewport dice viewport-fit=cover, asi que hay que devolverle el
       espacio del indicador de inicio o la barra de avisos queda debajo */
    grid-template-rows: minmax(0, 1fr) 42px
                        calc(var(--barra) + env(safe-area-inset-bottom));
    grid-template-areas: "centro" "pestanas" "avisos";
    padding-left: env(safe-area-inset-left);
    padding-right: env(safe-area-inset-right);
  }
  .avisos { padding-bottom: env(safe-area-inset-bottom); }
  #panel-chats { display: none; }
  #panel-centro, #panel-mapa { grid-area: centro; border-right: 0; }
  #app[data-pestana="chat"] #panel-mapa { display: none; }
  #app[data-pestana="mapa"] #panel-centro { display: none; }
  #pestanas {
    grid-area: pestanas; display: grid; grid-template-columns: 1fr 1fr;
    border-top: 1px solid var(--linea); background: var(--panel);
  }
  #pestanas button {
    background: transparent; border: 0; color: var(--tenue);
    font-size: 13px; cursor: pointer;
  }
  #pestanas button.activa { color: var(--acento); }
  .titulo #expandir { display: none; }
}
```

- [ ] **Step 6: Escribir el pegamento mínimo**

Crear `calipso/web/fabrica/app.js` — por ahora solo carga la ciudad, la dibuja y deja recorrerla. Los paneles y el chat llegan en las tareas 5 y 6:

```js
/**
 * calipso/web/fabrica/app.js — El pegamento.
 *
 * Engancha los eventos del navegador con los modulos puros. Toda la
 * logica que se puede testear vive en los otros archivos; aca solo hay
 * cableado.
 */
import {crearCamara, arrastrar, acercar, paso, encuadrar} from "./camara.js";
import {cargarCiudad, enPunto} from "./ciudad.js";
import {crearMapa} from "./mapa.js";

const lienzo = document.getElementById("mapa");
const sinFabrica = document.getElementById("sin-fabrica");
const mapa = crearMapa(lienzo);
const cam = crearCamara(0, 0, 1);

let ciudad = null;
let estadoRed = "cargando";   // cargando | activa | inactiva | sin-conexion
let resaltado = null;
let ultimo = 0;
let encuadrado = false;       // el bucle encuadra cuando el lienzo ya mide

async function traer() {
  try {
    const r = await cargarCiudad();
    if (r.activa) { ciudad = r.ciudad; estadoRed = "activa"; }
    else { ciudad = null; estadoRed = "inactiva"; }
  } catch (e) {
    // "no hay fabrica" y "no llego la respuesta" son cosas distintas y el
    // cartel no puede mentir sobre cual de las dos es
    estadoRed = "sin-conexion";
  }
  sinFabrica.textContent = estadoRed === "inactiva"
    ? "Todavia no hay fabrica: la economia no esta activa."
    : "Sin conexion con el servidor.";
  sinFabrica.classList.toggle("oculto", ciudad !== null);
}

window.addEventListener("online", () => { traer(); });

function bucle(ahora) {
  const dt = ultimo ? ahora - ultimo : 16;
  ultimo = ahora;
  paso(cam, dt);
  const v = mapa.vista();
  // el encuadre espera a que el lienzo tenga tamano: en el telefono nace
  // adentro de un panel oculto y mide cero
  if (ciudad && !encuadrado && v.ancho > 0 && v.alto > 0) {
    Object.assign(cam, encuadrar(ciudad.edificios, v));
    encuadrado = true;
  }
  if (ciudad) mapa.dibujar(ciudad, cam, resaltado, (ahora / 4000) % 1);
  requestAnimationFrame(bucle);
}

// un Map de punteros vivos, no una variable: con dos dedos hay que hacer
// pinza, y con una sola variable el segundo dedo le pasa a arrastrar() la
// separacion entre los dos y el mapa salta
const punteros = new Map();
let pinza = null;

const separacion = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const puntoMedio = (a, b) => ({x: (a.x + b.x) / 2, y: (a.y + b.y) / 2});

function local(ev) {
  const caja = lienzo.getBoundingClientRect();
  return {x: ev.clientX - caja.left, y: ev.clientY - caja.top};
}

lienzo.addEventListener("pointerdown", ev => {
  lienzo.setPointerCapture(ev.pointerId);
  const p = local(ev);
  punteros.set(ev.pointerId, {x: p.x, y: p.y, movio: false});
  if (punteros.size === 2) {
    const [a, b] = [...punteros.values()];
    pinza = separacion(a, b);
  }
  lienzo.classList.add("arrastrando");
});

lienzo.addEventListener("pointermove", ev => {
  const p = local(ev);
  const previo = punteros.get(ev.pointerId);
  if (previo) {
    const dx = p.x - previo.x, dy = p.y - previo.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) previo.movio = true;
    previo.x = p.x;
    previo.y = p.y;
    if (punteros.size >= 2) {
      const [a, b] = [...punteros.values()];
      const ahora = separacion(a, b);
      if (pinza > 0 && ahora > 0) {
        acercar(cam, ahora / pinza, puntoMedio(a, b), mapa.vista());
      }
      pinza = ahora;
      return;                       // con dos dedos se hace pinza, no paneo
    }
    arrastrar(cam, dx, dy);
    return;
  }
  if (!ciudad) return;
  resaltado = enPunto(ciudad, cam, mapa.vista(), p.x, p.y);
});

function soltar(ev) {
  punteros.delete(ev.pointerId);
  if (punteros.size < 2) pinza = null;
  if (!punteros.size) lienzo.classList.remove("arrastrando");
  if (lienzo.hasPointerCapture(ev.pointerId)) {
    lienzo.releasePointerCapture(ev.pointerId);
  }
}
lienzo.addEventListener("pointerup", soltar);
lienzo.addEventListener("pointercancel", soltar);

// solo el mouse tiene "salir": en touch el pointerleave llega SIEMPRE
// justo despues del pointerup, y borraria lo que el toque acaba de abrir
lienzo.addEventListener("pointerleave", ev => {
  if (ev.pointerType !== "mouse") return;
  resaltado = null;
});

lienzo.addEventListener("wheel", ev => {
  ev.preventDefault();
  acercar(cam, ev.deltaY < 0 ? 1.12 : 1 / 1.12, local(ev), mapa.vista());
}, {passive: false});

await traer();
requestAnimationFrame(bucle);
```

- [ ] **Step 7: Escribir el test de la ruta**

Agregar al final de `test_mapa_server.py`. El archivo ya tiene una fixture llamada `cliente` (un `TestClient` con la cookie puesta) y un `test_sin_auth_rechaza` que arma su propio `TestClient(srv.app)` sin cookie; estos tests siguen ese mismo patrón:

```python
def test_fabrica_sirve_la_app(cliente):
    r = cliente.get("/fabrica")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "/static/fabrica/app.js" in r.text


def test_los_modulos_del_cliente_se_sirven(cliente):
    for modulo in ("app.js", "camara.js", "ciudad.js", "mapa.js",
                   "sprites.js", "paleta.js"):
        r = cliente.get(f"/static/fabrica/{modulo}")
        assert r.status_code == 200, modulo
        assert "javascript" in r.headers["content-type"], modulo


def test_el_manifest_de_la_fabrica_arranca_en_la_fabrica(cliente):
    r = cliente.get("/fabrica/manifest.json")
    assert r.status_code == 200
    m = r.json()
    # el manifest global arranca en "/" y abriria la UI vieja
    assert m["start_url"] == "/fabrica"


def test_fabrica_sin_auth_manda_al_login(cliente):
    # /fabrica no es /api ni /ws: el middleware redirige en vez de dar 401
    c = TestClient(srv.app)
    r = c.get("/fabrica", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
```

El parámetro `cliente` en el último test está para que la fixture apunte `_ECO_BASE` al `tmp_path`, no porque se lo use: sin eso, el test tocaría la economía real del disco.

- [ ] **Step 8: Correr los tests para verificar que fallan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_server.py -v`
Esperado: los tres nuevos FALLAN con 404 (la ruta `/fabrica` todavía no existe).

- [ ] **Step 9: Agregar la ruta**

En `calipso/server.py`, justo después de la función `service_worker()` y antes del comentario de estáticos:

```python
@app.get("/fabrica")
def fabrica() -> FileResponse:
    """La consola de la fabrica. App propia: no toca la UI vieja de `/`."""
    return FileResponse(WEB / "fabrica" / "index.html")


@app.get("/fabrica/manifest.json")
def fabrica_manifest() -> FileResponse:
    """Manifest propio: el global arranca en `/` y abriria la UI vieja."""
    return FileResponse(WEB / "fabrica" / "manifest.json",
                        media_type="application/manifest+json")
```

- [ ] **Step 10: Correr los tests para verificar que pasan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_server.py test_fabrica_js.py -v`
Esperado: PASA.

- [ ] **Step 11: Commit**

```bash
git add calipso/web/fabrica/mapa.js calipso/web/fabrica/mapa.test.js \
        calipso/web/fabrica/index.html calipso/web/fabrica/estilo.css \
        calipso/web/fabrica/manifest.json calipso/web/fabrica/app.js \
        calipso/server.py test_mapa_server.py
git commit -m "feat(fabrica): la ruta, el esqueleto y la ciudad dibujada"
```

---

### Task 5: Paneles, tarjeta de hover, barra de avisos y PWA

**Files:**
- Create: `calipso/web/fabrica/paneles.js`
- Create: `calipso/web/fabrica/paneles.test.js`
- Modify: `calipso/web/fabrica/app.js`
- Modify: `calipso/web/sw.js`
- Modify: `test_mapa_server.py`

**Interfaces:**
- Consumes: `fichaDe(ciudad, id)` y `monedas(mm)` de `ciudad.js`.
- Produces: `ANCHO_TELEFONO=820`; `disposicion(ancho) -> "tres-paneles"|"dos-pestanas"`; `escapar(texto) -> string` (la tarea 6 se apoya en este export); `textoDeTarjeta(ficha) -> string` (HTML); `posicionDeTarjeta(x, y, caja, tarjeta) -> {x, y}`; `resumenDeAvisos(ciudad) -> array de {id, texto, sobre}`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `calipso/web/fabrica/paneles.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";

import {disposicion, textoDeTarjeta, posicionDeTarjeta, resumenDeAvisos,
        ANCHO_TELEFONO} from "./paneles.js";
import {fichaDe} from "./ciudad.js";

function ciudadDePrueba() {
  const base = {nombre: "atlas", zona: "fabrica", orden: 0, tamano: 4,
                estado: "activo", saldo_mm: 1_148_000, gasto_ciclo_mm: 22_500,
                ventas_ventana_mm: 900_000, eficiencia_pormil: 1234,
                actividad: 2, trabajos: [], compuertas: 0, x: 0, y: 0};
  return {
    edificios: [{...base, id: "dep:atlas"},
                {...base, id: "dep:frio", nombre: "frio", estado: "congelado"}],
    calles: [], unidades: [],
    avisos: [{id: "c1", tipo: "gasto", sobre: "dep:atlas",
              monedas_en_juego_mm: 50_000},
             {id: "c2", tipo: "renovacion", sobre: null,
              monedas_en_juego_mm: 120_000}],
  };
}

test("el ancho decide la disposicion", () => {
  assert.equal(disposicion(1400), "tres-paneles");
  assert.equal(disposicion(ANCHO_TELEFONO + 1), "tres-paneles");
  assert.equal(disposicion(ANCHO_TELEFONO), "dos-pestanas");
  assert.equal(disposicion(390), "dos-pestanas");
});

test("la tarjeta muestra los cinco numeros de la ficha", () => {
  const html = textoDeTarjeta(fichaDe(ciudadDePrueba(), "dep:atlas"));
  for (const esperado of ["atlas", "1.148", "22,5", "900", "123,4%"]) {
    assert.ok(html.includes(esperado), `falta ${esperado} en la tarjeta`);
  }
});

test("la tarjeta de un congelado lo dice", () => {
  const html = textoDeTarjeta(fichaDe(ciudadDePrueba(), "dep:frio"));
  assert.ok(/congelado/i.test(html));
});

test("la tarjeta no deja pasar html del modelo", () => {
  const c = ciudadDePrueba();
  c.edificios[0].nombre = "<img onerror=x>";
  const html = textoDeTarjeta(fichaDe(c, "dep:atlas"));
  assert.ok(!html.includes("<img"), "se colo una etiqueta del modelo");
  assert.ok(html.includes("&lt;img"), "no se escapo el nombre");
});

test("la tarjeta no se sale por la derecha ni por abajo", () => {
  const caja = {ancho: 400, alto: 300};
  const tarjeta = {ancho: 230, alto: 120};
  const p = posicionDeTarjeta(390, 290, caja, tarjeta);
  assert.ok(p.x + tarjeta.ancho <= caja.ancho, "se fue por la derecha");
  assert.ok(p.y + tarjeta.alto <= caja.alto, "se fue por abajo");
  assert.ok(p.x >= 0 && p.y >= 0, "se fue por el otro lado");
});

test("con lugar de sobra la tarjeta va al lado del dedo", () => {
  const p = posicionDeTarjeta(50, 50, {ancho: 800, alto: 600},
                              {ancho: 230, alto: 120});
  assert.ok(p.x > 50 && p.y >= 50);
});

test("los avisos salen ordenados por lo que hay en juego", () => {
  const r = resumenDeAvisos(ciudadDePrueba());
  assert.equal(r.length, 2);
  assert.equal(r[0].id, "c2");            // 120 monedas antes que 50
  assert.ok(r[0].texto.includes("120"));
});

test("una ciudad sin avisos devuelve una lista vacia, no null", () => {
  const c = ciudadDePrueba();
  c.avisos = [];
  assert.deepEqual(resumenDeAvisos(c), []);
});
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: FALLA con `Cannot find module` de `./paneles.js`.

- [ ] **Step 3: Escribir los paneles**

Crear `calipso/web/fabrica/paneles.js`:

```js
/**
 * calipso/web/fabrica/paneles.js — La disposicion y los avisos.
 *
 * Todo lo que decide QUE se muestra vive aca y es puro; el DOM lo toca
 * app.js. El nombre de un departamento lo escribe Pedro, asi que se
 * escapa antes de meterlo en el HTML de la tarjeta.
 */
import {monedas} from "./ciudad.js";

export const ANCHO_TELEFONO = 820;   // el mismo corte que el media query

export function disposicion(ancho) {
  return ancho > ANCHO_TELEFONO ? "tres-paneles" : "dos-pestanas";
}

export function escapar(texto) {
  return String(texto)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function fila(etiqueta, valor) {
  return `<div class="fila"><span>${escapar(etiqueta)}</span>` +
         `<span>${escapar(valor)}</span></div>`;
}

export function textoDeTarjeta(ficha) {
  if (!ficha) return "";
  const estado = ficha.estado === "congelado"
    ? '<div class="congelado">congelado</div>' : "";
  return `<div class="nombre">${escapar(ficha.nombre)}</div>` + estado +
    fila("saldo", ficha.saldo) +
    fila("gasto del ciclo", ficha.gasto_ciclo) +
    fila("ventas de la ventana", ficha.ventas_ventana) +
    fila("eficiencia", ficha.eficiencia) +
    fila("trabajos", ficha.trabajos) +
    fila("compuertas", ficha.compuertas);
}

export function posicionDeTarjeta(x, y, caja, tarjeta) {
  const margen = 12;
  let px = x + margen, py = y + margen;
  if (px + tarjeta.ancho > caja.ancho) px = x - margen - tarjeta.ancho;
  if (py + tarjeta.alto > caja.alto) py = y - margen - tarjeta.alto;
  return {x: Math.max(0, Math.min(px, caja.ancho - tarjeta.ancho)),
          y: Math.max(0, Math.min(py, caja.alto - tarjeta.alto))};
}

export function resumenDeAvisos(ciudad) {
  return [...(ciudad.avisos || [])]
    .sort((a, b) => (b.monedas_en_juego_mm - a.monedas_en_juego_mm) ||
                    (a.id < b.id ? -1 : 1))
    .map(a => ({
      id: a.id, sobre: a.sobre,
      texto: `${a.tipo}${a.sobre ? " en " + a.sobre.split(":").pop() : ""}` +
             ` — ${monedas(a.monedas_en_juego_mm)}`,
    }));
}
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: PASA.

- [ ] **Step 5: Cablear los paneles en app.js**

En `calipso/web/fabrica/app.js`, **extender la línea de import de `ciudad.js` que ya está** para que quede así (no agregar una segunda línea del mismo módulo):

```js
import {cargarCiudad, enPunto, fichaDe} from "./ciudad.js";
```

y agregar el import nuevo debajo de los otros:

```js
import {disposicion, escapar, textoDeTarjeta, posicionDeTarjeta,
        resumenDeAvisos} from "./paneles.js";
```

Y al final del archivo, antes de `await traer()`:

```js
const app = document.getElementById("app");
const tarjeta = document.getElementById("tarjeta");
const barra = document.getElementById("avisos");

// El layout lo resuelve el CSS con su media query, que no depende de que
// el JS ande. `disposicion` decide lo que el CSS no puede: en el telefono
// el dedo tapa la tarjeta si va pegada al punto, asi que ahi se ancla a
// una esquina del lienzo en vez de seguir al puntero.
function tarjetaSigueAlPuntero() {
  return disposicion(window.innerWidth) === "tres-paneles";
}

for (const boton of document.querySelectorAll("#pestanas button")) {
  boton.addEventListener("click", () => {
    app.dataset.pestana = boton.dataset.pestana;
    for (const otro of document.querySelectorAll("#pestanas button")) {
      otro.classList.toggle("activa", otro === boton);
    }
  });
}
app.dataset.pestana = "chat";

document.getElementById("expandir").addEventListener("click", () => {
  app.classList.toggle("mapa-entero");
});

function pintarAvisos() {
  const avisos = ciudad ? resumenDeAvisos(ciudad) : [];
  if (!avisos.length) {
    barra.innerHTML = '<span class="nada">Sin compuertas pendientes</span>';
    return;
  }
  barra.innerHTML = avisos
    .map(a => `<span class="aviso">${escapar(a.texto)}</span>`)
    .join("");
}

function pintarTarjeta(px, py) {
  const ficha = (ciudad && resaltado) ? fichaDe(ciudad, resaltado) : null;
  if (!ficha) { tarjeta.classList.add("oculto"); return; }
  tarjeta.innerHTML = textoDeTarjeta(ficha);
  tarjeta.classList.remove("oculto");   // visible antes de medirla
  if (!tarjetaSigueAlPuntero()) {
    tarjeta.style.left = "10px";
    tarjeta.style.top = "10px";
    return;
  }
  const caja = lienzo.getBoundingClientRect();
  const p = posicionDeTarjeta(px, py, {ancho: caja.width, alto: caja.height},
                              {ancho: tarjeta.offsetWidth,
                               alto: tarjeta.offsetHeight});
  tarjeta.style.left = p.x + "px";
  tarjeta.style.top = p.y + "px";
}
```

Después hay que tocar tres lugares del `app.js` que escribió la tarea 4.

**Uno.** En el `pointermove`, la última línea es `resaltado = enPunto(ciudad, cam, mapa.vista(), p.x, p.y);`. Agregarle debajo:

```js
  pintarTarjeta(p.x, p.y);
```

**Dos.** En el `pointerleave`, que ya filtra por `ev.pointerType !== "mouse"`, agregar después de `resaltado = null;`:

```js
  tarjeta.classList.add("oculto");
```

**Tres.** En la función `soltar`, **antes** de la línea `punteros.delete(ev.pointerId);`, abrir la tarjeta cuando el gesto fue un toque y no un arrastre. Es la única forma de consultar un edificio en el teléfono, donde no hay hover:

```js
  const tocado = punteros.get(ev.pointerId);
  if (tocado && !tocado.movio && punteros.size === 1 && ciudad) {
    resaltado = enPunto(ciudad, cam, mapa.vista(), tocado.x, tocado.y);
    pintarTarjeta(tocado.x, tocado.y);
  }
```

Y en el botón de expandir, además de alternar la clase, pedir un encuadre nuevo — el lienzo cambia de tamaño y la ciudad tiene que volver a entrar:

```js
  encuadrado = false;
```

Al final de `traer()`, agregar `pintarAvisos();`.

- [ ] **Step 6: Sumar el mapa al shell de la PWA**

En `calipso/web/sw.js`, cambiar la constante `CACHE` a `"calipso-shell-v2"` (para que el service worker viejo se retire) y agregar las rutas del cliente a `SHELL`:

```js
const CACHE = "calipso-shell-v2";
const SHELL = [
  "/",
  "/fabrica",
  "/fabrica/manifest.json",
  "/manifest.json",
  "/static/icon.svg",
  "/static/fabrica/estilo.css",
  "/static/fabrica/app.js",
  "/static/fabrica/paleta.js",
  "/static/fabrica/sprites.js",
  "/static/fabrica/camara.js",
  "/static/fabrica/ciudad.js",
  "/static/fabrica/mapa.js",
  "/static/fabrica/paneles.js"
];
```

`chat.js` **no** va todavía: lo crea la tarea 6, y `cache.addAll` rechaza el lote entero si una sola URL da 404. Entra en la tarea 6, junto con el archivo.

`calipso/web/manifest.json`, el global, **no se toca**: la fábrica ya tiene el suyo en `calipso/web/fabrica/manifest.json`, creado en la tarea 4, con `start_url` apuntando a `/fabrica`.

Agregar también a `test_mapa_server.py` un test que convierta un fallo silencioso del caché en un rojo:

```python
def test_todo_el_shell_del_service_worker_existe(cliente):
    """cache.addAll rechaza el lote entero si una URL da 404, y el service
    worker se lo traga con un catch. Que falle aca en vez de en silencio."""
    import re
    sw = (srv.WEB / "sw.js").read_text(encoding="utf-8")
    urls = re.findall(r'"(/[^"]*)"', sw.split("const SHELL")[1].split("];")[0])
    assert urls, "no se pudo leer el SHELL del service worker"
    for url in urls:
        assert cliente.get(url).status_code == 200, url
```

- [ ] **Step 7: Correr toda la suite**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest -q --ignore=test_chat_live.py`
Esperado: todo verde.

- [ ] **Step 8: Commit**

```bash
git add calipso/web/fabrica/paneles.js calipso/web/fabrica/paneles.test.js \
        calipso/web/fabrica/app.js calipso/web/sw.js test_mapa_server.py
git commit -m "feat(fabrica): paneles, tarjeta de hover, barra de avisos y PWA"
```

---

### Task 6: El panel de conversación

El chat contra el `/ws/chat` que ya existe, sin tocar el servidor. El acoplamiento de ida y vuelta con el mapa (que tocar un edificio contextualice a Calipso, y que Calipso mueva la cámara) es del Plan 3, porque necesita el `/ws/mapa` y la cuenta pagadora.

**Files:**
- Create: `calipso/web/fabrica/chat.js`
- Create: `calipso/web/fabrica/chat.test.js`
- Modify: `calipso/web/fabrica/app.js`
- Modify: `calipso/web/sw.js`

**Interfaces:**
- Produces: `estadoInicial() -> estado`; `aplicarEvento(estado, evento) -> estado`; `paquete(texto, chatId) -> objeto`; `crearChat(alCambiar) -> {enviar(texto), estado()}`. El `estado` es `{turnos: array de {quien, texto, abierto}, pensando: boolean, chatId: string|null, ruta: string|null, modelo: string|null, costo_usd: number, tokens: number}`.
- **El protocolo real de `/ws/chat`**, verificado en `calipso/server.py:2423-2425`: el evento de costo es `{type: "cost", model, route, tokens, cost_usd}`. No existe ningún `costo_mm` — eso es del pulso del Plan 3.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `calipso/web/fabrica/chat.test.js`:

```js
import test from "node:test";
import assert from "node:assert/strict";

import {estadoInicial, aplicarEvento, paquete} from "./chat.js";

const aplicar = (eventos, e0 = estadoInicial()) =>
  eventos.reduce((e, ev) => aplicarEvento(e, ev), e0);

test("el paquete lleva el texto y el chat", () => {
  assert.deepEqual(paquete("hola", "c1"), {text: "hola", chat_id: "c1"});
});

test("un paquete sin chat todavia no inventa uno", () => {
  assert.equal(paquete("hola", null).chat_id, null);
});

test("pensando prende la señal y los chunks arman el turno", () => {
  const e = aplicar([{type: "thinking"}, {type: "chunk", text: "hola "},
                     {type: "chunk", text: "Pedro"}]);
  assert.equal(e.pensando, true);
  assert.equal(e.turnos.at(-1).texto, "hola Pedro");
  assert.equal(e.turnos.at(-1).quien, "calipso");
});

test("done apaga la señal y deja el turno cerrado", () => {
  const e = aplicar([{type: "thinking"}, {type: "chunk", text: "listo"},
                     {type: "done"}]);
  assert.equal(e.pensando, false);
  assert.equal(e.turnos.length, 1);
  assert.equal(e.turnos[0].texto, "listo");
});

test("dos turnos seguidos no se pegan entre si", () => {
  const e = aplicar([{type: "thinking"}, {type: "chunk", text: "uno"},
                     {type: "done"},
                     {type: "thinking"}, {type: "chunk", text: "dos"},
                     {type: "done"}]);
  assert.deepEqual(e.turnos.map(t => t.texto), ["uno", "dos"]);
});

test("meta guarda por donde fue y con que modelo", () => {
  const e = aplicar([{type: "meta", route: "suscripcion", model: "opus"}]);
  assert.equal(e.ruta, "suscripcion");
  assert.equal(e.modelo, "opus");
});

test("el costo y los tokens se acumulan entre turnos", () => {
  // los campos son los que manda el servidor de verdad: cost_usd y tokens
  const e = aplicar([{type: "cost", model: "opus", route: "suscripcion",
                      tokens: 1200, cost_usd: 0.03},
                     {type: "cost", model: "opus", route: "suscripcion",
                      tokens: 800, cost_usd: 0.02}]);
  assert.equal(e.tokens, 2000);
  assert.ok(Math.abs(e.costo_usd - 0.05) < 1e-9);
});

test("un cost sin montos no ensucia el acumulado", () => {
  const e = aplicar([{type: "cost", tokens: 1200, cost_usd: 0.03},
                     {type: "cost"}]);
  assert.equal(e.tokens, 1200);
  assert.ok(Math.abs(e.costo_usd - 0.03) < 1e-9);
});

test("un error se ve y corta el pensar", () => {
  const e = aplicar([{type: "thinking"}, {type: "error", text: "se cayo"}]);
  assert.equal(e.pensando, false);
  assert.equal(e.turnos.at(-1).quien, "error");
  assert.ok(e.turnos.at(-1).texto.includes("se cayo"));
});

test("el chat activo que manda el servidor se guarda", () => {
  const e = aplicar([{type: "chat", action: "active", chat: {id: "c9"}}]);
  assert.equal(e.chatId, "c9");
});

test("un evento desconocido no rompe ni cambia nada", () => {
  const antes = estadoInicial();
  const despues = aplicarEvento(antes, {type: "vuelo_espacial"});
  assert.deepEqual(despues.turnos, antes.turnos);
  assert.equal(despues.pensando, antes.pensando);
});

test("aplicarEvento no muta el estado que recibe", () => {
  const antes = estadoInicial();
  aplicarEvento(antes, {type: "chunk", text: "x"});
  assert.equal(antes.turnos.length, 0);
});
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: FALLA con `Cannot find module` de `./chat.js`.

- [ ] **Step 3: Escribir el chat**

Crear `calipso/web/fabrica/chat.js`:

```js
/**
 * calipso/web/fabrica/chat.js — La conversacion con Calipso.
 *
 * Habla con el /ws/chat que ya existe, sin cambiarle nada al servidor.
 * El reductor de eventos es puro y no muta lo que recibe: por eso se
 * puede testear el protocolo entero sin abrir un socket.
 */

export function estadoInicial() {
  return {turnos: [], pensando: false, chatId: null, ruta: null,
          modelo: null, costo_usd: 0, tokens: 0};
}

export function paquete(texto, chatId) {
  return {text: texto, chat_id: chatId};
}

export function aplicarEvento(estado, ev) {
  const e = {...estado, turnos: [...estado.turnos]};
  switch (ev.type) {
    case "thinking":
      e.pensando = true;
      break;
    case "chunk": {
      const ultimo = e.turnos.at(-1);
      if (e.pensando && ultimo && ultimo.quien === "calipso" && ultimo.abierto) {
        e.turnos[e.turnos.length - 1] = {...ultimo,
                                         texto: ultimo.texto + (ev.text || "")};
      } else {
        e.turnos.push({quien: "calipso", texto: ev.text || "", abierto: true});
      }
      break;
    }
    case "done": {
      e.pensando = false;
      const ultimo = e.turnos.at(-1);
      if (ultimo && ultimo.abierto) {
        e.turnos[e.turnos.length - 1] = {...ultimo, abierto: false};
      }
      break;
    }
    case "meta":
      if (ev.route) e.ruta = ev.route;
      if (ev.model) e.modelo = ev.model;
      break;
    case "cost":
      // campos reales del /ws/chat: cost_usd y tokens (server.py:2423)
      e.costo_usd = e.costo_usd + (ev.cost_usd || 0);
      e.tokens = e.tokens + (ev.tokens || 0);
      break;
    case "error":
      e.pensando = false;
      e.turnos.push({quien: "error", texto: "error: " + (ev.text || ""),
                     abierto: false});
      break;
    case "chat":
      if (ev.chat && ev.chat.id) e.chatId = ev.chat.id;
      break;
    default:
      break;      // el /ws/chat manda mas cosas de las que este panel usa
  }
  return e;
}

export function crearChat(alCambiar) {
  let estado = estadoInicial();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let ws = null;

  function conectar() {
    ws = new WebSocket(`${proto}://${location.host}/ws/chat`);
    ws.addEventListener("message", ev => {
      let dato;
      try { dato = JSON.parse(ev.data); } catch { return; }
      estado = aplicarEvento(estado, dato);
      alCambiar(estado);
    });
    // si se cae, se reintenta: el mapa sigue andando mientras tanto
    ws.addEventListener("close", () => setTimeout(conectar, 2000));
  }
  conectar();

  return {
    estado: () => estado,
    enviar(texto) {
      if (!texto.trim() || !ws || ws.readyState !== WebSocket.OPEN) return;
      estado = {...estado,
                turnos: [...estado.turnos,
                         {quien: "pedro", texto, abierto: false}]};
      alCambiar(estado);
      ws.send(JSON.stringify(paquete(texto, estado.chatId)));
    },
  };
}
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -v`
Esperado: PASA.

- [ ] **Step 5: Cablear el chat en app.js**

Agregar un solo import arriba. `escapar` ya viene de `paneles.js` desde la tarea 5, así que esa línea no se toca:

```js
import {crearChat} from "./chat.js";
```

Y al final del archivo, antes de `await traer()`:

```js
const conversacion = document.getElementById("conversacion");
const formulario = document.getElementById("entrada");
const campo = document.getElementById("texto");

const chat = crearChat(estado => {
  conversacion.innerHTML = estado.turnos
    .map(t => `<div class="turno ${t.quien === "pedro" ? "mio" : ""}` +
              `${t.quien === "error" ? " error" : ""}">` +
              `${escapar(t.texto)}</div>`)
    .join("");
  conversacion.scrollTop = conversacion.scrollHeight;
});

formulario.addEventListener("submit", ev => {
  ev.preventDefault();
  chat.enviar(campo.value);
  campo.value = "";
});
```

Y cargar la lista de chats que ya expone el servidor. `GET /api/chats` devuelve `{"active": id o null, "chats": [...]}`, y cada chat trae `id`, `title`, `project_path`, `project_name`, `created_at`, `updated_at` y `messages` (un entero, la cantidad). `title` puede venir en `null`:

```js
const listaChats = document.getElementById("lista-chats");
try {
  const r = await fetch("/api/chats");
  if (r.ok) {
    const datos = await r.json();
    listaChats.innerHTML = (datos.chats || [])
      .map(c => `<div class="chat${c.id === datos.active ? " activo" : ""}"` +
                ` data-id="${escapar(c.id)}">` +
                `${escapar(c.title || "sin titulo")}</div>`)
      .join("");
  }
} catch (e) {
  listaChats.innerHTML = '<div class="chat">sin chats</div>';
}
```

- [ ] **Step 6: Sumar chat.js al shell del service worker**

Ahora que el archivo existe, entra en el caché. En `calipso/web/sw.js`, agregar al final de la lista `SHELL`:

```js
  "/static/fabrica/chat.js"
```

(acordate de la coma en la línea anterior). El test `test_todo_el_shell_del_service_worker_existe` que agregó la tarea 5 va a comprobar solo que la URL responde 200.

- [ ] **Step 7: Correr toda la suite**

Correr: `/var/home/pedro/calipso/.venv/bin/python -m pytest -q --ignore=test_chat_live.py`
Esperado: todo verde.

- [ ] **Step 8: Commit**

```bash
git add calipso/web/fabrica/chat.js calipso/web/fabrica/chat.test.js \
        calipso/web/fabrica/app.js calipso/web/sw.js
git commit -m "feat(fabrica): panel de conversacion contra el ws de chat que ya existe"
```

---

## Verificación a ojo (una vez, al cerrar el plan)

Los tests cubren la lógica; el render fino se mira. Levantar el servidor y abrir `/fabrica`:

1. La ciudad se ve: edificios con volumen, más altos los de más saldo, ventanas prendidas en los que gastaron hace poco.
2. Al abrir, la ciudad entera entra en pantalla sin tener que buscarla.
3. Arrastrar mueve en los dos ejes; la rueda acerca y aleja sin deformar el pixel. En el teléfono, dos dedos hacen pinza y el mapa no salta.
4. En el teléfono, tocar un edificio abre su tarjeta y el toque siguiente la cambia.
3. Pasar por encima de un edificio muestra la tarjeta con sus cinco números, y la tarjeta no se sale de la pantalla cerca de los bordes.
4. La barra de avisos lista las compuertas pendientes, la de más plata primero.
5. Achicando la ventana por debajo de 820 píxeles aparecen las dos pestañas y la barra de avisos sigue visible.
6. Un departamento congelado se ve gris y agrietado, sin una sola luz.

---

## Fuera de alcance de este plan (van al Plan 3)

- El pulso, el `WS /ws/mapa` y la instrumentación de los agentes.
- La marca `⟦foco:atlas⟧` y el vuelo de cámara disparado por la conversación.
- Que tocar un edificio contextualice a Calipso y que su billetera pague.
- Entrar a un departamento: el nivel de zoom interior, los escritorios y el razonamiento del empleado en el panel central.
