import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDeInbox, contadorDeInbox} from "./inbox.js";

const DESCRIPTORES = {
  mesa: {origen: "mesa", verbos: [
    {nombre: "financiar", etiqueta: "Financiar", parametros: ["cuenta"]},
    {nombre: "descartar", etiqueta: "Descartar", parametros: []}]},
  permisos: {origen: "permisos", verbos: [
    {nombre: "si", etiqueta: "Si", parametros: []},
    {nombre: "si_siempre", etiqueta: "Si, siempre", parametros: []},
    {nombre: "no", etiqueta: "No", parametros: []}]},
};

function datos(items) {
  return {items, descriptores: DESCRIPTORES, pendientes: items.length,
          fallaron: []};
}

test("el inbox vacio lo dice y no queda en blanco", () => {
  const html = textoDeInbox(datos([]));
  assert.match(html, /nada esperando|no hay nada/i);
});

test("solo se dibujan los verbos que el item declara validos", () => {
  const html = textoDeInbox(datos([{
    id: "sol_a", origen: "permisos", clase: "decision", ts: "", estado: "pendiente",
    titulo: "acunar 500000 mm", respuesta: null,
    cuerpo: {verbos_validos: ["si", "no"]}}]));
  assert.match(html, /data-verbo="si"/);
  assert.match(html, /data-verbo="no"/);
  assert.ok(!html.includes('data-verbo="si_siempre"'),
            "dibujo un verbo que el item no declaro");
});

test("el titulo se escapa: lo escribe un modelo", () => {
  const html = textoDeInbox(datos([{
    id: "a-1", origen: "mesa", clase: "decision", ts: "", estado: "alta",
    titulo: '<script>alert(1)</script>', respuesta: null,
    cuerpo: {verbos_validos: ["descartar"]}}]));
  assert.ok(!html.includes("<script"));
  assert.match(html, /&lt;script/);
});

test("un id con dos puntos no rompe el markup", () => {
  const html = textoDeInbox(datos([{
    id: "mandato:dep:a:2026-W35", origen: "cartas", clase: "decision",
    ts: "", estado: "encolada", titulo: "mandato", respuesta: null,
    cuerpo: {verbos_validos: ["atender"]}}]));
  assert.match(html, /data-id="mandato:dep:a:2026-W35"/);
  assert.match(html, /data-origen="cartas"/);
});

test("el contador cuenta decisiones y no avisos", () => {
  const d = datos([
    {id: "a", origen: "mesa", clase: "decision", cuerpo: {}, titulo: "x"},
    {id: "b", origen: "permisos", clase: "aviso", cuerpo: {}, titulo: "y"}]);
  assert.equal(contadorDeInbox(d), 1);
});

test("una bandeja caida se dice, no se calla", () => {
  const d = datos([]);
  d.fallaron = ["biblioteca"];
  assert.match(textoDeInbox(d), /biblioteca/);
});

test("null o undefined no revientan", () => {
  assert.match(textoDeInbox(null), /nada esperando|no hay nada/i);
  assert.equal(contadorDeInbox(undefined), 0);
});
