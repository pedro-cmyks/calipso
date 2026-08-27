/**
 * calipso/web/fabrica/plantel.js — La tira de controles del plantel.
 *
 * Lo que decide QUE se muestra vive aca y es puro; el DOM, los fetch y los
 * listeners los tiene app.js. El modo lo escribe Pedro por un input y
 * vuelve por la red, asi que TODO lo que sale por innerHTML pasa por
 * escapar().
 */
import {escapar} from "./paneles.js";

export function textoDePlantel(estado) {
  if (!estado || estado.activo === false) {
    return '<div class="estado">El plantel no esta disponible.</div>';
  }
  const prendido = estado.encendido ? "encendido" : "apagado";
  const peligro = estado.modo === "vivo"
    ? '<div class="peligro">En vivo: la fabrica gasta sola.</div>' : "";
  // El mismo criterio que ya usaba el boton de modo: se ofrece la accion
  // CONTRARIA al estado actual, nunca las dos parar/reanudar juntas. Con
  // las dos siempre presentes, la mitad de las veces Pedro aprieta la que
  // ya esta en efecto y no pasa nada -ni en el servidor ni en la pantalla-
  // y eso se lee como un boton roto.
  const interruptor = estado.encendido
    ? `<button type="button" data-plantel="parar">parar</button>`
    : `<button type="button" data-plantel="reanudar">reanudar</button>`;
  return `<div class="estado">${prendido} · modo ${escapar(estado.modo)} ` +
    `· techo ${escapar(String(estado.techo_tics))} tics</div>` + peligro +
    `<div class="botones">` + interruptor +
    `<button type="button" data-plantel="modo" data-modo="${estado.modo === "vivo"
      ? "ensayo" : "vivo"}">pasar a ${estado.modo === "vivo"
      ? "ensayo" : "vivo"}</button>` +
    `</div>` +
    `<form data-plantel="rutina">` +
    `<input name="cuenta" placeholder="dep:atlas" required>` +
    `<input name="minutos" type="number" value="60" min="1" required>` +
    `<button type="submit">crear rutina</button></form>`;
}
