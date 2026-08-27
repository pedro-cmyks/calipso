/**
 * calipso/web/fabrica/permisos.js — Lo que espera la respuesta de Pedro.
 *
 * El motor de permisos (calipso/permisos) para cualquier accion que no se
 * deshace sola: acunar por encima del techo, y mas adelante un comando o un
 * archivo. Sin esta pantalla una solicitud pendiente no tiene forma de
 * contestarse salvo con curl, y el techo que Pedro eligio se vuelve un muro
 * en vez de una pregunta.
 *
 * Lo que decide QUE se muestra vive aca y es puro; el DOM, los fetch y los
 * listeners los tiene app.js, igual que mesa.js, plantel.js y perillas.js.
 * `accion.titulo` y `contexto.chat/departamento` los puede escribir un
 * departamento (un modelo), asi que TODO lo que sale por innerHTML pasa por
 * escapar() -no solo lo que "parece" texto libre.
 *
 * El texto de cada solicitud no es un resumen amable: es la forma EXACTA
 * (`accion.forma`, la que compara el motor) mas una frase armada a mano
 * para las dos operaciones de plata que existen hoy. Una familia que
 * todavia no tiene vista propia (comando, archivo, app) no se disfraza de
 * nada que no sea: se muestra el titulo que mando el motor, tal cual.
 */
import {escapar} from "./paneles.js";
import {monedas} from "./ciudad.js";

/** "500000 mm supera el techo de 100000 mm" -> "500 monedas supera el
 *  techo de 100 monedas". El motor solo sabe de milimonedas; Pedro lee
 *  monedas (spec: 1 moneda = 1000 mm). La sustitucion es generica -corre
 *  sobre cualquier motivo, no solo el de plata- y donde no hay "N mm" no
 *  cambia nada, asi que un motivo de otra familia pasa intacto. */
export function motivoEnMonedas(motivo) {
  return String(motivo || "").replace(/(\d+)\s*mm\b/g,
    (_, n) => `${monedas(Number(n))} monedas`);
}

/** La frase exacta de lo que va a pasar, para las dos operaciones de plata
 *  enchufadas hoy. Fuera de "plata", no se inventa una frase: se devuelve
 *  el titulo que ya armo el motor (server.py), sin adornar. */
function descripcionDeAccion(accion) {
  const a = accion || {};
  const forma = a.forma || {};
  if (a.familia === "plata" && a.operacion === "acunar") {
    return `acunar ${escapar(monedas(forma.monto_mm || 0))} monedas ` +
      `(${escapar(forma.subtipo || "?")}) a ${escapar(forma.destino || "?")}`;
  }
  if (a.familia === "plata" && a.operacion === "movimiento") {
    return `registrar un ${escapar(forma.tipo || "?")} de ` +
      `${escapar(monedas(forma.monto_mm || 0))} monedas en ` +
      `${escapar(forma.categoria || "?")}`;
  }
  return escapar(a.titulo || `${a.familia || "?"}/${a.operacion || "?"}`);
}

/** Quien pidio esto, con el chat y el departamento si vinieron. Los tres
 *  campos los puede escribir un departamento -no son de confianza-, van
 *  escapados. */
function quienPide(contexto) {
  const c = contexto || {};
  const partes = [escapar(c.origen || "desconocido")];
  if (c.departamento) partes.push(`departamento ${escapar(c.departamento)}`);
  if (c.chat) partes.push(`chat ${escapar(c.chat)}`);
  return partes.join(" · ");
}

/** Los datos EXACTOS que el motor va a comparar, sin curar: el respaldo
 *  para cuando la frase de arriba no alcanza o se desconfia de ella. Nada
 *  queda escondido detras de un resumen. */
function bloqueCrudo(accion) {
  const json = JSON.stringify(accion || {}, null, 1);
  return `<details class="crudo"><summary>ver la forma exacta</summary>` +
    `<pre>${escapar(json)}</pre></details>`;
}

/** Los tres botones de 5.4: si una vez, si y no preguntes mas, no. El
 *  segundo solo si el endpoint de verdad lo admite -`si_siempre` sobre una
 *  solicitud con `siempre_pregunta` devuelve 400- y si no, se DICE por que
 *  no esta en vez de dibujar un boton que miente. */
function botonesDeRespuesta(s) {
  const id = escapar(s.id);
  const siSiempre = s.siempre_pregunta
    ? `<span class="nota">esta accion pregunta siempre: no admite ` +
      `permiso permanente</span>`
    : `<button data-accion="responder" data-id="${id}" ` +
      `data-respuesta="si_siempre">si, no preguntes mas</button>`;
  return `<div class="botones">` +
    `<button data-accion="responder" data-id="${id}" ` +
    `data-respuesta="si">si, una vez</button>` +
    siSiempre +
    `<button data-accion="responder" data-id="${id}" ` +
    `data-respuesta="no">no</button></div>`;
}

function intentosDeRodeo(s) {
  const n = (s.intentos || []).length;
  if (!n) return "";
  return `<div class="rodeo">se intento sortear esta espera ${n} ` +
    `${n === 1 ? "vez" : "veces"}</div>`;
}

function tarjetaSolicitud(s, etiquetaEstado) {
  const accion = s.accion || {};
  return `<div class="solicitud ${escapar(s.estado || "")}">` +
    `<div class="etiqueta">${escapar(etiquetaEstado)}</div>` +
    `<div class="cabeza">${descripcionDeAccion(accion)}</div>` +
    `<div class="fila"><span>por que se pregunta</span>` +
    `<span>${escapar(motivoEnMonedas(s.motivo))}</span></div>` +
    `<div class="fila"><span>quien pide</span><span>${quienPide(s.contexto)}` +
    `</span></div>` +
    `<div class="fila"><span>pedido</span><span>${escapar(s.ts || "")}</span>` +
    `</div>` +
    intentosDeRodeo(s) + bloqueCrudo(accion) + botonesDeRespuesta(s) +
    `</div>`;
}

function tarjetaAprobada(s) {
  return `<div class="solicitud aprobada">` +
    `<div class="etiqueta">aprobada, esperando que la rutina la tome</div>` +
    `<div class="cabeza">${descripcionDeAccion(s.accion || {})}</div>` +
    `</div>`;
}

function seccionEsperando(pendientes, estacionadas) {
  const todas = [
    ...pendientes.map(s => tarjetaSolicitud(s, "esperando tu respuesta")),
    ...estacionadas.map(s => tarjetaSolicitud(
      s, "una rutina quedo parada esperando esta respuesta")),
  ];
  if (!todas.length) {
    return `<div class="vacio">Nada esperando tu respuesta.</div>`;
  }
  return todas.join("");
}

function tarjetaConcedido(permiso) {
  const p = permiso || {};
  return `<div class="permiso">` +
    `<div class="cabeza">${escapar(p.familia || "?")}/${escapar(p.operacion || "?")}` +
    `</div>` +
    `<div class="fila"><span>forma</span>` +
    `<span>${escapar(JSON.stringify(p.forma || {}))}</span></div>` +
    `<div class="fila"><span>concedido</span><span>${escapar(p.ts || "")}` +
    `</span></div>` +
    `<button data-accion="revocar" data-id="${escapar(p.id)}">revocar</button>` +
    `</div>`;
}

function seccionConcedidos(concedidos) {
  const cuerpo = concedidos.length
    ? concedidos.map(tarjetaConcedido).join("")
    : `<div class="vacio">Ningun permiso permanente concedido.</div>`;
  return `<div class="subtitulo">permisos permanentes</div>` + cuerpo;
}

function seccionTecho(techos) {
  const mm = (techos || {}).plata_mm;
  const actual = typeof mm === "number" ? mm : 100_000;
  return `<div class="subtitulo">techo de plata</div>` +
    `<div class="fila"><span>hoy</span>` +
    `<span>${escapar(monedas(actual))} monedas</span></div>` +
    `<form data-accion="techo">` +
    `<label>nuevo techo (en monedas)` +
    `<input name="techo" inputmode="decimal" ` +
    `value="${escapar(monedas(actual))}" required></label>` +
    `<button type="submit">cambiar el techo</button></form>`;
}

/** Cuantas cosas esperan la respuesta de Pedro: pendientes (un prompt vivo)
 *  mas estacionadas (una rutina desatendida que quedo parada). Las dos se
 *  contestan por el mismo camino; las dos son "algo que Pedro tiene que
 *  ver sin buscarlo". 0 si el motor no esta disponible. */
export function contadorPendientes(datos) {
  if (!datos || !datos.activo) return 0;
  return (datos.pendientes || []).length + (datos.estacionadas || []).length;
}

/**
 * `datos`: la respuesta de GET /api/permisos -`{activo: false}` o
 * `{activo: true, pendientes, estacionadas, aprobadas, concedidos, techos,
 * error}`. `mensaje`: el aviso pasajero de la ultima accion, o null.
 */
export function textoDePermisos(datos, mensaje = null) {
  const listo = mensaje
    ? `<div class="listo">${escapar(mensaje)}</div>` : "";
  if (!datos || !datos.activo) {
    return listo + `<div class="vacio">El motor de permisos no esta ` +
      `disponible en este build.</div>`;
  }
  const error = datos.error
    ? `<div class="aviso">no se pudieron leer las solicitudes: ` +
      `${escapar(datos.error)}. Por las dudas, se trata como que no hay ` +
      `nada para mostrar -no como que no hay nada pendiente.</div>` : "";
  const pendientes = datos.pendientes || [];
  const estacionadas = datos.estacionadas || [];
  const aprobadas = datos.aprobadas || [];
  const bloqueAprobadas = aprobadas.length
    ? `<div class="subtitulo">aprobadas</div>` +
      aprobadas.map(tarjetaAprobada).join("")
    : "";
  return listo + error +
    `<div class="subtitulo">esperando tu respuesta</div>` +
    seccionEsperando(pendientes, estacionadas) +
    bloqueAprobadas +
    seccionConcedidos(datos.concedidos || []) +
    seccionTecho(datos.techos || {});
}
