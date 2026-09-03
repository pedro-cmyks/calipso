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

function esPreseed(propuesta) {
  return propuesta.tipo === "preseed";
}

/** Quien paga, cuando no hay nada que elegir. Un pre-seed se financia
 *  contra el TESORO y contra nada mas: `bus.financiar` rechaza cualquier
 *  billetera de departamento, asi que un selector aca seria un menu donde
 *  todas las opciones fallan. La cuenta va en el dataset de la fila, que
 *  es de donde app.js la saca. */
function pagaElTesoro() {
  return `<div class="pagar">paga <b>el tesoro</b> ` +
    `<span class="nota">una ronda pre-seed es capital, no plata de otro ` +
    `departamento</span></div>`;
}

function alcanza(propuesta, departamentos, tesoro_mm) {
  if (esPreseed(propuesta)) {
    // sin el dato (una respuesta vieja del servidor) no se inventa un
    // aviso: mejor callarse que decirle a Pedro que no alcanza cuando no
    // se sabe
    return typeof tesoro_mm !== "number" ||
           tesoro_mm >= propuesta.presupuesto_mm;
  }
  const dueno = departamentos.find(d => d.cuenta === propuesta.departamento);
  return !dueno || dueno.disponible_mm >= propuesta.presupuesto_mm;
}

/** El historial de promesas del departamento, "3/5", al lado de su nombre.
 *  `standing` puede faltar -una fila que vino de antes de esta tarea, o una
 *  respuesta vieja del servidor- y ahi no se dibuja nada: mejor callarse
 *  que mostrar un "undefined/undefined". */
function textoDeStanding(standing) {
  if (!standing || typeof standing.total !== "number") return "";
  return ` <span class="standing">` +
    `${escapar(String(standing.cumplidas))}/${escapar(String(standing.total))}` +
    `</span>`;
}

function fila(propuesta, departamentos, tesoro_mm) {
  const dep = escapar(propuesta.departamento.replace(/^dep:/, ""));
  const standing = textoDeStanding(propuesta.standing);
  const plata = escapar(monedas(propuesta.presupuesto_mm));
  const preseed = esPreseed(propuesta);
  // La etiqueta no sale del titulo -que lo escribe un modelo- sino del
  // campo `tipo` del bus: es la unica forma de que Pedro sepa que esto
  // sale del tesoro y no de una billetera, aunque el modelo haya escrito
  // cualquier cosa arriba.
  const sello = preseed
    ? `<span class="sello preseed">ronda pre-seed</span> ` : "";
  if (propuesta.estado === "financiada") {
    const gastado = escapar(monedas(propuesta.gastado_mm));
    // un pre-seed financiado no tiene gasto que mostrar: la plata quedo en
    // la cuenta del departamento, no en trabajo:<id> (situacion.py lo dice
    // igual del lado del jefe). Mostrar "gastado 0" seria un cero que no
    // significa nada.
    const cola = preseed ? "capital entregado" : `gastado ${gastado}`;
    return `<div class="propuesta financiada">` +
      `<div class="cabeza">${sello}<b>${dep}</b>${standing} · ` +
      `${escapar(propuesta.titulo)}</div>` +
      `<div class="datos">financiada · ${plata} · ${cola}</div>` +
      `</div>`;
  }
  const aviso = alcanza(propuesta, departamentos, tesoro_mm)
    ? "" : `<div class="aviso">${preseed ? "el tesoro no tiene tanto"
                                         : "sin saldo suficiente"}</div>`;
  // Dos filas a proposito, en vez de una sola que se parte sola cuando no
  // entra: "paga" + el selector arriba, los dos botones abajo. Asi el
  // ancho angosto de escritorio (donde antes "descartar" se caia a una
  // segunda linea desprolija) y el dedo en el telefono (que necesita los
  // 40px de alto) quedan resueltos con el MISMO marcado.
  // Campo opcional para las palabras de Pedro: lo lee app.js al reaccionar
  // (descartar/no-mas/financiar) y viaja con la reaccion al registro; vacio
  // no rompe nada, solo se pierde el motivo. Va en su propia fila, igual
  // que "pagar" y "botones", por la misma razon que el comentario de mas
  // arriba: cada bloque su fila, nada que se parta solo.
  const palabras = `<div class="palabras-campo">` +
    `<textarea class="palabras" data-id="${escapar(propuesta.id)}" ` +
    `placeholder="tus palabras (opcional)"></textarea></div>`;
  return `<div class="propuesta" ` +
    `data-presupuesto="${escapar(propuesta.presupuesto_mm)}"` +
    (preseed ? ` data-cuenta="tesoro"` : "") + `>` +
    `<div class="cabeza">${sello}<b>${dep}</b>${standing} · ` +
    `${escapar(propuesta.titulo)}</div>` +
    `<div class="datos">${preseed ? "pide" : "presupuesto"} ${plata}</div>` +
    aviso +
    `<div class="acciones">` +
    (preseed ? pagaElTesoro()
             : `<div class="pagar">paga ${selector(propuesta, departamentos)}</div>`) +
    palabras +
    `<div class="botones">` +
    `<button data-accion="financiar" data-id="${escapar(propuesta.id)}">` +
    `financiar</button>` +
    `<button data-accion="descartar" data-id="${escapar(propuesta.id)}">` +
    `descartar</button>` +
    `<button data-accion="no-mas" data-id="${escapar(propuesta.id)}">` +
    `no mas</button></div></div></div>`;
}

/** La pila de pedidos de pre-seed vencidos, que NO es una fila de la mesa.
 *
 *  El agujero que tapa: un pedido vencido sale de la mesa -- y esta bien
 *  que salga, no hay ninguna decision que tomar sobre el: no reserva cupo,
 *  no se puede financiar, y la ronda ya se puede volver a pedir con los
 *  numeros de hoy-- pero el bus es append-only y nadie barre, asi que se
 *  queda en `alta` para siempre. Sacarlo de la unica pantalla que daba su
 *  id borraba el ultimo camino para limpiarlo: `descartar` sigue
 *  contestando 200, solo que el id ya no se veia en ningun lado. Cada
 *  departamento acumulaba un `alta` muerto por ventana vencida, y los
 *  cinco lectores del bus los volvian a leer y a evaluar en cada GET.
 *
 *  Por eso va PLEGADO y en un bloque aparte: es una pila para tirar, no
 *  una bandeja de entrada. Si se mezclara con las propuestas volveria a
 *  ser lo que la mesa dice de si misma que no es -- un historial-- y
 *  encima con botones que no pueden funcionar. Lo unico que ofrece es
 *  descartar, que es lo unico que se puede hacer.
 */
function bloqueVencidas(vencidas) {
  if (!vencidas.length) return "";
  const filas = vencidas.map(v => {
    const dep = escapar(String(v.departamento || "").replace(/^dep:/, ""));
    return `<div class="vencida">` +
      `<div class="cabeza"><b>${dep}</b> · ${escapar(v.titulo || "")}</div>` +
      `<div class="datos">pedia ${escapar(monedas(v.presupuesto_mm || 0))} ` +
      `en ${escapar(v.semana || "?")}</div>` +
      `<button data-accion="descartar" data-id="${escapar(v.id)}">` +
      `descartar</button></div>`;
  }).join("");
  return `<details class="vencidas"><summary>${vencidas.length} ` +
    `${vencidas.length === 1 ? "pedido de pre-seed vencido"
                             : "pedidos de pre-seed vencidos"}</summary>` +
    `<div class="nota">Su semana quedo fuera de la ventana con la que se ` +
    `podrian pagar: ya no reservan cupo y el departamento puede volver a ` +
    `pedir la ronda con los numeros de hoy. No hay nada que decidir, pero ` +
    `siguen escritos en el bus hasta que los descartes.</div>` +
    filas + `</details>`;
}

/** Una fila de "por juzgar": un trabajo que llego a su plazo (`bus.vencida`,
 *  punto 5) y todavia no tiene veredicto. Juzgar es reputacion, no plata: a
 *  diferencia de `fila()` no hay selector de cuenta ni monto, solo lo que
 *  prometio -su `metrica`/`sobre`, la misma tabla que ya usa la fila
 *  financiable- y los dos botones del veredicto. El campo de palabras es el
 *  mismo patron que financiar/descartar/no-mas: opcional, y app.js lo lee
 *  de la fila al postear.
 */
function filaPorJuzgar(item) {
  const dep = escapar(String(item.departamento || "").replace(/^dep:/, ""));
  const id = escapar(item.id);
  const metrica = item.metrica || item.promete || "";
  const sobre = item.sobre;
  const tieneSobre = sobre !== undefined && sobre !== null && sobre !== "";
  const promesa = metrica
    ? `prometio ${escapar(metrica)}` +
      (tieneSobre ? ` sobre ${escapar(String(sobre))}` : "")
    : "sin metrica registrada";
  return `<div class="juzgar-item">` +
    `<div class="cabeza"><b>${dep}</b> · ${escapar(item.titulo || "")}</div>` +
    `<div class="datos">${promesa}</div>` +
    `<div class="palabras-campo">` +
    `<input class="palabras" data-id="${id}" ` +
    `placeholder="tus palabras (opcional)"></div>` +
    `<div class="botones">` +
    `<button data-accion="cumplio" data-id="${id}">cumplio</button>` +
    `<button data-accion="no-cumplio" data-id="${id}">no cumplio</button>` +
    `</div></div>`;
}

/** La seccion "por juzgar": a diferencia de la pila de vencidos (que es
 *  para tirar), aca hay algo que decidir, asi que va destapada y arriba de
 *  la mesa -no plegada en un `<details>`- para que Pedro no tenga que
 *  buscarla. */
function bloquePorJuzgar(por_juzgar) {
  if (!por_juzgar || !por_juzgar.length) return "";
  const filas = por_juzgar.map(filaPorJuzgar).join("");
  return `<div class="por-juzgar">` +
    `<div class="titulo">por juzgar</div>` +
    `<div class="nota">Llegaron a su plazo: decidi si cumplieron lo que ` +
    `prometieron. No mueve plata, solo el historial del departamento.</div>` +
    filas + `</div>`;
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
  // el mismo filtro que las propuestas: tocar un edificio en el mapa acota
  // la mesa entera, y una pila de otro departamento ahi adentro seria
  // ruido. `|| []` porque una respuesta vieja del servidor no la trae.
  const muertas = (datos.vencidas || []).filter(
    v => !filtro || v.departamento === filtro);
  // mismo filtro que propuestas/vencidas: "por juzgar" tambien es del
  // departamento que le toco, y `|| []` porque una respuesta vieja del
  // servidor (de antes de esta tarea) no trae la clave.
  const juzgar = bloquePorJuzgar((datos.por_juzgar || []).filter(
    j => !filtro || j.departamento === filtro));
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
    // la pila se dibuja igual con la mesa vacia: es justo cuando pasa --
    // el pedido vencio y no quedo nada que decidir-- y si se fuera con las
    // propuestas volveria a no tener ninguna cara.
    return semana + cabecera + juzgar + `<div class="vacio">${vacio}</div>` +
           bloqueVencidas(muertas);
  }
  return semana + cabecera + juzgar +
         props.map(p => fila(p, deps, datos.tesoro_mm)).join("") +
         bloqueVencidas(muertas);
}
