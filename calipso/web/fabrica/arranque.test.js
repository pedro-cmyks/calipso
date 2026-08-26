/**
 * arranque.test.js — Que el mapa arranque aunque la red se cuelgue.
 *
 * `app.js` es el pegamento, y un pegamento que no termina de evaluar deja
 * la pantalla entera muerta. El modo de fallo que fija este archivo no es
 * el rechazo —eso lo cubre un try/catch— sino la DEMORA: una promesa que no
 * resuelve nunca, que es lo que pasa cuando el telefono salta de WiFi a
 * datos. Con un `await` arriba de todo, un solo fetch colgado se lleva
 * puesto el bucle de dibujo, el encuadre y el cartel que deberia explicarlo.
 *
 * Se monta un DOM de mentira con los mismos elementos que declara
 * index.html, igual que `lienzo.test.js` monta un contexto 2D de mentira:
 * no hay jsdom en el repo y no lo va a haber.
 */
import test from "node:test";
import assert from "node:assert/strict";

/** Un contexto 2D que no dibuja nada y anota lo que le piden. */
function contextoFalso() {
  const ops = [];
  const anotar = op => (...a) => ops.push({op, a});
  return {
    ops,
    fillStyle: null, strokeStyle: null, lineWidth: 0,
    imageSmoothingEnabled: true,
    setTransform: anotar("setTransform"), fillRect: anotar("fillRect"),
    strokeRect: anotar("strokeRect"), drawImage: anotar("drawImage"),
    setLineDash: anotar("setLineDash"), beginPath: anotar("beginPath"),
    moveTo: anotar("moveTo"), lineTo: anotar("lineTo"),
    stroke: anotar("stroke"),
  };
}

/** Un nodo con lo poco que `app.js` le toca de verdad. */
function nodo(id, etiqueta = "div") {
  const clases = new Set();
  return {
    id, tagName: etiqueta, dataset: {}, style: {}, className: "",
    textContent: "", innerHTML: "", value: "", placeholder: "",
    offsetWidth: 200, offsetHeight: 110,
    scrollTop: 0, scrollHeight: 0,
    hijos: [], oyentes: new Map(),
    classList: {
      add: c => clases.add(c),
      remove: c => clases.delete(c),
      contains: c => clases.has(c),
      toggle(c, v) {
        const poner = v === undefined ? !clases.has(c) : !!v;
        if (poner) clases.add(c); else clases.delete(c);
        return poner;
      },
    },
    clases,
    addEventListener(tipo, f) {
      if (!this.oyentes.has(tipo)) this.oyentes.set(tipo, []);
      this.oyentes.get(tipo).push(f);
    },
    appendChild(n) { this.hijos.push(n); return n; },
    removeChild(n) {
      const i = this.hijos.indexOf(n);
      if (i < 0) throw new Error("removeChild sobre un nodo que no es hijo");
      this.hijos.splice(i, 1);
      return n;
    },
    querySelectorAll: () => [],
    getBoundingClientRect: () => ({left: 0, top: 0, width: 800, height: 600}),
    setPointerCapture() {}, releasePointerCapture() {},
    hasPointerCapture: () => false,
  };
}

function ciudadDePrueba() {
  const base = {zona: "fabrica", orden: 0, tamano: 4, estado: "activo",
                saldo_mm: 1000, gasto_ciclo_mm: 0, ventas_ventana_mm: 0,
                eficiencia_pormil: 900, actividad: 1, trabajos: [],
                compuertas: 1};
  return {
    edificios: [{...base, id: "dep:a", nombre: "a", x: -60, y: 0},
                {...base, id: "dep:b", nombre: "b", x: 60, y: 30}],
    calles: [{a: "dep:a", b: "dep:b", peso_mm: 1, ancho: 2, tipo: "calle"}],
    unidades: [],
    avisos: [{id: "c1", tipo: "gasto", sobre: "dep:a",
              monedas_en_juego_mm: 5000}],
  };
}

/**
 * Deja el navegador de mentira colgado en `globalThis` y devuelve las
 * anotaciones. `/api/chats` entrega una promesa que NO resuelve nunca; la
 * ciudad contesta normal.
 */
function montarNavegador() {
  const ctx = contextoFalso();
  const canvas = Object.assign(nodo("mapa", "canvas"), {
    clientWidth: 800, clientHeight: 600, getContext: () => ctx,
  });
  let ancho = 0, alto = 0;
  Object.defineProperty(canvas, "width",
                        {get: () => ancho, set: v => { ancho = v; }});
  Object.defineProperty(canvas, "height",
                        {get: () => alto, set: v => { alto = v; }});

  const nodos = new Map([["mapa", canvas]]);
  for (const id of ["app", "panel-chats", "lista-chats", "panel-centro",
                    "conversacion", "entrada", "texto", "panel-mapa",
                    "expandir", "tarjeta", "sin-fabrica", "pestanas",
                    "avisos"]) {
    nodos.set(id, nodo(id));
  }
  const pestanas = [nodo("", "button"), nodo("", "button")];
  pestanas[0].dataset.pestana = "chat";
  pestanas[1].dataset.pestana = "mapa";

  globalThis.document = {
    getElementById: id => nodos.get(id) || null,
    querySelectorAll: sel => (sel === "#pestanas button" ? pestanas : []),
    createElement(etiqueta) {
      if (etiqueta !== "canvas") return nodo("", etiqueta);
      return {width: 0, height: 0, getContext: () => contextoFalso()};
    },
  };
  globalThis.window = {devicePixelRatio: 1, innerWidth: 1400,
                       addEventListener() {}};
  globalThis.location = {protocol: "http:", host: "127.0.0.1:8137"};

  const cuadros = [];
  globalThis.requestAnimationFrame = f => cuadros.push(f);

  // un socket de mentira que se acuerda de sus oyentes, para poder empujarle
  // eventos del /ws/chat sin abrir ninguna conexion
  const sockets = [];
  globalThis.WebSocket = class {
    static OPEN = 1;
    constructor(url) {
      this.url = url;
      this.readyState = 0;
      this.enviados = [];
      this.oyentes = new Map();
      sockets.push(this);
    }
    addEventListener(tipo, f) {
      if (!this.oyentes.has(tipo)) this.oyentes.set(tipo, []);
      this.oyentes.get(tipo).push(f);
    }
    emitir(tipo, ev) { for (const f of this.oyentes.get(tipo) || []) f(ev); }
    dice(evento) { this.emitir("message", {data: JSON.stringify(evento)}); }
    send(d) { this.enviados.push(d); }
    close() {}
  };

  const pedidos = [];
  globalThis.fetch = url => {
    pedidos.push(String(url));
    if (String(url).includes("/api/chats")) return new Promise(() => {});
    return Promise.resolve({ok: true,
                            json: async () => ({activa: true,
                                                ciudad: ciudadDePrueba()})});
  };

  return {ctx, canvas, nodos, pedidos, cuadros, sockets,
          medidaDelLienzo: () => ({ancho, alto})};
}

const nav = montarNavegador();

// La carga va con plazo: si `app.js` volviera a bloquearse en un `await`,
// esta espera no terminaria nunca y el test moriria por timeout del runner
// en vez de decir que fue lo que paso.
const PLAZO = 3000;
let plazo;
const cargado = await Promise.race([
  import("./app.js").then(() => "cargado"),
  new Promise(r => { plazo = setTimeout(() => r("colgado"), PLAZO); }),
]);
// el plazo se apaga apenas gana el import: tiene que sostener el proceso
// mientras corre (si no, el runner muere con un "unsettled top-level await"
// que no explica nada) y no demorar la corrida cuando todo anda bien
clearTimeout(plazo);

test("el modulo termina de evaluar con la lista de chats colgada", () => {
  assert.equal(cargado, "cargado",
               `app.js no termino de evaluar en ${PLAZO} ms: un await del ` +
               "cuerpo del modulo se comio el arranque entero");
});

test("la ciudad se pide aunque la lista de chats no conteste", () => {
  assert.ok(nav.pedidos.some(u => u.includes("/api/mapa/ciudad")),
            "no se pidio la ciudad; solo se pidio " +
            JSON.stringify(nav.pedidos));
});

test("el bucle de dibujo arranca aunque la lista de chats no conteste", () => {
  assert.ok(nav.cuadros.length >= 1,
            "requestAnimationFrame no se llamo ni una vez: el mapa nunca " +
            "empieza a dibujarse");
});

test("el bucle arranca sin esperar a ninguna respuesta", () => {
  // el orden importa: si el primer cuadro se pidiera recien despues de que
  // la ciudad conteste, una ciudad lenta dejaria el lienzo sin dimensionar
  assert.ok(nav.cuadros.length >= 1);
  assert.equal(typeof nav.cuadros[0], "function");
});

test("cuando la ciudad llega, el cuadro siguiente la dibuja", async () => {
  await new Promise(r => setTimeout(r, 0));   // que corra el .then de traer()
  const antes = nav.ctx.ops.length;
  nav.cuadros[nav.cuadros.length - 1](16);
  assert.ok(nav.ctx.ops.length > antes, "el bucle no dibujo nada");
  assert.ok(nav.ctx.ops.some(o => o.op === "drawImage"),
            "no se dibujo ningun edificio");
  const m = nav.medidaDelLienzo();
  assert.deepEqual(m, {ancho: 800, alto: 600},
                   "el lienzo quedo sin dimensionar");
});

test("la barra de avisos se pinta sin la lista de chats", async () => {
  await new Promise(r => setTimeout(r, 0));
  assert.ok(nav.nodos.get("avisos").innerHTML.includes("gasto"),
            "la barra de avisos quedo vacia: " +
            JSON.stringify(nav.nodos.get("avisos").innerHTML));
});

test("la lista de chats colgada queda vacia y no rompe a nadie", () => {
  // sin respuesta no hay nada que pintar, y eso esta bien: lo que no puede
  // pasar es que su ausencia se lleve puesto al resto de la pantalla
  assert.equal(nav.nodos.get("lista-chats").innerHTML, "");
});

// --- El pintado de la conversacion, contra el mismo app.js ya cargado. ---
//
// Lo que se fija aca es que el turno abierto conserve su NODO mientras
// llegan chunks. Si el nodo se reemplaza, la seleccion del navegador se
// destruye en cada token y no se puede copiar lo que Calipso esta
// escribiendo mientras lo escribe.

const socket = nav.sockets[0];
const conversacion = nav.nodos.get("conversacion");

test("el chat se engancha a /ws/chat", () => {
  assert.ok(socket, "crearChat no abrio ningun socket");
  assert.ok(socket.url.endsWith("/ws/chat"), socket.url);
});

test("cada chunk agranda el mismo nodo en vez de rearmar la conversacion",
     () => {
  socket.readyState = 1;
  socket.emitir("open", {});
  socket.dice({type: "thinking"});
  socket.dice({type: "chunk", text: "hola"});
  const nodoAbierto = conversacion.hijos.at(-1);
  const cuantos = conversacion.hijos.length;
  socket.dice({type: "chunk", text: " mundo"});
  socket.dice({type: "chunk", text: "!"});
  assert.equal(conversacion.hijos.length, cuantos, "aparecio un nodo de mas");
  assert.equal(conversacion.hijos.at(-1), nodoAbierto,
               "el nodo del turno abierto se reemplazo: en el navegador eso " +
               "borra la seleccion en cada token");
  assert.equal(nodoAbierto.textContent, "hola mundo!");
});

test("el historial ya pintado no se vuelve a tocar", () => {
  socket.dice({type: "done"});
  const viejos = [...conversacion.hijos];
  socket.dice({type: "thinking"});
  socket.dice({type: "chunk", text: "otra respuesta"});
  const ahora = conversacion.hijos;
  assert.ok(ahora.length === viejos.length + 1, "no se agrego el turno nuevo");
  for (let i = 0; i < viejos.length; i++) {
    assert.equal(ahora[i], viejos[i], `se rehizo el turno ${i}`);
  }
});

test("un turno de error lleva su clase y no se mezcla con los demas", () => {
  socket.dice({type: "done"});
  socket.dice({type: "error", text: "se cayo el modelo"});
  const ultimo = conversacion.hijos.at(-1);
  assert.ok(ultimo.className.includes("error"), ultimo.className);
  assert.ok(ultimo.textContent.includes("se cayo el modelo"));
});

test("el texto del modelo no se interpreta como HTML", () => {
  socket.dice({type: "thinking"});
  socket.dice({type: "chunk", text: "<img onerror=x> o'brien"});
  const ultimo = conversacion.hijos.at(-1);
  // con textContent no hay nada que escapar: el texto entra literal y el
  // innerHTML del nodo nunca se escribe
  assert.equal(ultimo.textContent, "<img onerror=x> o'brien");
  assert.equal(ultimo.innerHTML, "",
               "el turno se pinto por innerHTML: volvio el rearmado");
  socket.dice({type: "done"});
});

test("el aviso de 'no se envio' es pasajero y se va en el proximo pintado",
     () => {
  const formulario = nav.nodos.get("entrada");
  const campo = nav.nodos.get("texto");
  socket.readyState = 0;                       // socket caido
  campo.value = "un mensaje que no va a salir";
  for (const f of formulario.oyentes.get("submit") || []) {
    f({preventDefault() {}});
  }
  const aviso = conversacion.hijos.at(-1);
  assert.ok(aviso.textContent.includes("no se envio"), aviso.textContent);
  assert.equal(campo.value, "un mensaje que no va a salir",
               "se perdio el texto que no se pudo mandar");
  socket.readyState = 1;
  socket.emitir("open", {});                   // el proximo pintado lo barre
  assert.ok(!conversacion.hijos.includes(aviso),
            "el aviso pasajero quedo clavado en la conversacion");
});
