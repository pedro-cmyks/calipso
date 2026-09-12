import test from "node:test";
import assert from "node:assert/strict";

import {textosDeCarga} from "./carga.js";

const MARCA = {nivel: "cargada", mem_disponible_mb: 480, motivo: "mem 480 < 5746",
               ruta: "subscription", gesto: null,
               aviso: "maquina cargada (480 MB libres): contesto por Mariana"};

test("sin marca no hay texto", () => {
  assert.deepEqual(textosDeCarga(null), []);
  assert.deepEqual(textosDeCarga(undefined), []);
  assert.deepEqual(textosDeCarga({}), []);
  assert.deepEqual(textosDeCarga("cargada"), []);
});

test("la marca muestra el aviso del server y los numeros en el detalle", () => {
  const [m] = textosDeCarga(MARCA);
  assert.equal(m.texto, "maquina cargada (480 MB libres): contesto por Mariana");
  assert.equal(m.detalle, "nivel cargada, 480 MB libres, motivo: mem 480 < 5746, ruta: subscription");
  const [g] = textosDeCarga({...MARCA, ruta: "local", gesto: "/local",
                             aviso: "maquina cargada (480 MB libres): /local es local, puede tardar o fallar"});
  assert.equal(g.texto, "maquina cargada (480 MB libres): /local es local, puede tardar o fallar");
  assert.match(g.detalle, /gesto: \/local$/);
  assert.equal(textosDeCarga({type: "carga", ...MARCA})[0].texto, m.texto);   // el `type` sobrante no molesta
});

test("sin aviso compone uno minimo desde nivel y memoria", () => {
  assert.deepEqual(textosDeCarga({nivel: "cargada", mem_disponible_mb: 480}),
                   [{texto: "maquina cargada (480 MB libres)", detalle: "nivel cargada, 480 MB libres"}]);
  assert.deepEqual(textosDeCarga({nivel: "justa"}), [{texto: "maquina justa", detalle: "nivel justa"}]);
});
