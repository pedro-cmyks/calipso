import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDeFreno} from "./freno.js";

const LIBRE = {nombre: "atlas", propuestas_propias: 1, freno_pedir: null};

test("un departamento que puede pedir no dibuja ningun aviso", () => {
  assert.equal(textoDeFreno(LIBRE, 3), "");
});

test("null o undefined no revientan", () => {
  assert.equal(textoDeFreno(null, 3), "");
  assert.equal(textoDeFreno(undefined, 3), "");
});

test("el freno del pre-seed se pinta con las palabras del servidor", () => {
  const html = textoDeFreno(
    {...LIBRE, freno_pedir: "el techo de la ventana es 60000 mm y entre lo " +
                            "financiado (0) y lo pedido en pie (60000) ya van " +
                            "60000: que Pedro suba la perilla"}, 3);
  assert.match(html, /class="aviso freno"/);
  assert.match(html, /no puede pedir su ronda pre-seed/);
  // el texto del servidor entero, no un resumen que se despegue de el
  assert.match(html, /pedido en pie \(60000\)/);
  assert.match(html, /suba la perilla/);
});

test("la bandeja llena se dice aparte, porque tapa proponer Y pedir", () => {
  const html = textoDeFreno({...LIBRE, propuestas_propias: 3}, 3);
  assert.match(html, /no puede proponer ni pedir/);
  assert.match(html, /3 de 3 propuestas en pie/);
  // y nombra las tres salidas, incluida la que no pide un gesto de Pedro
  assert.match(html, /financiando o descartando/);
  assert.match(html, /sale de la ventana/);
});

test("con los dos frenos a la vez se dicen los dos, no el primero", () => {
  const html = textoDeFreno(
    {...LIBRE, propuestas_propias: 4, freno_pedir: "sin techo de pre-seed"}, 3);
  assert.match(html, /no puede proponer ni pedir/);
  assert.match(html, /sin techo de pre-seed/);
  // dos renglones: son dos gestos distintos de Pedro y elegir uno solo lo
  // dejaria arreglando la mitad
  assert.equal((html.match(/<div>/g) || []).length, 2);
});

test("sin el techo de propuestas (respuesta vieja) no inventa el aviso", () => {
  // mejor callarse que decirle a Pedro que un departamento esta trabado
  // comparando contra un techo que no sabemos: es la misma regla que
  // `alcanza` en mesa.js sigue con el saldo del tesoro
  assert.equal(textoDeFreno({...LIBRE, propuestas_propias: 9}, undefined), "");
  assert.equal(textoDeFreno({...LIBRE, propuestas_propias: 9}, 0), "");
});

test("el texto del servidor pasa por escapar()", () => {
  const html = textoDeFreno(
    {...LIBRE, freno_pedir: "<img src=x onerror=alert(1)>"}, 3);
  assert.ok(!html.includes("<img"), "inyecto marcado crudo");
  assert.match(html, /&lt;img/);
});
