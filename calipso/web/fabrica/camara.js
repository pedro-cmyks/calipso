/**
 * calipso/web/fabrica/camara.js — Paneo, zoom y vuelo.
 *
 * Aritmetica pura: ni canvas ni DOM, para que se pueda testear entera.
 * `cam.x` y `cam.y` son el punto del MUNDO que queda en el centro de la
 * vista. El vuelo converge exacto —al terminar, las coordenadas son las
 * del destino, no una aproximacion— porque el foco tiene que aterrizar
 * donde dijo que iba.
 */

export const ESCALA_MIN = 0.2;
export const ESCALA_MAX = 6;

export function crearCamara(x = 0, y = 0, escala = 1) {
  return {x, y, escala, vuelo: null};
}

export function aPantalla(cam, mundo, vista) {
  return {x: (mundo.x - cam.x) * cam.escala + vista.ancho / 2,
          y: (mundo.y - cam.y) * cam.escala + vista.alto / 2};
}

export function aMundo(cam, pantalla, vista) {
  return {x: (pantalla.x - vista.ancho / 2) / cam.escala + cam.x,
          y: (pantalla.y - vista.alto / 2) / cam.escala + cam.y};
}

export function arrastrar(cam, dx, dy) {
  cam.x -= dx / cam.escala;
  cam.y -= dy / cam.escala;
  cam.vuelo = null;               // la mano manda sobre el vuelo
  return cam;
}

export function acercar(cam, factor, punto, vista) {
  const antes = aMundo(cam, punto, vista);
  cam.escala = Math.max(ESCALA_MIN, Math.min(ESCALA_MAX, cam.escala * factor));
  const despues = aMundo(cam, punto, vista);
  cam.x += antes.x - despues.x;   // el punto bajo el dedo no se mueve
  cam.y += antes.y - despues.y;
  cam.vuelo = null;
  return cam;
}

export function volarA(cam, destino, ms = 600) {
  cam.vuelo = {
    desde: {x: cam.x, y: cam.y, escala: cam.escala},
    hasta: {x: destino.x, y: destino.y,
            escala: destino.escala === undefined ? cam.escala : destino.escala},
    ms, t: 0,
  };
  return cam;
}

/** Easing: arranca rapido y frena al llegar. */
export function suave(u) {
  const v = 1 - u;
  return 1 - v * v * v;
}

/** Avanza el vuelo `dt` milisegundos. Devuelve si habia algo que avanzar. */
export function paso(cam, dt) {
  const v = cam.vuelo;
  if (!v) return false;
  v.t = Math.min(v.ms, v.t + dt);
  const u = v.ms === 0 ? 1 : v.t / v.ms;
  const k = suave(u);
  cam.x = v.desde.x + (v.hasta.x - v.desde.x) * k;
  cam.y = v.desde.y + (v.hasta.y - v.desde.y) * k;
  cam.escala = v.desde.escala + (v.hasta.escala - v.desde.escala) * k;
  if (u >= 1) {
    cam.x = v.hasta.x;            // exacto, no "casi"
    cam.y = v.hasta.y;
    cam.escala = v.hasta.escala;
    cam.vuelo = null;
  }
  return true;
}

/** El pixel no se deforma: los sprites se pintan a escala entera. */
export function escalaEntera(cam) {
  return Math.max(1, Math.round(cam.escala));
}

/**
 * Donde poner la camara para que la ciudad entera entre en la vista.
 * Se llama cuando llega el modelo: el mundo que emite el urbanismo mide
 * lo que mida, y hardcodear una posicion inicial deja medio mapa afuera.
 */
export function encuadrar(edificios, vista, margen = 60) {
  if (!edificios.length) return {x: 0, y: 0, escala: 1};
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const e of edificios) {
    x0 = Math.min(x0, e.x); x1 = Math.max(x1, e.x);
    y0 = Math.min(y0, e.y); y1 = Math.max(y1, e.y);
  }
  const util = {ancho: Math.max(1, vista.ancho - margen * 2),
                alto: Math.max(1, vista.alto - margen * 2)};
  const ancho = x1 - x0, alto = y1 - y0;
  const cabe = Math.min(ancho > 0 ? util.ancho / ancho : ESCALA_MAX,
                        alto > 0 ? util.alto / alto : ESCALA_MAX);
  const escala = Math.max(ESCALA_MIN, Math.min(ESCALA_MAX, cabe));
  return {x: (x0 + x1) / 2, y: (y0 + y1) / 2, escala};
}
