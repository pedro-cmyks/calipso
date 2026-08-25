/**
 * calipso/web/fabrica/app.js — El pegamento.
 *
 * Engancha los eventos del navegador con los modulos puros. Toda la
 * logica que se puede testear vive en los otros archivos; aca solo hay
 * cableado.
 */
import {crearCamara, arrastrar, acercar, paso, encuadrar} from "./camara.js";
import {cargarCiudad, enPunto} from "./ciudad.js";
import {crearMapa} from "./mapa.js";

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
});

function soltar(ev) {
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
});

lienzo.addEventListener("wheel", ev => {
  ev.preventDefault();
  acercar(cam, ev.deltaY < 0 ? 1.12 : 1 / 1.12, local(ev), mapa.vista());
}, {passive: false});

await traer();
requestAnimationFrame(bucle);
