/**
 * calipso/web/fabrica/paleta.js — Los colores de la ciudad.
 *
 * Un sprite es una matriz de estos indices, no de colores: la forma se
 * decide una vez y la estetica se puede cambiar entera tocando solo este
 * archivo. Cero imagenes: todo se dibuja por codigo.
 */

export const TRANSPARENTE = 0;
export const FRENTE = 1;
export const LATERAL = 2;
export const TECHO = 3;
export const VENTANA = 4;
export const PRENDIDA = 5;
export const BORDE = 6;
export const GRIETA = 7;

export const RAMPAS = {
  // la fabrica es acero frio; lo personal es calido y aparte
  fabrica: {
    [FRENTE]: "#3d4f63", [LATERAL]: "#26313d", [TECHO]: "#566e88",
    [VENTANA]: "#1b2430", [PRENDIDA]: "#ffd75f", [BORDE]: "#12181f",
    [GRIETA]: "#12181f",
  },
  personal: {
    [FRENTE]: "#5a4668", [LATERAL]: "#382a43", [TECHO]: "#78608a",
    [VENTANA]: "#241c2b", [PRENDIDA]: "#c9a3e0", [BORDE]: "#180f1d",
    [GRIETA]: "#180f1d",
  },
  // un departamento quebrado se ve quebrado: gris, sin luz, agrietado
  congelado: {
    [FRENTE]: "#3a3a3a", [LATERAL]: "#262626", [TECHO]: "#4d4d4d",
    [VENTANA]: "#1c1c1c", [PRENDIDA]: "#1c1c1c", [BORDE]: "#0f0f0f",
    [GRIETA]: "#0a0a0a",
  },
};

export function rampaDe(edificio) {
  if (edificio.estado === "congelado") return RAMPAS.congelado;
  return RAMPAS[edificio.zona] || RAMPAS.fabrica;
}
