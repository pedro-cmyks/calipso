/**
 * calipso/web/fabrica/app.js — El pegamento.
 *
 * Engancha los eventos del navegador con los modulos puros. Toda la
 * logica que se puede testear vive en los otros archivos; aca solo hay
 * cableado.
 */
import {crearCamara, arrastrar, acercar, paso, encuadrar,
        volarA} from "./camara.js";
import {cargarCiudad, enPunto, fichaDe, monedas} from "./ciudad.js";
import {escritorioEnPunto, opacidadDeTecho} from "./interior.js";
import {crearMapa} from "./mapa.js";
import {disposicion, escapar, textoDeTarjeta, posicionDeTarjeta,
        resumenDeAvisos, textoDeCosto, textoDeFoco,
        textoDeEmpleado, textoDeRazonamiento} from "./paneles.js";
import {crearChat} from "./chat.js";
import {crearPulso, empleadosDe, estadoVisible} from "./pulso.js";
import {textoDeMesa} from "./mesa.js";
import {textoDePlantel} from "./plantel.js";
import {textoDePerillas, aMilimonedas, aMilimonedasConCero, aEntero,
        cuerpoDeSuscripciones, departamentosDeSiembra,
        resumenDeSiembra} from "./perillas.js";
import {textoDePermisos, contadorPendientes} from "./permisos.js";
import {textoDeInbox, contadorDeInbox} from "./inbox.js";

const lienzo = document.getElementById("mapa");
const sinFabrica = document.getElementById("sin-fabrica");
const mapa = crearMapa(lienzo);
const cam = crearCamara(0, 0, 1);

let ciudad = null;
let estadoRed = "cargando";   // cargando | activa | inactiva | sin-conexion
let resaltado = null;
let ultimo = 0;
let encuadrado = false;       // el bucle encuadra cuando el lienzo ya mide

async function traer() {
  try {
    const r = await cargarCiudad();
    if (r.activa) { ciudad = r.ciudad; estadoRed = "activa"; }
    else { ciudad = null; estadoRed = "inactiva"; }
  } catch (e) {
    // "no hay fabrica" y "no llego la respuesta" son cosas distintas y el
    // cartel no puede mentir sobre cual de las dos es
    estadoRed = "sin-conexion";
  }
  sinFabrica.textContent = estadoRed === "inactiva"
    ? "Todavia no hay fabrica: la economia no esta activa."
    : "Sin conexion con el servidor.";
  sinFabrica.classList.toggle("oculto", ciudad !== null);
  pintarAvisos();
}

window.addEventListener("online", () => { traer(); });

function bucle(ahora) {
  const dt = ultimo ? ahora - ultimo : 16;
  ultimo = ahora;
  paso(cam, dt);
  const v = mapa.vista();
  // el encuadre espera a que el lienzo tenga tamano: en el telefono nace
  // adentro de un panel oculto y mide cero
  if (ciudad && !encuadrado && v.ancho > 0 && v.alto > 0) {
    Object.assign(cam, encuadrar(ciudad.edificios, v));
    encuadrado = true;
  }
  if (ciudad) {
    mapa.dibujar(ciudad, cam, resaltado, (ahora / 4000) % 1, plantel());
  }
  requestAnimationFrame(bucle);
}

/** Los estados de cada departamento, en el orden en que se sientan. */
function plantel() {
  const ahora = Date.now();
  const salida = {};
  for (const dep of Object.keys(pulso.empleados)) {
    salida[dep] = empleadosDe(pulso, dep).map(e => estadoVisible(e, ahora));
  }
  return salida;
}

// un Map de punteros vivos, no una variable: con dos dedos hay que hacer
// pinza, y con una sola variable el segundo dedo le pasa a arrastrar() la
// separacion entre los dos y el mapa salta
const punteros = new Map();
let pinza = null;

const separacion = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const puntoMedio = (a, b) => ({x: (a.x + b.x) / 2, y: (a.y + b.y) / 2});

function local(ev) {
  const caja = lienzo.getBoundingClientRect();
  return {x: ev.clientX - caja.left, y: ev.clientY - caja.top};
}

lienzo.addEventListener("pointerdown", ev => {
  lienzo.setPointerCapture(ev.pointerId);
  const p = local(ev);
  punteros.set(ev.pointerId, {x: p.x, y: p.y, movio: false});
  if (punteros.size === 2) {
    const [a, b] = [...punteros.values()];
    pinza = separacion(a, b);
  }
  lienzo.classList.add("arrastrando");
});

lienzo.addEventListener("pointermove", ev => {
  const p = local(ev);
  const previo = punteros.get(ev.pointerId);
  if (previo) {
    const dx = p.x - previo.x, dy = p.y - previo.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) previo.movio = true;
    previo.x = p.x;
    previo.y = p.y;
    if (punteros.size >= 2) {
      const [a, b] = [...punteros.values()];
      const ahora = separacion(a, b);
      if (pinza > 0 && ahora > 0) {
        acercar(cam, ahora / pinza, puntoMedio(a, b), mapa.vista());
      }
      pinza = ahora;
      return;                       // con dos dedos se hace pinza, no paneo
    }
    arrastrar(cam, dx, dy);
    return;
  }
  if (!ciudad) return;
  resaltado = enPunto(ciudad, cam, mapa.vista(), p.x, p.y);
  pintarTarjeta(p.x, p.y);
});

function soltar(ev) {
  const tocado = punteros.get(ev.pointerId);
  if (tocado && !tocado.movio && punteros.size === 1 && ciudad) {
    resaltado = enPunto(ciudad, cam, mapa.vista(), tocado.x, tocado.y);
    pintarTarjeta(tocado.x, tocado.y);
    let tocoEmpleado = false;
    if (resaltado && opacidadDeTecho(cam.escala) < 1) {
      const i = escritorioEnPunto(ciudad.edificios.find(e => e.id === resaltado),
                                  cam, mapa.vista(), tocado.x, tocado.y);
      const gente = empleadosDe(pulso, resaltado);
      if (i !== null && gente[i]) {
        mostrarEmpleado(gente[i]);
        tocoEmpleado = true;   // tocar un empleado no cambia el contexto
      }
    }
    if (!tocoEmpleado) {
      // el toque afuera cierra el popup Y saca al panel del medio del modo
      // lectura: cerrar uno solo deja a Pedro fijando un departamento sin
      // ver la conversacion, y la salida que queda -el boton "volver al
      // chat"- esta en el panel que justo dejo de mirar
      volverAlChat();
      // tocar un departamento tambien acota la mesa a sus propuestas
      // (punto 4): la senal ya existia para el chat, la mesa solo tenia
      // que enterarse
      if (resaltado) { enFoco = resaltado; pintarFoco(); pintarMesa(); }
    }
  }
  punteros.delete(ev.pointerId);
  if (punteros.size < 2) pinza = null;
  if (!punteros.size) lienzo.classList.remove("arrastrando");
  if (lienzo.hasPointerCapture(ev.pointerId)) {
    lienzo.releasePointerCapture(ev.pointerId);
  }
}
lienzo.addEventListener("pointerup", soltar);
lienzo.addEventListener("pointercancel", soltar);

// solo el mouse tiene "salir": en touch el pointerleave llega SIEMPRE
// justo despues del pointerup, y borraria lo que el toque acaba de abrir
lienzo.addEventListener("pointerleave", ev => {
  if (ev.pointerType !== "mouse") return;
  resaltado = null;
  tarjeta.classList.add("oculto");
});

lienzo.addEventListener("wheel", ev => {
  ev.preventDefault();
  acercar(cam, ev.deltaY < 0 ? 1.12 : 1 / 1.12, local(ev), mapa.vista());
}, {passive: false});

const app = document.getElementById("app");
const tarjeta = document.getElementById("tarjeta");
const barra = document.getElementById("avisos");
const barraCosto = document.getElementById("costo");
const barraFoco = document.getElementById("foco");
let enFoco = null;            // el edificio tocado: contexto y pagador
let ultimaEpoca = 0;

const popupEmpleado = document.getElementById("empleado");

function pintarFoco() {
  const ficha = (ciudad && enFoco) ? fichaDe(ciudad, enFoco) : null;
  barraFoco.classList.toggle("oculto", !ficha);
  barraFoco.innerHTML = ficha ? textoDeFoco(ficha) : "";
}

barraFoco.addEventListener("click", ev => {
  if (ev.target && ev.target.dataset.accion === "quitar") {
    enFoco = null;
    pintarFoco();
    // la mesa tambien esta filtrada por este mismo foco (punto 4): sacarlo
    // desde la barra del chat tiene que destrabar la mesa igual que el
    // boton "ver todas" que vive ahi
    pintarMesa();
  }
});

// El layout lo resuelve el CSS con su media query, que no depende de que
// el JS ande. `disposicion` decide lo que el CSS no puede: en el telefono
// el dedo tapa la tarjeta si va pegada al punto, asi que ahi se ancla a
// una esquina del lienzo en vez de seguir al puntero.
function tarjetaSigueAlPuntero() {
  return disposicion(window.innerWidth) === "tres-paneles";
}

for (const boton of document.querySelectorAll("#pestanas button")) {
  boton.addEventListener("click", () => {
    app.dataset.pestana = boton.dataset.pestana;
    for (const otro of document.querySelectorAll("#pestanas button")) {
      otro.classList.toggle("activa", otro === boton);
    }
    // sin esto, tocar la pestana muestra la foto del momento en que cargo
    // la pagina en vez de lo que hay ahora (spec seccion 9)
    // permisos tambien, y no solo la mesa: es la otra mitad de "sin
    // buscarlo" (punto 1) -si algo quedo pendiente mientras Pedro miraba
    // el chat o el mapa, tocar "Mesa" tiene que traerlo ya, no esperar a
    // los proximos 60s del refresco de fondo.
    if (boton.dataset.pestana === "mesa") { pintarMesa(); pintarPermisos(); }
  });
}
app.dataset.pestana = "chat";

document.getElementById("expandir").addEventListener("click", () => {
  app.classList.toggle("mapa-entero");
  encuadrado = false;
});

function pintarAvisos() {
  const avisos = ciudad ? resumenDeAvisos(ciudad) : [];
  if (!avisos.length) {
    barra.innerHTML = '<span class="nada">Sin compuertas pendientes</span>';
    return;
  }
  barra.innerHTML = avisos
    .map(a => `<span class="aviso">${escapar(a.texto)}</span>`)
    .join("");
}

const cajaMesa = document.getElementById("mesa");

async function pintarMesa() {
  // arranque.test.js monta un DOM de mentira que no declara "mesa": sin
  // esta guarda, importar el modulo ahi revienta antes de llegar a un
  // solo test que sea de esta pantalla.
  if (!cajaMesa) return;
  try {
    const r = await fetch("/api/economia/bus");
    if (!r.ok) {
      cajaMesa.innerHTML = '<div class="vacio">No se pudo leer el bus.</div>';
      return;
    }
    cajaMesa.innerHTML = textoDeMesa(await r.json(), enFoco);
  } catch (_) {
    cajaMesa.innerHTML = '<div class="vacio">No se pudo leer el bus.</div>';
  }
}

async function accionDeMesa(boton) {
  const accion = boton.dataset.accion;
  const id = boton.dataset.id;
  boton.disabled = true;
  try {
    let r;
    if (accion === "abrir-semana") {
      r = await fetch("/api/economia/abrir", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({cuota_firmable_mpt: 4000,
                              reserva_personal_mpt: 1000})});
    } else if (accion === "financiar") {
      const sel = cajaMesa.querySelector(`select.paga[data-id="${id}"]`);
      const fila = boton.closest(".propuesta");
      const mm = Number(fila?.dataset.presupuesto || 0);
      // `data-cuenta` gana sobre el selector: una ronda pre-seed se paga
      // contra el tesoro y contra nada mas (bus.financiar rechaza
      // cualquier billetera de departamento), asi que su fila no dibuja
      // selector y trae la cuenta puesta.
      const cuenta = fila?.dataset.cuenta || (sel ? sel.value : "");
      r = await fetch(`/api/economia/bus/${encodeURIComponent(id)}/financiar`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({cuenta, mm})});
    } else if (accion === "descartar") {
      r = await fetch(`/api/economia/bus/${encodeURIComponent(id)}/descartar`,
                      {method: "POST"});
    } else {
      return;
    }
    if (!r.ok) {
      let detalle = "no se pudo";
      try { detalle = (await r.json()).detail || detalle; } catch (_) {}
      alert(detalle);
    }
  } finally {
    boton.disabled = false;
    await pintarMesa();
  }
}

cajaMesa?.addEventListener("click", evento => {
  const boton = evento.target.closest("button[data-accion]");
  if (!boton) return;
  if (boton.dataset.accion === "ver-todas") {
    // sacar el filtro es local, no pide nada al servidor: la misma salida
    // que el boton "quitar" de la barra del chat, para que la mesa nunca
    // deje a Pedro sin forma de volver a ver todas las propuestas
    enFoco = null;
    pintarFoco();
    pintarMesa();
    return;
  }
  accionDeMesa(boton);
});

const cajaPlantel = document.getElementById("plantel");

async function pintarPlantel() {
  // arranque.test.js monta un DOM de mentira que no declara "plantel": sin
  // esta guarda, importar el modulo ahi revienta antes de llegar a un solo
  // test que sea de esta pantalla (mismo problema que cajaMesa mas arriba).
  if (!cajaPlantel) return;
  try {
    const r = await fetch("/api/plantel");
    cajaPlantel.innerHTML = textoDePlantel(r.ok ? await r.json() : null);
  } catch (_) {
    cajaPlantel.innerHTML = textoDePlantel(null);
  }
}

cajaPlantel?.addEventListener("click", async evento => {
  const boton = evento.target.closest("button[data-plantel]");
  if (!boton || boton.type === "submit") return;
  const que = boton.dataset.plantel;
  boton.disabled = true;
  try {
    let r;
    if (que === "modo") {
      r = await fetch("/api/plantel/modo", {
        method: "PUT", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({modo: boton.dataset.modo})});
    } else {
      r = await fetch(`/api/plantel/${que}`, {method: "POST"});
    }
    if (!r.ok) {
      let detalle = "no se pudo";
      try { detalle = (await r.json()).detail || detalle; } catch (_) {}
      alert(detalle);
    }
  } finally {
    boton.disabled = false;
    await pintarPlantel();
  }
});

cajaPlantel?.addEventListener("submit", async evento => {
  evento.preventDefault();
  const form = evento.target;
  const cuenta = form.cuenta.value.trim();
  const minutos = Number(form.minutos.value);
  const boton = form.querySelector('button[type="submit"]');
  if (boton) boton.disabled = true;
  try {
    const r = await fetch("/api/routines", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({kind: "departamento", label: `jefe de ${cuenta}`,
                            interval_minutes: minutos, enabled: true,
                            cuenta})});
    if (!r.ok) {
      let detalle = "no se pudo crear la rutina";
      try { detalle = (await r.json()).detail || detalle; } catch (_) {}
      alert(detalle);
    } else {
      form.reset();
    }
  } finally {
    if (boton) boton.disabled = false;
  }
});

// --- Las perillas: el tesoro de la fabrica y el banco de Pedro ---------
//
// Viven en la misma columna que la mesa, detras de una segunda pestana
// local ("Decidir" / "Plata"): la mesa financia o descarta con la plata
// que ya esta puesta, las perillas son de donde esa plata sale. No es una
// pestana global de #pestanas -esa grilla es del telefono y de las cuatro
// columnas de escritorio, y esta pantalla no necesita una columna propia-
// sino un segundo modo DENTRO de "La mesa", que es donde Pedro ya decide
// sobre plata.
const cajaPerillas = document.getElementById("perillas");
let mensajePerillas = null;              // el aviso pasajero de "salio bien"

async function pintarPerillas() {
  // mismo motivo que la guarda de cajaMesa/cajaPlantel: arranque.test.js
  // no declara "perillas" en su DOM de mentira.
  if (!cajaPerillas) return;
  try {
    // dos lecturas: el tablero (saldos) y la config (los numeros que se
    // pueden mover). Van juntas y no en dos repintados porque son una sola
    // pantalla; si la config falla se pinta el tablero igual -- perder los
    // ajustes es peor que perder los saldos, pero perder los dos es peor
    // que perder uno.
    const [r, rc] = await Promise.all([
      fetch("/api/economia/tablero"),
      fetch("/api/economia/config").catch(() => null),
    ]);
    if (!r.ok) {
      cajaPerillas.innerHTML = '<div class="vacio">No se pudo leer el tablero.</div>';
      return;
    }
    let config = null;
    try { config = rc && rc.ok ? await rc.json() : null; } catch (_) {}
    cajaPerillas.innerHTML = textoDePerillas(await r.json(), mensajePerillas,
                                             config);
  } catch (_) {
    cajaPerillas.innerHTML = '<div class="vacio">No se pudo leer el tablero.</div>';
  }
}

/** El mensaje se ve un rato despues de una accion y despues se apaga solo
 *  -mismo patron que avisoPasajero del chat- para que la prueba de que
 *  "salio bien" no dependa de que Pedro llegue a leerlo en el instante
 *  exacto en que la pantalla se repinta. */
function avisarEnPerillas(texto) {
  mensajePerillas = texto;
  pintarPerillas();
  setTimeout(() => {
    if (mensajePerillas === texto) { mensajePerillas = null; pintarPerillas(); }
  }, 5000);
}

// --- Permisos: lo que Calipso quiere hacer y no se deshace solo --------
//
// Tercera sub-pestana de "La mesa", al lado de "Decidir" (propuestas ya
// financiables) y "Plata" (mover el capital de Pedro): esta es donde se
// aprueba o se niega, no donde se decide cuanto gastar ni de donde sale.
// Acunar por encima del techo es el primer consumidor del motor de
// permisos; comandos y archivos van a caer en la misma pantalla el dia que
// se enchufen (calipso/permisos/motor.py), asi que el lugar donde se
// contesta tambien tiene que ser uno solo.
//
// El badge (aca y en la pestana global "Mesa") es lo que hace que Pedro se
// entere SIN buscarlo: si algo queda esperando su respuesta mientras esta
// mirando el chat o el mapa, el numero ya esta puesto cuando llegue.
const cajaPermisos = document.getElementById("permisos");
const badgeSubmesa = document.getElementById("badge-submesa");
const badgePestanaMesa = document.getElementById("badge-pestana-mesa");
let mensajePermisos = null;

function pintarBadgesDePermisos(datos) {
  const n = contadorPendientes(datos);
  for (const badge of [badgeSubmesa, badgePestanaMesa]) {
    if (!badge) continue;
    badge.textContent = String(n);
    badge.classList.toggle("oculto", n === 0);
  }
}

async function pintarPermisos() {
  // mismo motivo que la guarda de cajaMesa/cajaPlantel/cajaPerillas:
  // arranque.test.js no declara "permisos" en su DOM de mentira.
  if (!cajaPermisos) return;
  try {
    const r = await fetch("/api/permisos");
    if (!r.ok) {
      cajaPermisos.innerHTML = '<div class="vacio">No se pudo leer los permisos.</div>';
      pintarBadgesDePermisos(null);
      return;
    }
    const datos = await r.json();
    cajaPermisos.innerHTML = textoDePermisos(datos, mensajePermisos);
    pintarBadgesDePermisos(datos);
  } catch (_) {
    cajaPermisos.innerHTML = '<div class="vacio">No se pudo leer los permisos.</div>';
    pintarBadgesDePermisos(null);
  }
}

/** Mismo patron que avisarEnPerillas: el aviso de "salio bien" se ve un
 *  rato y se apaga solo. */
function avisarEnPermisos(texto) {
  mensajePermisos = texto;
  pintarPermisos();
  setTimeout(() => {
    if (mensajePermisos === texto) { mensajePermisos = null; pintarPermisos(); }
  }, 5000);
}

cajaPermisos?.addEventListener("click", async evento => {
  const boton = evento.target.closest("button[data-accion]");
  if (!boton) return;
  const accion = boton.dataset.accion;
  const id = boton.dataset.id;
  // deshabilitar TODOS los botones de la tarjeta, no solo el que se toco:
  // un permiso concedido con un solo toque en cada lado no se puede pedir
  // dos veces (revocar dos veces es inofensivo, pero acunar dos monedas en
  // vez de una por un doble toque no se deshace).
  const tarjeta = boton.closest(".solicitud, .permiso") || boton;
  const botones = tarjeta.querySelectorAll
    ? tarjeta.querySelectorAll("button") : [boton];
  for (const b of botones) b.disabled = true;
  try {
    let r;
    if (accion === "responder") {
      r = await fetch(
        `/api/permisos/solicitudes/${encodeURIComponent(id)}/responder`,
        {method: "POST", headers: {"Content-Type": "application/json"},
         body: JSON.stringify({respuesta: boton.dataset.respuesta})});
    } else if (accion === "revocar") {
      r = await fetch(
        `/api/permisos/concedidos/${encodeURIComponent(id)}/revocar`,
        {method: "POST"});
    } else {
      return;
    }
    if (!r.ok) {
      let detalle = "no se pudo";
      try { detalle = (await r.json()).detail || detalle; } catch (_) {}
      alert(detalle);
    } else if (accion === "responder") {
      const etiqueta = {si: "aprobada una vez", si_siempre: "aprobada para siempre",
                        no: "rechazada"}[boton.dataset.respuesta] || "contestada";
      avisarEnPermisos(`listo: la solicitud quedo ${etiqueta}`);
    } else {
      avisarEnPermisos("listo: se revoco el permiso");
    }
  } finally {
    for (const b of botones) b.disabled = false;
    await pintarPermisos();
  }
});

cajaPermisos?.addEventListener("submit", async evento => {
  evento.preventDefault();
  const form = evento.target;
  if (form.dataset.accion !== "techo") return;
  const mm = aMilimonedas(form.techo.value);
  if (mm === null) { alert("el techo tiene que ser un numero mayor que cero"); return; }
  const boton = form.querySelector('button[type="submit"]');
  if (boton) boton.disabled = true;
  try {
    const r = await fetch("/api/permisos/techo", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({nombre: "plata_mm", valor: mm})});
    if (!r.ok) {
      let detalle = "no se pudo cambiar el techo";
      try { detalle = (await r.json()).detail || detalle; } catch (_) {}
      alert(detalle);
    } else {
      avisarEnPermisos(`listo: el techo de plata ahora es ${monedas(mm)} monedas`);
    }
  } finally {
    if (boton) boton.disabled = false;
    await pintarPermisos();
  }
});

// --- Inbox: las cuatro bandejas juntas, "Todo" -------------------------
//
// Primera sub-vista de "La mesa" (no una pestana global: en escritorio la
// grilla es de cuatro columnas fijas y #pestanas esta apagado, asi que una
// pestana nueva no tendria donde vivir). Solo muestra y cuenta -- el
// despacho de data-inbox="responder" a cada endpoint de accion es del
// plan 2, porque los cuatro endpoints tienen cuerpos y errores distintos
// que hay que arreglar antes de poder enchufarlos con un solo patron.
const cajaInbox = document.getElementById("caja-inbox");
const badgeInbox = document.getElementById("badge-inbox");

async function pintarInbox() {
  // la guarda no es defensiva por gusto: arranque.test.js monta un DOM que
  // no declara este id, y sin esto el import de app.js revienta ahi antes
  // de correr un solo test
  if (!cajaInbox) return;
  try {
    const r = await fetch("/api/inbox");
    // mismo molde que pintarMesa/pintarPerillas/pintarPermisos: el unico
    // no-200 real de este endpoint es un 401 sin sesion (todo lo demas ya
    // llega envuelto en un 200 con `fallaron`), y sin este chequeo esa
    // sesion vencida se leia como "Nada esperando" -- tapando justo el
    // problema.
    if (!r.ok) {
      cajaInbox.innerHTML = `<div class="nota">no se pudo leer el inbox</div>`;
      if (badgeInbox) badgeInbox.classList.add("oculto");
      return;
    }
    const datos = await r.json();
    cajaInbox.innerHTML = textoDeInbox(datos);
    const n = contadorDeInbox(datos);
    if (badgeInbox) {
      badgeInbox.textContent = String(n);
      badgeInbox.classList.toggle("oculto", n === 0);
    }
  } catch (e) {
    cajaInbox.innerHTML = `<div class="nota">no se pudo leer el inbox</div>`;
    if (badgeInbox) badgeInbox.classList.add("oculto");
  }
}

for (const boton of document.querySelectorAll("#submesa button")) {
  boton.addEventListener("click", () => {
    const vista = boton.dataset.vista;
    for (const otro of document.querySelectorAll("#submesa button")) {
      otro.classList.toggle("activa", otro === boton);
    }
    cajaInbox?.classList.toggle("oculto", vista !== "inbox");
    cajaPlantel?.classList.toggle("oculto", vista !== "decidir");
    cajaMesa?.classList.toggle("oculto", vista !== "decidir");
    cajaPerillas?.classList.toggle("oculto", vista !== "plata");
    cajaPermisos?.classList.toggle("oculto", vista !== "permisos");
    // igual que la pestana global de "Mesa" (spec seccion 9): sin esto,
    // tocar una sub-pestana muestra la foto del momento en que cargo la
    // pagina.
    if (vista === "inbox") pintarInbox();
    if (vista === "plata") pintarPerillas();
    if (vista === "permisos") pintarPermisos();
  });
}

/** El unico camino que aplica una capacidad, desde el formulario o desde
 *  el boton "aplicar N" del numero medido. Un 409 no es un error: es el
 *  motor de permisos diciendo que quedo esperando tu respuesta, y decirle
 *  a Pedro "no se pudo" cuando en realidad quedo en la tira de permisos lo
 *  mandaria a reintentar para siempre. */
async function aplicarCapacidad(nombre, capacidad, reserva, boton) {
  if (capacidad === null || capacidad <= 0) {
    alert("la capacidad del ciclo tiene que ser un entero mayor que cero");
    return;
  }
  if (boton) boton.disabled = true;
  try {
    const cuerpo = {capacidad_ciclo: capacidad};
    if (reserva !== null && reserva !== undefined) cuerpo.reserva_personal = reserva;
    const r = await fetch(
      `/api/economia/suscripciones/${encodeURIComponent(nombre)}/capacidad`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(cuerpo)});
    if (r.status === 409) {
      let detalle = "";
      try { detalle = (await r.json()).detail || ""; } catch (_) {}
      alert(detalle || "quedo esperando tu respuesta en Permisos");
      pintarPermisos();
    } else if (!r.ok) {
      let detalle = "no se pudo aplicar la capacidad";
      try { detalle = (await r.json()).detail || detalle; } catch (_) {}
      alert(detalle);
    } else {
      avisarEnPerillas(`listo: ${nombre} queda en ${capacidad} unidades por ciclo`);
    }
  } finally {
    if (boton) boton.disabled = false;
    await pintarPerillas();
  }
}

cajaPerillas?.addEventListener("click", async evento => {
  const boton = evento.target.closest('button[data-ajuste="aplicar-medido"]');
  if (!boton) return;
  // el numero medido se aplica TAL CUAL, sin tocar la reserva: moverla
  // sola es otra decision, y el endpoint avisa si la reserva vieja ya no
  // entra en la capacidad nueva en vez de que esta pantalla la invente.
  await aplicarCapacidad(boton.dataset.suscripcion,
                         Number(boton.dataset.capacidad), null, boton);
});

cajaPerillas?.addEventListener("submit", async evento => {
  evento.preventDefault();
  const form = evento.target;
  const cual = form.dataset.perillas;
  const boton = form.querySelector('button[type="submit"]');

  if (cual === "sembrar") {
    // la zona sale del campo en el que Pedro escribio cada nombre. Hasta
    // hoy iba "fabrica" para todos, hardcodeada aca, y eso hacia imposible
    // sembrar el departamento personal que la economia da por hecho -- sin
    // vuelta atras, porque `Registro` no tiene baja ni deja ajustar la zona.
    const {departamentos, error} = departamentosDeSiembra(
      form.fabrica.value, form.personal.value);
    if (error) { alert(error); return; }
    // y la capacidad sale de los INPUTS, no de la constante: el numero que
    // se siembra tiene que ser el que Pedro esta viendo, lo haya propuesto
    // el probe o lo haya corregido el a mano. `data-medido` y
    // `data-propuesta` guardan de donde salio la propuesta y cual era, para
    // que el confirm no haga pasar un numero tipeado por una medicion.
    const capacidades = [...form.querySelectorAll("input[data-suscripcion]")]
      .map(i => ({nombre: i.dataset.suscripcion,
                  capacidad_ciclo: aEntero(i.value),
                  medido: i.dataset.medido
                    ? {proveedor: i.dataset.medido,
                       propuesta: Number(i.dataset.propuesta)} : null}));
    const mala = capacidades.find(c => !c.capacidad_ciclo);
    if (mala) {
      alert(`la capacidad de ${mala.nombre} tiene que ser un entero mayor ` +
            `que cero`);
      return;
    }
    // la lista entera, no un resumen: es el ultimo momento en el que un
    // nombre o una zona se pueden corregir. `resumenDeSiembra` ademas
    // encabeza con el aviso de que falta el departamento de finanzas.
    if (!confirm(resumenDeSiembra(departamentos, capacidades))) return;
    // el freno del doble toque es el mismo que ya usa financiar/descartar
    // en la mesa: deshabilitar ANTES del await, no despues -asi un segundo
    // toque mientras el primero sigue en vuelo no dispara un segundo pedido
    boton.disabled = true;
    try {
      const r = await fetch("/api/economia/sembrar", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          departamentos,
          suscripciones: cuerpoDeSuscripciones(capacidades),
        })});
      if (!r.ok) {
        let detalle = "no se pudo sembrar";
        try { detalle = (await r.json()).detail || detalle; } catch (_) {}
        alert(detalle);
      } else {
        form.reset();
        avisarEnPerillas("listo: la economia esta sembrada");
      }
    } finally {
      boton.disabled = false;
      await pintarPerillas();
    }
    return;
  }

  if (cual === "techo-preseed") {
    const nombre = form.dataset.departamento;
    const mm = aMilimonedasConCero(form.monto.value);
    if (mm === null) { alert("el techo tiene que ser un numero (0 = no pide)"); return; }
    // los dos techos viajan en el MISMO POST: son la misma decision, y
    // mandarlos por separado dejaria una ventana en la que el techo por
    // pedido ya subio y el del ciclo todavia no -- justo el estado en el
    // que el jefe puede pedir mas de lo que se le va a poder pagar.
    const ciclo = aMilimonedasConCero(form.ciclo.value);
    if (ciclo === null) {
      alert("el techo del ciclo tiene que ser un numero (0 = no pide)");
      return;
    }
    // sin confirmacion: una perilla se deshace escribiendola de nuevo, y
    // no mueve un milimon -- lo que se pida sigue necesitando que toques
    // "financiar" en la mesa. Es la misma razon por la que el endpoint no
    // pasa por el motor de permisos.
    boton.disabled = true;
    try {
      const r = await fetch(
        `/api/economia/departamentos/${encodeURIComponent(nombre)}/perillas`, {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({techo_preseed_mm: mm,
                                techo_preseed_ciclo_mm: ciclo})});
      if (!r.ok) {
        let detalle = "no se pudo guardar la perilla";
        try { detalle = (await r.json()).detail || detalle; } catch (_) {}
        alert(detalle);
      } else {
        avisarEnPerillas(mm > 0 && ciclo > 0
          ? `listo: ${nombre} puede pedir hasta ${monedas(mm)} monedas por ` +
            `ronda y ${monedas(ciclo)} en todo el ciclo`
          : `listo: ${nombre} no pide pre-seed`);
      }
    } finally {
      boton.disabled = false;
      await pintarPerillas();
    }
    return;
  }

  if (cual === "capacidad") {
    await aplicarCapacidad(form.dataset.suscripcion,
                           aEntero(form.capacidad.value),
                           aEntero(form.reserva.value), boton);
    return;
  }

  if (cual === "acunar") {
    const mm = aMilimonedas(form.monto.value);
    if (mm === null) { alert("el monto tiene que ser un numero mayor que cero"); return; }
    // acunar es append-only: una vez asentado en el libro no hay forma de
    // deshacerlo, asi que -a diferencia de financiar/descartar en la
    // mesa, que solo mueven plata ya puesta- esto pide una confirmacion
    // explicita ademas del freno del doble toque.
    if (!confirm(`Poner ${monedas(mm)} monedas en el tesoro? Es capital ` +
                 `tuyo entrando a la fabrica: no se puede deshacer.`)) return;
    boton.disabled = true;
    try {
      const r = await fetch("/api/economia/frontera/acunar", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({subtipo: "capital", destino: "tesoro",
                              monto_mm: mm, evidencia: {tipo: "firma_pedro"}})});
      if (!r.ok) {
        let detalle = "no se pudo acunar";
        try { detalle = (await r.json()).detail || detalle; } catch (_) {}
        alert(detalle);
      } else {
        form.reset();
        avisarEnPerillas(`listo: se pusieron ${monedas(mm)} monedas en el tesoro`);
      }
    } finally {
      boton.disabled = false;
      await pintarPerillas();
    }
    return;
  }

  if (cual === "movimiento") {
    const mm = aMilimonedas(form.monto.value);
    const tipo = form.tipo.value;
    const categoria = form.categoria.value.trim();
    if (mm === null) { alert("el monto tiene que ser un numero mayor que cero"); return; }
    if (!categoria) { alert("escribi una categoria"); return; }
    // el banco personal nunca acuna y nunca toca el libro de la fabrica
    // (spec): un movimiento de mas se corrige con otro movimiento, no con
    // un asiento irreversible, asi que no pide la confirmacion de acunar.
    boton.disabled = true;
    try {
      const r = await fetch("/api/economia/personal/movimiento", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({tipo, monto_mm: mm, categoria,
                              nota: form.nota.value.trim()})});
      if (!r.ok) {
        let detalle = "no se pudo registrar";
        try { detalle = (await r.json()).detail || detalle; } catch (_) {}
        alert(detalle);
      } else {
        form.reset();
        avisarEnPerillas(`listo: se registro un ` +
          `${tipo === "ingreso" ? "ingreso" : "egreso"} de ${monedas(mm)} monedas`);
      }
    } finally {
      boton.disabled = false;
      await pintarPerillas();
    }
  }
});

let tarjetaPintada = "";                 // el html que ya esta en la tarjeta
let medidaTarjeta = {ancho: 0, alto: 0};

function pintarTarjeta(px, py) {
  const ficha = (ciudad && resaltado) ? fichaDe(ciudad, resaltado) : null;
  if (!ficha) { tarjeta.classList.add("oculto"); return; }
  const html = textoDeTarjeta(ficha);
  tarjeta.classList.remove("oculto");   // visible antes de medirla
  // Escribir el innerHTML invalida el layout, y leer offsetWidth justo
  // despues obliga al navegador a rehacerlo AHORA. Con el mouse quieto
  // sobre un edificio eso pasaba en cada pointermove, para volver a pintar
  // exactamente lo mismo. Comparar el html -y no solo el id- ademas deja
  // que la tarjeta se actualice sola si el modelo cambia bajo el puntero.
  if (html !== tarjetaPintada) {
    tarjeta.innerHTML = html;
    tarjetaPintada = html;
    medidaTarjeta = {ancho: tarjeta.offsetWidth, alto: tarjeta.offsetHeight};
  }
  if (!tarjetaSigueAlPuntero()) {
    tarjeta.style.left = "10px";
    tarjeta.style.top = "10px";
    return;
  }
  const caja = lienzo.getBoundingClientRect();
  const p = posicionDeTarjeta(px, py, {ancho: caja.width, alto: caja.height},
                              medidaTarjeta);
  tarjeta.style.left = p.x + "px";
  tarjeta.style.top = p.y + "px";
}

const conversacion = document.getElementById("conversacion");
const formulario = document.getElementById("entrada");
const campo = document.getElementById("texto");

// Un nodo por turno, en el mismo orden que `estado.turnos`. Rearmar el
// innerHTML entero en cada evento cuesta O(turnos) por token -o sea
// cuadratico a lo largo de la sesion- pero lo caro no es el costo: rehacer
// el subarbol destruye la seleccion, y entonces no se puede copiar lo que
// Calipso esta escribiendo mientras lo escribe. La UI vieja de este mismo
// repo ya hace append incremental (calipso/web/index.html, appendBotText).
const nodosDeTurno = [];
let avisoPasajero = null;

function claseDeTurno(t) {
  return "turno" + (t.quien === "pedro" ? " mio" : "") +
         (t.quien === "error" ? " error" : "");
}

function pintarConversacion(turnos) {
  // el aviso del submit es pasajero: se va en el proximo pintado, igual que
  // cuando el innerHTML lo barria. Se saca ANTES de agregar turnos para que
  // los nuevos no queden colgados atras suyo.
  if (avisoPasajero) {
    conversacion.removeChild(avisoPasajero);
    avisoPasajero = null;
  }
  for (let i = nodosDeTurno.length; i < turnos.length; i++) {
    const div = document.createElement("div");
    div.className = claseDeTurno(turnos[i]);
    div.textContent = turnos[i].texto;   // textContent no necesita escapado
    nodosDeTurno.push(div);
    conversacion.appendChild(div);
  }
  // el unico turno que cambia mientras llegan chunks es el ultimo: al resto
  // del historial no se lo vuelve a tocar
  const i = turnos.length - 1;
  if (i < 0) return;
  const div = nodosDeTurno[i];
  if (div.textContent !== turnos[i].texto) div.textContent = turnos[i].texto;
  const clase = claseDeTurno(turnos[i]);
  if (div.className !== clase) div.className = clase;
}

const chat = crearChat(estado => {
  if (estado.epoca !== ultimaEpoca) {
    // se cargo otro chat: los nodos del anterior no se reciclan
    ultimaEpoca = estado.epoca;
    nodosDeTurno.length = 0;
    avisoPasajero = null;
    conversacion.innerHTML = "";
  }
  pintarConversacion(estado.turnos);
  conversacion.scrollTop = conversacion.scrollHeight;
  // el estado de conexion se pinta DESDE el estado. El aviso que agrega el
  // submit es pasajero y el proximo render lo borra; esto no, y por eso es
  // lo que Pedro mira para saber si Calipso lo esta escuchando.
  formulario.classList.toggle("sin-conexion", !estado.conectado);
  campo.placeholder = estado.conectado
    ? "Escribi a Calipso" : "Sin conexion con Calipso";
  barraCosto.textContent = textoDeCosto(estado);
});

formulario.addEventListener("submit", ev => {
  ev.preventDefault();
  if (chat.enviar(campo.value, enFoco)) {
    campo.value = "";
    return;
  }
  // enviar() no toca los turnos cuando no hay conexion: el aviso se pinta
  // aparte para no perder el texto que Pedro todavia no pudo mandar
  if (avisoPasajero) conversacion.removeChild(avisoPasajero);
  const aviso = document.createElement("div");
  aviso.className = "turno error";
  aviso.textContent = "sin conexion con Calipso: el mensaje no se envio";
  conversacion.appendChild(aviso);
  avisoPasajero = aviso;
  conversacion.scrollTop = conversacion.scrollHeight;
});

const listaChats = document.getElementById("lista-chats");

function pintarChats(datos) {
  listaChats.innerHTML = (datos.chats || [])
    .map(c => `<div class="chat${c.id === datos.active ? " activo" : ""}"` +
              ` data-id="${escapar(c.id)}">` +
              `${escapar(c.title || "sin titulo")}</div>`)
    .join("");
}

listaChats.addEventListener("click", async ev => {
  const fila = ev.target && ev.target.dataset && ev.target.dataset.id
    ? ev.target : null;
  if (!fila) return;
  try {
    const r = await fetch(`/api/chats/${encodeURIComponent(fila.dataset.id)}/activate`,
                          {method: "POST"});
    if (!r.ok) return;
    chat.cargar(await r.json());
    fetch("/api/chats").then(x => (x.ok ? x.json() : null))
      .then(d => { if (d) pintarChats(d); });
  } catch (e) {
    // sin conexion no se cambia de chat; el que estaba sigue entero
  }
});

// El mapa arranca PRIMERO y sin esperar a nadie. Este modulo no lleva un
// solo `await` arriba de todo a proposito: un `await` en el cuerpo del
// modulo no espera una respuesta, espera una promesa, y una promesa que no
// resuelve nunca (el telefono saltando de WiFi a datos) deja el modulo sin
// terminar de evaluar — sin bucle, sin lienzo dimensionado y sin cartel que
// lo explique. El try/catch no cubre eso: cubre el rechazo, no la demora.
traer();
requestAnimationFrame(bucle);

// La lista de chats es lo menos importante de la pantalla: se dispara y se
// pinta cuando llega, y si no llega el resto no se entera.
fetch("/api/chats")
  .then(r => (r.ok ? r.json() : null))
  .then(datos => { if (datos) pintarChats(datos); })
  .catch(() => { listaChats.innerHTML = '<div class="chat">sin chats</div>'; });

pintarMesa();
pintarPlantel();
pintarPerillas();
// Se pintan (y con ellas, los badges) desde el arranque y sin esperar a
// que Pedro toque "Todo" o "Permisos": es la unica forma de que se entere
// de algo estacionado SIN buscarlo, si arranca la pantalla en Chat o en
// Mapa. Para el inbox pesa mas todavia -su badge suma las cuatro
// bandejas- porque sin este llamado se queda en blanco hasta que pasen
// los 60 segundos del intervalo, o hasta que Pedro entra a "Todo" y el
// badge ya no le dice nada nuevo.
pintarInbox();
pintarPermisos();

// La mesa no tiene push: sin este refresco, Pedro abre /fabrica, hace otra
// cosa, toca la pestana "Mesa" y ve la foto del momento de la carga (spec
// seccion 9). Lo que la cambia es una rutina del jefe tiqueando, que se
// mide en minutos, no en segundos: 60s alcanza para que una propuesta
// nueva aparezca sin que Pedro tenga que forzar nada, y no pide el bus a
// cada rato mientras la pantalla esta quieta. `.unref?.()` es defensivo:
// en Node (los tests) evita que el timer sostenga el proceso vivo; en el
// navegador `setInterval` devuelve un numero sin ese metodo, y el opcional
// lo saltea sin romper nada.
setInterval(pintarMesa, 60_000).unref?.();
// Las perillas cambian por las mismas razones que la mesa -un cierre
// semanal, un jefe gastando- asi que el mismo refresco de fondo aplica.
setInterval(pintarPerillas, 60_000).unref?.();
// Y el inbox, con el mismo intervalo: es lo unico que mantiene el badge de
// "Todo" al dia si Pedro no vuelve a tocar esa sub-vista.
setInterval(pintarInbox, 60_000).unref?.();
// Y los permisos, con el mismo intervalo: es lo que mantiene el badge al
// dia mientras Pedro esta en otra pestana.
setInterval(pintarPermisos, 60_000).unref?.();

const panelCentro = document.getElementById("panel-centro");
const panelRazonamiento = document.getElementById("razonamiento");
let mirando = null;             // agente_id que se esta leyendo

function mostrarEmpleado(empleado) {
  popupEmpleado.innerHTML = textoDeEmpleado(empleado);
  popupEmpleado.classList.remove("oculto");
  mirando = empleado.agente_id;
  pintarRazonamiento();
  panelRazonamiento.classList.remove("oculto");   // gana al display:none
  panelCentro.dataset.modo = "razonamiento";
  app.dataset.pestana = "chat";     // en el telefono, el panel del medio
}

function pintarRazonamiento() {
  if (!mirando) return;
  const todos = Object.keys(pulso.empleados)
    .flatMap(dep => empleadosDe(pulso, dep));
  const empleado = todos.find(e => e.agente_id === mirando);
  if (!empleado) return;            // el anillo lo olvido: se deja lo ultimo
  panelRazonamiento.innerHTML = textoDeRazonamiento(empleado);
  panelRazonamiento.scrollTop = panelRazonamiento.scrollHeight;
}

/** Salir del modo lectura. Los dos caminos que lo cierran hacen lo mismo. */
function volverAlChat() {
  mirando = null;
  panelCentro.dataset.modo = "chat";
  panelRazonamiento.classList.add("oculto");
  popupEmpleado.classList.add("oculto");
}

panelRazonamiento.addEventListener("click", ev => {
  if (ev.target && ev.target.dataset.accion === "volver") volverAlChat();
});

let pulso = {conectado: false, empleados: {}, foco: null, seq: 0};
let ultimoFoco = 0;

const conexionPulso = crearPulso(estado => {
  pulso = estado;
  if (pulso.foco && pulso.foco.seq !== ultimoFoco) {
    ultimoFoco = pulso.foco.seq;
    volarAEdificio(pulso.foco.departamento);
  }
  pintarRazonamiento();
});

/** El foco de la conversacion mueve la camara (spec seccion 8). */
function volarAEdificio(id) {
  if (!ciudad) return;
  const e = ciudad.edificios.find(x => x.id === id);
  if (!e) return;              // la ciudad puede no tenerlo todavia
  volarA(cam, {x: e.x, y: e.y, escala: Math.max(cam.escala, 2)});
}

// Solo para arranque.test.js: la camara es interna y sin esto el test del
// foco no puede afirmar nada mas que "el chat no se entero", que es la
// mitad que no importa. Es de lectura y no la deja tocar.
export const camaraDePrueba = () => cam;
