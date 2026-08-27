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

/**
 * `datos`: la respuesta de GET /api/economia/tablero, `{activa: false}` o
 * `{activa: true, tablero: {...}, pendientes}`. `mensaje`: el aviso
 * pasajero de la ultima accion, o null.
 */
export function textoDePerillas(datos, mensaje = null) {
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
    formularioAcunar() + formularioMovimiento();
}
