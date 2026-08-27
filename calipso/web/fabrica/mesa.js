/**
 * calipso/web/fabrica/mesa.js — La mesa de Pedro.
 *
 * Lo que decide QUE se muestra vive aca y es puro; el DOM lo toca app.js.
 * El titulo de una propuesta lo escribe un modelo local, asi que TODO lo que
 * sale por innerHTML pasa por escapar().
 */
import {escapar} from "./paneles.js";
import {monedas} from "./ciudad.js";

function selector(propuesta, departamentos) {
  const opciones = departamentos.map(d => {
    const elegido = d.cuenta === propuesta.departamento ? " selected" : "";
    return `<option value="${escapar(d.cuenta)}"${elegido}>` +
           `${escapar(d.nombre)}</option>`;
  }).join("");
  return `<select class="paga" data-id="${escapar(propuesta.id)}">` +
         `${opciones}</select>`;
}

function alcanza(propuesta, departamentos) {
  const dueno = departamentos.find(d => d.cuenta === propuesta.departamento);
  return !dueno || dueno.disponible_mm >= propuesta.presupuesto_mm;
}

function fila(propuesta, departamentos) {
  const dep = escapar(propuesta.departamento.replace(/^dep:/, ""));
  const plata = escapar(monedas(propuesta.presupuesto_mm));
  if (propuesta.estado === "financiada") {
    const gastado = escapar(monedas(propuesta.gastado_mm));
    return `<div class="propuesta financiada">` +
      `<div class="cabeza"><b>${dep}</b> · ${escapar(propuesta.titulo)}</div>` +
      `<div class="datos">financiada · ${plata} · gastado ${gastado}</div>` +
      `</div>`;
  }
  const aviso = alcanza(propuesta, departamentos)
    ? "" : `<div class="aviso">sin saldo suficiente</div>`;
  return `<div class="propuesta" ` +
    `data-presupuesto="${escapar(propuesta.presupuesto_mm)}">` +
    `<div class="cabeza"><b>${dep}</b> · ${escapar(propuesta.titulo)}</div>` +
    `<div class="datos">${plata}</div>` + aviso +
    `<div class="acciones">paga ${selector(propuesta, departamentos)}` +
    `<button data-accion="financiar" data-id="${escapar(propuesta.id)}">` +
    `financiar</button>` +
    `<button data-accion="descartar" data-id="${escapar(propuesta.id)}">` +
    `descartar</button></div></div>`;
}

export function hayQueAvisarDeLaSemana(datos) {
  return Boolean(datos && datos.activa && datos.semana_abierta === false);
}

export function textoDeMesa(datos) {
  if (!datos || !datos.activa) {
    return `<div class="vacio">La economia no esta activa.</div>`;
  }
  const deps = datos.departamentos || [];
  const props = datos.propuestas || [];
  const semana = hayQueAvisarDeLaSemana(datos)
    ? `<div class="aviso semana">La semana ${escapar(datos.semana)} no esta ` +
      `abierta: financiar va a fallar hasta que la abras.` +
      `<button data-accion="abrir-semana">abrir la semana</button></div>`
    : "";
  if (!props.length) {
    return semana + `<div class="vacio">Ninguna propuesta esperando.</div>`;
  }
  return semana + props.map(p => fila(p, deps)).join("");
}
