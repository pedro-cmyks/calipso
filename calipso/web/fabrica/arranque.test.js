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
  const n = {
    id, tagName: etiqueta, dataset: {}, style: {}, className: "",
    textContent: "", value: "", placeholder: "",
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
  // el innerHTML se cuenta: escribirlo invalida el layout del navegador, y
  // "cuantas veces se escribio" es lo unico que se puede medir de eso desde
  // afuera de un navegador de verdad
  let html = "", escrituras = 0;
  Object.defineProperty(n, "innerHTML", {
    get: () => html,
    set: v => { html = v; escrituras++; },
    enumerable: true, configurable: true,
  });
  n.escriturasDeHtml = () => escrituras;
  return n;
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
                    "avisos", "costo", "foco", "razonamiento",
                    "abismo", "abismo-texto", "abismo-viaje",
                    "abismo-viaje-texto", "empleado",
                    "mesa", "plantel", "aparatos",
                    "badge-permisos", "badge-aparatos"]) {
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
  // pedidos guarda solo la URL (los tests viejos hacen .includes() sobre
  // eso); peticiones guarda tambien las opciones -metodo y body- que es lo
  // que necesita el test del clic en financiar para afirmar que se armo el
  // POST correcto.
  const peticiones = [];
  globalThis.fetch = (url, opciones) => {
    pedidos.push(String(url));
    peticiones.push({url: String(url), opciones});
    // solo la lista cuelga: es el caso que este archivo fija (el mapa
    // arranca sin esperarla). El activate tiene que poder resolver
    if (String(url).endsWith("/api/chats")) return new Promise(() => {});
    if (String(url).includes("/activate")) {
      return Promise.resolve({ok: true, json: async () => (
        {id: "c9", title: "otro", messages: [{role: "user", text: "viejo"}]})});
    }
    // la lista de aparatos contesta con UN golpe vigente y nada mas: es el
    // caso que separa los badges de la submesa (cero permisos pendientes,
    // un aparato esperando en la puerta). El endsWith deja afuera a
    // /aprobar y a /{hash}/revocar, que son POST y contestan {ok: true}.
    if (String(url).endsWith("/api/aparatos")) {
      return Promise.resolve({ok: true, json: async () => ({aparatos: [
        {hash_id: null, id_pedido: "ped_1", aparato: "e-reader",
         tipo: "lector", creada: "2026-09-08T10:00:00", ultima_vez: null,
         estado: "golpeando", efectivo: "golpeando"}]})});
    }
    return Promise.resolve({ok: true,
                            json: async () => ({activa: true,
                                                ciudad: ciudadDePrueba()})});
  };

  return {ctx, canvas, nodos, pedidos, peticiones, cuadros, sockets,
          medidaDelLienzo: () => ({ancho, alto})};
}

const nav = montarNavegador();

// La carga va con plazo: si `app.js` volviera a bloquearse en un `await`,
// esta espera no terminaria nunca y el test moriria por timeout del runner
// en vez de decir que fue lo que paso.
const PLAZO = 3000;
let plazo;
let modulo = null;
const cargado = await Promise.race([
  import("./app.js").then(m => { modulo = m; return "cargado"; }),
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

test("el mouse quieto sobre un edificio no reescribe la tarjeta", () => {
  const tarjeta = nav.nodos.get("tarjeta");
  const mover = (x, y) => {
    for (const f of nav.canvas.oyentes.get("pointermove") || []) {
      f({pointerId: 7, pointerType: "mouse", clientX: x, clientY: y});
    }
  };
  // se barre la pantalla hasta encontrar un edificio: la camara ya encuadro
  // la ciudad en el cuadro que dibujo el test anterior, y adonde cae cada
  // edificio depende de ese encuadre
  let punto = null;
  for (let y = 0; y < 600 && !punto; y += 8) {
    for (let x = 0; x < 800 && !punto; x += 8) {
      mover(x, y);
      if (tarjeta.innerHTML) punto = {x, y};
    }
  }
  assert.ok(punto, "no se encontro ningun edificio debajo del puntero");
  const antes = tarjeta.escriturasDeHtml();
  mover(punto.x, punto.y);
  mover(punto.x, punto.y);
  mover(punto.x, punto.y);
  assert.equal(tarjeta.escriturasDeHtml(), antes,
               "la tarjeta se reescribio con el mismo edificio debajo: cada " +
               "reescritura invalida el layout, y el offsetWidth que se lee " +
               "justo despues obliga al navegador a rehacerlo AHORA");
  assert.ok(tarjeta.style.left, "la tarjeta no se llego a posicionar");
});

// --- El pintado de la conversacion, contra el mismo app.js ya cargado. ---
//
// Lo que se fija aca es que el turno abierto conserve su NODO mientras
// llegan chunks. Si el nodo se reemplaza, la seleccion del navegador se
// destruye en cada token y no se puede copiar lo que Calipso esta
// escribiendo mientras lo escribe.

// dos sockets vivos: el del chat y el del pulso. Elegirlos por INDICE ata el
// test al orden de los imports de app.js
const socket = nav.sockets.find(s => s.url.endsWith("/ws/chat"));
const socketMapa = nav.sockets.find(s => s.url.endsWith("/ws/mapa"));
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

test("el mapa se engancha a /ws/mapa", () => {
  assert.ok(socketMapa, "crearPulso no abrio ningun socket");
});

test("un foco por el pulso hace volar la camara, sin tocar el chat", async () => {
  await new Promise(r => setTimeout(r, 0));   // la ciudad ya contesto
  const conversacionAntes = nav.nodos.get("conversacion").hijos.length;
  socketMapa.dice({seq: 1, ts: 1, agente_id: null, evento: "foco",
                   departamento: "dep:b"});
  const cam = modulo.camaraDePrueba();
  // la ciudad de prueba pone a dep:b en (60, 30): la camara arranca un VUELO
  // hacia ahi, no se teletransporta
  assert.ok(cam.vuelo, "el foco no disparo ningun vuelo");
  assert.deepEqual({x: cam.vuelo.hasta.x, y: cam.vuelo.hasta.y},
                   {x: 60, y: 30});
  assert.equal(nav.nodos.get("conversacion").hijos.length, conversacionAntes,
               "el foco toco la conversacion");
});

// --- El panel del medio: entrar en modo lectura y salir. ---

/** Un toque completo: baja, no se mueve, sube. */
function tocar(canvas, x, y, pointerId = 11) {
  for (const f of canvas.oyentes.get("pointerdown") || []) {
    f({pointerId, pointerType: "touch", clientX: x, clientY: y});
  }
  for (const f of canvas.oyentes.get("pointerup") || []) {
    f({pointerId, pointerType: "touch", clientX: x, clientY: y});
  }
}

test("cerrar el popup tocando el mapa devuelve el panel del medio al chat",
     async () => {
  const {aPantalla, escalaEntera} = await import("./camara.js");
  const {centroDe} = await import("./ciudad.js");
  const {medidas, plazasDe} = await import("./sprites.js");

  const cam = modulo.camaraDePrueba();
  const edificio = ciudadDePrueba().edificios[0];      // dep:a, en (-60, 0)
  // encima del edificio y adentro: pasado el umbral se ven los escritorios
  Object.assign(cam, {x: edificio.x, y: edificio.y, escala: 4, vuelo: null});
  socketMapa.dice({seq: 20, ts: 20, agente_id: "a1", departamento: "dep:a",
                   evento: "inicio", rol: "scout", modelo: "sonnet"});

  const vista = {ancho: 800, alto: 600};
  const esc = escalaEntera(cam);
  const m = medidas(edificio);
  const p = aPantalla(cam, centroDe(edificio), vista);
  const plaza = plazasDe(edificio)[0];
  const px = p.x - (m.ancho * esc) / 2 + plaza.x * esc + 1;
  const py = p.y - m.alto * esc + plaza.y * esc + 1;

  const panelCentro = nav.nodos.get("panel-centro");
  const razonamiento = nav.nodos.get("razonamiento");
  const empleado = nav.nodos.get("empleado");

  tocar(nav.canvas, px, py);
  assert.equal(panelCentro.dataset.modo, "razonamiento",
               "tocar el escritorio no abrio el panel de razonamiento");
  assert.ok(!empleado.classList.contains("oculto"), "el popup no se abrio");

  // el toque afuera de un escritorio cierra el popup; el panel del medio
  // tiene que volver con el, o Pedro fija un departamento y deja de ver la
  // conversacion. La salida existia -el boton "volver al chat"- pero la
  // asimetria se lee como un cuelgue.
  const escrituras = razonamiento.escriturasDeHtml();
  tocar(nav.canvas, 5, 5, 12);
  assert.equal(panelCentro.dataset.modo, "chat");
  assert.ok(razonamiento.classList.contains("oculto"));
  assert.ok(empleado.classList.contains("oculto"));

  // y se dejo de mirar a nadie: un evento nuevo del mismo agente ya no
  // repinta el panel de razonamiento
  socketMapa.dice({seq: 21, ts: 21, agente_id: "a1", departamento: "dep:a",
                   evento: "razonando", texto: "sigo pensando"});
  assert.equal(razonamiento.escriturasDeHtml(), escrituras,
               "el panel de razonamiento se siguio pintando: quedo mirando " +
               "a un empleado que Pedro ya cerro");
});

// --- La mesa y el plantel: antes de sumar sus ids a la lista de arriba,
// cajaMesa y cajaPlantel quedaban null y las guardas de app.js
// (`if (!cajaMesa) return`, `cajaPlantel?.`) hacian que esta linea no
// corriera en NINGUN test -- ni pintarMesa, ni pintarPlantel, ni
// accionDeMesa, ni el armado del body de financiar, ni los manejadores del
// plantel. ---

test("con el id sumado, la mesa se pinta sola (la guarda ya no la bloquea)",
     async () => {
  await new Promise(r => setTimeout(r, 0));
  const cajaMesa = nav.nodos.get("mesa");
  assert.ok(cajaMesa.innerHTML, "pintarMesa nunca escribio nada");
});

test("con el id sumado, el plantel se pinta solo (la guarda ya no lo " +
     "bloquea)", async () => {
  await new Promise(r => setTimeout(r, 0));
  const cajaPlantel = nav.nodos.get("plantel");
  assert.ok(cajaPlantel.innerHTML, "pintarPlantel nunca escribio nada");
});

test("un clic en financiar arma el POST con la cuenta del selector y el " +
     "presupuesto de la fila", async () => {
  const cajaMesa = nav.nodos.get("mesa");
  // cajaMesa es un nodo de mentira sin querySelector real: se lo agrega
  // aca, apuntado, en vez de forzar todo el arnes de closest/querySelector
  // del DOM completo para un solo caso.
  const selsPedidos = [];
  cajaMesa.querySelector = sel => {
    selsPedidos.push(sel);
    return {value: "dep:atlas"};
  };
  // sin querySelector la fila no tiene de donde leer las palabras: null
  // es la misma respuesta que un DOM real da cuando el campo no esta.
  const fila = {dataset: {presupuesto: "10000"}, querySelector: () => null};
  const boton = {
    dataset: {accion: "financiar", id: "p1"},
    disabled: false,
    // el mismo boton hace de target.closest("button[data-accion]") (se
    // devuelve a si mismo) y de boton.closest(".propuesta") (devuelve la
    // fila), que es exactamente como los usa accionDeMesa en app.js
    closest(sel) { return sel === ".propuesta" ? fila : boton; },
  };

  const antes = nav.peticiones.length;
  for (const f of cajaMesa.oyentes.get("click") || []) f({target: boton});
  await new Promise(r => setTimeout(r, 0));
  await new Promise(r => setTimeout(r, 0));

  const pedido = nav.peticiones.slice(antes)
    .find(p => p.url.includes("/financiar"));
  assert.ok(pedido, "el clic no armo ningun POST a /financiar");
  assert.equal(pedido.opciones.method, "POST");
  // palabras vacio: la fila de mentira no tiene el campo, como una fila
  // real sin nada escrito
  assert.deepEqual(JSON.parse(pedido.opciones.body),
                   {cuenta: "dep:atlas", mm: 10000, palabras: ""});
  assert.ok(selsPedidos.includes('select.paga[data-id="p1"]'),
            "no se pidio el selector de la propuesta p1");
});

// --- Los aparatos: aprobar manda el tipo que dice el SELECTOR ------------
//
// Es la mitad que el modulo puro no puede probar. `aparatos.test.js` fija
// que la tarjeta dibuja el selector preseleccionado en la sugerencia; lo que
// se fija aca es que el POST lleve lo que el selector dice EN EL MOMENTO DEL
// CLIC. Si el cableado mandara `golpe.tipo` (la sugerencia del aparato),
// cambiar el tipo antes de aprobar no cambiaria nada y Pedro le daria a un
// aparato un alcance que no eligio -- el canario del invariante 4 del lado
// del cliente.

test("con el id sumado, la lista de aparatos se pinta sola", async () => {
  await new Promise(r => setTimeout(r, 0));
  const caja = nav.nodos.get("aparatos");
  assert.ok(caja.innerHTML, "pintarAparatos nunca escribio nada");
  assert.ok(nav.pedidos.some(u => u.includes("/api/aparatos")),
            "no se pidio la lista de aparatos");
});

// Un badge dice "hay algo esperandote ACA". Si la cuenta de los golpes se
// escribiera en el badge de otra bandeja, Pedro abriria esa, la encontraria
// vacia, y el golpe -que vive 10 minutos- se venceria mientras busca donde
// no es: lo contrario de enterarse sin buscarlo. Cada sub-pestana escribe
// SOLO su propio badge.
test("el golpe prende el badge de Aparatos y no toca el de Permisos",
     async () => {
  await new Promise(r => setTimeout(r, 0));
  const badgeAparatos = nav.nodos.get("badge-aparatos");
  const badgePermisos = nav.nodos.get("badge-permisos");
  assert.equal(badgeAparatos.textContent, "1",
               "el golpe no llego al badge de su propia sub-pestana: quedo " +
               `en ${JSON.stringify(badgeAparatos.textContent)}`);
  assert.equal(badgeAparatos.clases.has("oculto"), false,
               "el badge de Aparatos quedo oculto con un golpe esperando");
  // este DOM de mentira no declara "permisos", asi que pintarPermisos ni
  // corre: si el badge de Permisos tiene algo escrito, se lo escribio la
  // bandeja de aparatos, que es exactamente el numero que apunta a la
  // bandeja equivocada
  assert.equal(badgePermisos.textContent, "",
               "la cuenta de los golpes se escribio en el badge de Permisos");
});

test("aprobar arma el POST con el tipo del selector, no con el sugerido",
     async () => {
  const caja = nav.nodos.get("aparatos");
  // misma tactica que el clic en financiar: el nodo de mentira no tiene
  // querySelector de verdad, se lo apunta para el unico selector que el
  // manejador busca
  const tarjeta = {
    querySelector: sel => (sel === "select[data-tipo-de]"
                           ? {value: "tablero"} : null),
    querySelectorAll: () => [],
  };
  const boton = {
    dataset: {aparato: "aprobar", id: "ped_1"},
    disabled: false,
    closest(sel) { return sel === "button[data-aparato]" ? boton : tarjeta; },
  };

  const antes = nav.peticiones.length;
  for (const f of caja.oyentes.get("click") || []) f({target: boton});
  await new Promise(r => setTimeout(r, 0));
  await new Promise(r => setTimeout(r, 0));

  const pedido = nav.peticiones.slice(antes)
    .find(p => p.url.includes("/api/aparatos/aprobar"));
  assert.ok(pedido, "el clic no armo ningun POST a /api/aparatos/aprobar");
  assert.equal(pedido.opciones.method, "POST");
  assert.deepEqual(JSON.parse(pedido.opciones.body),
                   {id_pedido: "ped_1", tipo: "tablero"});
});

test("revocar manda el hash por el path y no manda cuerpo", async () => {
  const caja = nav.nodos.get("aparatos");
  const tarjeta = {querySelector: () => null, querySelectorAll: () => []};
  const boton = {
    dataset: {aparato: "revocar", id: "a1b2c3d4"},
    disabled: false,
    closest(sel) { return sel === "button[data-aparato]" ? boton : tarjeta; },
  };

  const antes = nav.peticiones.length;
  for (const f of caja.oyentes.get("click") || []) f({target: boton});
  await new Promise(r => setTimeout(r, 0));
  await new Promise(r => setTimeout(r, 0));

  const pedido = nav.peticiones.slice(antes)
    .find(p => p.url.includes("/revocar"));
  assert.ok(pedido, "el clic no armo ningun POST a revocar");
  assert.equal(pedido.url, "/api/aparatos/a1b2c3d4/revocar");
  assert.equal(pedido.opciones.method, "POST");
});

// El repintado (cada 60 s, tras cada accion, al entrar a la pestana)
// reconstruye el HTML de la caja entera. Lo que se fija aca es que ANTES de
// reconstruirlo, pintarAparatos lea lo que dicen los selectores y se lo
// pase al modulo puro. El DOM de mentira no reconstruye nada, asi que el
// observable es el HTML generado: si el selector de ped_1 decia "tablero",
// el HTML nuevo tiene que traer `tablero` seleccionado y no la sugerencia
// del aparato ("lector", que es lo que contesta /api/aparatos aca). Sin
// esto, rechazar OTRO golpe -o el intervalo de 60 s- le devolvia a este el
// tipo que sugirio el aparato, y el POST de aprobar se lo llevaba.
test("el repintado conserva el tipo que Pedro eligio en el selector",
     async () => {
  const caja = nav.nodos.get("aparatos");
  // el selector que Pedro ya toco, tal como pintarAparatos lo busca
  const selectTocado = {dataset: {tipoDe: "ped_1"}, value: "tablero"};
  caja.querySelectorAll = sel =>
    (sel === "select[data-tipo-de]" ? [selectTocado] : []);
  try {
    // el repintado lo dispara una accion sobre OTRA tarjeta: rechazar el
    // golpe ped_2 (el finally del click repinta la caja entera)
    const tarjeta = {querySelector: () => null, querySelectorAll: () => []};
    const boton = {
      dataset: {aparato: "rechazar", id: "ped_2"},
      disabled: false,
      closest(sel) { return sel === "button[data-aparato]" ? boton : tarjeta; },
    };
    for (const f of caja.oyentes.get("click") || []) f({target: boton});
    for (let i = 0; i < 3; i++) await new Promise(r => setTimeout(r, 0));
    assert.match(caja.innerHTML, /<option value="tablero" selected>/,
                 "el repintado volvio el selector a la sugerencia del aparato");
    assert.ok(!caja.innerHTML.includes('<option value="lector" selected>'),
              "la sugerencia del aparato quedo seleccionada");
    assert.match(caja.innerHTML, /Ve toda la fabrica/,
                 "el alcance en grande volvio a describir la sugerencia");
  } finally {
    caja.querySelectorAll = () => [];
  }
});

test("cambiar el tipo reescribe el alcance en grande", () => {
  const caja = nav.nodos.get("aparatos");
  const alcance = {textContent: "Solo sus endpoints de lectura (/api/lectura)"};
  const tarjeta = {querySelector: sel => (sel === ".alcance" ? alcance : null)};
  const select = {
    value: "navegador",
    closest(sel) { return sel === ".golpe" ? tarjeta : select; },
  };

  for (const f of caja.oyentes.get("change") || []) f({target: select});
  assert.equal(alcance.textContent, "Todo: la PWA completa, como la Ally",
               "el cartel del alcance quedo describiendo el tipo anterior");
});

// --- El renglon del abismo: fuera de la conversacion, y con cierre ------

test("el pondering del abismo no agrega nodos a la conversacion y el chunk sigue en el mismo", () => {
  socket.dice({type: "done"});
  socket.dice({type: "thinking"});
  socket.dice({type: "chunk", text: "Dejame ver "});
  const nodoAbierto = conversacion.hijos.at(-1);
  const cuantos = conversacion.hijos.length;
  socket.dice({type: "abismo", fase: "pondering", fuente: "chats", verbo: "buscando en tus chats"});
  const caja = nav.nodos.get("abismo");
  const renglon = nav.nodos.get("abismo-texto");
  assert.ok(!caja.classList.contains("oculto"), "el renglon del abismo no se mostro");
  assert.ok(renglon.textContent.startsWith("buscando en tus chats..."), renglon.textContent);
  assert.equal(conversacion.hijos.length, cuantos, "el pondering se pinto como turno");
  socket.dice({type: "abismo", fase: "pescado", fuente: "chats", tamano: 40, viaje: {destino: "local"}});
  socket.dice({type: "chunk", text: "y sigo"});
  assert.equal(conversacion.hijos.at(-1), nodoAbierto, "la continuacion abrio otra burbuja");
  assert.equal(nodoAbierto.textContent, "Dejame ver y sigo");
  assert.equal(renglon.textContent, "del abismo: chats (40 chars)");
  assert.ok(nav.nodos.get("abismo-viaje").classList.contains("oculto"), "en local no hay detalle del viaje");
  socket.dice({type: "done"});
  assert.ok(caja.classList.contains("oculto"), "done no apago el renglon");
});

test("con destino nube el renglon del abismo despliega el texto tapado", () => {
  // spec seccion 9: el detalle desplegable con el texto tapado va en las
  // DOS UIs; es la informacion verificable de que viajo (seccion 8.3)
  socket.dice({type: "thinking"});
  socket.dice({type: "abismo", fase: "pondering", fuente: "chats"});
  const detalle = nav.nodos.get("abismo-viaje");
  assert.ok(detalle.classList.contains("oculto"), "el detalle se mostro antes de pescar");
  socket.dice({type: "abismo", fase: "pescado", fuente: "chats", tamano: 40,
               viaje: {destino: "nube", tapados: [{marcador: "[ID_1]", tipo: "identidad"}],
                       texto_tapado: "hola [ID_1]"}});
  assert.ok(!detalle.classList.contains("oculto"), "el detalle del viaje no se mostro");
  assert.equal(nav.nodos.get("abismo-viaje-texto").textContent, "hola [ID_1]");
  assert.equal(nav.nodos.get("abismo-texto").textContent,
               "del abismo: chats (40 chars, viajo tapado a la nube: [ID_1])");
  socket.dice({type: "done"});
  assert.ok(detalle.classList.contains("oculto"), "done no apago el detalle");
  assert.ok(nav.nodos.get("abismo").classList.contains("oculto"), "done no apago el renglon");
});
