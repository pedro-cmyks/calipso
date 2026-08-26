/**
 * calipso/web/fabrica/interior.js — Entrar a un departamento.
 *
 * El "entrar" es un acercamiento continuo, no un cambio de pantalla: al
 * pasar el umbral el techo se desvanece y aparece el interior. Todo lo de
 * aca es aritmetica pura; el dibujo lo hace mapa.js.
 */
import {aPantalla, escalaEntera} from "./camara.js";
import {centroDe} from "./ciudad.js";
import {ESC_ALTO, ESC_ANCHO, medidas, plazasDe} from "./sprites.js";

export const UMBRAL = 3;        // escala a partir de la cual se esta adentro
export const FUNDIDO = 0.8;     // cuanto dura el desvanecido, en escala

/** 1 = techo entero, 0 = adentro. Monotona: acercarse nunca vuelve a tapar. */
export function opacidadDeTecho(escala) {
  if (escala >= UMBRAL) return 0;
  if (escala <= UMBRAL - FUNDIDO) return 1;
  return (UMBRAL - escala) / FUNDIDO;
}

export const plazas = plazasDe;

/** El indice del escritorio bajo el punto, o null. */
export function escritorioEnPunto(edificio, cam, vista, px, py) {
  const esc = escalaEntera(cam);
  const m = medidas(edificio);
  const p = aPantalla(cam, centroDe(edificio), vista);
  const x0 = p.x - (m.ancho * esc) / 2;
  const y0 = p.y - m.alto * esc;
  const lugares = plazasDe(edificio);
  for (let i = 0; i < lugares.length; i++) {
    const ex = x0 + lugares[i].x * esc, ey = y0 + lugares[i].y * esc;
    if (px >= ex && px < ex + ESC_ANCHO * esc &&
        py >= ey && py < ey + ESC_ALTO * esc) return i;
  }
  return null;
}
