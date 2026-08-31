/**
 * calipso/web/fabrica/freno.js — Por que un departamento esta callado.
 *
 * El agujero que tapa: Pedro veia el acumulado de la ventana en CERO y al
 * departamento sin publicar nada, y no habia forma de conectar las dos
 * cosas. Lo que lo frenaba era un pedido suyo olvidado en la mesa -- que
 * el jefe se descuenta como reserva y el numero de Pedro no cuenta-- o la
 * bandeja llena de propuestas en pie. Los dos frenos existian y ninguno
 * tenia cara.
 *
 * Lo que este modulo NO hace: decidir. El texto del freno del pre-seed lo
 * escribe `jefe.freno_preseed` en el servidor y viaja hecho en
 * `freno_pedir`; aca solo se pinta. Reimplementar los cuatro frenos en JS
 * seria una segunda fuente de verdad sobre el mismo techo, que es
 * exactamente el error que este techo ya cometio dos veces (`server.py` y
 * `situacion.py` contestando distinto "en que ventana estoy"). Por eso lo
 * unico que se calcula aca es la comparacion del contador de la bandeja,
 * con el techo que TAMBIEN manda el servidor.
 *
 * Modulo puro que devuelve HTML, como mesa.js y perillas.js: el DOM lo
 * toca app.js. Todo lo que sale por innerHTML pasa por escapar().
 */
import {escapar} from "./paneles.js";

/**
 * `dep`: una fila de `GET /api/economia/config`.departamentos.
 * `techoPropuestas`: `config.techo_propuestas` (o null/undefined si la
 * respuesta es vieja y no lo trae).
 *
 * Devuelve "" cuando el departamento puede pedir: el silencio es la senal
 * de que no hay nada que explicar, y un renglon permanente de "esta bien"
 * se vuelve invisible en dos dias. Un aviso solo aparece cuando hay algo
 * trabado, que es cuando Pedro lo necesita.
 */
export function textoDeFreno(dep, techoPropuestas) {
  if (!dep) return "";
  const lineas = [];
  const enPie = Number(dep.propuestas_propias || 0);
  const techo = Number(techoPropuestas || 0);
  // La bandeja va PRIMERO porque es el freno que corre primero en
  // `jefe._puede`, y porque tapa a los dos verbos: con la bandeja llena el
  // departamento no puede ni proponer ni pedir. Decir solo el del pre-seed
  // dejaria a Pedro subiendo una perilla que no destraba nada.
  if (techo > 0 && enPie >= techo) {
    lineas.push(`no puede proponer ni pedir: tiene ${escapar(enPie)} de ` +
      `${escapar(techo)} propuestas en pie. Se despeja financiando o ` +
      `descartando en la mesa, y un pedido de pre-seed ademas se despeja ` +
      `solo cuando su semana sale de la ventana.`);
  }
  // Y el del pre-seed, EN LAS PALABRAS DEL SERVIDOR. Es el mismo string
  // que recibio el jefe: si aca se leyera distinto de lo que al jefe lo
  // freno, Pedro estaria depurando dos cosas.
  if (dep.freno_pedir) {
    lineas.push(`no puede pedir su ronda pre-seed: ` +
                `${escapar(dep.freno_pedir)}`);
  }
  if (!lineas.length) return "";
  return `<div class="aviso freno">` +
    lineas.map(x => `<div>${x}</div>`).join("") + `</div>`;
}
