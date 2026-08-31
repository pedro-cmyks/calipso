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
import {motivoEnMonedas} from "./permisos.js";

/**
 * `dep`: una fila de `GET /api/economia/config`.departamentos.
 * `techoPropuestas`: `config.techo_propuestas` (o null/undefined si la
 * respuesta es vieja y no lo trae).
 *
 * Devuelve "" cuando el departamento puede pedir: el silencio es la senal
 * de que no hay nada que explicar, y un renglon permanente de "esta bien"
 * se vuelve invisible en dos dias. Un aviso solo aparece cuando hay algo
 * trabado, que es cuando Pedro lo necesita.
 *
 * Y por la misma razon hay DOS bloques y no uno: lo trabado va en --acento
 * con la barra al costado, y lo que todavia no se autorizo -- el default de
 * todo departamento nuevo -- va en gris como las demas notas. Un rojo que
 * esta siempre no se lee mas que un gris, y se lleva puesto al que importa.
 */
export function textoDeFreno(dep, techoPropuestas) {
  if (!dep) return "";
  const lineas = [];   // lo que esta trabado: --acento y barra al costado
  const notas = [];    // lo que todavia no se autorizo: gris, como el resto
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
  //
  // Lo unico que cambia es la UNIDAD, con `motivoEnMonedas` -- el mismo
  // sustituidor generico que ya usa la pantalla de permisos sobre los
  // motivos del motor. El jefe habla milimonedas (su prompt entero esta en
  // milimonedas) y Pedro lee monedas, y este era el unico renglon en mm de
  // una tarjeta donde todo lo demas pasa por `monedas()`: tres lineas mas
  // arriba el campo "techo por pedido (en monedas)" con un 50 adentro y
  // aca abajo "el techo de la ronda es 50000". El mismo numero, leido como
  // si fueran mil veces distintos. No es reescribir la frase: la frase
  // sigue siendo la del servidor, palabra por palabra.
  if (dep.freno_pedir) {
    const motivo = escapar(motivoEnMonedas(dep.freno_pedir));
    // El "no puede pedir su ronda pre-seed:" de adelante hace falta cuando
    // el motivo por si solo no dice QUE esta trabado ("ya tiene 55 monedas
    // entre billetera y pedidos en pie"). El del default ya lo dice entero,
    // y ponerselo repetia el sujeto y encadenaba dos dos-puntos: "no puede
    // pedir su ronda pre-seed: sin techo de pre-seed: Pedro todavia no
    // autorizo cuanto puede pedir". Ademas la nota vive adentro de la
    // tarjeta de las perillas de pre-seed, que ya es el contexto.
    const texto = dep.freno_pedir_sin_autorizar
      ? motivo : `no puede pedir su ronda pre-seed: ${motivo}`;
    // y la CLASE, que la manda el servidor (`freno_pedir_sin_autorizar`).
    // Un departamento recien dado de alta tiene las dos perillas de
    // pre-seed en su default cero, y el freno dice "Pedro todavia no
    // autorizo": eso no esta trabado, es el estado inicial, y las dos
    // perillas estan tres renglones mas arriba con su cero a la vista y
    // editables. Pintarlo en --acento con la barra al costado le
    // estrenaba a cada departamento nuevo un aviso rojo permanente -- el
    // mismo modo de falla que este renglon vino a evitar, dado vuelta: un
    // aviso que esta siempre se vuelve invisible en dos dias, y despues el
    // que si importa (bandeja llena, techo de la ventana) aparece al lado
    // de uno que Pedro ya aprendio a ignorar. Se dice igual, en gris.
    if (dep.freno_pedir_sin_autorizar) notas.push(texto);
    else lineas.push(texto);
  }
  const pinta = (clase, xs) => xs.length
    ? `<div class="aviso ${clase}">` +
      xs.map(x => `<div>${x}</div>`).join("") + `</div>`
    : "";
  return pinta("freno", lineas) + pinta("nota", notas);
}
