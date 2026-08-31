import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDeFreno} from "./freno.js";

const LIBRE = {nombre: "atlas", propuestas_propias: 1, freno_pedir: null};

test("un departamento que puede pedir no dibuja ningun aviso", () => {
  assert.equal(textoDeFreno(LIBRE, 3), "");
});

test("null o undefined no revientan", () => {
  assert.equal(textoDeFreno(null, 3), "");
  assert.equal(textoDeFreno(undefined, 3), "");
});

test("el freno del pre-seed se pinta con las palabras del servidor", () => {
  const html = textoDeFreno(
    {...LIBRE, freno_pedir: "el techo de la ventana es 60000 mm y entre lo " +
                            "financiado (0) y lo pedido en pie (60000) ya van " +
                            "60000: que Pedro suba la perilla"}, 3);
  assert.match(html, /class="aviso freno"/);
  assert.match(html, /no puede pedir su ronda pre-seed/);
  // el texto del servidor entero, no un resumen que se despegue de el
  assert.match(html, /pedido en pie \(60000\)/);
  assert.match(html, /suba la perilla/);
});

test("la bandeja llena se dice aparte, porque tapa proponer Y pedir", () => {
  const html = textoDeFreno({...LIBRE, propuestas_propias: 3}, 3);
  assert.match(html, /no puede proponer ni pedir/);
  assert.match(html, /3 de 3 propuestas en pie/);
  // y nombra las tres salidas, incluida la que no pide un gesto de Pedro
  assert.match(html, /financiando o descartando/);
  assert.match(html, /sale de la ventana/);
});

test("con los dos frenos a la vez se dicen los dos, no el primero", () => {
  const html = textoDeFreno(
    {...LIBRE, propuestas_propias: 4, freno_pedir: "sin techo de pre-seed"}, 3);
  assert.match(html, /no puede proponer ni pedir/);
  assert.match(html, /sin techo de pre-seed/);
  // dos renglones: son dos gestos distintos de Pedro y elegir uno solo lo
  // dejaria arreglando la mitad
  assert.equal((html.match(/<div>/g) || []).length, 2);
});

test("sin el techo de propuestas (respuesta vieja) no inventa el aviso", () => {
  // mejor callarse que decirle a Pedro que un departamento esta trabado
  // comparando contra un techo que no sabemos: es la misma regla que
  // `alcanza` en mesa.js sigue con el saldo del tesoro
  assert.equal(textoDeFreno({...LIBRE, propuestas_propias: 9}, undefined), "");
  assert.equal(textoDeFreno({...LIBRE, propuestas_propias: 9}, 0), "");
});

test("el texto del servidor pasa por escapar()", () => {
  const html = textoDeFreno(
    {...LIBRE, freno_pedir: "<img src=x onerror=alert(1)>"}, 3);
  assert.ok(!html.includes("<img"), "inyecto marcado crudo");
  assert.match(html, /&lt;img/);
});

test("el freno se lee en monedas, como todo lo demas de la tarjeta", () => {
  // El jefe habla milimonedas -- su prompt entero esta en milimonedas -- y
  // Pedro lee monedas. Este era el unico renglon en mm de una tarjeta donde
  // todo lo demas pasa por monedas(): tres lineas mas arriba el campo
  // "techo por pedido (en monedas)" con un 50 adentro, y aca abajo "el
  // techo de la ronda es 50000". El mismo numero, leido como si fueran mil
  // veces distintos.
  const html = textoDeFreno(
    {...LIBRE, freno_pedir: "ya tiene 55000 mm entre billetera y pedidos " +
                            "en pie, y el techo de la ronda es 50000 mm: " +
                            "el pre-seed es para arrancar sin plata"}, 3);
  assert.match(html, /ya tiene 55 monedas entre billetera/);
  assert.match(html, /el techo de la ronda es 50 monedas/);
  assert.ok(!/\d+ mm/.test(html), `quedo un numero en mm: ${html}`);
  // y la frase sigue siendo la del servidor, palabra por palabra
  assert.match(html, /el pre-seed es para arrancar sin plata/);
});

test("el default de las perillas se dice en gris, no en rojo", () => {
  // `techo_preseed_mm` nace en cero, asi que sin esto cada departamento de
  // fabrica recien dado de alta estrenaba una barra roja permanente sobre
  // su estado por defecto. Un aviso que esta siempre se vuelve invisible en
  // dos dias, y despues el que si importa aparece al lado de uno que Pedro
  // ya aprendio a ignorar. Se dice igual -- Pedro tiene que poder leer por
  // que ese departamento esta callado -- pero como nota.
  const html = textoDeFreno(
    {...LIBRE, freno_pedir: "sin techo de pre-seed: Pedro todavia no " +
                            "autorizo cuanto puede pedir",
     freno_pedir_sin_autorizar: true}, 3);
  assert.match(html, /class="aviso nota"/);
  assert.ok(!/class="aviso freno"/.test(html), `lo pinto trabado: ${html}`);
  assert.match(html, /Pedro todavia no autorizo cuanto puede pedir/);
});

test("y el freno de verdad sigue en rojo, aunque haya una nota al lado", () => {
  // el caso que separa las dos clases: la bandeja llena SI esta trabada y
  // pide un gesto de Pedro, y el pre-seed todavia sin autorizar no. Los dos
  // se dicen, cada uno en su bloque.
  const html = textoDeFreno(
    {...LIBRE, propuestas_propias: 3,
     freno_pedir: "sin techo de pre-seed: Pedro todavia no autorizo cuanto " +
                  "puede pedir",
     freno_pedir_sin_autorizar: true}, 3);
  assert.match(html, /class="aviso freno"/);
  assert.match(html, /class="aviso nota"/);
  assert.match(html, /no puede proponer ni pedir/);
  assert.match(html, /todavia no autorizo/);
  assert.ok(html.indexOf('class="aviso freno"')
            < html.indexOf('class="aviso nota"'), "la nota tapo al freno");
});
