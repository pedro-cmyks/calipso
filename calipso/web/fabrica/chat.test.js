import test from "node:test";
import assert from "node:assert/strict";

import {estadoInicial, aplicarEvento, paquete, crearChat,
        turnosDeHistorial, textoDeAbismo} from "./chat.js";
import {textoDeCosto} from "./paneles.js";

const aplicar = (eventos, e0 = estadoInicial()) =>
  eventos.reduce((e, ev) => aplicarEvento(e, ev), e0);

// `crearChat` arma la URL con `location`, que solo existe en el navegador.
globalThis.location = {protocol: "http:", host: "localhost.invalido"};

// Un doble minimo del WebSocket del navegador: sin abrir ninguna conexion
// de verdad, solo guarda lo que se le manda y deja que el test dispare
// "open"/"message"/"close" a mano.
class WSFalso {
  constructor(url) {
    this.url = url;
    this.readyState = WSFalso.CONNECTING;
    this.enviados = [];
    this.escuchas = {};
  }
  addEventListener(tipo, fn) {
    (this.escuchas[tipo] ||= []).push(fn);
  }
  send(texto) { this.enviados.push(texto); }
  disparar(tipo, detalle) {
    for (const fn of this.escuchas[tipo] || []) fn(detalle || {});
  }
}
WSFalso.CONNECTING = 0;
WSFalso.OPEN = 1;
WSFalso.CLOSED = 3;

/** Un WSFalso que ya nace en el estado que pida el test. */
function claseConEstado(readyState) {
  return class extends WSFalso {
    constructor(url) { super(url); this.readyState = readyState; }
  };
}

test("el paquete lleva el texto y el chat", () => {
  assert.deepEqual(paquete("hola", "c1"), {text: "hola", chat_id: "c1"});
});

test("un paquete sin chat todavia no inventa uno", () => {
  assert.equal(paquete("hola", null).chat_id, null);
});

test("el paquete lleva el departamento tocado, y solo si hay uno", () => {
  assert.deepEqual(paquete("hola", "c1", "dep:atlas"),
                   {text: "hola", chat_id: "c1", departamento: "dep:atlas"});
  assert.deepEqual(paquete("hola", "c1", null),
                   {text: "hola", chat_id: "c1"});
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

test("el evento cost dice quien pago", () => {
  let e = estadoInicial();
  e = aplicarEvento(e, {type: "cost", cost_usd: 0.004, tokens: 1200,
                        cuenta: "dep:atlas", mm: 270});
  assert.equal(e.cuenta, "dep:atlas");
  assert.equal(e.costo_mm, 270);
  assert.equal(e.tokens, 1200);
  // dos turnos seguidos acumulan las milimonedas, igual que los tokens
  e = aplicarEvento(e, {type: "cost", cost_usd: 0.001, tokens: 300,
                        cuenta: "dep:atlas", mm: 30});
  assert.equal(e.costo_mm, 300);
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

test("el historial de otro chat se convierte en turnos", () => {
  const turnos = turnosDeHistorial([
    {role: "user", text: "hola", ts: "x"},
    {role: "assistant", text: "que tal", meta: {route: "api"}},
  ]);
  assert.deepEqual(turnos, [{quien: "pedro", texto: "hola", abierto: false},
                            {quien: "calipso", texto: "que tal",
                             abierto: false}]);
  assert.deepEqual(turnosDeHistorial(null), []);
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

test("el estado arranca desconectado", () => {
  assert.equal(estadoInicial().conectado, false);
});

test("el reductor no toca la bandera de conectado", () => {
  const e0 = {...estadoInicial(), conectado: true};
  const e = aplicarEvento(e0, {type: "thinking"});
  assert.equal(e.conectado, true);
});

test("enviar no manda nada si el socket todavia no esta abierto", () => {
  const vistos = [];
  const chat = crearChat(estado => { vistos.push(estado); },
                         claseConEstado(WSFalso.CONNECTING));
  const antes = vistos.length;      // el aviso del estado inicial ya paso
  const ok = chat.enviar("hola");
  assert.equal(ok, false);
  assert.equal(chat.estado().turnos.length, 0);
  assert.equal(vistos.length, antes, "no debio avisar un cambio que no paso");
});

test("avisa el estado inicial al construirse, sin esperar al socket", () => {
  // hasta el primer evento del socket nadie mas va a decir que no hay
  // conexion: si el handshake se cuelga sin llegar a cerrarse, el formulario
  // se ve conectado indefinidamente
  const vistos = [];
  crearChat(estado => { vistos.push(estado); },
            claseConEstado(WSFalso.CONNECTING));
  assert.equal(vistos.length, 1, "no aviso el estado inicial");
  assert.equal(vistos[0].conectado, false);
  assert.deepEqual(vistos[0].turnos, []);
});

test("si el constructor del socket tira, la reconexion sigue viva", t => {
  // Adentro del setTimeout del reintento no hay nadie que agarre la
  // excepcion: escapa del timer y la cadena de reconexion muere en silencio,
  // para siempre. Los timers van simulados porque la cadena es infinita a
  // proposito y si no el proceso del test no terminaria nunca.
  t.mock.timers.enable({apis: ["setTimeout"]});
  let intentos = 0;
  class WSQueTira {
    static OPEN = 1;
    constructor() {
      intentos++;
      throw new Error("SecurityError: la politica del navegador lo bloqueo");
    }
  }
  const vistos = [];
  let chat;
  assert.doesNotThrow(() => {
    chat = crearChat(estado => { vistos.push(estado); }, WSQueTira);
  }, "crearChat dejo escapar la excepcion del constructor");
  assert.equal(intentos, 1);
  t.mock.timers.tick(2000);
  assert.equal(intentos, 2, "no reintento despues de que el constructor tirara");
  t.mock.timers.tick(2000);
  assert.equal(intentos, 3, "la cadena de reconexion se corto en el segundo");
  assert.equal(chat.estado().conectado, false);
  assert.equal(chat.enviar("hola"), false, "creyo que podia mandar sin socket");
  assert.ok(vistos.length >= 1, "no aviso que no hay conexion");
});

test("enviar manda y devuelve true cuando el socket esta abierto", () => {
  let ultimoWs;
  class WSAbierto extends WSFalso {
    constructor(url) { super(url); ultimoWs = this; this.readyState = WSFalso.OPEN; }
  }
  const chat = crearChat(() => {}, WSAbierto);
  const ok = chat.enviar("hola Calipso");
  assert.equal(ok, true);
  assert.equal(chat.estado().turnos.length, 1);
  assert.equal(chat.estado().turnos[0].texto, "hola Calipso");
  assert.equal(ultimoWs.enviados.length, 1);
  assert.deepEqual(JSON.parse(ultimoWs.enviados[0]), paquete("hola Calipso", null));
});

test("un texto en blanco no manda nada aunque el socket este abierto", () => {
  const chat = crearChat(() => {}, claseConEstado(WSFalso.OPEN));
  const ok = chat.enviar("   ");
  assert.equal(ok, false);
  assert.equal(chat.estado().turnos.length, 0);
});

test("abrir el socket prende la bandera de conectado", () => {
  let ultimoWs;
  class WSCapturado extends WSFalso {
    constructor(url) { super(url); ultimoWs = this; }
  }
  let visto = null;
  const chat = crearChat(estado => { visto = estado; }, WSCapturado);
  ultimoWs.disparar("open");
  assert.equal(chat.estado().conectado, true);
  assert.equal(visto.conectado, true);
});

test("el cierre del socket apaga la bandera de conectado, sin tocar los turnos", () => {
  let ultimoWs;
  class WSCapturado extends WSFalso {
    constructor(url) { super(url); ultimoWs = this; this.readyState = WSFalso.OPEN; }
  }
  const propioSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = () => 0;   // no reintentar de verdad en el test
  try {
    const chat = crearChat(() => {}, WSCapturado);
    chat.enviar("hola");
    ultimoWs.disparar("close");
    assert.equal(chat.estado().conectado, false);
    assert.equal(chat.estado().turnos.length, 1, "el cierre no debe borrar la charla");
  } finally {
    globalThis.setTimeout = propioSetTimeout;
  }
});

test("cargar otro chat reemplaza los turnos y sube la epoca", () => {
  // la epoca es lo que le dice a app.js que tiene que rehacer los nodos:
  // sin eso, los turnos del chat viejo quedan arriba de los del nuevo
  const vistos = [];
  const chat = crearChat(e => vistos.push(e), WSFalso);
  chat.cargar({id: "c9", messages: [{role: "user", text: "viejo"}]});
  const estado = vistos.at(-1);
  assert.equal(estado.chatId, "c9");
  assert.equal(estado.turnos.length, 1);
  assert.ok(estado.epoca > estadoInicial().epoca);
});

// El socket de /ws/chat es uno solo y persistente: si Pedro cambia de chat
// mientras Calipso le esta respondiendo al anterior, el resto de ese stream
// (chunk/done/meta/cost/chat) sigue llegando por la misma conexion. Sin
// filtrarlo se pega sobre el historial que `cargar` acaba de poner.
function wsAbierto() {
  let ultimoWs;
  class WSCapturado extends WSFalso {
    constructor(url) { super(url); ultimoWs = this; this.readyState = WSFalso.OPEN; }
  }
  const chat = crearChat(() => {}, WSCapturado);
  return {chat, disparar: (ev) => ultimoWs.disparar("message", {data: JSON.stringify(ev)})};
}

test("un chunk que llega despues de cargar otro chat no toca los turnos cargados", () => {
  const {chat, disparar} = wsAbierto();
  disparar({type: "thinking"});
  disparar({type: "chunk", text: "empezando"});
  chat.cargar({id: "c9", messages: [{role: "user", text: "viejo"}]});
  const antes = chat.estado().turnos;
  // el resto del turno que quedo respondiendo sigue llegando por el mismo
  // socket, y no tiene que pegarse sobre el historial recien cargado
  disparar({type: "chunk", text: "resto del turno viejo"});
  disparar({type: "done"});
  assert.deepEqual(chat.estado().turnos, antes);
});

test("un thinking despues de cargar levanta la marca y el chunk siguiente se pinta", () => {
  const {chat, disparar} = wsAbierto();
  chat.cargar({id: "c9", messages: [{role: "user", text: "viejo"}]});
  disparar({type: "chunk", text: "resto del turno viejo"});   // se descarta
  disparar({type: "thinking"});                                // turno nuevo
  disparar({type: "chunk", text: "hola de nuevo"});
  assert.equal(chat.estado().turnos.length, 2,
              "el turno nuevo se agrego sin mezclarse con el viejo");
  assert.equal(chat.estado().turnos.at(-1).texto, "hola de nuevo");
});

test("la barra de costo se vacia al cargar otro chat", () => {
  const {chat, disparar} = wsAbierto();
  disparar({type: "meta", route: "api", model: "sonnet"});
  disparar({type: "cost", tokens: 500, cost_usd: 0.01,
            cuenta: "dep:atlas", mm: 50});
  assert.notEqual(textoDeCosto(chat.estado()), "", "no habia costo que vaciar");
  chat.cargar({id: "c9", messages: []});
  assert.equal(textoDeCosto(chat.estado()), "");
});

test("un error del chat anterior no agrega ningun turno tras cargar", () => {
  // el servidor puede mandar un error EN MEDIO de un turno normal (ruta
  // local, la generacion tira sin ruta de fallback) y seguir con cost/done
  // despues: no es solo el caso de la conexion cortada
  const {chat, disparar} = wsAbierto();
  chat.cargar({id: "c9", messages: [{role: "user", text: "viejo"}]});
  const antes = chat.estado().turnos;
  disparar({type: "error", text: "se cayo la ruta local"});
  assert.deepEqual(chat.estado().turnos, antes,
                   "el error del chat viejo se pego sobre el historial nuevo");
});

test("un error de un turno nuevo si se pinta, porque llega despues de su thinking", () => {
  const {chat, disparar} = wsAbierto();
  chat.cargar({id: "c9", messages: [{role: "user", text: "viejo"}]});
  disparar({type: "thinking"});           // arranca el turno nuevo de verdad
  disparar({type: "error", text: "se cayo de nuevo"});
  const ultimo = chat.estado().turnos.at(-1);
  assert.equal(ultimo.quien, "error");
  assert.ok(ultimo.texto.includes("se cayo de nuevo"));
});

// --- El abismo: un renglon hermano del pensando, nunca un turno ---------

test("el pondering del abismo no agrega turnos y el chunk siguiente sigue en el mismo", () => {
  const e = aplicar([{type: "thinking"}, {type: "chunk", text: "Dejame ver "},
                     {type: "abismo", fase: "pondering", fuente: "chats",
                      verbo: "buscando en tus chats"},
                     {type: "chunk", text: "y sigo"}]);
  assert.equal(e.turnos.length, 1);
  assert.equal(e.turnos[0].texto, "Dejame ver y sigo");
  assert.equal(e.abismo.fase, "pondering");
  assert.equal(e.abismo.fuente, "chats");
  assert.equal(e.abismo.n, 1);
});

test("pescado reemplaza el pondering y done lo apaga", () => {
  let e = aplicar([{type: "thinking"},
                   {type: "abismo", fase: "pondering", fuente: "memoria"},
                   {type: "abismo", fase: "pescado", fuente: "memoria", tamano: 120,
                    viaje: {destino: "local"}}]);
  assert.deepEqual({fase: e.abismo.fase, tamano: e.abismo.tamano, n: e.abismo.n},
                   {fase: "pescado", tamano: 120, n: 1});
  e = aplicarEvento(e, {type: "done"});
  assert.equal(e.abismo, null);
});

test("un thinking nuevo apaga un pondering colgado del turno anterior", () => {
  // un turno que murio sin done (socket caido) no deja el renglon vivo
  // hasta el done del turno siguiente: el thinking del turno nuevo lo apaga
  const e = aplicar([{type: "thinking"}, {type: "abismo", fase: "pondering", fuente: "chats"},
                     {type: "thinking"}]);
  assert.equal(e.abismo, null);
});

test("la segunda consulta del mismo turno sube n, y error y cargar apagan", () => {
  let e = aplicar([{type: "thinking"},
                   {type: "abismo", fase: "pondering", fuente: "chats"},
                   {type: "abismo", fase: "pescado", fuente: "chats", tamano: 5},
                   {type: "abismo", fase: "pondering", fuente: "proyecto"}]);
  assert.equal(e.abismo.n, 2);
  assert.equal(aplicarEvento(e, {type: "error", text: "x"}).abismo, null);
  const vistos = [];
  const chat = crearChat(x => vistos.push(x), WSFalso);
  chat.cargar({id: "c9", messages: []});
  assert.equal(vistos.at(-1).abismo, null);
});

test("una fase inventada del abismo no cambia nada", () => {
  const antes = aplicar([{type: "thinking"}]);
  const despues = aplicarEvento(antes, {type: "abismo", fase: "bailando", fuente: "chats"});
  assert.equal(despues.abismo, antes.abismo);
});

test("un abismo que llega despues de cargar otro chat se descarta", () => {
  const {chat, disparar} = wsAbierto();
  disparar({type: "thinking"});
  chat.cargar({id: "c9", messages: [{role: "user", text: "viejo"}]});
  disparar({type: "abismo", fase: "pondering", fuente: "chats"});
  assert.equal(chat.estado().abismo, null);
});

test("el texto del renglon del abismo", () => {
  assert.equal(textoDeAbismo({fase: "pondering", fuente: "chats", verbo: ""}, 3),
               "buscando en tus chats... 3 s");
  assert.equal(textoDeAbismo({fase: "pondering", fuente: "chats", verbo: "hurgando"}, 0),
               "hurgando... 0 s");
  assert.equal(textoDeAbismo({fase: "pescado", fuente: "memoria", tamano: 120,
                              viaje: {destino: "local"}}, 0),
               "del abismo: memoria (120 chars)");
  assert.equal(textoDeAbismo({fase: "pescado", fuente: "chats", tamano: 12,
                              viaje: {destino: "nube", tapados: [{marcador: "[ID_1]", tipo: "identidad"}]}}, 0),
               "del abismo: chats (12 chars, viajo tapado a la nube: [ID_1])");
  assert.equal(textoDeAbismo({fase: "fallo", fuente: "chats", motivo: "solo_hondo"}, 0),
               "el abismo (chats): solo habia hondo");
});

// --- los canarios: la marca vive en el turno de Calipso, no aparte ------

const VEREDICTO = {anclaje: {aplica: true, aplica_por: ["senal:te conte"], hechos: [],
                             sin_anclaje: [{tipo: "recuerdo", texto: "Recuerdo que te conte"}],
                             anclado_solo_en_calipso: 0, tapado: false},
                   degeneracion: [], ventana: []};

test("canario entre chunk y done se guarda en el ultimo turno de Calipso y no agrega turnos", () => {
  const e = aplicar([{type: "thinking"}, {type: "chunk", text: "Recuerdo que te conte"},
                     {type: "canario", ...VEREDICTO}, {type: "done"}]);
  assert.equal(e.turnos.length, 1);
  assert.equal(e.turnos[0].texto, "Recuerdo que te conte");
  assert.equal(e.turnos[0].abierto, false);
  assert.deepEqual(e.turnos[0].canarios, VEREDICTO);      // sin el `type`
});

test("un canario sin turno abierto de Calipso no toca nada", () => {
  const e0 = aplicar([{type: "thinking"}]);
  assert.deepEqual(aplicar([{type: "canario", ...VEREDICTO}], e0).turnos, e0.turnos);
  const conError = aplicar([{type: "thinking"}, {type: "error", text: "x"}]);
  assert.deepEqual(aplicar([{type: "canario", ...VEREDICTO}], conError).turnos, conError.turnos);
});

test("un canario que llega despues de cargar otro chat se descarta", () => {
  const {chat, disparar} = wsAbierto();
  disparar({type: "thinking"});
  disparar({type: "chunk", text: "empezando"});
  chat.cargar({id: "c9", messages: [{role: "user", text: "viejo"}, {role: "assistant", text: "resp"}]});
  const antes = chat.estado().turnos;
  disparar({type: "canario", ...VEREDICTO});
  disparar({type: "done"});
  assert.deepEqual(chat.estado().turnos, antes);
});

test("el historial cargado lleva meta.canarios al turno, y solo cuando lo trae", () => {
  const turnos = turnosDeHistorial([
    {role: "user", text: "hola"},
    {role: "assistant", text: "que tal", meta: {route: "local", canarios: VEREDICTO}},
    {role: "assistant", text: "otra", meta: {route: "local"}},
  ]);
  assert.deepEqual(turnos[0], {quien: "pedro", texto: "hola", abierto: false});
  assert.deepEqual(turnos[1].canarios, VEREDICTO);
  assert.deepEqual(turnos[2], {quien: "calipso", texto: "otra", abierto: false});
});
