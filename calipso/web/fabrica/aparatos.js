/**
 * calipso/web/fabrica/aparatos.js — Quien entra a Calipso desde afuera.
 *
 * La capa de sesion deja que un aparato remoto (el e-reader, el celular)
 * golpee la puerta y espere; el unico lugar donde ese golpe se contesta es
 * esta pantalla, y aprobar es solo desde la Ally (invariante 4). Sin ella un
 * aparato nuevo se aprueba con curl, que es exactamente la friccion que la
 * capa venia a sacar.
 *
 * Lo que decide QUE se muestra vive aca y es puro; el DOM, los fetch y los
 * listeners los tiene app.js, igual que permisos.js y perillas.js.
 *
 * Dos cosas gobiernan la forma de la tarjeta:
 *
 * 1. El nombre del aparato es input NO autenticado -lo escribe cualquiera
 *    que llegue a POST /api/aparatos/golpear, sin credencial-, asi que pasa
 *    por escapar() siempre, sin excepcion.
 * 2. El tipo que sugiere el aparato es una SUGERENCIA y nada mas: quien lo
 *    fija es Pedro al aprobar. Por eso la tarjeta no muestra el tipo como un
 *    hecho sino como un selector, y arriba de todo el ALCANCE en palabras --
 *    "navegador" no dice nada, "todo: la PWA completa, como la Ally" si.
 *    Y lo que Pedro ya eligio en ese selector manda sobre la sugerencia en
 *    cada repintado (`elegidos`): la lista se reconstruye cada 60 s y tras
 *    cada accion, y un repintado que devolviera el selector a la
 *    sugerencia dejaria que el aparato fije el tipo si Pedro se demora.
 */
import {escapar} from "./paneles.js";

/**
 * Que abre cada tipo, en castellano. La autoridad sigue siendo
 * `sesiones.ALCANCES` en el server (esa tabla es la que el guard compara);
 * esta es su traduccion para que Pedro pueda decidir sin leer python. Si las
 * dos se separan, la que manda es la del server y esta es un bug de UX.
 */
const ALCANCES = {
  lector: "Solo sus endpoints de lectura (/api/lectura)",
  tablero: "Ve toda la fabrica y firma la mesa y los permisos. Jamas " +
    "archivos, comandos ni configuracion",
  navegador: "Todo: la PWA completa, como la Ally",
};

export function alcanceDe(tipo) {
  // `hasOwn` y no `ALCANCES[tipo] || ...`: un tipo llamado "constructor"
  // devolveria una funcion de Object.prototype, que es "algo" y taparia el
  // aviso. Un tipo que la tabla no conoce no se disfraza de inofensivo: el
  // server lo valida, asi que llegar aca ya significa que algo no cuadra.
  return Object.hasOwn(ALCANCES, tipo) ? ALCANCES[tipo]
    : "Este tipo de aparato no se conoce: no aprobar sin saber que abre";
}

/** La hora del almacen es ISO en UTC y no se lee de un vistazo. Una fecha
 *  que no se puede parsear se muestra CRUDA y no en blanco: un renglon
 *  vacio se lee como "nunca entro", que es una cosa distinta. */
export function fechaLegible(iso) {
  const crudo = String(iso ?? "");
  const cuando = new Date(crudo);
  if (Number.isNaN(cuando.getTime())) return crudo;
  const dosDigitos = n => String(n).padStart(2, "0");
  return `${cuando.getFullYear()}-${dosDigitos(cuando.getMonth() + 1)}-` +
    `${dosDigitos(cuando.getDate())} ${dosDigitos(cuando.getHours())}:` +
    `${dosDigitos(cuando.getMinutes())}`;
}

/** Los tres tipos, del que menos abre al que mas. El orden es a proposito:
 *  el mas peligroso no es el primero que cae bajo el dedo. */
function opcionesDeTipo(sugerido) {
  return Object.keys(ALCANCES)
    .map(tipo => `<option value="${tipo}"` +
                 `${tipo === sugerido ? " selected" : ""}>${tipo}</option>`)
    .join("");
}

/** Un golpe vigente: lo unico de esta pantalla que espera un si o un no.
 *  El alcance sale en grande y app.js lo reescribe cuando cambia el
 *  selector -- un cartel que describa el tipo sugerido mientras el selector
 *  dice otro es peor que no tener cartel. El selector y el cartel salen con
 *  lo que Pedro ya eligio para este golpe si lo toco (`elegidos`), y con la
 *  sugerencia si no; la linea "sugiere:" muestra la sugerencia siempre. */
function tarjetaDeGolpe(golpe, elegidos) {
  const id = escapar(golpe.id_pedido);
  const tipo = elegidos.has(golpe.id_pedido)
    ? elegidos.get(golpe.id_pedido) : golpe.tipo;
  return `<div class="golpe">` +
    `<div class="nombre">${escapar(golpe.aparato)}</div>` +
    `<div class="sugerido">sugiere: ${escapar(golpe.tipo)}</div>` +
    `<div class="alcance">${escapar(alcanceDe(tipo))}</div>` +
    `<label>que le doy<select data-tipo-de="${id}">` +
    `${opcionesDeTipo(tipo)}</select></label>` +
    `<div class="botones">` +
    `<button data-aparato="aprobar" data-id="${id}" type="button">` +
    `aprobar</button>` +
    `<button data-aparato="rechazar" data-id="${id}" type="button">` +
    `rechazar</button>` +
    `</div></div>`;
}

/** Todo lo que ya no golpea: vivas, caducas, revocadas y rechazadas. El
 *  boton de revocar sale SOLO para una viva con hash. Una viva sin hash es
 *  una aprobacion que el aparato todavia no canjeo (el hash nace en el
 *  canje): no hay con que revocarla, y un boton que da 404 miente. */
function filaDeAparato(aparato) {
  const viva = aparato.efectivo === "viva";
  const sinCanjear = viva && !aparato.hash_id
    ? `<div class="nota">aprobado, esperando al aparato</div>` : "";
  const revocar = viva && aparato.hash_id
    ? `<button data-aparato="revocar" data-id="${escapar(aparato.hash_id)}" ` +
      `type="button">revocar</button>` : "";
  return `<div class="aparato">` +
    `<div class="nombre">${escapar(aparato.aparato)}</div>` +
    `<div class="fila"><span>${escapar(aparato.tipo)}</span>` +
    `<span class="etiqueta">${escapar(aparato.efectivo)}</span></div>` +
    `<div class="fila"><span>ultima vez</span>` +
    `<span>${escapar(fechaLegible(aparato.ultima_vez))}</span></div>` +
    sinCanjear + revocar + `</div>`;
}

/** Cuantos aparatos estan esperando que Pedro conteste. Es lo que se suma
 *  al badge de la mesa: un golpe caduca en 10 minutos, asi que enterarse
 *  sin buscarlo es la diferencia entre aprobar y volver a golpear. */
export function contadorDeAparatos(datos) {
  return (datos?.aparatos || []).filter(a => a.efectivo === "golpeando").length;
}

/**
 * `datos`: la respuesta de GET /api/aparatos -`{aparatos: [...]}` con el
 * estado `efectivo` ya derivado del reloj por el server-. `mensaje`: el
 * aviso pasajero de la ultima accion, o null. `elegidos`: Map id_pedido ->
 * tipo con lo que dicen los selectores que YA estan en pantalla (app.js los
 * lee justo antes de reemplazar el HTML); un Map y no un objeto para que un
 * id_pedido llamado "constructor" o "__proto__" no encuentre nada raro.
 */
export function textoDeAparatos(datos, mensaje = null, elegidos = new Map()) {
  const listo = mensaje
    ? `<div class="listo">${escapar(mensaje)}</div>` : "";
  const todos = datos?.aparatos || [];
  const golpes = todos.filter(a => a.efectivo === "golpeando");
  const resto = todos.filter(a => a.efectivo !== "golpeando");
  const bloqueGolpes = golpes.length
    ? golpes.map(g => tarjetaDeGolpe(g, elegidos)).join("")
    : `<div class="vacio">Ningun aparato esta pidiendo entrar.</div>`;
  const bloqueLista = resto.length
    ? resto.map(filaDeAparato).join("")
    : `<div class="vacio">Ningun aparato dado de alta.</div>`;
  return listo +
    `<div class="subtitulo">pidiendo entrar</div>` + bloqueGolpes +
    `<div class="subtitulo">aparatos</div>` + bloqueLista;
}
