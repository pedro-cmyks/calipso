/**
 * calipso/web/fabrica/perillas.js — Las dos perillas de Pedro.
 *
 * El tesoro de la fabrica y su banco personal, las dos en la misma
 * pantalla, mas las dos suscripciones que ya paga de su bolsillo. Lo que
 * decide QUE se muestra vive aca y es puro; el DOM, los fetch y los
 * listeners los tiene app.js, igual que mesa.js y plantel.js. Los numeros
 * que llegan del servidor son de confianza (no los escribe un modelo),
 * pero TODO lo que sale por innerHTML pasa por escapar() igual: la
 * disciplina no depende de si el dato de turno es de fiar.
 */
import {escapar} from "./paneles.js";
import {monedas} from "./ciudad.js";

// Lo que Pedro ya paga de verdad, fuera de la fabrica (spec: "considera que
// ya estoy pagando dos sucripciones"). Nombres canonicos de
// pagador.SUSCRIPCION_POR_CLIENTE ("claude" -> "claude_max", "codex" ->
// "chatgpt_plus"): sembrar con otro nombre deja el cobro de dispatch.py sin
// suscripcion que encontrar. Solo mandamos costo_mensual_mm -el numero que
// Pedro realmente dio-; capacidad_ciclo, reserva_personal y
// costo_api_mm_por_unidad quedan afuera a proposito: son estimaciones que
// ni Pedro ni esta pantalla pueden derivar todavia (el propio servidor las
// marca "A AJUSTAR" en EcoSembrarSuscripcionBody), asi que las pone el
// default del servidor en vez de que esta pantalla invente un numero.
export const SUSCRIPCIONES = [
  {nombre: "claude_max", etiqueta: "Claude Max", costo_mensual_mm: 200_000},
  {nombre: "chatgpt_plus", etiqueta: "ChatGPT Plus", costo_mensual_mm: 20_000},
];

function totalSuscripciones_mm() {
  return SUSCRIPCIONES.reduce((s, x) => s + x.costo_mensual_mm, 0);
}

/** El cuerpo para sembrar: un diccionario nombre -> {costo_mensual_mm},
 *  la forma que pide EcoSembrarBody.suscripciones (dict, no lista). */
export function cuerpoDeSuscripciones() {
  const out = {};
  for (const {nombre, costo_mensual_mm} of SUSCRIPCIONES) {
    out[nombre] = {costo_mensual_mm};
  }
  return out;
}

/** Un texto en monedas (string, con coma decimal) a milimonedas enteros.
 *  null si no es un numero positivo: mentirle a la fabrica con un NaN o un
 *  monto en cero es peor que no dejar mandar el formulario. */
export function aMilimonedas(texto) {
  const limpio = String(texto ?? "").trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(limpio)) return null;
  const mm = Math.round(parseFloat(limpio) * 1000);
  return mm > 0 ? mm : null;
}

/** Igual que `aMilimonedas`, pero el cero es un valor legitimo y no un
 *  error. Hace falta para el techo de pre-seed: cero significa "este
 *  departamento no pide", que es como nacen todos, asi que rechazarlo
 *  dejaria a Pedro sin forma de volver a apagar uno que ya autorizo.
 *  Sigue devolviendo null para lo que no es un numero. */
export function aMilimonedasConCero(texto) {
  const limpio = String(texto ?? "").trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(limpio)) return null;
  return Math.round(parseFloat(limpio) * 1000);
}

/** Un entero positivo de un campo de texto, o null. Las unidades de
 *  capacidad no son monedas: no se dividen por mil ni admiten decimales. */
export function aEntero(texto) {
  const limpio = String(texto ?? "").trim();
  if (!/^\d+$/.test(limpio)) return null;
  return parseInt(limpio, 10);
}

function bloqueSuscripciones() {
  const filas = SUSCRIPCIONES.map(s =>
    `<div class="fila"><span>${escapar(s.etiqueta)}</span>` +
    `<span>${escapar(monedas(s.costo_mensual_mm))}/mes</span></div>`).join("");
  return `<div class="suscripciones">` +
    `<div class="subtitulo">ya pagas de tu bolsillo</div>` + filas +
    `<div class="fila total"><span>total</span>` +
    `<span>${escapar(monedas(totalSuscripciones_mm()))}/mes</span></div>` +
    `</div>`;
}

function filaDato(etiqueta, valor) {
  return `<div class="fila"><span>${escapar(etiqueta)}</span>` +
         `<span>${escapar(valor)}</span></div>`;
}

function filaDepartamento(cuenta, dep) {
  const nombre = escapar(String(cuenta).replace(/^dep:/, ""));
  const congelado = dep.congelado
    ? ' <span class="congelado">congelado</span>' : "";
  return `<div class="fila"><span>${nombre}${congelado}</span>` +
    `<span>${escapar(monedas(dep.saldo_mm || 0))}</span></div>`;
}

/** El mensaje pasajero de "salio bien", si hay uno vivo. Lo administra
 *  app.js con un timeout, igual que avisoPasajero en el chat. */
function bloqueListo(mensaje) {
  return mensaje ? `<div class="listo">${escapar(mensaje)}</div>` : "";
}

function formularioSembrar() {
  return `<div class="vacio">La economia todavia no existe: falta ` +
    `~/.calipso/economia. Sembrala para que el tesoro y tu banco empiecen ` +
    `a existir.</div>` +
    `<form data-perillas="sembrar">` +
    `<label>departamentos (separados por coma)` +
    `<input name="departamentos" placeholder="atlas, mercado" required>` +
    `</label>` +
    `<button type="submit">sembrar la economia</button></form>`;
}

function formularioAcunar() {
  return `<form data-perillas="acunar">` +
    `<label>poner plata en la fabrica (en monedas)` +
    `<input name="monto" inputmode="decimal" placeholder="100" required>` +
    `</label>` +
    `<button type="submit">acunar capital al tesoro</button></form>`;
}

function formularioMovimiento() {
  return `<form data-perillas="movimiento">` +
    `<label>tu banco: ingreso o egreso` +
    `<select name="tipo"><option value="ingreso">ingreso</option>` +
    `<option value="gasto">egreso</option></select></label>` +
    `<label>monto (en monedas)` +
    `<input name="monto" inputmode="decimal" placeholder="50" required>` +
    `</label>` +
    `<label>categoria<input name="categoria" placeholder="sueldo, alquiler..."` +
    ` required></label>` +
    `<label>nota (opcional)<input name="nota" placeholder="nota"></label>` +
    `<button type="submit">registrar</button></form>`;
}

// --------------------------------------------------------------------------
// Los ajustes: los numeros que hasta hoy solo se cambiaban editando el json
//
// `POST /api/economia/sembrar` escribe departamentos.json y
// suscripciones.json UNA sola vez y se niega a correr de nuevo. Esta es la
// otra mitad: la cara de los dos endpoints que dejan mover un numero
// despues del sembrado. Sin cara, las dos superficies quedan muertas -- ya
// paso hoy con cuatro endpoints de permisos sin pantalla.
// --------------------------------------------------------------------------

function filaTechoPreseed(dep) {
  const n = escapar(dep.nombre);
  const entrado = dep.preseed_ciclo_mm || 0;
  const techoCiclo = dep.techo_preseed_ciclo_mm || 0;
  // el acumulado del ciclo, al lado de su techo. Sin esto el numero de
  // abajo se pone a ciegas: la mesa muestra cada pedido suelto y ninguna
  // pantalla decia cuanto capital ya entro este ciclo.
  const yaEntro = `<div class="nota">ya entro este ciclo: ` +
    `${escapar(monedas(entrado))}` +
    (techoCiclo ? ` de ${escapar(monedas(techoCiclo))}` : "") + `</div>`;
  return `<form class="ajuste" data-perillas="techo-preseed" ` +
    `data-departamento="${n}">` +
    `<label>${n}: techo por pedido (en monedas)` +
    `<input name="monto" inputmode="decimal" ` +
    `value="${escapar(monedas(dep.techo_preseed_mm || 0))}"></label>` +
    `<label>${n}: techo del ciclo (en monedas)` +
    `<input name="ciclo" inputmode="decimal" ` +
    `value="${escapar(monedas(techoCiclo))}"></label>` +
    yaEntro +
    `<button type="submit">guardar</button></form>`;
}

function bloquePreseed(departamentos) {
  const fabrica = departamentos.filter(d => d.zona === "fabrica");
  if (!fabrica.length) {
    return `<div class="vacio">Sin departamentos de fabrica.</div>`;
  }
  return `<div class="subtitulo">cuanto puede pedir cada departamento</div>` +
    `<div class="nota">Es autorizacion a PEDIR, no plata: el jefe publica ` +
    `su ronda pre-seed en la mesa y vos decidis ahi si la financias y por ` +
    `cuanto. En cero no pide.</div>` +
    // los DOS techos van juntos porque son la misma decision partida en
    // dos preguntas: cuanto vale cada ronda, y cuanto capital entra en
    // todo el ciclo antes de que tengas que volver a decidir. El del
    // ciclo ata tambien a la mesa: pasado ese total, "financiar" te
    // rechaza el pedido hasta que subas este numero. Los dos en cero no
    // piden, y ninguno tiene un valor por defecto que autorice algo.
    `<div class="nota">El techo por pedido acota cuanto vale CADA ronda; ` +
    `el del ciclo acota cuanto capital entra en las 4 semanas del ciclo, ` +
    `contando lo que ya financiaste mas lo que sigue en la mesa. Pasado ` +
    `el del ciclo, financiar te lo rechaza hasta que lo subas: es a ` +
    `proposito, para que no se cruce en silencio.</div>` +
    fabrica.map(filaTechoPreseed).join("");
}

/** Lo que el probe pasivo propone para esta suscripcion, en palabras.
 *  Distingue los tres "todavia no" -- sin foto, sin proveedor, sin
 *  historia suficiente-- en vez de dibujar un cero que invitaria a
 *  aplicar un numero que nadie midio. */
function bloqueMedido(sus) {
  const m = sus.medido;
  if (!m) {
    return `<div class="nota">Ningun proveedor medido corresponde a esta ` +
      `suscripcion.</div>`;
  }
  const prov = escapar(m.proveedor);
  if (m.capacidad_ciclo_propuesta === null ||
      m.capacidad_ciclo_propuesta === undefined) {
    return `<div class="nota">El probe de ${prov} todavia no propone un ` +
      `numero. ${escapar(m.nota || "")}</div>`;
  }
  const n = Number(m.capacidad_ciclo_propuesta);
  return `<div class="medido">` +
    `<span>medido en ${prov}: <b>${escapar(n)}</b> unidades por ciclo</span>` +
    `<button type="button" data-ajuste="aplicar-medido" ` +
    `data-suscripcion="${escapar(sus.nombre)}" data-capacidad="${escapar(n)}">` +
    `aplicar ${escapar(n)}</button></div>` +
    // la nota va SIEMPRE y sin recortar: es lo que separa una medicion
    // (Codex expone used_percent real) de una extrapolacion (Claude no
    // expone ningun porcentaje). Esconderla dejaria a Pedro aplicando dos
    // numeros que no valen lo mismo como si valieran igual.
    `<div class="nota">${escapar(m.nota || "")}</div>`;
}

function filaSuscripcion(sus) {
  const n = escapar(sus.nombre);
  return `<div class="ajuste-suscripcion">` +
    `<div class="subtitulo">${n}</div>` +
    `<div class="fila"><span>capacidad del ciclo</span>` +
    `<span>${escapar(sus.capacidad_ciclo)} unidades ` +
    `(${escapar(sus.capacidad_fabrica)} para la fabrica)</span></div>` +
    `<div class="fila"><span>precio de la unidad</span>` +
    `<span>${escapar(monedas(sus.precio_base_mm))}</span></div>` +
    `<div class="fila"><span>ya comprado en este ciclo</span>` +
    `<span>${escapar(sus.consumido_ciclo || 0)} unidades</span></div>` +
    bloqueMedido(sus) +
    `<form class="ajuste" data-perillas="capacidad" data-suscripcion="${n}">` +
    `<label>capacidad del ciclo<input name="capacidad" inputmode="numeric" ` +
    `value="${escapar(sus.capacidad_ciclo)}" required></label>` +
    `<label>reserva personal<input name="reserva" inputmode="numeric" ` +
    `value="${escapar(sus.reserva_personal)}" required></label>` +
    `<button type="submit">aplicar</button></form></div>`;
}

/**
 * `config`: la respuesta de GET /api/economia/config, o null si no se pudo
 * leer. Se separa de `textoDePerillas` porque es otra pregunta -"que
 * numeros tiene puesta la economia"- y porque asi se testea sola.
 */
export function textoDeAjustes(config) {
  if (!config || !config.activa) return "";
  const deps = config.departamentos || [];
  const sus = config.suscripciones || [];
  const generado = config.medido_generado
    ? `<div class="nota">Ultima medicion del probe: ` +
      `${escapar(config.medido_generado)}.</div>`
    : `<div class="nota">El probe de consumo todavia no dejo ninguna foto ` +
      `(la deja la rutina "consumo").</div>`;
  return `<div class="ajustes">` + bloquePreseed(deps) +
    `<div class="subtitulo">capacidad de las suscripciones</div>` +
    `<div class="nota">Cambiar esto reprecia la capacidad: el precio de la ` +
    `unidad se estampa en cada compra que la fabrica escribe despues, y el ` +
    `libro es append-only. Por encima del techo de plata te lo va a ` +
    `preguntar.</div>` + generado +
    sus.map(filaSuscripcion).join("") + `</div>`;
}

/**
 * `datos`: la respuesta de GET /api/economia/tablero, `{activa: false}` o
 * `{activa: true, tablero: {...}, pendientes}`. `mensaje`: el aviso
 * pasajero de la ultima accion, o null. `config`: la de
 * GET /api/economia/config, para los ajustes de abajo.
 */
export function textoDePerillas(datos, mensaje = null, config = null) {
  const suscripciones = bloqueSuscripciones();
  const listo = bloqueListo(mensaje);
  if (!datos || !datos.activa) {
    return listo + suscripciones + formularioSembrar();
  }
  const t = datos.tablero || {};
  const deps = t.departamentos || {};
  const filasDeps = Object.keys(deps).length
    ? Object.entries(deps).map(([c, d]) => filaDepartamento(c, d)).join("")
    : `<div class="vacio">Sin departamentos.</div>`;
  const personal = t.personal || {};
  return listo + suscripciones +
    `<div class="dosperillas">` +
    `<div class="perilla"><span class="etiqueta">tesoro de la fabrica</span>` +
    `<span class="valor">${escapar(monedas(t.tesoro_mm || 0))}</span></div>` +
    `<div class="perilla"><span class="etiqueta">tu banco personal</span>` +
    `<span class="valor">${escapar(monedas(personal.neto_mm || 0))}</span>` +
    `</div></div>` +
    `<div class="datos">` +
    filaDato("direccion", monedas(t.direccion_mm || 0)) +
    filaDato("cuenta de Pedro", monedas(t.cuenta_pedro_mm || 0)) +
    filaDato("1 PT vale", monedas(t.tipo_cambio_mm || 0)) +
    filaDato("linea de empleo (por hora)", monedas(t.linea_empleo_mm || 0)) +
    `</div>` +
    `<div class="subtitulo">departamentos</div>` +
    `<div class="departamentos">${filasDeps}</div>` +
    formularioAcunar() + formularioMovimiento() + textoDeAjustes(config);
}
