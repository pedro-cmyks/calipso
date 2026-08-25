/**
 * calipso/web/fabrica/mapa.js — El dibujo de la ciudad.
 *
 * La geometria (donde va cada calle, donde esta cada unidad) es pura y se
 * testea; el canvas queda como una capa fina encima. La `fase` de las
 * unidades entra por parametro en vez de leer el reloj adentro: asi el
 * dibujo sigue siendo una funcion de sus argumentos.
 */
import {aPantalla, escalaEntera} from "./camara.js";
import {centroDe, indice, ordenDePintado} from "./ciudad.js";
import {rampaDe} from "./paleta.js";
import {edificioSprite, pintar} from "./sprites.js";

const FONDO = "#0b0f14";
const CALLE = "#2a3038";
const CABLE = "#c9a3e0";
const UNIDAD = "#9ae6a4";
const AVISO = "#ffd75f";
const RESALTE = "#66d9ff";
const RADIO_ORBITA = 22;

// `idx` entra por parametro para que el bucle de dibujo lo calcule una sola
// vez por cuadro en vez de una vez por calle y por unidad.
export function puntosDeCalle(ciudad, cam, vista, idx = indice(ciudad)) {
  const {porId} = idx;
  const out = [];
  for (const c of ciudad.calles) {
    const a = porId.get(c.a), b = porId.get(c.b);
    if (!a || !b) continue;          // una punta que no existe no se dibuja
    out.push({desde: aPantalla(cam, centroDe(a), vista),
              hasta: aPantalla(cam, centroDe(b), vista),
              ancho: c.ancho, tipo: c.tipo});
  }
  return out;
}

/** `fase` va de 0 a 1 y vuelve a empezar. */
export function posicionDeUnidad(unidad, ciudad, cam, vista, fase,
                                 idx = indice(ciudad)) {
  const {porId} = idx;
  const casa = porId.get(unidad.dueno);
  if (!casa) return null;
  const p = aPantalla(cam, centroDe(casa), vista);
  const destino = unidad.hacia ? porId.get(unidad.hacia) : null;
  if (!destino) {
    // sin calle a donde ir, la unidad orbita su propia casa
    const a = fase * Math.PI * 2;
    return {x: p.x + Math.cos(a) * RADIO_ORBITA,
            y: p.y + Math.sin(a) * RADIO_ORBITA};
  }
  const q = aPantalla(cam, centroDe(destino), vista);
  // ida y vuelta, para que la unidad no teletransporte al llegar
  const u = fase <= 0.5 ? fase * 2 : (1 - fase) * 2;
  return {x: p.x + (q.x - p.x) * u, y: p.y + (q.y - p.y) * u};
}

export function crearMapa(canvas) {
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;     // pixel art: nada de interpolar
  const cache = new Map();               // sprites ya rasterizados

  function vista() {
    return {ancho: canvas.clientWidth, alto: canvas.clientHeight};
  }

  /**
   * DEUDA DECLARADA: el dpr se redondea a entero. Los aparatos de Pedro
   * (el Ally, el iPhone, el Mac) tienen todos dpr entero, y redondear
   * mantiene la escala de dibujo entera con un solo sistema de
   * coordenadas. En una pantalla con dpr fraccionario (Windows al 150%)
   * el navegador reescala el lienzo entero y el pixel art pierde nitidez.
   * El arreglo completo es pintar en pixeles fisicos, y cuesta manejar
   * dos sistemas de coordenadas a la vez.
   */
  function dpr() {
    return Math.max(1, Math.min(3, Math.round(window.devicePixelRatio || 1)));
  }

  // reasigna el bitmap SOLO si cambio de tamano: asignar canvas.width lo
  // borra entero y es caro, y aca se llama en cada cuadro
  function ajustar() {
    const d = dpr(), v = vista();
    const ancho = Math.round(v.ancho * d), alto = Math.round(v.alto * d);
    if (canvas.width === ancho && canvas.height === alto) return;
    canvas.width = ancho;
    canvas.height = alto;
    ctx.setTransform(d, 0, 0, d, 0, 0);
    ctx.imageSmoothingEnabled = false;
  }

  /** Un edificio se dibuja una vez por combinacion y despues se copia. */
  function rasterizar(e, esc) {
    const clave = `${e.id}|${e.zona}|${e.estado}|${e.tamano}|${e.actividad}|${esc}`;
    const guardado = cache.get(clave);
    if (guardado) return guardado;
    const sprite = edificioSprite(e);
    const fuera = document.createElement("canvas");
    fuera.width = sprite.ancho * esc;
    fuera.height = sprite.alto * esc;
    const octx = fuera.getContext("2d");
    octx.imageSmoothingEnabled = false;
    pintar(octx, sprite, rampaDe(e), 0, 0, esc);
    const listo = {lienzo: fuera, ancho: fuera.width, alto: fuera.height};
    if (cache.size > 300) cache.clear();   // techo simple; la ciudad es chica
    cache.set(clave, listo);
    return listo;
  }

  function dibujar(ciudad, cam, resaltado = null, fase = 0) {
    ajustar();
    const v = vista();
    ctx.fillStyle = FONDO;
    ctx.fillRect(0, 0, v.ancho, v.alto);
    const esc = escalaEntera(cam);
    const idx = indice(ciudad);            // una vez por cuadro, no por item
    const {avisosPorId} = idx;

    for (const s of puntosDeCalle(ciudad, cam, v, idx)) {
      ctx.strokeStyle = s.tipo === "cable" ? CABLE : CALLE;
      ctx.lineWidth = s.ancho * esc;
      ctx.setLineDash(s.tipo === "cable" ? [6 * esc, 4 * esc] : []);
      ctx.beginPath();
      ctx.moveTo(s.desde.x, s.desde.y);
      ctx.lineTo(s.hasta.x, s.hasta.y);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    for (const e of ordenDePintado(ciudad.edificios)) {
      const r = rasterizar(e, esc);
      const p = aPantalla(cam, centroDe(e), v);
      const x = Math.round(p.x - r.ancho / 2);
      const y = Math.round(p.y - r.alto);
      if (x + r.ancho < 0 || x > v.ancho ||
          y + r.alto < 0 || y > v.alto) continue;
      ctx.drawImage(r.lienzo, x, y);
      if (e.id === resaltado) {
        ctx.strokeStyle = RESALTE;
        ctx.lineWidth = 2;
        ctx.strokeRect(x - 2, y - 2, r.ancho + 4, r.alto + 4);
      }
      const avisos = avisosPorId.get(e.id) || 0;
      for (let i = 0; i < avisos; i++) {
        ctx.fillStyle = AVISO;
        ctx.fillRect(x + i * 5 * esc, y - 6 * esc, 3 * esc, 3 * esc);
      }
    }

    for (const u of ciudad.unidades) {
      const p = posicionDeUnidad(u, ciudad, cam, v, fase, idx);
      if (!p) continue;
      ctx.fillStyle = UNIDAD;
      ctx.fillRect(Math.round(p.x) - esc, Math.round(p.y) - esc,
                   2 * esc, 2 * esc);
    }
  }

  return {dibujar, vista};
}
