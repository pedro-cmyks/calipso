import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDeMesa, hayQueAvisarDeLaSemana} from "./mesa.js";

const DEPS = [
  {cuenta: "dep:atlas", nombre: "atlas", zona: "fabrica", disponible_mm: 400000},
  {cuenta: "dep:mercado", nombre: "mercado", zona: "fabrica", disponible_mm: 5000},
];

function datos(propuestas, extra = {}) {
  return {activa: true, semana: "2026-W35", semana_abierta: true,
          propuestas, departamentos: DEPS, ...extra};
}

const P1 = {id: "p1", estado: "alta", departamento: "dep:atlas",
            titulo: "radar de precios", presupuesto_mm: 10000,
            retorno_mm: 10000, criterio: {}, gastado_mm: 0, aportes: {}};

test("sin propuestas lo dice, no queda en blanco", () => {
  const html = textoDeMesa(datos([]));
  assert.match(html, /ninguna propuesta|nada que decidir/i);
});

test("una propuesta trae su departamento, su titulo y sus dos botones", () => {
  const html = textoDeMesa(datos([P1]));
  assert.match(html, /atlas/);
  assert.match(html, /radar de precios/);
  assert.match(html, /data-accion="financiar"/);
  assert.match(html, /data-accion="descartar"/);
  assert.match(html, /data-id="p1"/);
});

test("el titulo se escapa: lo escribe un modelo, no es de confianza", () => {
  const malo = {...P1, titulo: '<img src=x onerror="alert(1)">'};
  const html = textoDeMesa(datos([malo]));
  assert.ok(!html.includes("<img"), "se colo una etiqueta del modelo");
  assert.match(html, /&lt;img/);
});

test("el id, la cuenta y el departamento tambien se escapan", () => {
  // una etiqueta distinta por campo, y ninguna que la plantilla emita por su
  // cuenta: asi un fallo dice cual se colo. El <b> no sirve de payload
  // porque fila() ya lo usa para el nombre del departamento.
  const venenoso = {...P1, id: '"><img src=x onerror="alert(1)">',
                    departamento: 'dep:<iframe src=x>'};
  const deps = [{cuenta: '"><script>alert(1)</script>', nombre: "raro",
                 zona: "fabrica", disponible_mm: 999999}];
  const html = textoDeMesa({activa: true, semana: "2026-W35",
                            semana_abierta: true, propuestas: [venenoso],
                            departamentos: deps});
  assert.ok(!html.includes("<img"), "se colo una etiqueta por el id");
  assert.ok(!html.includes("<script"), "se colo una etiqueta por la cuenta");
  assert.ok(!html.includes("<iframe"), "se colo una etiqueta por el departamento");
});

test("el selector ofrece los departamentos y preselecciona al dueno", () => {
  const html = textoDeMesa(datos([P1]));
  assert.match(html, /<option value="dep:atlas" selected/);
  assert.match(html, /<option value="dep:mercado"/);
});

test("un departamento sin plata suficiente queda anotado", () => {
  const html = textoDeMesa(datos([{...P1, departamento: "dep:mercado"}]));
  assert.match(html, /sin saldo|no alcanza/i);
});

test("una financiada muestra lo gastado y no ofrece botones", () => {
  const fin = {...P1, estado: "financiada", gastado_mm: 3000,
               aportes: {"dep:atlas": 10000}};
  const html = textoDeMesa(datos([fin]));
  assert.ok(!html.includes('data-accion="financiar"'));
  assert.ok(!html.includes('data-accion="descartar"'));
  assert.match(html, /financiada/i);
});

test("la fila lleva el presupuesto, que es lo que se manda al financiar", () => {
  const html = textoDeMesa(datos([P1]));
  assert.match(html, /data-presupuesto="10000"/);
});

test("el numero del presupuesto dice que es un presupuesto", () => {
  // un numero pelado no dice si es plata, milimonedas o tics; en la fila
  // financiable (a diferencia de la financiada, que ya dice "gastado") no
  // hay contexto que lo aclare, asi que la etiqueta va al lado.
  const html = textoDeMesa(datos([P1]));
  assert.match(html, /presupuesto 10\b/);
});

test("con la semana cerrada hay que avisar", () => {
  assert.equal(hayQueAvisarDeLaSemana(datos([P1], {semana_abierta: false})), true);
  assert.equal(hayQueAvisarDeLaSemana(datos([P1])), false);
});

test("sin economia activa no se avisa de la semana", () => {
  assert.equal(hayQueAvisarDeLaSemana({activa: false}), false);
});

test("sin economia activa la mesa lo dice", () => {
  assert.match(textoDeMesa({activa: false}), /economia no esta activa/i);
});
