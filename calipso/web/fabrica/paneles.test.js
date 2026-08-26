import test from "node:test";
import assert from "node:assert/strict";

import {disposicion, textoDeTarjeta, posicionDeTarjeta, resumenDeAvisos,
        ANCHO_TELEFONO, textoDeCosto, textoDeFoco,
        textoDeEmpleado, textoDeRazonamiento} from "./paneles.js";
import {fichaDe} from "./ciudad.js";

function ciudadDePrueba() {
  const base = {nombre: "atlas", zona: "fabrica", orden: 0, tamano: 4,
                estado: "activo", saldo_mm: 1_148_000, gasto_ciclo_mm: 22_500,
                ventas_ventana_mm: 900_000, eficiencia_pormil: 1234,
                actividad: 2, trabajos: [], compuertas: 0, x: 0, y: 0};
  return {
    edificios: [{...base, id: "dep:atlas"},
                {...base, id: "dep:frio", nombre: "frio", estado: "congelado"}],
    calles: [], unidades: [],
    avisos: [{id: "c1", tipo: "gasto", sobre: "dep:atlas",
              monedas_en_juego_mm: 50_000},
             {id: "c2", tipo: "renovacion", sobre: null,
              monedas_en_juego_mm: 120_000}],
  };
}

test("el ancho decide la disposicion", () => {
  assert.equal(disposicion(1400), "tres-paneles");
  assert.equal(disposicion(ANCHO_TELEFONO + 1), "tres-paneles");
  assert.equal(disposicion(ANCHO_TELEFONO), "dos-pestanas");
  assert.equal(disposicion(390), "dos-pestanas");
});

test("la tarjeta muestra los cinco numeros de la ficha", () => {
  const html = textoDeTarjeta(fichaDe(ciudadDePrueba(), "dep:atlas"));
  for (const esperado of ["atlas", "1.148", "22,5", "900", "123,4%"]) {
    assert.ok(html.includes(esperado), `falta ${esperado} en la tarjeta`);
  }
});

test("la tarjeta de un congelado lo dice", () => {
  const html = textoDeTarjeta(fichaDe(ciudadDePrueba(), "dep:frio"));
  assert.ok(/congelado/i.test(html));
});

test("la tarjeta no deja pasar html del modelo", () => {
  const c = ciudadDePrueba();
  c.edificios[0].nombre = "<img onerror=x> o'brien";
  const html = textoDeTarjeta(fichaDe(c, "dep:atlas"));
  assert.ok(!html.includes("<img"), "se colo una etiqueta del modelo");
  assert.ok(html.includes("&lt;img"), "no se escapo el nombre");
  assert.ok(html.includes("&#39;"), "no se escapo la comilla simple");
  assert.ok(!html.includes("o'brien"), "se colo la comilla simple sin escapar");
});

test("la tarjeta se da vuelta cuando no entra a la derecha ni abajo", () => {
  const caja = {ancho: 400, alto: 300};
  const tarjeta = {ancho: 230, alto: 120};
  const p = posicionDeTarjeta(390, 290, caja, tarjeta);
  // El valor exacto del volteo, no una desigualdad: la tarjeta se pone del
  // OTRO lado del punto, en 390-12-230 y 290-12-120. Sin el volteo, el
  // recorte contra el borde daria (170, 180) -tambien adentro de la caja y
  // tambien a la izquierda del punto-, asi que cualquier afirmacion mas
  // floja que esta la cumplen las dos versiones y el volteo se puede borrar
  // entero sin que nada falle.
  assert.deepEqual(p, {x: 148, y: 158});
  assert.ok(p.x + tarjeta.ancho <= caja.ancho, "se fue por la derecha");
  assert.ok(p.y + tarjeta.alto <= caja.alto, "se fue por abajo");
  assert.ok(p.x >= 0 && p.y >= 0, "se fue por el otro lado");
});

test("el recorte agarra lo que el volteo no alcanza a acomodar", () => {
  // tarjeta casi tan grande como la caja: no entra ni adelante ni atras del
  // punto, el volteo la manda a negativo y lo unico que la salva es el
  // recorte contra el borde
  const caja = {ancho: 200, alto: 150};
  const tarjeta = {ancho: 190, alto: 140};
  const p = posicionDeTarjeta(195, 145, caja, tarjeta);
  assert.deepEqual(p, {x: 0, y: 0});
  assert.ok(p.x + tarjeta.ancho <= caja.ancho &&
            p.y + tarjeta.alto <= caja.alto, "quedo afuera de la caja");
});

test("con lugar de sobra la tarjeta va al lado del dedo", () => {
  const p = posicionDeTarjeta(50, 50, {ancho: 800, alto: 600},
                              {ancho: 230, alto: 120});
  assert.ok(p.x > 50 && p.y >= 50);
});

test("los avisos salen ordenados por lo que hay en juego", () => {
  const r = resumenDeAvisos(ciudadDePrueba());
  assert.equal(r.length, 2);
  assert.equal(r[0].id, "c2");            // 120 monedas antes que 50
  assert.ok(r[0].texto.includes("120"));
});

test("una ciudad sin avisos devuelve una lista vacia, no null", () => {
  const c = ciudadDePrueba();
  c.avisos = [];
  assert.deepEqual(resumenDeAvisos(c), []);
});

test("el costo corriendo dice ruta, modelo, tokens y quien paga", () => {
  const texto = textoDeCosto({ruta: "api", modelo: "sonnet", tokens: 1234,
                              costo_usd: 0.0042, cuenta: "dep:atlas",
                              costo_mm: 270});
  assert.match(texto, /api/);
  assert.match(texto, /sonnet/);
  assert.match(texto, /1\.234/);        // separador de miles en es
  assert.match(texto, /atlas/);
  assert.match(texto, /0,27/);          // 270 milimonedas son 0,27 monedas
});

test("sin turno todavia, la barra de costo esta vacia y no dice cero", () => {
  assert.equal(textoDeCosto({ruta: null, modelo: null, tokens: 0,
                             costo_usd: 0}), "");
});

test("el costo no inventa una cuenta cuando paga Pedro", () => {
  const texto = textoDeCosto({ruta: "local", modelo: "qwen2.5:7b",
                              tokens: 40, costo_usd: 0});
  assert.ok(!texto.includes("paga"), texto);
});

test("la etiqueta de foco nombra al departamento y ofrece soltarlo", () => {
  const texto = textoDeFoco({id: "dep:atlas", nombre: "atlas",
                             saldo: "1.148"});
  assert.match(texto, /atlas/);
  assert.match(texto, /data-accion="quitar"/);
  // el nombre lo escribe Pedro: va escapado, como en la tarjeta
  const feo = textoDeFoco({id: "dep:x", nombre: '<img src=x>', saldo: "0"});
  assert.ok(!feo.includes("<img"), feo);
});

const EMPLEADO = {agente_id: "a1", rol: "scout", modelo: "sonnet",
                  estado: "razonando", texto: "mirando el libro",
                  tokens_in: 1200, tokens_out: 340, costo_mm: 270,
                  runtime_ms: 4500,
                  diff: {ruta: "calipso/mapa/ciudad.py", diff: "- a\n+ b"}};

test("el popup del empleado trae rol, modelo, runtime, tokens y costo", () => {
  const texto = textoDeEmpleado(EMPLEADO);
  assert.match(texto, /scout/);
  assert.match(texto, /sonnet/);
  assert.match(texto, /4,5 s/);              // runtime en segundos, no en ms
  assert.match(texto, /1\.200/);
  assert.match(texto, /0,27/);               // 270 milimonedas
  assert.match(texto, /ciudad\.py/);
});

test("un empleado liberado se ve liberado, no vacio", () => {
  const texto = textoDeEmpleado({...EMPLEADO, estado: "liberado",
                                 texto: "", diff: null});
  assert.match(texto, /liberado/);
  assert.ok(!texto.includes("undefined"), texto);
  assert.ok(!texto.includes("null"), texto);
});

test("el razonamiento va con el diff y con el boton de volver", () => {
  const texto = textoDeRazonamiento(EMPLEADO);
  assert.match(texto, /mirando el libro/);
  assert.match(texto, /- a/);
  assert.match(texto, /data-accion="volver"/);
});

test("el texto del agente se escapa: lo escribe un modelo", () => {
  const texto = textoDeRazonamiento({...EMPLEADO,
                                     texto: '<script>alert(1)</script>'});
  assert.ok(!texto.includes("<script>"), texto);
});
