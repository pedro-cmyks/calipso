/**
 * pulso.test.js — El reductor de la capa viva.
 *
 * El servidor manda eventos sueltos; el cliente arma con eso el plantel de
 * cada departamento. Se testea el reductor entero sin abrir un socket,
 * igual que chat.test.js hace con el protocolo del chat.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {aplicarEvento, crearPulso, empleadosDe, estadoInicial,
        estadoVisible} from "./pulso.js";

function ev(evento, campos = {}, seq = 1, ts = 1000) {
  return {seq, ts, agente_id: "a1", departamento: "dep:atlas", trabajo: null,
          rol: "scout", modelo: "sonnet", evento, ...campos};
}

test("el inicio abre un escritorio en su departamento", () => {
  const e = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  const empleados = empleadosDe(e, "dep:atlas");
  assert.equal(empleados.length, 1);
  assert.equal(empleados[0].rol, "scout");
  assert.equal(empleados[0].modelo, "sonnet");
  assert.equal(empleados[0].estado, "esperando");
  assert.deepEqual(empleadosDe(e, "dep:mercado"), []);
});

test("el reductor no muta lo que recibe", () => {
  const antes = estadoInicial();
  const despues = aplicarEvento(antes, ev("inicio"), 5000);
  assert.notEqual(antes, despues);
  assert.deepEqual(empleadosDe(antes, "dep:atlas"), []);
});

test("el razonamiento se acumula, no se reemplaza", () => {
  let e = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  e = aplicarEvento(e, ev("razonando", {texto: "mirando "}, 2), 5001);
  e = aplicarEvento(e, ev("razonando", {texto: "el libro"}, 3), 5002);
  const empleado = empleadosDe(e, "dep:atlas")[0];
  assert.equal(empleado.texto, "mirando el libro");
  assert.equal(empleado.estado, "razonando");
});

test("los tokens son el ultimo acumulado, no la suma", () => {
  let e = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  e = aplicarEvento(e, ev("tokens", {tokens_in: 100, tokens_out: 10,
                                     costo_mm: 5}, 2), 5001);
  e = aplicarEvento(e, ev("tokens", {tokens_in: 300, tokens_out: 40,
                                     costo_mm: 17}, 3), 5002);
  const empleado = empleadosDe(e, "dep:atlas")[0];
  assert.equal(empleado.tokens_in, 300);
  assert.equal(empleado.costo_mm, 17);
});

test("el fin libera el escritorio y guarda el rastro", () => {
  let e = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  e = aplicarEvento(e, ev("diff", {ruta: "a.py", diff: "- x\n+ y"}, 2), 5001);
  e = aplicarEvento(e, ev("fin", {runtime_ms: 1500, resultado: "ok"}, 3), 5002);
  const empleado = empleadosDe(e, "dep:atlas")[0];
  assert.equal(empleado.estado, "liberado");
  assert.equal(empleado.runtime_ms, 1500);
  // ver que el departamento SOLTO gente es tan informativo como verlo
  // contratar: el rastro del que se fue no se borra
  assert.deepEqual(empleado.diff, {ruta: "a.py", diff: "- x\n+ y"});
});

test("el que dejo de publicar se ve inactivo, el liberado no", () => {
  let e = aplicarEvento(estadoInicial(), ev("razonando", {texto: "x"}), 5000);
  const vivo = empleadosDe(e, "dep:atlas")[0];
  assert.equal(estadoVisible(vivo, 5000 + 599_000), "razonando");
  assert.equal(estadoVisible(vivo, 5000 + 601_000), "inactivo");
  e = aplicarEvento(e, ev("fin", {runtime_ms: 1, resultado: "ok"}, 2), 5001);
  const suelto = empleadosDe(e, "dep:atlas")[0];
  assert.equal(estadoVisible(suelto, 5000 + 9_999_000), "liberado");
});

test("dos agentes del mismo departamento son dos escritorios", () => {
  let e = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  e = aplicarEvento(e, ev("inicio", {agente_id: "a2", rol: "copista"}, 2),
                    5001);
  const empleados = empleadosDe(e, "dep:atlas");
  assert.deepEqual(empleados.map(x => x.agente_id), ["a2", "a1"]);
});

test("el foco se guarda con su seq para que no vuele dos veces", () => {
  let e = aplicarEvento(estadoInicial(),
                        {seq: 7, ts: 1, agente_id: null, evento: "foco",
                         departamento: "dep:atlas"}, 5000);
  assert.deepEqual(e.foco, {departamento: "dep:atlas", seq: 7});
  // un evento cualquiera despues no borra el foco ni le cambia el seq
  e = aplicarEvento(e, ev("inicio", {}, 8), 5001);
  assert.deepEqual(e.foco, {departamento: "dep:atlas", seq: 7});
});

test("el latido y lo desconocido no rompen ni ensucian el estado", () => {
  const base = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  assert.equal(aplicarEvento(base, {evento: "latido", seq: 9}, 5001), base);
  assert.equal(aplicarEvento(base, {evento: "bailando", seq: 9}, 5001), base);
  assert.equal(aplicarEvento(base, null, 5001), base);
});

test("un evento sin departamento no cuelga de ningun escritorio", () => {
  // el turno de chat sin edificio tocado publica igual: se ve en el flujo
  // pero no tiene donde sentarse
  const e = aplicarEvento(estadoInicial(),
                          ev("inicio", {departamento: null}), 5000);
  assert.deepEqual(Object.keys(e.empleados), []);
});

test("un evento repetido no duplica el texto", () => {
  let e = aplicarEvento(estadoInicial(), ev("inicio", {}, 1, 1000), 5000);
  e = aplicarEvento(e, ev("razonando", {texto: "hola Pedro"}, 2, 1001), 5001);
  // el servidor arranca CADA conexion con el cursor en cero, asi que toda
  // reconexion reproduce el anillo entero. Sin descartar por seq, el texto
  // del turno se pegaba a si mismo: "hola Pedrohola Pedro"
  e = aplicarEvento(e, ev("razonando", {texto: "hola Pedro"}, 2, 1001), 5002);
  assert.equal(empleadosDe(e, "dep:atlas")[0].texto, "hola Pedro");
});

test("reproducir el anillo entero no cambia nada", () => {
  const anillo = [ev("inicio", {}, 1, 1000),
                  ev("razonando", {texto: "hola "}, 2, 1001),
                  ev("razonando", {texto: "Pedro"}, 3, 1002),
                  ev("tokens", {tokens_in: 9, tokens_out: 3}, 4, 1003)];
  let e = estadoInicial();
  for (const x of anillo) e = aplicarEvento(e, x, 5000);
  let repetido = e;
  for (const x of anillo) repetido = aplicarEvento(repetido, x, 6000);
  assert.equal(repetido, e, "la reproduccion del anillo toco el estado");
  assert.equal(empleadosDe(repetido, "dep:atlas")[0].texto, "hola Pedro");
});

test("un seq que retrocede resetea: el servidor se reinicio", () => {
  let e = aplicarEvento(estadoInicial(), ev("inicio", {}, 40, 1000), 5000);
  e = aplicarEvento(e, ev("razonando", {texto: "hola Pedro"}, 41, 1001), 5001);
  // el contador del servidor vuelve a uno; el reloj no. Un numero viejo con
  // un `ts` nuevo es lo unico que distingue el arranque de una reproduccion,
  // y sin distinguirlo el cliente descartaria TODO lo que publique el
  // servidor nuevo hasta que su contador pase al viejo
  e = aplicarEvento(e, ev("inicio", {agente_id: "a9"}, 1, 2000), 6000);
  assert.deepEqual(empleadosDe(e, "dep:atlas").map(x => x.agente_id), ["a9"]);
  assert.equal(e.seq, 1);
});

test("el socket se engancha a /ws/mapa y reconecta cuando se cae", () => {
  const abiertos = [];
  class WSFalso {
    static OPEN = 1;
    constructor(url) {
      this.url = url;
      this.oyentes = new Map();
      abiertos.push(this);
    }
    addEventListener(tipo, f) {
      if (!this.oyentes.has(tipo)) this.oyentes.set(tipo, []);
      this.oyentes.get(tipo).push(f);
    }
    emitir(tipo, ev) { for (const f of this.oyentes.get(tipo) || []) f(ev); }
    dice(dato) { this.emitir("message", {data: JSON.stringify(dato)}); }
    close() {}
  }
  // se guardan y se restauran: si no, este es el ultimo test del archivo y
  // parece inofensivo, pero es una trampa para el que agregue otro debajo
  const ubicacionOriginal = globalThis.location;
  const setTimeoutOriginal = globalThis.setTimeout;
  globalThis.location = {protocol: "http:", host: "127.0.0.1:8137"};
  const vistos = [];
  const reintentos = [];
  globalThis.setTimeout = f => { reintentos.push(f); return 0; };

  try {
    crearPulso(e => vistos.push(e), WSFalso, () => 5000);
    assert.ok(abiertos[0].url.endsWith("/ws/mapa"), abiertos[0].url);
    // el estado inicial se pinta ANTES de conectar: si no, la interfaz se ve
    // conectada hasta el primer evento
    assert.equal(vistos[0].conectado, false);

    abiertos[0].emitir("open", {});
    assert.equal(vistos.at(-1).conectado, true);
    abiertos[0].dice(ev("inicio"));
    assert.equal(empleadosDe(vistos.at(-1), "dep:atlas").length, 1);

    abiertos[0].emitir("close", {});
    assert.equal(vistos.at(-1).conectado, false);
    assert.equal(reintentos.length, 1, "no se programo la reconexion");
    reintentos[0]();
    assert.equal(abiertos.length, 2);
    // y lo que ya sabia no se pierde: el mapa no se vacia porque se corto el
    // socket (el pulso es efimero, pero no amnesico)
    assert.equal(empleadosDe(vistos.at(-1), "dep:atlas").length, 1);
  } finally {
    globalThis.location = ubicacionOriginal;
    globalThis.setTimeout = setTimeoutOriginal;
  }
});
