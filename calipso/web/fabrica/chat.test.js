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
