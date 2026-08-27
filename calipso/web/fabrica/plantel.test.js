import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDePlantel} from "./plantel.js";

function estado(extra = {}) {
  return {activo: true, encendido: true, modo: "ensayo", techo_tics: 500,
          ...extra};
}

test("el plantel no disponible muestra el aviso y no ofrece botones", () => {
  for (const e of [null, {activo: false}]) {
    const html = textoDePlantel(e);
    assert.match(html, /no esta disponible/i);
    assert.ok(!html.includes("data-plantel"),
              "aparecio un control de plantel sin plantel disponible");
    assert.ok(!html.includes("<form"),
              "aparecio el formulario de rutina sin plantel disponible");
  }
});

test("los botones de accion llevan type=\"button\" y su data-plantel", () => {
  // sin type="button" el navegador les da "submit" por default -esten o no
  // dentro de un form- y el click handler de app.js descarta justo los
  // botones de tipo submit: este es el test que habria atrapado ese bug.
  const html = textoDePlantel(estado());
  assert.match(html, /<button type="button" data-plantel="parar">parar<\/button>/);
  assert.match(html, /<button type="button" data-plantel="modo" data-modo="/);
});

test("encendido ofrece parar, no reanudar: reanudar ya esta en efecto", () => {
  // con los dos botones siempre presentes, apretar el que ya esta en
  // efecto no produce NINGUNA senal (el servidor contesta 200 igual, la
  // tira se repinta identica): asi lo vivio Pedro. Cada estado ofrece
  // solo la accion que todavia puede cambiar algo.
  const html = textoDePlantel(estado({encendido: true}));
  assert.match(html, /data-plantel="parar"/);
  assert.ok(!html.includes('data-plantel="reanudar"'),
            "aparecio 'reanudar' con el plantel ya encendido");
});

test("apagado ofrece reanudar, no parar: parar ya esta en efecto", () => {
  const html = textoDePlantel(estado({encendido: false}));
  assert.match(html, /data-plantel="reanudar"/);
  assert.ok(!html.includes('data-plantel="parar"'),
            "aparecio 'parar' con el plantel ya apagado");
});

test("el boton de modo ofrece pasar a vivo cuando esta en ensayo", () => {
  const html = textoDePlantel(estado({modo: "ensayo"}));
  assert.match(html, /data-modo="vivo">pasar a vivo<\/button>/);
});

test("el boton de modo ofrece pasar a ensayo cuando esta en vivo", () => {
  const html = textoDePlantel(estado({modo: "vivo"}));
  assert.match(html, /data-modo="ensayo">pasar a ensayo<\/button>/);
});

test("en modo vivo aparece la advertencia de que la fabrica gasta sola", () => {
  const html = textoDePlantel(estado({modo: "vivo"}));
  assert.match(html, /class="peligro"/);
  assert.match(html, /gasta sola/);
});

test("en modo ensayo no aparece la advertencia de vivo", () => {
  const html = textoDePlantel(estado({modo: "ensayo"}));
  assert.ok(!html.includes("peligro"),
            "aparecio la advertencia de vivo estando en ensayo");
});

test("el estado dice apagado cuando encendido es falso", () => {
  const html = textoDePlantel(estado({encendido: false}));
  assert.match(html, /class="estado">apagado/);
});

test("el estado dice encendido cuando encendido es verdadero", () => {
  const html = textoDePlantel(estado({encendido: true}));
  assert.match(html, /class="estado">encendido/);
});

test("el modo se escapa antes de entrar al html: lo manda un input de Pedro",
     () => {
  const malo = '<img src=x onerror="alert(1)">';
  const html = textoDePlantel(estado({modo: malo}));
  assert.ok(!html.includes("<img"), "se colo una etiqueta por el modo");
  assert.match(html, /&lt;img/);
});

test("el techo tambien se escapa", () => {
  // no deberia llegar nunca un string por techo_tics, pero escapar(String())
  // esta ahi por las dudas: si algun dia se rompe, que se note aca y no en
  // el navegador de Pedro
  const html = textoDePlantel(estado({techo_tics: '<script>x</script>'}));
  assert.ok(!html.includes("<script"), "se colo una etiqueta por el techo");
  assert.match(html, /&lt;script/);
});
