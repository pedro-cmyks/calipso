import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDeGoals, tarjetaDeGoal, contadorDeGoals, consumoDe, esperaDe} from "./goals.js";

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
