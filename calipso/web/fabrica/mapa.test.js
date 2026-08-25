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
