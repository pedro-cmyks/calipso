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
  // si el dueno no esta en la lista de departamentos de fabrica, ninguna
  // opcion coincide con el; sin una seleccion EXPLICITA el navegador elige
  // la primera solo, y financiar paga desde ahi sin ningun indicio
  const dueno = departamentos.some(d => d.cuenta === propuesta.departamento);
  const opciones = departamentos.map((d, i) => {
    const elegido = dueno ? d.cuenta === propuesta.departamento : i === 0;
    return `<option value="${escapar(d.cuenta)}"${elegido ? " selected" : ""}>` +
           `${escapar(d.nombre)}</option>`;
  }).join("");
  const aviso = dueno ? "" : `<div class="aviso">el dueno ` +
    `(${escapar(propuesta.departamento)}) no esta en la lista: revisa ` +
    `quien paga antes de financiar</div>`;
  return aviso + `<select class="paga" data-id="${escapar(propuesta.id)}">` +
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
  // Dos filas a proposito, en vez de una sola que se parte sola cuando no
  // entra: "paga" + el selector arriba, los dos botones abajo. Asi el
  // ancho angosto de escritorio (donde antes "descartar" se caia a una
  // segunda linea desprolija) y el dedo en el telefono (que necesita los
  // 40px de alto) quedan resueltos con el MISMO marcado.
  return `<div class="propuesta" ` +
    `data-presupuesto="${escapar(propuesta.presupuesto_mm)}">` +
    `<div class="cabeza"><b>${dep}</b> · ${escapar(propuesta.titulo)}</div>` +
    `<div class="datos">presupuesto ${plata}</div>` + aviso +
    `<div class="acciones">` +
    `<div class="pagar">paga ${selector(propuesta, departamentos)}</div>` +
    `<div class="botones">` +
    `<button data-accion="financiar" data-id="${escapar(propuesta.id)}">` +
    `financiar</button>` +
    `<button data-accion="descartar" data-id="${escapar(propuesta.id)}">` +
    `descartar</button></div></div></div>`;
}

export function hayQueAvisarDeLaSemana(datos) {
  return Boolean(datos && datos.activa && datos.semana_abierta === false);
}

/** El nombre del departamento para el encabezado del filtro: el de la
 *  lista de fabrica si esta, o el id pelado (sin "dep:") si no -por
 *  ejemplo cuando el edificio tocado es el personal de Pedro, que nunca
 *  es dueno de ninguna propuesta pero igual se puede tocar en el mapa. */
function nombreDeDepartamento(id, departamentos) {
  const d = departamentos.find(x => x.cuenta === id);
  return d ? d.nombre : id.replace(/^dep:/, "");
}

/**
 * `filtro`: la cuenta del departamento tocado en el mapa (`enFoco` en
 * app.js), o null/undefined para ver la mesa entera -el estado de hoy.
 * Acotar la lista es solo un filtro sobre lo que ya trajo el bus: el
 * campo `departamento` de cada propuesta ya viene del servidor (spec del
 * punto 4), asi que no hace falta ningun pedido nuevo.
 */
export function textoDeMesa(datos, filtro = null) {
  if (!datos || !datos.activa) {
    return `<div class="vacio">La economia no esta activa.</div>`;
  }
  const deps = datos.departamentos || [];
  const todas = datos.propuestas || [];
  const props = filtro ? todas.filter(p => p.departamento === filtro) : todas;
  const semana = hayQueAvisarDeLaSemana(datos)
    ? `<div class="aviso semana">La semana ${escapar(datos.semana)} no esta ` +
      `abierta: financiar va a fallar hasta que la abras.` +
      `<button data-accion="abrir-semana">abrir la semana</button></div>`
    : "";
  // El boton "ver todas" tiene que estar SIEMPRE que hay un filtro activo,
  // incluso si el departamento no tiene ninguna propuesta: sin el, tocar
  // un edificio sin propuestas deja a Pedro mirando una mesa vacia sin
  // forma de salir del filtro.
  const cabecera = filtro
    ? `<div class="filtro">mostrando solo ` +
      `<b>${escapar(nombreDeDepartamento(filtro, deps))}</b>` +
      `<button type="button" data-accion="ver-todas">ver todas</button></div>`
    : "";
  if (!props.length) {
    const vacio = filtro
      ? "Este departamento no tiene propuestas en la mesa."
      : "Ninguna propuesta esperando.";
    return semana + cabecera + `<div class="vacio">${vacio}</div>`;
  }
  return semana + cabecera + props.map(p => fila(p, deps)).join("");
}
