/**
 * lienzo.test.js — La capa que toca el canvas, con un contexto de mentira.
 *
 * `crearMapa` era la unica superficie del cliente sin test: no hay jsdom en
 * el repo y nadie iba a abrir un navegador en cada corrida. En vez de eso,
 * aca se le pasa un contexto falso que ANOTA cada operacion, y despues se
 * afirma sobre lo anotado. Es el codigo de verdad el que corre: el orden de
 * pintado, el cache de sprites, la guarda del redimensionado y el recorte
 * de lo que queda fuera de pantalla.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {crearCamara, escalaEntera} from "./camara.js";
import {centroDe, indice, ordenDePintado} from "./ciudad.js";
import {crearMapa} from "./mapa.js";
import {medidas} from "./sprites.js";

/** Un contexto 2D que no dibuja nada y se acuerda de todo. */
function contextoFalso() {
  const ops = [];
  return {
    ops,
    fillStyle: null, strokeStyle: null, lineWidth: 0,
    imageSmoothingEnabled: true,
    setTransform: (...a) => ops.push({op: "setTransform", a}),
    fillRect: (x, y, w, h) => ops.push({op: "fillRect", x, y, w, h}),
    strokeRect: (x, y, w, h) => ops.push({op: "strokeRect", x, y, w, h}),
    drawImage: (img, x, y) => ops.push({op: "drawImage", x, y,
                                        ancho: img.width, alto: img.height}),
    setLineDash: (d) => ops.push({op: "setLineDash", d: [...d]}),
    beginPath: () => ops.push({op: "beginPath"}),
    moveTo: (x, y) => ops.push({op: "moveTo", x, y}),
    lineTo: (x, y) => ops.push({op: "lineTo", x, y}),
    stroke: () => ops.push({op: "stroke"}),
  };
}

/** Prepara los globales del navegador que `mapa.js` toca. */
function montar(ancho = 800, alto = 600, dpr = 1) {
  const creados = [];
  globalThis.window = {devicePixelRatio: dpr};
  globalThis.document = {
    createElement() {
      const c = {width: 0, height: 0, getContext: () => contextoFalso()};
      creados.push(c);
      return c;
    },
  };
  const ctx = contextoFalso();
  let anchoAsignado = 0, altoAsignado = 0, asignaciones = 0;
  const lienzo = {
    clientWidth: ancho, clientHeight: alto,
    getContext: () => ctx,
    get width() { return anchoAsignado; },
    set width(v) { anchoAsignado = v; asignaciones++; },
    get height() { return altoAsignado; },
    set height(v) { altoAsignado = v; },
  };
  return {lienzo, ctx, creados, cuantasAsignaciones: () => asignaciones};
}

function edi(id, extra = {}) {
  return {id, nombre: id.split(":").pop(), zona: "fabrica", orden: 0,
          tamano: 4, estado: "activo", saldo_mm: 0, gasto_ciclo_mm: 0,
          ventas_ventana_mm: 0, eficiencia_pormil: null, actividad: 1,
          trabajos: [], compuertas: 0, x: 0, y: 0, ...extra};
}

function ciudadDePrueba() {
  return {
    edificios: [edi("dep:a", {x: -120, y: 0}),
                edi("dep:b", {x: 120, y: 40}),
                edi("personal:p", {x: 0, y: -80, zona: "personal"})],
    calles: [{a: "dep:a", b: "dep:b", peso_mm: 1, ancho: 2, tipo: "calle"},
             {a: "dep:a", b: "personal:p", peso_mm: 1, ancho: 1,
              tipo: "cable"}],
    unidades: [{id: "u1", dueno: "dep:a", gastado_mm: 0, hacia: "dep:b"}],
    avisos: [{id: "c1", tipo: "gasto", sobre: "dep:b",
              monedas_en_juego_mm: 1}],
  };
}

test("el fondo se pinta primero y cubre toda la vista", () => {
  const {lienzo, ctx} = montar();
  crearMapa(lienzo).dibujar(ciudadDePrueba(), crearCamara(0, 0, 1));
  const primera = ctx.ops.find(o => o.op === "fillRect");
  assert.deepEqual(
    {x: primera.x, y: primera.y, w: primera.w, h: primera.h},
    {x: 0, y: 0, w: 800, h: 600});
});

test("las calles se dibujan ANTES que los edificios", () => {
  const {lienzo, ctx} = montar();
  crearMapa(lienzo).dibujar(ciudadDePrueba(), crearCamara(0, 0, 1));
  const ultimoTrazo = ctx.ops.map(o => o.op).lastIndexOf("stroke");
  const primerEdificio = ctx.ops.findIndex(o => o.op === "drawImage");
  assert.ok(ultimoTrazo >= 0 && primerEdificio >= 0, "falto algo por dibujar");
  assert.ok(ultimoTrazo < primerEdificio,
            "un edificio quedo tapado por una calle");
});

test("un cable va punteado y una calle no", () => {
  const {lienzo, ctx} = montar();
  crearMapa(lienzo).dibujar(ciudadDePrueba(), crearCamara(0, 0, 1));
  const guiones = ctx.ops.filter(o => o.op === "setLineDash");
  assert.ok(guiones.some(g => g.d.length > 0), "ningun cable punteado");
  assert.ok(guiones.some(g => g.d.length === 0), "ninguna calle continua");
});

test("cada edificio se dibuja donde el hit test lo va a buscar", () => {
  const c = ciudadDePrueba();
  const cam = crearCamara(0, 0, 1);
  const vista = {ancho: 800, alto: 600};
  const {lienzo, ctx} = montar(vista.ancho, vista.alto);
  crearMapa(lienzo).dibujar(c, cam);
  const dibujados = ctx.ops.filter(o => o.op === "drawImage");
  assert.equal(dibujados.length, c.edificios.length);
  const esc = escalaEntera(cam);
  for (const e of c.edificios) {
    const m = medidas(e);
    // la misma cuenta que hace enPunto: base al centro
    const px = (e.x - cam.x) * cam.escala + vista.ancho / 2;
    const py = (e.y - cam.y) * cam.escala + vista.alto / 2;
    const x = Math.round(px - (m.ancho * esc) / 2);
    const y = Math.round(py - m.alto * esc);
    assert.ok(dibujados.some(d => d.x === x && d.y === y),
              `${e.id} no se dibujo en (${x}, ${y})`);
  }
});

test("se pintan de atras hacia adelante", () => {
  const c = ciudadDePrueba();
  const {lienzo, ctx} = montar();
  crearMapa(lienzo).dibujar(c, crearCamara(0, 0, 1));
  const ys = ctx.ops.filter(o => o.op === "drawImage").map(o => o.y);
  const esperado = ordenDePintado(c.edificios).map(e => e.id);
  assert.deepEqual(esperado, ["personal:p", "dep:a", "dep:b"]);
  for (let i = 1; i < ys.length; i++) {
    assert.ok(ys[i] >= ys[i - 1], "el orden de pintado se invirtio");
  }
});

test("un edificio fuera de pantalla no se dibuja", () => {
  const c = ciudadDePrueba();
  c.edificios.push(edi("dep:lejos", {x: 90_000, y: 90_000}));
  const {lienzo, ctx} = montar();
  crearMapa(lienzo).dibujar(c, crearCamara(0, 0, 1));
  assert.equal(ctx.ops.filter(o => o.op === "drawImage").length, 3,
               "se dibujo el que estaba lejos");
});

test("el sprite se rasteriza una sola vez y despues se copia", () => {
  const c = ciudadDePrueba();
  const {lienzo, creados} = montar();
  const mapa = crearMapa(lienzo);
  const cam = crearCamara(0, 0, 1);
  mapa.dibujar(c, cam);
  const tras_uno = creados.length;
  assert.equal(tras_uno, c.edificios.length, "no rasterizo cada edificio");
  for (let i = 0; i < 20; i++) mapa.dibujar(c, cam);
  assert.equal(creados.length, tras_uno,
               `el cache no sirvio: ${creados.length} rasterizados`);
});

test("cambiar el saldo de un edificio lo vuelve a rasterizar", () => {
  const c = ciudadDePrueba();
  const {lienzo, creados} = montar();
  const mapa = crearMapa(lienzo);
  const cam = crearCamara(0, 0, 1);
  mapa.dibujar(c, cam);
  const antes = creados.length;
  c.edificios[0].tamano = 8;      // el edificio crecio: otro sprite
  mapa.dibujar(c, cam);
  assert.equal(creados.length, antes + 1);
});

test("el lienzo se redimensiona una sola vez si no cambia de tamano", () => {
  const {lienzo, cuantasAsignaciones} = montar();
  const mapa = crearMapa(lienzo);
  const cam = crearCamara(0, 0, 1);
  for (let i = 0; i < 30; i++) mapa.dibujar(ciudadDePrueba(), cam);
  assert.equal(cuantasAsignaciones(), 1,
               "asignar canvas.width borra el lienzo entero en cada cuadro");
});

test("si la ventana cambia de tamano, el lienzo la sigue", () => {
  const {lienzo, cuantasAsignaciones} = montar();
  const mapa = crearMapa(lienzo);
  const cam = crearCamara(0, 0, 1);
  mapa.dibujar(ciudadDePrueba(), cam);
  lienzo.clientWidth = 1200;
  mapa.dibujar(ciudadDePrueba(), cam);
  assert.equal(cuantasAsignaciones(), 2);
  assert.equal(lienzo.width, 1200);
});

test("el devicePixelRatio se redondea a entero", () => {
  const {lienzo} = montar(800, 600, 2.5);
  crearMapa(lienzo).dibujar(ciudadDePrueba(), crearCamara(0, 0, 1));
  assert.equal(lienzo.width, 800 * 3);   // 2,5 redondea a 3, no queda en 2,5
});

test("el edificio resaltado lleva su marco y los demas no", () => {
  const {lienzo, ctx} = montar();
  crearMapa(lienzo).dibujar(ciudadDePrueba(), crearCamara(0, 0, 1), "dep:b");
  assert.equal(ctx.ops.filter(o => o.op === "strokeRect").length, 1);
});

test("un edificio con compuertas pendientes lleva su marca", () => {
  const c = ciudadDePrueba();
  c.avisos.push({id: "c2", tipo: "gasto", sobre: "dep:b",
                 monedas_en_juego_mm: 1});
  const {lienzo, ctx} = montar();
  crearMapa(lienzo).dibujar(c, crearCamara(0, 0, 1));
  const {avisosPorId} = indice(c);
  assert.equal(avisosPorId.get("dep:b"), 2);
  // fondo + dos marcas de aviso + la unidad
  assert.equal(ctx.ops.filter(o => o.op === "fillRect").length, 4);
});

test("una ciudad vacia se dibuja sin romper nada", () => {
  const {lienzo, ctx} = montar();
  const vacia = {edificios: [], calles: [], unidades: [], avisos: []};
  crearMapa(lienzo).dibujar(vacia, crearCamara(0, 0, 1));
  assert.equal(ctx.ops.filter(o => o.op === "drawImage").length, 0);
  assert.ok(ctx.ops.some(o => o.op === "fillRect"), "ni el fondo se pinto");
});

test("la vista informa el tamano en pixeles de CSS", () => {
  const {lienzo} = montar(1024, 768, 2);
  assert.deepEqual(crearMapa(lienzo).vista(), {ancho: 1024, alto: 768});
  assert.equal(centroDe({x: 5, y: 7}).x, 5);
});
