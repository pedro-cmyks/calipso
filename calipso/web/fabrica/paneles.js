/**
 * calipso/web/fabrica/paneles.js — La disposicion y los avisos.
 *
 * Todo lo que decide QUE se muestra vive aca y es puro; el DOM lo toca
 * app.js. El nombre de un departamento lo escribe Pedro, asi que se
 * escapa antes de meterlo en el HTML de la tarjeta y de la etiqueta de foco.
 */
import {monedas} from "./ciudad.js";

const NUMERO = new Intl.NumberFormat("es", {maximumFractionDigits: 0,
                                            useGrouping: "always"});

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

/** El costo del turno, corriendo. Vacio antes del primer turno: una barra
 *  que dice "0 tokens" ocupa lugar para no decir nada. */
export function textoDeCosto(estado) {
  if (!estado || (!estado.ruta && !estado.tokens)) return "";
  const partes = [estado.ruta, estado.modelo,
                  `${NUMERO.format(estado.tokens || 0)} tokens`];
  if (estado.costo_usd) partes.push(`${estado.costo_usd.toFixed(4)} USD`);
  if (estado.cuenta) {
    partes.push(`paga ${estado.cuenta.split(":").pop()}` +
                (estado.costo_mm ? ` ${monedas(estado.costo_mm)}` : ""));
  }
  return partes.filter(Boolean).join(" · ");
}

/** La etiqueta de que departamento esta fijado como contexto. */
export function textoDeFoco(ficha) {
  if (!ficha) return "";
  return `<span>hablando sobre <b>${escapar(ficha.nombre)}</b>` +
         ` — saldo ${escapar(ficha.saldo)}</span>` +
         `<button type="button" data-accion="quitar">quitar</button>`;
}

const SEGUNDOS = new Intl.NumberFormat("es", {maximumFractionDigits: 1});

function segundos(ms) {
  return SEGUNDOS.format((ms || 0) / 1000) + " s";
}

/** El popup: lo que se ve del empleado sin abandonar el mapa. */
export function textoDeEmpleado(empleado) {
  if (!empleado) return "";
  const e = empleado;
  return `<div class="nombre">${escapar(e.rol || "agente")}</div>` +
    `<div class="estado ${escapar(e.estado)}">${escapar(e.estado)}</div>` +
    fila("modelo", e.modelo || "sin dato") +
    fila("corriendo", segundos(e.runtime_ms)) +
    fila("tokens", `${NUMERO.format(e.tokens_in || 0)} / ` +
                   `${NUMERO.format(e.tokens_out || 0)}`) +
    fila("costo", monedas(e.costo_mm || 0)) +
    (e.diff ? fila("toco", e.diff.ruta) : "");
}
