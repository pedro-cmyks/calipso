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
import {textoDeFreno} from "./freno.js";

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

/** La INVERSA de `aMilimonedasConCero`, para pintar un valor que despues
 *  se vuelve a leer del mismo input.
 *
 *  `monedas()` es para MOSTRAR: agrupa de a miles con la locale "es", asi
 *  que 20.000.000 mm sale "20.000". Pero el parser de arriba trata el
 *  punto como separador DECIMAL (acepta coma y punto por igual, que es lo
 *  que un campo `inputmode="decimal"` necesita), asi que ese "20.000"
 *  vuelve a entrar como 20.000 mm: el ida y vuelta dividia por mil todo
 *  techo de 10.000 monedas para arriba, y con siete digitos ("1.234.567")
 *  daba null y abortaba el guardado entero. Como los dos techos viajan en
 *  el MISMO POST, tocar uno reescribia el otro sin que Pedro lo tocara.
 *
 *  Aca no se agrupa nada y el decimal es la coma: lo que sale es
 *  exactamente lo que el parser vuelve a leer. Los milimonedas que no
 *  llegan a moneda entera van despues de la coma, sin ceros de relleno
 *  (1.500 mm -> "1,5"), porque el techo es un numero que Pedro edita a
 *  mano y no una etiqueta. */
export function monedasEditable(mm) {
  const n = Math.round(Number(mm) || 0);
  const signo = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  const dec = String(abs % 1000).padStart(3, "0").replace(/0+$/, "");
  return signo + String(Math.trunc(abs / 1000)) + (dec ? "," + dec : "");
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

function filaTechoPreseed(dep, sumadas, techoPropuestas) {
  const n = escapar(dep.nombre);
  const entrado = dep.preseed_ventana_mm || 0;
  const techoCiclo = dep.techo_preseed_ciclo_mm || 0;
  const pendiente = dep.preseed_pendiente_mm || 0;
  const libera = dep.preseed_libera_mm || 0;
  const sale = dep.preseed_libera_al_salir || "";
  // el acumulado de la VENTANA, al lado de su techo. Decia "ya entro este
  // ciclo" y eso dejo de ser cierto: el techo ya no se mide sobre el ciclo
  // de facturacion (una ventana fija que se reseteaba entera en la quinta
  // semana) sino sobre las ultimas N semanas operativas, deslizante.
  //
  // Y el N es `preseed_ventana_sumadas`, no la constante de la regla: la
  // ventana mete la semana de hoy este abierta o no, asi que el lunes,
  // hasta que Pedro toca el boton de abrir, el tramo sumado son CINCO
  // etiquetas. Este renglon dice lo que SE SUMO; la regla ("cualquier
  // corrida de 4") la dice la nota de arriba, que sigue con la constante.
  const tramo = sumadas === 1
    ? "la ultima semana operativa"
    : `las ultimas ${escapar(sumadas)} semanas operativas`;
  const yaEntro = `<div class="nota">entro en ${tramo}: ` +
    `${escapar(monedas(entrado))}` +
    (techoCiclo ? ` de ${escapar(monedas(techoCiclo))}` : "") + `</div>`;
  // y CUANDO vuelve cupo, que es lo unico bueno de perder el reset en
  // bloque: con la ventana fija el cupo volvia entero, de golpe y sin
  // ninguna senal de que la ventana acababa de rodar. Solo se dibuja si
  // hay algo que liberar -- prometer "se liberan 0" es ruido-- Y si hay
  // techo acumulado: en CERO la perilla no es "sin limite" sino "todavia
  // no" (ver departamentos.py) y `bus.financiar` corta antes con "no tiene
  // techo de pre-seed acumulado", asi que el cupo que vuelve no habilita
  // nada. Es el caso real de bajar la perilla a cero despues de haber
  // financiado -- lo que el resto de esta pantalla llama cerrar la canilla
  // -- y prometer ahi un alivio es la misma clase de mentira que el ruido.
  const seLibera = libera && techoCiclo
    ? `<div class="nota">cuando abras la proxima semana operativa sale ` +
      `${escapar(sale)} de la ventana y se liberan ` +
      `${escapar(monedas(libera))}.</div>`
    : "";
  // y lo PEDIDO que sigue en la mesa, que no es lo mismo y hasta hoy no
  // se veia en ningun lado. El numero de arriba es el de Pedro (lo
  // financiado, el unico que mira `financiar`); este es la reserva que el
  // jefe se descuenta para no publicar lo que no se le va a poder pagar.
  // Un pedido olvidado en la mesa deja al jefe frenado para siempre con
  // el acumulado en cero, y descartarlo es lo unico que lo suelta: sin
  // este renglon, nada se lo sugiere.
  //
  // Y lo que la nota decia hasta hoy -- "esas no se sueltan solas"-- ya no
  // es cierto, que es todo el arreglo: un pedido de pre-seed VENCE cuando
  // su semana sale de la ventana (`bus.preseed_vencido`), deja de reservar
  // y `financiar` no lo paga mas. Antes la unica salida era un gesto de
  // Pedro, asi que su inaccion apretaba a ese departamento para siempre.
  // La rodada de la ventana sigue sin soltarlo -- eso libera lo financiado,
  // no lo pedido-- y por eso las dos frases van juntas y separadas.
  const enLaMesa = pendiente
    ? `<div class="nota">y ${escapar(monedas(pendiente))} pedidas y sin ` +
      `financiar en la mesa: al jefe le reservan cupo de la ventana hasta ` +
      `que las financies, las descartes, o venzan al salir su semana de la ` +
      `ventana. Rodar la ventana no las suelta: eso libera lo financiado.` +
      `</div>`
    : "";
  return `<form class="ajuste" data-perillas="techo-preseed" ` +
    `data-departamento="${n}">` +
    `<label>${n}: techo por pedido (en monedas)` +
    `<input name="monto" inputmode="decimal" ` +
    `value="${escapar(monedasEditable(dep.techo_preseed_mm || 0))}"></label>` +
    `<label>${n}: techo de la ventana (en monedas)` +
    `<input name="ciclo" inputmode="decimal" ` +
    `value="${escapar(monedasEditable(techoCiclo))}"></label>` +
    yaEntro + seLibera + enLaMesa + textoDeFreno(dep, techoPropuestas) +
    `<button type="submit">guardar</button></form>`;
}

function bloquePreseed(departamentos, semanas, sumadas, techoPropuestas) {
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
    //
    // Y la nota dice la regla de PEDRO, que es la del numero que esta dos
    // renglones mas abajo. Antes decia que el techo acumulado cuenta "lo
    // que ya financiaste mas lo que sigue en la mesa" -- esa es la regla
    // del JEFE (`jefe._puede`, que reserva lo pedido en pie), no la del
    // freno que Pedro choca: `bus.financiar` cuenta SOLO lo financiado, y
    // era lo mismo que informaba el acumulado pegado abajo. Tres textos
    // sobre el mismo techo, dos de ellos contando distinto.
    //
    // Y la ventana: DESLIZANTE, no el ciclo de facturacion. Decirlo aca
    // importa porque cambia lo que Pedro siente -- el cupo ya no vuelve
    // entero en una fecha, vuelve de a pedazos-- y porque el reset del
    // ciclo era el agujero: el techo entero entraba en la ultima semana
    // del ciclo y otra vez en la primera del siguiente.
    `<div class="nota">El techo por pedido acota cuanto vale CADA ronda; ` +
    `el acumulado acota cuanto capital ENTRA en cualquier corrida de ` +
    `${escapar(semanas)} semanas operativas: lo que ya financiaste, que es ` +
    `el numero de abajo. La ventana se desliza, no se resetea: el cupo ` +
    `vuelve de a poco, a medida que cada semana sale por atras. Pasado ese ` +
    `total, financiar te lo rechaza hasta que lo subas: es a proposito, ` +
    `para que no se cruce en silencio. El jefe se frena antes que vos, ` +
    `porque el ademas se descuenta lo que ya pidio y sigue en la ` +
    `mesa.</div>` +
    fabrica.map(d => filaTechoPreseed(d, sumadas, techoPropuestas))
           .join("");
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
  // el largo de la ventana lo manda el servidor (`VENTANA_PRESEED_SEMANAS`)
  // en vez de escribirse aca: un 4 propio en la pantalla seria una segunda
  // fuente de verdad sobre el mismo techo.
  const semanasVentana = config.preseed_ventana_semanas || 4;
  // y cuantas etiquetas de semana se sumaron de verdad para el acumulado,
  // que no siempre es la constante de la regla (ver el comentario del
  // servidor). Sin el dato, el tramo se rotula con la regla, que es lo que
  // hacia la pantalla entera hasta hoy.
  const sumadas = config.preseed_ventana_sumadas || semanasVentana;
  return `<div class="ajustes">` +
    bloquePreseed(deps, semanasVentana, sumadas,
                  config.techo_propuestas) +
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
