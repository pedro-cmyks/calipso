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
  // 2000 de ancho contra 800 de vista aprieta (0,4) mas que 100 de alto
  // contra 600 (6). El ancho se elige a proposito para que el encaje caiga
  // por ENCIMA de ESCALA_MIN: si cayera por debajo, el recorte decidiria en
  // lugar del eje y el test dejaria de medir lo que dice medir.
  const e = encuadrar([{x: 0, y: 0}, {x: 2000, y: 100}], VISTA, 0);
  assert.ok(e.escala > ESCALA_MIN, `el recorte se comio la prueba: ${e.escala}`);
  assert.ok(e.escala <= VISTA.ancho / 2000 + 1e-9, `escala ${e.escala}`);
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
