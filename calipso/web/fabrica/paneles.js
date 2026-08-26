/**
 * calipso/web/fabrica/paneles.js — La disposicion y los avisos.
 *
 * Todo lo que decide QUE se muestra vive aca y es puro; el DOM lo toca
 * app.js. El nombre de un departamento lo escribe Pedro, asi que se
 * escapa antes de meterlo en el HTML de la tarjeta.
 */
import {monedas} from "./ciudad.js";

export const ANCHO_TELEFONO = 820;   // el mismo corte que el media query

export function disposicion(ancho) {
  return ancho > ANCHO_TELEFONO ? "tres-paneles" : "dos-pestanas";
}

export function escapar(texto) {
  return String(texto)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fila(etiqueta, valor) {
  return `<div class="fila"><span>${escapar(etiqueta)}</span>` +
         `<span>${escapar(valor)}</span></div>`;
}

export function textoDeTarjeta(ficha) {
  if (!ficha) return "";
  const estado = ficha.estado === "congelado"
    ? '<div class="congelado">congelado</div>' : "";
  return `<div class="nombre">${escapar(ficha.nombre)}</div>` + estado +
    fila("saldo", ficha.saldo) +
    fila("gasto del ciclo", ficha.gasto_ciclo) +
    fila("ventas de la ventana", ficha.ventas_ventana) +
    fila("eficiencia", ficha.eficiencia) +
    fila("trabajos", ficha.trabajos) +
    fila("compuertas", ficha.compuertas);
}

export function posicionDeTarjeta(x, y, caja, tarjeta) {
  const margen = 12;
  let px = x + margen, py = y + margen;
  if (px + tarjeta.ancho > caja.ancho) px = x - margen - tarjeta.ancho;
  if (py + tarjeta.alto > caja.alto) py = y - margen - tarjeta.alto;
  return {x: Math.max(0, Math.min(px, caja.ancho - tarjeta.ancho)),
          y: Math.max(0, Math.min(py, caja.alto - tarjeta.alto))};
}

export function resumenDeAvisos(ciudad) {
  return [...(ciudad.avisos || [])]
    .sort((a, b) => (b.monedas_en_juego_mm - a.monedas_en_juego_mm) ||
                    (a.id < b.id ? -1 : 1))
    .map(a => ({
      id: a.id, sobre: a.sobre,
      texto: `${a.tipo}${a.sobre ? " en " + a.sobre.split(":").pop() : ""}` +
             ` — ${monedas(a.monedas_en_juego_mm)}`,
    }));
}
