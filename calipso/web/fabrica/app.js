/**
 * calipso/web/fabrica/app.js — El pegamento.
 *
 * Engancha los eventos del navegador con los modulos puros. Toda la
 * logica que se puede testear vive en los otros archivos; aca solo hay
 * cableado.
 */
import {crearCamara, arrastrar, acercar, paso, encuadrar} from "./camara.js";
import {cargarCiudad, enPunto, fichaDe} from "./ciudad.js";
import {crearMapa} from "./mapa.js";
import {disposicion, escapar, textoDeTarjeta, posicionDeTarjeta,
        resumenDeAvisos} from "./paneles.js";
import {crearChat} from "./chat.js";

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
  if (ciudad) mapa.dibujar(ciudad, cam, resaltado, (ahora / 4000) % 1);
  requestAnimationFrame(bucle);
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

function pintarTarjeta(px, py) {
  const ficha = (ciudad && resaltado) ? fichaDe(ciudad, resaltado) : null;
  if (!ficha) { tarjeta.classList.add("oculto"); return; }
  tarjeta.innerHTML = textoDeTarjeta(ficha);
  tarjeta.classList.remove("oculto");   // visible antes de medirla
  if (!tarjetaSigueAlPuntero()) {
    tarjeta.style.left = "10px";
    tarjeta.style.top = "10px";
    return;
  }
  const caja = lienzo.getBoundingClientRect();
  const p = posicionDeTarjeta(px, py, {ancho: caja.width, alto: caja.height},
                              {ancho: tarjeta.offsetWidth,
                               alto: tarjeta.offsetHeight});
  tarjeta.style.left = p.x + "px";
  tarjeta.style.top = p.y + "px";
}

const conversacion = document.getElementById("conversacion");
const formulario = document.getElementById("entrada");
const campo = document.getElementById("texto");

const chat = crearChat(estado => {
  conversacion.innerHTML = estado.turnos
    .map(t => `<div class="turno ${t.quien === "pedro" ? "mio" : ""}` +
              `${t.quien === "error" ? " error" : ""}">` +
              `${escapar(t.texto)}</div>`)
    .join("");
  conversacion.scrollTop = conversacion.scrollHeight;
  // el estado de conexion se pinta DESDE el estado. El aviso que agrega el
  // submit es pasajero y el proximo render lo borra; esto no, y por eso es
  // lo que Pedro mira para saber si Calipso lo esta escuchando.
  formulario.classList.toggle("sin-conexion", !estado.conectado);
  campo.placeholder = estado.conectado
    ? "Escribi a Calipso" : "Sin conexion con Calipso";
});

formulario.addEventListener("submit", ev => {
  ev.preventDefault();
  if (chat.enviar(campo.value)) {
    campo.value = "";
    return;
  }
  // enviar() no toca los turnos cuando no hay conexion: el aviso se pinta
  // aparte para no perder el texto que Pedro todavia no pudo mandar
  const aviso = document.createElement("div");
  aviso.className = "turno error";
  aviso.textContent = "sin conexion con Calipso: el mensaje no se envio";
  conversacion.appendChild(aviso);
  conversacion.scrollTop = conversacion.scrollHeight;
});

const listaChats = document.getElementById("lista-chats");
try {
  const r = await fetch("/api/chats");
  if (r.ok) {
    const datos = await r.json();
    listaChats.innerHTML = (datos.chats || [])
      .map(c => `<div class="chat${c.id === datos.active ? " activo" : ""}"` +
                ` data-id="${escapar(c.id)}">` +
                `${escapar(c.title || "sin titulo")}</div>`)
      .join("");
  }
} catch (e) {
  listaChats.innerHTML = '<div class="chat">sin chats</div>';
}

await traer();
requestAnimationFrame(bucle);
