/**
 * calipso/web/fabrica/sprites.js — De un edificio a una matriz de pixeles.
 *
 * Perspectiva forzada: el volumen esta horneado en el sprite (cara
 * frontal, lateral oscurecido y techo aclarado), no armado con tiles
 * isometricos. La funcion es pura y devuelve datos, no dibujo: por eso se
 * puede testear sin navegador y por eso el mismo modelo da siempre el
 * mismo bitmap. Nada de Math.random ni de reloj aca adentro.
 */
import {TRANSPARENTE, FRENTE, LATERAL, TECHO, VENTANA, PRENDIDA, BORDE,
        GRIETA, PISO, ESCRITORIO, OCUPADO, ESPERA} from "./paleta.js";

export const ANCHO = 16;      // ancho de la cara frontal, en pixeles
export const PROF = 6;        // cuanto se corre la perspectiva
export const ALTO_BASE = 6;   // planta baja
export const ALTO_PISO = 4;   // cada piso que suma el tamano

const VENT_ANCHO = 3;
const VENT_ALTO = 2;
const VENT_COLS = 3;

export const ESC_ANCHO = 3;
export const ESC_ALTO = 2;
export const ESC_COLS = 3;

/** FNV-1a de 32 bits. Estable entre navegadores y entre corridas. */
export function fnv1a(texto) {
  let h = 0x811c9dc5;
  for (let i = 0; i < texto.length; i++) {
    h ^= texto.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

function pisosDe(tamano) {
  return Math.max(1, Math.min(9, Math.trunc(tamano) || 1));
}

export function alturaDe(tamano) {
  return ALTO_BASE + pisosDe(tamano) * ALTO_PISO;
}

export function medidas(edificio) {
  const altoFrente = alturaDe(edificio.tamano);
  return {ancho: ANCHO + PROF, alto: altoFrente + PROF, altoFrente};
}

export function edificioSprite(edificio) {
  const {ancho, alto, altoFrente} = medidas(edificio);
  const pix = new Uint8Array(ancho * alto);   // arranca todo en TRANSPARENTE
  const en = (x, y, v) => {
    if (x >= 0 && x < ancho && y >= 0 && y < alto) pix[y * ancho + x] = v;
  };
  const congelado = edificio.estado === "congelado";
  const arriba = PROF;                        // primera fila de la cara frontal

  // cara frontal
  for (let y = arriba; y < arriba + altoFrente; y++)
    for (let x = 0; x < ANCHO; x++) en(x, y, FRENTE);

  // cara lateral: se corre un pixel arriba por cada pixel a la derecha
  for (let d = 1; d <= PROF; d++)
    for (let y = arriba; y < arriba + altoFrente; y++)
      en(ANCHO - 1 + d, y - d, LATERAL);

  // techo: el mismo corrimiento, apoyado en el borde de arriba del frente
  for (let d = 1; d <= PROF; d++)
    for (let x = 0; x < ANCHO; x++) en(x + d, arriba - d, TECHO);

  // ventanas: patron estable derivado del id, encendido segun la actividad
  const h = fnv1a(edificio.id);
  const act = congelado ? 0 : Math.max(0, Math.min(3, edificio.actividad || 0));
  const pisos = pisosDe(edificio.tamano);
  for (let p = 0; p < pisos; p++) {
    for (let c = 0; c < VENT_COLS; c++) {
      const sorteo = (h >>> ((p * VENT_COLS + c) % 29)) & 3;
      const v = (act > 0 && sorteo < act) ? PRENDIDA : VENTANA;
      const x0 = 2 + c * 5;
      const y0 = arriba + 2 + p * ALTO_PISO;
      for (let dy = 0; dy < VENT_ALTO; dy++)
        for (let dx = 0; dx < VENT_ANCHO; dx++) en(x0 + dx, y0 + dy, v);
    }
  }

  // contorno del frente, para que los edificios no se fundan entre si
  for (let x = 0; x < ANCHO; x++) {
    en(x, arriba, BORDE);
    en(x, arriba + altoFrente - 1, BORDE);
  }
  for (let y = arriba; y < arriba + altoFrente; y++) {
    en(0, y, BORDE);
    en(ANCHO - 1, y, BORDE);
  }

  // grieta: una sola linea que baja en zigzag por la cara frontal
  if (congelado) {
    let x = 3 + (h % (ANCHO - 6));
    for (let i = 0; i < altoFrente; i++) {
      en(x, arriba + i, GRIETA);
      x += (fnv1a(edificio.id + ":" + i) & 1) ? 1 : -1;
      x = Math.max(1, Math.min(ANCHO - 2, x));
    }
  }

  return {ancho, alto, pix};
}

/**
 * Donde va cada escritorio, en pixeles del sprite. Misma grilla que las
 * ventanas: una ventana prendida ES un escritorio ocupado, y que las dos
 * cosas coincidan es lo que hace que acercarse se lea como entrar.
 * De arriba hacia abajo, para que el que llego primero se siente arriba.
 */
export function plazasDe(edificio) {
  const pisos = pisosDe(edificio.tamano);
  const arriba = PROF;
  const salida = [];
  // p = 0 es el piso de mas arriba (la y mas chica), igual que en las
  // ventanas de `edificioSprite`. Recorrerlo al reves dejaria a p[0] abajo y
  // el contrato dice "de arriba hacia abajo"
  for (let p = 0; p < pisos; p++) {
    for (let c = 0; c < ESC_COLS; c++) {
      salida.push({x: 2 + c * 5, y: arriba + 2 + p * ALTO_PISO});
    }
  }
  return salida;
}

/**
 * El mismo edificio, sin techo y con la gente adentro. `estados` es la lista
 * de estados de los empleados, en el orden en que se sientan; los que no
 * entran no se dibujan (el popup igual los lista).
 */
export function interiorSprite(edificio, estados = []) {
  const {ancho, alto, altoFrente} = medidas(edificio);
  const pix = new Uint8Array(ancho * alto);
  const en = (x, y, v) => {
    if (x >= 0 && x < ancho && y >= 0 && y < alto) pix[y * ancho + x] = v;
  };
  const arriba = PROF;
  // el hueco: donde estaba la cara frontal ahora se ve el piso
  for (let y = arriba; y < arriba + altoFrente; y++)
    for (let x = 0; x < ANCHO; x++) en(x, y, PISO);
  // el contorno se queda: sin el, el edificio se funde con el de al lado
  for (let x = 0; x < ANCHO; x++) {
    en(x, arriba, BORDE);
    en(x, arriba + altoFrente - 1, BORDE);
  }
  for (let y = arriba; y < arriba + altoFrente; y++) {
    en(0, y, BORDE);
    en(ANCHO - 1, y, BORDE);
  }
  const plazas = plazasDe(edificio);
  for (let i = 0; i < plazas.length; i++) {
    const estado = estados[i];
    // tres estados, que son los que enumera el spec: el que piensa se ve
    // prendido, el que espera ocupado pero apagado, y el que se fue deja el
    // escritorio vacio — ver que el departamento SOLTO gente es tan
    // informativo como verlo contratar
    const v = estado === "razonando" ? OCUPADO
      : estado === "esperando" ? ESPERA : ESCRITORIO;
    for (let dy = 0; dy < ESC_ALTO; dy++)
      for (let dx = 0; dx < ESC_ANCHO; dx++)
        en(plazas[i].x + dx, plazas[i].y + dy, v);
  }
  return {ancho, alto, pix};
}

/** La unica funcion del modulo que toca un canvas. Escala SIEMPRE entera. */
export function pintar(ctx, sprite, rampa, x, y, escala) {
  const e = Math.max(1, Math.round(escala));
  for (let j = 0; j < sprite.alto; j++) {
    for (let i = 0; i < sprite.ancho; i++) {
      const v = sprite.pix[j * sprite.ancho + i];
      if (v === TRANSPARENTE) continue;
      ctx.fillStyle = rampa[v];
      ctx.fillRect(x + i * e, y + j * e, e, e);
    }
  }
}
