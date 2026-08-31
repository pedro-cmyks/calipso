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
// suscripcion que encontrar.
//
// `reserva_personal` y `costo_api_mm_por_unidad` siguen sin viajar: son
// estimaciones que ni Pedro ni esta pantalla pueden derivar, y el default
// del servidor es mejor que un numero inventado aca. `capacidad_ciclo` SI
// viaja ahora, y es el arreglo: el default del servidor esta marcado
// literalmente "ESTIMACION A AJUSTAR" y no mandarlo hacia que sembrar desde
// esta pantalla ignorara lo que el probe de consumo hubiera medido.
export const SUSCRIPCIONES = [
  {nombre: "claude_max", etiqueta: "Claude Max", costo_mensual_mm: 200_000},
  {nombre: "chatgpt_plus", etiqueta: "ChatGPT Plus", costo_mensual_mm: 20_000},
];

// Las dos zonas de `departamentos.py` (ZONA_FABRICA / ZONA_PERSONAL), que
// son las dos unicas que `Departamento.__post_init__` acepta. Se escriben
// aca porque el formulario tiene que MANDARLAS: hasta hoy ponia "fabrica"
// para todos, y la zona no es una perilla ajustable -- `Registro` no tiene
// baja y `ajustar` no deja tocar ni el nombre ni la zona, asi que un
// departamento sembrado en la zona equivocada solo se arregla borrando
// ~/.calipso/economia a mano.
export const ZONA_FABRICA = "fabrica";
export const ZONA_PERSONAL = "personal";

// El departamento que la economia da por hecho y nadie pide. `pagador`
// cobra el consumo personal de Pedro contra la cuenta literal
// "personal:finanzas"; sin un departamento con ESE nombre en zona personal
// el cargo levanta ErrorMercado, queda en cargos_pendientes.jsonl y se
// reintenta para siempre sin aplicarse nunca. Como sembrar no se deshace,
// el formulario lo trae puesto: olvidarlo tiene que ser una borrada
// explicita de Pedro, no un descuido.
export const DEPARTAMENTO_FINANZAS = "finanzas";

// La capacidad con la que nace una suscripcion cuando el probe todavia no
// midio nada. Es el mismo numero que pone el servidor por default
// (EcoSembrarSuscripcionBody), repetido a proposito: ahora el cuerpo lleva
// `capacidad_ciclo` SIEMPRE, asi que el numero tiene que estar a la vista
// -- y editable-- antes de sembrar, en vez de aparecer despues en
// suscripciones.json sin que nadie lo haya elegido.
export const CAPACIDAD_ESTIMADA = 1000;

function totalSuscripciones_mm() {
  return SUSCRIPCIONES.reduce((s, x) => s + x.costo_mensual_mm, 0);
}

/** Que `capacidad_ciclo` proponerle a cada suscripcion en el formulario de
 *  siembra, y DE DONDE sale ese numero.
 *
 *  `config` es la respuesta de GET /api/economia/config, la misma que ya
 *  consume `bloqueMedido`: cada suscripcion trae `medido` con lo que el
 *  probe pasivo de calipso/consumo.py propone, o null de tres formas
 *  distintas (sin foto, sin proveedor, sin historia suficiente).
 *
 *  VERIFICADO Y NO RESUELTO DESDE EL CLIENTE: ese endpoint corta con
 *  {activa: false} antes de leer la foto del probe mientras la economia no
 *  exista, que es exactamente cuando este formulario se dibuja, y ningun
 *  otro endpoint publica el resumen. O sea que hoy esto cae siempre en
 *  CAPACIDAD_ESTIMADA, y la pantalla lo dice con esas palabras en vez de
 *  hacer pasar la estimacion por una medicion. Se lee igual, con la forma
 *  que el servidor ya usa, para que el dia que sirva la foto sin economia
 *  sembrada el formulario se llene solo. */
export function capacidadesDeSiembra(config) {
  const filas = (config && config.suscripciones) || [];
  return SUSCRIPCIONES.map(s => {
    const fila = filas.find(f => f && f.nombre === s.nombre) || {};
    const m = fila.medido || null;
    const propuesta = Number(m && m.capacidad_ciclo_propuesta);
    // el input pide un entero y `aEntero` no acepta decimales: redondear
    // aca es lo que evita que una propuesta con coma deje el formulario
    // imposible de mandar.
    const medida = Number.isFinite(propuesta) && propuesta > 0
      ? Math.round(propuesta) : null;
    return {
      nombre: s.nombre,
      etiqueta: s.etiqueta,
      capacidad_ciclo: medida === null ? CAPACIDAD_ESTIMADA : medida,
      medido: medida === null
        ? null : {proveedor: m.proveedor || "", nota: m.nota || ""},
    };
  });
}

/** El cuerpo para sembrar: un diccionario nombre -> {costo_mensual_mm,
 *  capacidad_ciclo}, la forma que pide EcoSembrarBody.suscripciones (dict,
 *  no lista).
 *
 *  `capacidades` son las que Pedro tiene delante en el formulario (las de
 *  `capacidadesDeSiembra`, ya corregidas a mano si las corrigio), no las de
 *  esta constante: el numero que se siembra tiene que ser el que se leyo.
 *  Sin argumento cae en la estimacion, que es lo mismo que hacia el default
 *  del servidor, pero explicito. */
export function cuerpoDeSuscripciones(capacidades) {
  const porNombre = new Map(
    (capacidades || capacidadesDeSiembra(null)).map(c => [c.nombre, c]));
  const out = {};
  for (const {nombre, costo_mensual_mm} of SUSCRIPCIONES) {
    const cap = porNombre.get(nombre);
    out[nombre] = {costo_mensual_mm,
                   capacidad_ciclo: cap ? cap.capacidad_ciclo : CAPACIDAD_ESTIMADA};
  }
  return out;
}

/** Los departamentos del POST, o el error que impide armarlos.
 *
 *  Dos campos de texto separados por coma, uno por zona: la zona es el
 *  campo en el que se escribe el nombre y no una palabra que haya que
 *  recordar ni una sintaxis que memorizar. Es la forma que menos cambia lo
 *  que Pedro ya hace -escribir una lista con comas- y la que no tiene un
 *  default silencioso: hasta hoy TODOS nacian en "fabrica" sin que el
 *  formulario lo dijera en ningun lado.
 *
 *  Los tres rechazos son los que el servidor tambien rechaza (lista vacia,
 *  nombre con dos puntos, nombre repetido). Se comprueban aca igual porque
 *  el mensaje llega antes y en las palabras del formulario; el que manda
 *  sigue siendo el servidor. */
export function departamentosDeSiembra(textoFabrica, textoPersonal) {
  const lista = t => String(t ?? "").split(",").map(s => s.trim()).filter(Boolean);
  const departamentos = [
    ...lista(textoFabrica).map(nombre => ({nombre, zona: ZONA_FABRICA})),
    ...lista(textoPersonal).map(nombre => ({nombre, zona: ZONA_PERSONAL})),
  ];
  if (!departamentos.length) {
    return {departamentos: [], error: "escribi al menos un departamento"};
  }
  // Un departamento de fabrica, por lo menos. El servidor solo exige que la
  // lista no este vacia, asi que sembrar unicamente "finanzas" -que viene
  // precargado en el campo personal- pasa sus validaciones y deja la fabrica
  // sin un solo departamento PARA SIEMPRE: `Registro` no tiene alta fuera de
  // la siembra, y la siembra no corre dos veces. Es el mismo error
  // irreversible que estos dos campos existen para evitar, entrando por la
  // puerta de al lado: dibujar el formulario y tocar el boton sin escribir.
  if (!departamentos.some(d => d.zona === ZONA_FABRICA)) {
    return {departamentos: [],
            error: "escribi al menos un departamento de la fabrica. Sin " +
                   "ninguno la fabrica queda vacia y no se le puede agregar " +
                   "uno despues: no hay alta de departamentos fuera de la " +
                   "siembra, y la siembra corre una sola vez"};
  }
  const conDosPuntos = departamentos.find(d => d.nombre.includes(":"));
  if (conDosPuntos) {
    return {departamentos: [],
            error: `"${conDosPuntos.nombre}" no puede llevar dos puntos: el ` +
                   `nombre arma la cuenta del departamento (dep:nombre, ` +
                   `personal:nombre) y los dos puntos son el separador`};
  }
  // el nombre es la cuenta, asi que un mismo nombre en las dos zonas no
  // son dos departamentos: es uno repetido, y el servidor corta con
  // "departamentos repetidos en el pedido" sin escribir nada.
  const vistos = new Set();
  const repetidos = new Set();
  for (const {nombre} of departamentos) {
    if (vistos.has(nombre)) repetidos.add(nombre);
    vistos.add(nombre);
  }
  if (repetidos.size) {
    return {departamentos: [],
            error: `departamento repetido: ${[...repetidos].join(", ")}. El ` +
                   `nombre es la cuenta: no puede estar dos veces ni en las ` +
                   `dos zonas`};
  }
  return {departamentos, error: null};
}

/** El aviso de que falta el departamento que la economia da por hecho, o
 *  "" si esta. Es lo unico de esta pantalla que sabe de una cuenta
 *  hardcodeada tres capas mas abajo, y por eso se dice entero: el sintoma
 *  de olvidarlo no es un error visible sino un cargo que se reintenta para
 *  siempre en silencio, y no hay forma de agregarlo despues. */
export function avisoDeFinanzas(departamentos) {
  const hay = (departamentos || []).some(
    d => d.zona === ZONA_PERSONAL && d.nombre === DEPARTAMENTO_FINANZAS);
  if (hay) return "";
  return `OJO: no hay ningun departamento "${DEPARTAMENTO_FINANZAS}" en zona ` +
    `personal. Tu consumo personal se cobra contra la cuenta ` +
    `personal:${DEPARTAMENTO_FINANZAS}, y sin ese departamento el cargo no ` +
    `se aplica nunca: se apila y se reintenta para siempre. No se puede ` +
    `agregar despues.`;
}

/** Exactamente lo que se va a sembrar, renglon por renglon, para el
 *  confirm de app.js.
 *
 *  La LISTA y no un resumen: sembrar es de escritura unica y el error
 *  tipico es de una letra -una zona cambiada, un nombre de mas-, asi que
 *  lo que hay que poder leer antes de tocar aceptar es cada departamento
 *  con su zona y cada suscripcion con su capacidad. El aviso de finanzas,
 *  si hace falta, va arriba de todo: es lo que no se ve mirando la lista. */
export function resumenDeSiembra(departamentos, capacidades) {
  const aviso = avisoDeFinanzas(departamentos);
  const lineas = aviso ? [aviso, ""] : [];
  lineas.push("Sembrar la economia con esto, tal cual:", "", "departamentos:");
  for (const d of departamentos) lineas.push(`  ${d.nombre} - zona ${d.zona}`);
  lineas.push("", "suscripciones:");
  for (const c of capacidades || []) {
    // lo que el probe midio se dice APARTE del numero que se va a sembrar:
    // el input es editable y los dos pueden no ser el mismo.
    const fuente = c.medido && c.medido.proveedor
      ? `el probe de ${c.medido.proveedor} midio ${c.medido.propuesta}`
      : "estimacion: nadie lo midio todavia";
    lineas.push(`  ${c.nombre} - ${c.capacidad_ciclo} unidades por ciclo ` +
                `(${fuente})`);
  }
  lineas.push("", "No se puede deshacer: no hay baja de departamentos, y ni " +
                  "el nombre ni la zona se pueden cambiar despues.");
  return lineas.join("\n");
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

/** Una suscripcion en el formulario de siembra: su capacidad editable y,
 *  debajo, de donde salio ese numero. La fuente va SIEMPRE y separada del
 *  input -no dentro del value- porque son dos hechos distintos: el numero
 *  es el que se va a sembrar (Pedro puede haberlo corregido) y la nota
 *  dice que midio el probe, que es lo que separa una medicion de una
 *  estimacion. Es la misma disciplina de `bloqueMedido`, que ya no
 *  esconde la nota del probe en la pantalla de ajustes. */
function filaCapacidadSiembra(cap) {
  const n = escapar(cap.nombre);
  // el proveedor Y el numero que propuso, los dos en el DOM: el input es
  // editable, asi que despues de que Pedro lo corrija el confirm tiene que
  // poder decir "sembras 600, el probe midio 480" en vez de hacer pasar su
  // numero por una medicion.
  const medido = cap.medido
    ? ` data-medido="${escapar(cap.medido.proveedor)}" ` +
      `data-propuesta="${escapar(cap.capacidad_ciclo)}"` : "";
  const fuente = cap.medido
    ? `<div class="nota">medido por el probe de ` +
      `${escapar(cap.medido.proveedor)}. ${escapar(cap.medido.nota)}</div>`
    // sin foto no se disfraza de medicion: el numero es la estimacion con
    // la que el servidor llenaba este hueco en silencio, ahora a la vista
    // y editable. Y se dice DONDE se mide, porque el probe es una rutina
    // que hay que correr, no algo que pase solo.
    : `<div class="nota">nadie lo midio: es la estimacion con la que nace ` +
      `la economia. El probe de consumo deja su foto cuando corre la ` +
      `rutina "consumo", pero esta pantalla recien la puede leer con la ` +
      `economia ya sembrada; hasta entonces el numero es este, y despues ` +
      `se corrige desde los ajustes de esta misma pantalla.</div>`;
  return `<label>${escapar(cap.etiqueta)}: unidades por ciclo` +
    `<input inputmode="numeric" data-suscripcion="${n}"${medido} ` +
    `value="${escapar(cap.capacidad_ciclo)}"></label>` + fuente;
}

/** `config`: la de GET /api/economia/config, para proponer la capacidad
 *  medida. Llega con {activa: false} mientras la economia no exista -- ver
 *  `capacidadesDeSiembra`. */
function formularioSembrar(config) {
  return `<div class="vacio">La economia todavia no existe: falta ` +
    `~/.calipso/economia. Sembrala para que el tesoro y tu banco empiecen ` +
    `a existir.</div>` +
    `<form data-perillas="sembrar">` +
    // el aviso va ARRIBA del primer campo, no pegado al boton: lo que
    // decide si esta lista esta bien escrita es la cabeza con la que se la
    // escribe, y esta lista no se corrige despues.
    `<div class="nota">Se siembra UNA vez y no se deshace: no hay baja de ` +
    `departamentos, y ni el nombre ni la zona se pueden cambiar mas (las ` +
    `perillas de plata si). Corregir un nombre o una zona obliga a borrar ` +
    `~/.calipso/economia a mano.</div>` +
    // dos campos, uno por zona, en vez de una sintaxis dentro de un campo
    // solo: la zona es DONDE lo escribis. El de fabrica es `required`
    // porque una siembra sin ninguno deja la fabrica vacia sin vuelta
    // atras; `departamentosDeSiembra` lo vuelve a comprobar en castellano
    // por si el repintado de fondo vacia el campo.
    //
    // El placeholder NO propone nombres. Decia "atlas, mercado", y los dos
    // son de la lista inventada que este trabajo saco del prompt: atlas ni
    // siquiera es un departamento, es un PROYECTO que consume varios. Un
    // ejemplo al lado de una escritura irreversible no es un ejemplo: es
    // una sugerencia, y aca la sugerencia estaba mal.
    `<label>departamentos de la fabrica (separados por coma)` +
    `<input name="fabrica" placeholder="uno por coma" autocomplete="off" ` +
    `required></label>` +
    `<label>departamentos personales (separados por coma)` +
    `<input name="personal" autocomplete="off" ` +
    `value="${escapar(DEPARTAMENTO_FINANZAS)}"></label>` +
    `<div class="nota">La zona es el campo en el que lo escribis. ` +
    `"${escapar(DEPARTAMENTO_FINANZAS)}" viene puesto porque la economia lo ` +
    `da por hecho: tu consumo personal se cobra contra la cuenta ` +
    `personal:${escapar(DEPARTAMENTO_FINANZAS)} y sin ese departamento el ` +
    `cargo no se aplica nunca. Y la zona decide que perillas tiene: los dos ` +
    `techos de pre-seed son de fabrica, un departamento personal no pide ` +
    `capital.</div>` +
    `<div class="subtitulo">capacidad de las suscripciones</div>` +
    capacidadesDeSiembra(config).map(filaCapacidadSiembra).join("") +
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
    return listo + suscripciones + formularioSembrar(config);
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
