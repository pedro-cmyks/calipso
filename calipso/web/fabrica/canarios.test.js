import test from "node:test";
import assert from "node:assert/strict";

import {textosDeCanario, textoDeRecorte} from "./canarios.js";

const limpio = {anclaje: {aplica: false, aplica_por: [], hechos: [], sin_anclaje: [],
                          anclado_solo_en_calipso: 0, tapado: false},
                degeneracion: [], ventana: [{pasada: 1, ruta: "local", estimado: 900, evaluado: 910,
                                             num_ctx: 8192, cabe: true, recorte: [],
                                             no_cabe: false, truncado: false}]};

test("un veredicto limpio no produce ninguna marca", () => {
  assert.deepEqual(textosDeCanario(limpio), []);
  assert.deepEqual(textosDeCanario(null), []);
  assert.deepEqual(textosDeCanario({}), []);
});

test("sin verificar (N) solo cuando aplica, con los hechos en el detalle", () => {
  const sin = [{tipo: "recuerdo", texto: "Recuerdo que te conte sobre una trilogia"},
               {tipo: "accion", accion: "consulto", texto: "Consultando los recuerdos de Pedro..."},
               {tipo: "nombre", texto: "Gabriel Garcia Marquez"}];
  const v = {...limpio, anclaje: {...limpio.anclaje, aplica: true, aplica_por: ["senal:te conte"], sin_anclaje: sin}};
  const [m] = textosDeCanario(v);
  assert.equal(m.texto, "sin verificar (3)");
  assert.equal(m.detalle, "recuerdo: Recuerdo que te conte sobre una trilogia\n" +
                          "accion: Consultando los recuerdos de Pedro...\nGabriel Garcia Marquez");
  // la medicion corre igual sin aplicar, pero la marca no sale (invariante 5)
  const sinAplicar = {...v, anclaje: {...v.anclaje, aplica: false}};
  assert.deepEqual(textosDeCanario(sinAplicar), []);
});

test("cada senal de degeneracion es una marca 'respuesta rara' con su evidencia", () => {
  const v = {...limpio, degeneracion: [{senal: "fuga_de_reentrada", evidencia: "Segui exactamente desde ahi, sin repetir."},
                                       {senal: "eco_de_episodio", evidencia: "[charla con mariana 2026-08-20]"},
                                       {senal: "inventada"}]};
  assert.deepEqual(textosDeCanario(v).map(m => m.texto),
                   ["respuesta rara: fuga de reentrada", "respuesta rara: eco del molde", "respuesta rara: inventada"]);
  assert.equal(textosDeCanario(v)[0].detalle, "Segui exactamente desde ahi, sin repetir.");
});

test("la ventana: recorte, truncado por pasada y no cupo", () => {
  const v = {...limpio, ventana: [
    {pasada: 1, ruta: "local", estimado: 7000, estimado_sin_recorte: 9000, num_ctx: 8192, cabe: true,
     recorte: ["historial:2", "historial:2", "recuerdo:1"], no_cabe: false, truncado: false, evaluado: 7010},
    {pasada: 2, ruta: "local", estimado: 8100, num_ctx: 8192, cabe: true, recorte: [], no_cabe: false, truncado: true, evaluado: 7900},
  ]};
  assert.deepEqual(textosDeCanario(v).map(m => m.texto), [
    "contexto: se recorto el historial viejo (4 mensajes), recuerdos (1) (pasada 1)",
    "Ollama trunco la pasada 2"]);
  // en api no hay techo: truncado es null (no se juzga) y, aunque viniera
  // true de una version vieja, la marca "Ollama trunco" es solo de local
  const api = {...limpio, ventana: [
    {pasada: 1, ruta: "api", estimado: 900, num_ctx: null, cabe: null, recorte: [], no_cabe: false, truncado: null, evaluado: 10},
    {pasada: 2, ruta: "api", estimado: 900, num_ctx: null, cabe: null, recorte: [], no_cabe: false, truncado: true, evaluado: 10},
  ]};
  assert.deepEqual(textosDeCanario(api), []);
  const noCupo = {...limpio, ventana: [{pasada: 1, estimado: 9000, num_ctx: 8192, cabe: false,
                                        recorte: ["repo", "web"], no_cabe: true, truncado: "sin medicion"}]};
  assert.deepEqual(textosDeCanario(noCupo).map(m => m.texto), ["contexto: no cupo aun recortando"]);
  assert.equal(textoDeRecorte(["historial:2", "repo", "web", "bloque:1"]),
               "el historial viejo (2 mensajes), el brief del repo, los resultados web, un bloque viejo del abismo");
});

test("si el canario no corrio se dice, y nada mas", () => {
  assert.deepEqual(textosDeCanario({error: "TimeoutError", detalle: "", anclaje: null, degeneracion: [], ventana: []}),
                   [{texto: "canario: no corrio (TimeoutError)", detalle: ""}]);
});
