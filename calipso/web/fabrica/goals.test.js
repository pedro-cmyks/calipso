import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDeGoals, tarjetaDeGoal, contadorDeGoals, consumoDe, esperaDe,
        notasEscritas, instruccionDe} from "./goals.js";

const BASE = {
  id: "goal_abc123", title: "saludo.py con hola() y su test", objective: "crea saludo.py",
  status: "active", manos: "claude", repo: "/home/p/.calipso/goals/goal_abc123/repo",
  criterio: {tipo: "comando", comando: "pytest -q"},
  tope: {golpes: 6, minutos: 10, unidades: 30, mm: 0},
  consumo: {golpes: 2, minutos: 1.5, unidades: 12, mm: 0},
  espera: null, plan: ["leer", "escribir", "probar"],
};
const GOLPES = [
  {n: 1, fase: "fin", manos: "claude", unidades: 5, duracion_ms: 40000, diff_stat: "saludo.py | 3 +++",
   veredicto_del_golpe: {estado: "sigo", resumen: "escribi saludo.py"},
   comandos: [{cmd: "pytest -q", resultado_tail: "1 passed"}], cobro: {unidades: 5, cobrado: false}},
  {n: 2, fase: "inicio", manos: "claude"},
];

test("el consumo se lee contra el tope", () => {
  assert.equal(consumoDe(BASE), "2/6 golpes, 1.5/10 min, 12/30 unidades");
  assert.equal(consumoDe({tope: {golpes: 3}}), "0/3 golpes, 0/? min, 0/? unidades");
  assert.equal(consumoDe({}), "0/? golpes, 0/? min, 0/? unidades");
});

test("la espera se lee con su motivo y su pregunta", () => {
  assert.equal(esperaDe({status: "active"}), "");
  assert.match(esperaDe({status: "waiting", espera: {motivo: "tope", tope: "golpes"}}), /tope: golpes/);
  assert.match(esperaDe({status: "waiting", espera: {motivo: "pregunta", pregunta: "pytest o unittest?"}}),
               /pytest o unittest\?/);
  assert.match(esperaDe({status: "waiting", espera: {motivo: "cumplido", sin_veredicto_de_modelo: true}}),
               /sin veredicto de modelo/);
  assert.match(esperaDe({status: "waiting", espera: {motivo: "no_convergencia", diagnostico: "tres golpes"}}),
               /tres golpes/);
});

test("la tarjeta del activo trae estado, consumo y el ledger", () => {
  const html = tarjetaDeGoal(BASE, GOLPES);
  assert.match(html, /saludo\.py con hola\(\)/);
  assert.match(html, /class="estado active"/);
  assert.match(html, /2\/6 golpes/);
  assert.match(html, /golpe 1/);
  assert.match(html, /escribi saludo\.py/);
  assert.match(html, /pytest -q/);
  assert.match(html, /saludo\.py \| 3 \+\+\+/);
  assert.match(html, /golpe 2 \(en curso\)/);
  assert.match(html, /5 unidades/);
});

test("los botones dependen del estado", () => {
  const p = tarjetaDeGoal({...BASE, status: "proposed"});
  assert.match(p, /data-goal="dale" data-id="goal_abc123"/);
  assert.match(p, /data-goal="no"/);
  assert.doesNotMatch(p, /data-goal="parar"/);
  const a = tarjetaDeGoal(BASE);
  assert.match(a, /data-goal="parar"/);
  assert.doesNotMatch(a, /data-goal="dale"/);
  const w = tarjetaDeGoal({...BASE, status: "waiting", espera: {motivo: "tope", tope: "golpes"}});
  assert.match(w, /data-goal="segui"/);
  assert.match(w, /data-nota-de="goal_abc123"/);
  assert.match(w, /data-goal="no"/);
  assert.doesNotMatch(w, /data-goal="dale"/);
  const c = tarjetaDeGoal({...BASE, status: "waiting", espera: {motivo: "cumplido", resumen: "listo"}});
  assert.match(c, /data-goal="dale"/);              // el dale final
  assert.match(c, /data-goal="segui"/);             // o devolverlo con nota
  const f = tarjetaDeGoal({...BASE, status: "complete"});
  assert.doesNotMatch(f, /data-goal=/);
});

test("la lista pone el activo primero y cuenta los waiting", () => {
  const datos = {activo: {...BASE, status: "waiting", espera: {motivo: "tope", tope: "golpes"}},
                 goals: [{...BASE, id: "goal_viejo", status: "complete"},
                         {...BASE, status: "waiting", espera: {motivo: "tope", tope: "golpes"}}]};
  const html = textoDeGoals(datos, GOLPES);
  assert.ok(html.indexOf("goal_abc123") < html.indexOf("goal_viejo"));
  assert.match(html, /esperando a Pedro/);
  assert.equal(contadorDeGoals(datos), 1);
  assert.equal(contadorDeGoals({activo: null, goals: []}), 0);
  assert.match(textoDeGoals({activo: null, goals: []}), /Ningun goal/);
});

test("todo pasa por escapar", () => {
  const malo = "<img src=x onerror=alert(1)>";
  const html = textoDeGoals({activo: null, goals: [{...BASE, id: malo, title: malo, status: "waiting",
                                                     espera: {motivo: "pregunta", pregunta: malo}}]},
                            [{n: 1, fase: "fin", veredicto_del_golpe: {estado: "sigo", resumen: malo},
                              comandos: [{cmd: malo, resultado_tail: malo}], diff_stat: malo}]);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
});

test("robustez: null, undefined, goals rotos", () => {
  assert.match(textoDeGoals(null), /Ningun goal/);
  assert.match(textoDeGoals(undefined), /Ningun goal/);
  assert.match(textoDeGoals({goals: [{}]}), /sin titulo/);
  assert.equal(contadorDeGoals(null), 0);
  assert.equal(typeof tarjetaDeGoal({}, null), "string");
});

test("la nota que Pedro tipea en un waiting sobrevive al repintado", () => {
  // cierre 2026-09-14 (rev:ui-smoke): el sondeo de 60 s y avisarEnGoals
  // reemplazan el HTML entero de la caja y el input nacia vacio. app.js lee
  // las notas con notasEscritas ANTES de repintar y textoDeGoals las repone
  // en el value del input de cada goal; vacias o solo espacios no cuentan.
  const caja = {querySelectorAll: sel => sel === "input[data-nota-de]" ? [
    {dataset: {notaDe: "goal_abc123"}, value: 'falta el test <b class="x">'},
    {dataset: {notaDe: "goal_otro"}, value: "   "}] : []};
  const notas = notasEscritas(caja);
  assert.deepEqual(notas, {goal_abc123: 'falta el test <b class="x">'});
  assert.deepEqual(notasEscritas(null), {});
  assert.deepEqual(notasEscritas({}), {});
  const w = {...BASE, status: "waiting", espera: {motivo: "tope", tope: "golpes"}};
  const html = textoDeGoals({activo: w, goals: [{...w, id: "goal_otro"}]}, [], notas);
  assert.match(html, /data-nota-de="goal_abc123"[^>]*value="falta el test &lt;b class=&quot;x&quot;&gt;"/);
  assert.doesNotMatch(html, /<b class/);
  // el goal sin nota nace sin value, y sin el mapa tampoco
  assert.doesNotMatch(html.slice(html.indexOf('data-nota-de="goal_otro"')), /value=/);
  assert.doesNotMatch(tarjetaDeGoal(w), /value=/);
});

test("la espera trae las opciones del runner y la instruccion por el chat", () => {
  // cierre 2026-09-14 (Pedro no se pierde): un waiting por tope, cuota o no
  // convergencia lleva `espera.opciones` (goals_runner.OPCIONES_RETOMAR) y
  // la tarjeta las lista; y siempre dice como seguir por el chat: la opcion
  // "por el chat:" del runner si vino, si no `/goal segui <nota>` (para
  // tope, `/goal segui tope: ...`).
  const tope = {...BASE, status: "waiting", espera: {motivo: "tope", tope: "golpes",
    opciones: ["si = seguir con el tope ampliado un 50 %", "no = cancelar el goal",
               "por el chat: /goal segui tope: <N golpes | Nm | N unidades>"]}};
  assert.equal(instruccionDe(tope), "/goal segui tope: <N golpes | Nm | N unidades>");
  const html = tarjetaDeGoal(tope);
  assert.match(html, /<li>si = seguir con el tope ampliado un 50 %<\/li>/);
  assert.match(html, /<li>no = cancelar el goal<\/li>/);
  assert.match(html, /por el chat: \/goal segui tope: &lt;N golpes \| Nm \| N unidades&gt;/);
  // sin opciones (la pregunta del martillo, una compuerta, el cumplido): la instruccion igual
  const pregunta = {...BASE, status: "waiting", espera: {motivo: "pregunta", pregunta: "pytest o unittest?"}};
  assert.equal(instruccionDe(pregunta), "/goal segui <nota>");
  assert.match(tarjetaDeGoal(pregunta), /por el chat: \/goal segui &lt;nota&gt;/);
  assert.doesNotMatch(tarjetaDeGoal(pregunta), /<ul/);
  // tope sin opciones (un goal viejo): la instruccion del tope
  assert.equal(instruccionDe({...BASE, status: "waiting", espera: {motivo: "tope", tope: "minutos"}}),
               "/goal segui tope: <N golpes | Nm | N unidades>");
  // el cumplido: cerrar o devolverlo con nota
  const c = instruccionDe({...BASE, status: "waiting", espera: {motivo: "cumplido"}});
  assert.match(c, /\/goal dale/);
  assert.match(c, /\/goal segui <nota>/);
  // fuera de waiting no hay instruccion ni opciones
  assert.equal(instruccionDe(BASE), "");
  assert.equal(instruccionDe(null), "");
  assert.doesNotMatch(tarjetaDeGoal(BASE), /por el chat/);
  // las opciones tambien pasan por escapar
  const malo = "<img src=x onerror=alert(1)>";
  const m = tarjetaDeGoal({...tope, espera: {motivo: "tope", opciones: [malo, 42, null]}});
  assert.doesNotMatch(m, /<img/);
  assert.match(m, /&lt;img/);
});
