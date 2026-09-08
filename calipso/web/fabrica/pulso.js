/**
 * calipso/web/fabrica/pulso.js — La capa viva, del lado del cliente.
 *
 * El servidor manda eventos sueltos por /ws/mapa y este reductor arma con
 * ellos el plantel de cada departamento. Es puro y no muta lo que recibe:
 * por eso se puede testear el protocolo entero sin abrir un socket.
 *
 * El reloj entra por parametro (`ahora`) y se guarda en cada empleado como
 * `desde` y `visto`: el `ts` del evento es del reloj DEL SERVIDOR y
 * compararlo contra el del navegador es comparar dos relojes distintos. Para
 * saber si alguien dejo de publicar alcanza con cuando lo vimos nosotros.
 *
 * El unico lugar donde si se mira el reloj del servidor es el descarte por
 * `seq`, y ahi se compara `ts` contra `ts`: los dos son del mismo reloj.
 */
import {crearSocketQueReconecta} from "./socket.js";

export const INACTIVO_MS = 600_000;    // diez minutos, igual que el servidor

export function estadoInicial() {
  return {conectado: false, empleados: {}, foco: null, seq: 0, ts: 0};
}

function vacio(ev, ahora) {
  // `desde` es cuando lo vimos por primera vez y no se toca nunca mas;
  // `visto` es cuando publico por ultima vez. Son dos preguntas distintas:
  // una ordena los escritorios, la otra decide quien se colgo.
  return {agente_id: ev.agente_id, departamento: ev.departamento,
          rol: ev.rol, modelo: ev.modelo, trabajo: ev.trabajo,
          estado: "esperando", texto: "", tokens_in: 0, tokens_out: 0,
          costo_mm: 0, runtime_ms: 0, diff: null, herramienta: null,
          abismo: null, desde: ahora, visto: ahora};
}

const CONOCIDOS = ["inicio", "razonando", "herramienta", "tokens", "diff",
                   "fin", "foco", "abismo"];

export function aplicarEvento(estado, ev, ahora) {
  if (!ev || !CONOCIDOS.includes(ev.evento)) return estado;   // latido incluido
  // El servidor arranca CADA conexion con el cursor en cero, asi que toda
  // reconexion -el reintento de 2 s de socket.js, la pestana que el telefono
  // suspende- reproduce el anillo entero. Sin esto, el `razonando` de un turno
  // se acumulaba encima del que ya estaba: "hola Pedro" -> "hola Pedrohola
  // Pedro". Reiniciar el escritorio con el `inicio` no alcanza: el `inicio` se
  // cae del anillo dentro del mismo turno, porque se publica un evento por
  // cada chunk del stream.
  if (ev.seq && ev.seq <= estado.seq) {
    // `seq` y `ts` son los dos del reloj del SERVIDOR, asi que compararlos
    // entre si es legitimo. Un numero viejo con un ts viejo es el anillo
    // reproducido: se descarta. Un numero viejo con un ts nuevo es un
    // servidor que arranco de nuevo -su contador vuelve a uno, su reloj no- y
    // ahi descartar dejaria al cliente mudo hasta que el contador nuevo pase
    // al viejo.
    if (!(ev.ts > estado.ts)) return estado;
    estado = {...estadoInicial(), conectado: estado.conectado};
  }
  if (ev.evento === "foco") {
    if (!ev.departamento) return estado;
    return {...estado, seq: ev.seq || estado.seq, ts: ev.ts || estado.ts,
            foco: {departamento: ev.departamento, seq: ev.seq}};
  }
  if (!ev.departamento || !ev.agente_id) return estado;
  const dep = estado.empleados[ev.departamento] || {};
  const previo = dep[ev.agente_id];
  // el `inicio` de un agente que ya estaba lo reinicia: un id repetido es un
  // trabajo nuevo, no la continuacion del anterior
  const base = (previo && ev.evento !== "inicio") ? previo : vacio(ev, ahora);
  const e = {...base, visto: ahora,
             rol: ev.rol || base.rol, modelo: ev.modelo || base.modelo,
             trabajo: ev.trabajo || base.trabajo};
  switch (ev.evento) {
    case "razonando":
      e.texto = base.texto + (ev.texto || "");
      e.estado = "razonando";
      break;
    case "herramienta":
      e.herramienta = {nombre: ev.nombre, resumen: ev.resumen || ""};
      e.estado = "razonando";
      break;
    case "tokens":
      // acumulados: se reemplazan, no se suman
      e.tokens_in = ev.tokens_in || 0;
      e.tokens_out = ev.tokens_out || 0;
      e.costo_mm = ev.costo_mm || 0;
      break;
    case "diff":
      e.diff = {ruta: ev.ruta, diff: ev.diff};
      break;
    case "fin":
      e.estado = "liberado";
      e.runtime_ms = ev.runtime_ms || 0;
      e.resultado = ev.resultado || "ok";
      break;
    case "abismo":
      // la consulta al abismo del turno de chat (spec del abismo, seccion
      // 9): pondering | pescado | fallo. No es texto del razonamiento: el
      // texto sigue llegando por `razonando`; esto es un estado al lado
      e.abismo = {fase: ev.fase, fuente: ev.fuente};
      if (ev.fase === "pondering") e.estado = "razonando";
      break;
    default:
      break;
  }
  return {...estado, seq: ev.seq || estado.seq, ts: ev.ts || estado.ts,
          empleados: {...estado.empleados,
                      [ev.departamento]: {...dep, [ev.agente_id]: e}}};
}

/**
 * En el orden en que llegaron: el que llego primero se sienta arriba, que es
 * el contrato que escribe `plazasDe` en sprites.js y la unica forma de que
 * los escritorios se LLENEN en vez de correrse uno cada vez que entra
 * alguien. Ordenar por `visto` -que se actualiza en cada evento- mandaba al
 * primer escritorio al que acababa de publicar: con el turno de chat y su
 * borrador vivos a la vez se intercambiaban de asiento, y `escritorioEnPunto`
 * abre el que quedo arriba EN ESE INSTANTE.
 */
export function empleadosDe(estado, departamento) {
  const dep = estado.empleados[departamento];
  if (!dep) return [];
  return Object.values(dep).sort((a, b) => (a.desde - b.desde) ||
                                           (a.agente_id < b.agente_id ? -1 : 1));
}

/** Un liberado se queda liberado; el que se colgo se marca inactivo. */
export function estadoVisible(empleado, ahora, inactivoMs = INACTIVO_MS) {
  if (!empleado) return "esperando";
  if (empleado.estado === "liberado") return "liberado";
  return (ahora - empleado.visto > inactivoMs) ? "inactivo" : empleado.estado;
}

export function crearPulso(alCambiar, ConstructorWS = WebSocket,
                           ahora = () => Date.now()) {
  let estado = estadoInicial();
  alCambiar(estado);        // el estado inicial dice "sin conexion" y se pinta

  crearSocketQueReconecta("/ws/mapa", {
    alAbrir() {
      estado = {...estado, conectado: true};
      alCambiar(estado);
    },
    alMensaje(dato) {
      estado = aplicarEvento(estado, dato, ahora());
      alCambiar(estado);
    },
    // si se cae, el mapa sigue mostrando la foto: el pulso es una capa
    // encima, no el mapa
    alCerrar() {
      estado = {...estado, conectado: false};
      alCambiar(estado);
    },
  }, ConstructorWS);

  return {estado: () => estado};
}
