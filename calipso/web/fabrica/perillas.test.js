import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDePerillas, aMilimonedas, cuerpoDeSuscripciones,
        SUSCRIPCIONES} from "./perillas.js";

test("las dos suscripciones estan siempre a la vista, este sembrada o no",
     () => {
  const apagada = textoDePerillas({activa: false});
  const sembrada = textoDePerillas({activa: true, tablero: {
    tesoro_mm: 0, direccion_mm: 0, cuenta_pedro_mm: 0, tipo_cambio_mm: 5000,
    linea_empleo_mm: 0, departamentos: {}, personal: {neto_mm: 0}}});
  for (const html of [apagada, sembrada]) {
    assert.match(html, /Claude Max/);
    assert.match(html, /ChatGPT Plus/);
    assert.match(html, /200/);
    assert.match(html, /20\b/);
    assert.match(html, /220/);   // el total: lo que ya sale del bolsillo
  }
});

test("sin economia activa, ofrece sembrar y no miente diciendo que hay tesoro",
     () => {
  const html = textoDePerillas({activa: false});
  assert.match(html, /todavia no existe/i);
  assert.match(html, /data-perillas="sembrar"/);
  assert.ok(!html.includes("tesoro de la fabrica"),
            "mostro un tesoro con la economia apagada");
});

test("null o undefined se tratan como apagada, no revientan", () => {
  assert.match(textoDePerillas(null), /todavia no existe/i);
  assert.match(textoDePerillas(undefined), /todavia no existe/i);
});

test("sembrada, muestra el tesoro y el banco personal en monedas, no en milimonedas",
     () => {
  const html = textoDePerillas({activa: true, tablero: {
    tesoro_mm: 512_340, direccion_mm: 1000, cuenta_pedro_mm: 2000,
    tipo_cambio_mm: 5000, linea_empleo_mm: 15000,
    departamentos: {}, personal: {neto_mm: -3_500}}});
  assert.match(html, /tesoro de la fabrica/);
  assert.match(html, /512,34/);      // 512340 mm = 512,34 monedas
  assert.match(html, /tu banco personal/);
  assert.match(html, /-3,5\b/);      // el banco puede estar en rojo
});

test("cada departamento aparece con su saldo en monedas", () => {
  const html = textoDePerillas({activa: true, tablero: {
    tesoro_mm: 0, direccion_mm: 0, cuenta_pedro_mm: 0, tipo_cambio_mm: 5000,
    linea_empleo_mm: 0, personal: {neto_mm: 0},
    departamentos: {"dep:atlas": {saldo_mm: 40_000, congelado: false},
                    "dep:mercado": {saldo_mm: 0, congelado: true}}}});
  assert.match(html, /atlas/);
  assert.match(html, /40\b/);
  assert.match(html, /mercado/);
  assert.match(html, /congelado/);
});

test("sin departamentos lo dice, no queda en blanco", () => {
  const html = textoDePerillas({activa: true, tablero: {
    tesoro_mm: 0, direccion_mm: 0, cuenta_pedro_mm: 0, tipo_cambio_mm: 5000,
    linea_empleo_mm: 0, departamentos: {}, personal: {neto_mm: 0}}});
  assert.match(html, /sin departamentos/i);
});

test("el id de un departamento se escapa: no es texto libre, pero nada que " +
     "entra por innerHTML queda exento", () => {
  const html = textoDePerillas({activa: true, tablero: {
    tesoro_mm: 0, direccion_mm: 0, cuenta_pedro_mm: 0, tipo_cambio_mm: 5000,
    linea_empleo_mm: 0, personal: {neto_mm: 0},
    departamentos: {'dep:<img src=x onerror="alert(1)">':
                    {saldo_mm: 100, congelado: false}}}});
  assert.ok(!html.includes("<img"), "se colo una etiqueta por el id del dep");
  assert.match(html, /&lt;img/);
});

test("sembrada, ofrece los dos formularios de mover plata y no el de sembrar",
     () => {
  const html = textoDePerillas({activa: true, tablero: {
    tesoro_mm: 0, direccion_mm: 0, cuenta_pedro_mm: 0, tipo_cambio_mm: 5000,
    linea_empleo_mm: 0, departamentos: {}, personal: {neto_mm: 0}}});
  assert.match(html, /data-perillas="acunar"/);
  assert.match(html, /data-perillas="movimiento"/);
  assert.ok(!html.includes('data-perillas="sembrar"'),
            "ofrecio sembrar con la economia ya sembrada");
});

test("un mensaje de 'salio bien' aparece cuando se lo pasan, y no cuando no",
     () => {
  const sinMensaje = textoDePerillas({activa: false});
  assert.ok(!sinMensaje.includes('class="listo"'));
  const conMensaje = textoDePerillas({activa: false}, "listo: se sembro");
  assert.match(conMensaje, /class="listo"/);
  assert.match(conMensaje, /listo: se sembro/);
});

test("el mensaje tambien se escapa", () => {
  const html = textoDePerillas({activa: false}, '<img src=x onerror="1">');
  assert.ok(!html.includes("<img"));
  assert.match(html, /&lt;img/);
});

// --- aMilimonedas: lo que Pedro escribe en el formulario, a mm enteros ---

test("aMilimonedas convierte monedas con decimales a milimonedas enteros", () => {
  assert.equal(aMilimonedas("100"), 100_000);
  assert.equal(aMilimonedas("12.5"), 12_500);
  assert.equal(aMilimonedas("12,5"), 12_500);   // coma decimal, como escribe Pedro
  assert.equal(aMilimonedas("0.001"), 1);
});

test("aMilimonedas rechaza lo que no es un monto positivo", () => {
  assert.equal(aMilimonedas("0"), null);
  assert.equal(aMilimonedas("-5"), null);
  assert.equal(aMilimonedas("abc"), null);
  assert.equal(aMilimonedas(""), null);
  assert.equal(aMilimonedas(undefined), null);
  assert.equal(aMilimonedas("5e3"), null);      // notacion cientifica: no es lo que tipea Pedro
});

test("cuerpoDeSuscripciones arma el diccionario nombre -> costo_mensual_mm " +
     "que pide EcoSembrarBody.suscripciones (un dict, no una lista), con " +
     "los nombres canonicos del pagador y sin la etiqueta de pantalla",
     () => {
  const cuerpo = cuerpoDeSuscripciones();
  assert.deepEqual(Object.keys(cuerpo).sort(), ["chatgpt_plus", "claude_max"]);
  assert.deepEqual(cuerpo.claude_max, {costo_mensual_mm: 200_000});
  assert.deepEqual(cuerpo.chatgpt_plus, {costo_mensual_mm: 20_000});
});

test("las dos suscripciones sumadas dan lo que Pedro dijo que paga: 220 al mes",
     () => {
  const total = SUSCRIPCIONES.reduce((s, x) => s + x.costo_mensual_mm, 0);
  assert.equal(total, 220_000);   // 220 monedas = 220 USD
});
