/**
 * interior.test.js — La aritmetica de entrar a un departamento.
 *
 * El fundido y las plazas son numeros puros: lo unico que el navegador
 * agrega es pintarlos.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {crearCamara} from "./camara.js";
import {UMBRAL, escritorioEnPunto, opacidadDeTecho, plazas} from "./interior.js";
import {ALTO_PISO, PROF, medidas} from "./sprites.js";

const EDIFICIO = {id: "dep:atlas", nombre: "atlas", zona: "fabrica",
                  estado: "activo", tamano: 3, actividad: 2, x: 0, y: 0};

test("el techo se desvanece cruzando el umbral, no de golpe", () => {
  assert.equal(opacidadDeTecho(UMBRAL - 1.5), 1);     // lejos: techo entero
  assert.equal(opacidadDeTecho(UMBRAL + 1), 0);       // adentro: sin techo
  const medio = opacidadDeTecho(UMBRAL - 0.4);
  assert.ok(medio > 0 && medio < 1, `fundido roto: ${medio}`);
  // y es monotono: acercarse nunca vuelve a tapar el interior
  assert.ok(opacidadDeTecho(UMBRAL - 0.2) < opacidadDeTecho(UMBRAL - 0.6));
});

test("hay una plaza por ventana y estan adentro del sprite", () => {
  const m = medidas(EDIFICIO);
  const p = plazas(EDIFICIO);
  assert.equal(p.length, 3 * 3);        // tres pisos, tres columnas
  for (const {x, y} of p) {
    assert.ok(x >= 0 && x < m.ancho, `x fuera del sprite: ${x}`);
    assert.ok(y >= PROF && y < m.alto, `y fuera del sprite: ${y}`);
  }
  // de arriba hacia abajo: el primer escritorio es el del piso mas alto
  assert.ok(p[0].y < p.at(-1).y);
  // y no hay dos en el mismo lugar
  assert.equal(new Set(p.map(q => `${q.x},${q.y}`)).size, p.length);
});

test("un edificio mas alto tiene mas plazas", () => {
  assert.ok(plazas({...EDIFICIO, tamano: 6}).length >
            plazas({...EDIFICIO, tamano: 2}).length);
});

test("el escritorio bajo el dedo es el que se toco", () => {
  const cam = crearCamara(0, 0, 4);
  const vista = {ancho: 400, alto: 300};
  const p = plazas(EDIFICIO);
  // el centro de la plaza 4, llevado a pantalla con la misma cuenta que
  // usa el dibujo, tiene que devolver 4 y no su vecina
  const m = medidas(EDIFICIO);
  const esc = Math.round(cam.escala);
  const x0 = vista.ancho / 2 - (m.ancho * esc) / 2;
  const y0 = vista.alto / 2 - m.alto * esc;
  const px = x0 + (p[4].x + 1.5) * esc;
  const py = y0 + (p[4].y + 1) * esc;
  assert.equal(escritorioEnPunto(EDIFICIO, cam, vista, px, py), 4);
  // afuera del edificio no hay escritorio
  assert.equal(escritorioEnPunto(EDIFICIO, cam, vista, 5, 5), null);
});
