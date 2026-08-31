import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDePerillas, textoDeAjustes, aMilimonedas, aMilimonedasConCero,
        aEntero, cuerpoDeSuscripciones, monedasEditable,
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

// -- los ajustes: los numeros que hasta hoy solo se cambiaban en el json ---
const CONFIG = {
  activa: true, semana: "2026-W35", ciclo: 0,
  medido_generado: "2026-08-27T09:00:00+00:00",
  departamentos: [
    {nombre: "atlas", zona: "fabrica", presupuesto_semanal_mm: 25000,
     techo_api_ciclo_mm: 0, explorar_explotar_pct: 50, agresividad_pct: 30,
     techo_preseed_mm: 50000, techo_preseed_ciclo_mm: 150000,
     preseed_ciclo_mm: 50000},
    {nombre: "finanzas", zona: "personal", presupuesto_semanal_mm: 0,
     techo_api_ciclo_mm: 0, explorar_explotar_pct: 50, agresividad_pct: 30,
     techo_preseed_mm: 0, techo_preseed_ciclo_mm: 0, preseed_ciclo_mm: 0},
  ],
  suscripciones: [
    {nombre: "claude_max", costo_mensual_mm: 200000, capacidad_ciclo: 1000,
     reserva_personal: 200, costo_api_mm_por_unidad: 3000,
     capacidad_fabrica: 800, precio_base_mm: 200, consumido_ciclo: 12,
     medido: {proveedor: "claude", capacidad_ciclo_propuesta: 1360,
              nota: "extrapolacion lineal: NO mide cuota real", medicion: {}}},
  ],
};

test("sin config, los ajustes no dibujan nada", () => {
  assert.equal(textoDeAjustes(null), "");
  assert.equal(textoDeAjustes({activa: false}), "");
});

test("el techo de pre-seed tiene un formulario por departamento de fabrica", () => {
  const html = textoDeAjustes(CONFIG);
  assert.match(html, /data-perillas="techo-preseed"/);
  assert.match(html, /data-departamento="atlas"/);
  // la zona personal no propone ni pide: no tiene por que tener la perilla
  assert.ok(!html.includes('data-departamento="finanzas"'));
});

test("los ajustes dicen que el techo autoriza a pedir, no entrega plata", () => {
  const html = textoDeAjustes(CONFIG);
  assert.match(html, /autorizacion a PEDIR/);
  assert.match(html, /En cero no pide/);
});

test("el numero medido llega con su boton para aplicarlo", () => {
  const html = textoDeAjustes(CONFIG);
  assert.match(html, /data-ajuste="aplicar-medido"/);
  assert.match(html, /data-suscripcion="claude_max"/);
  assert.match(html, /data-capacidad="1360"/);
});

test("la nota del probe va siempre: separa una medicion de una extrapolacion", () => {
  const html = textoDeAjustes(CONFIG);
  assert.match(html, /NO mide cuota real/);
});

test("sin numero propuesto no hay boton que aplique nada", () => {
  const sinNumero = {...CONFIG, suscripciones: [
    {...CONFIG.suscripciones[0],
     medido: {proveedor: "claude", capacidad_ciclo_propuesta: null,
              nota: "sin suficiente historia todavia"}}]};
  const html = textoDeAjustes(sinNumero);
  assert.ok(!html.includes('data-ajuste="aplicar-medido"'),
            "ofrecio aplicar un numero que nadie midio");
  assert.match(html, /todavia no propone un numero/);
  assert.match(html, /sin suficiente historia/);
});

test("una suscripcion sin proveedor medido lo dice y no muestra un cero", () => {
  const sinProveedor = {...CONFIG, suscripciones: [
    {...CONFIG.suscripciones[0], medido: null}]};
  const html = textoDeAjustes(sinProveedor);
  assert.match(html, /Ningun proveedor medido/);
  assert.ok(!html.includes('data-ajuste="aplicar-medido"'));
});

test("avisa que repreciar se estampa en asientos que no se reescriben", () => {
  const html = textoDeAjustes(CONFIG);
  assert.match(html, /append-only/);
  assert.match(html, /techo de plata/);
});

test("muestra lo ya comprado del ciclo: es el piso del cambio", () => {
  // bajar la capacidad por debajo de esto deja la cuota agotada hasta que
  // el ciclo cierre (el guardia del endpoint), asi que el numero tiene que
  // estar a la vista ANTES de que Pedro escriba uno mas chico
  assert.match(textoDeAjustes(CONFIG), /12 unidades/);
});

test("los ajustes cuelgan de las perillas cuando la economia esta activa", () => {
  const html = textoDePerillas({activa: true, tablero: {
    tesoro_mm: 0, direccion_mm: 0, cuenta_pedro_mm: 0, tipo_cambio_mm: 5000,
    linea_empleo_mm: 0, departamentos: {}, personal: {neto_mm: 0}}},
    null, CONFIG);
  assert.match(html, /data-perillas="techo-preseed"/);
});

test("cero es un techo valido: es como nacen todos los departamentos", () => {
  // `aMilimonedas` devuelve null para 0 (un monto en cero no es un monto);
  // el techo si admite el cero, que significa "este no pide"
  assert.equal(aMilimonedas("0"), null);
  assert.equal(aMilimonedasConCero("0"), 0);
  assert.equal(aMilimonedasConCero("1,5"), 1500);
  assert.equal(aMilimonedasConCero("nada"), null);
  assert.equal(aMilimonedasConCero(""), null);
});

test("las unidades de capacidad no son monedas: no se dividen por mil", () => {
  assert.equal(aEntero("1360"), 1360);
  assert.equal(aEntero("1.5"), null);
  assert.equal(aEntero(""), null);
  assert.equal(aEntero("-3"), null);
});

test("todo lo de los ajustes pasa por escapar()", () => {
  const venenoso = {...CONFIG,
    departamentos: [{...CONFIG.departamentos[0],
                     nombre: '"><img src=x onerror="alert(1)">'}],
    suscripciones: [{...CONFIG.suscripciones[0],
                     nombre: '"><iframe src=x>',
                     medido: {proveedor: '<svg onload=1>',
                              capacidad_ciclo_propuesta: 5,
                              nota: '<object data=x>'}}]};
  const html = textoDeAjustes(venenoso);
  for (const etiqueta of ["<img", "<iframe", "<svg", "<object"]) {
    assert.ok(!html.includes(etiqueta), `se colo ${etiqueta}`);
  }
});

// -- el segundo techo del pre-seed: el acumulado por ciclo -----------------

test("el techo del ciclo tiene su propio campo: sin cara Pedro no lo mueve", () => {
  const html = textoDeAjustes(CONFIG);
  assert.match(html, /name="ciclo"/);
  assert.match(html, /techo del ciclo/);
  // y con el valor que ya tiene puesto, no vacio: la perilla se lee antes
  // de escribirse
  assert.match(html, /value="150"/);
});

test("los dos techos van en el mismo formulario: son una sola decision", () => {
  // mandarlos por separado deja una ventana en la que el techo por pedido
  // ya subio y el del ciclo todavia no -- justo el estado en el que el
  // jefe puede pedir mas de lo que se le va a poder pagar
  const html = textoDeAjustes(CONFIG);
  const forms = html.match(/<form class="ajuste" data-perillas="techo-preseed"[\s\S]*?<\/form>/g);
  assert.equal(forms.length, 1);
  assert.match(forms[0], /name="monto"/);
  assert.match(forms[0], /name="ciclo"/);
});

test("muestra cuanto capital ya entro en el ciclo, al lado de su techo", () => {
  // sin el acumulado a la vista, el techo del ciclo es un numero que Pedro
  // pone a ciegas y un rechazo que le llega recien al tocar "financiar"
  assert.match(textoDeAjustes(CONFIG), /ya entro este ciclo: 50 de 150/);
});

test("dice que el techo del ciclo ata tambien a la mesa", () => {
  // "lo que NO puede pasar es que se cruce en silencio": si financiar
  // rechaza, la pantalla tiene que haberlo dicho antes
  const html = textoDeAjustes(CONFIG);
  assert.match(html, /financiar te lo rechaza/);
  assert.match(html, /4 semanas del ciclo/);
});

test("la zona personal no tiene ninguno de los dos techos", () => {
  const html = textoDeAjustes(CONFIG);
  assert.ok(!html.includes('data-departamento="finanzas"'));
});


// -- el ida y vuelta del formulario de los dos techos ----------------------

test("el techo que se pinta es el mismo que se vuelve a leer: sin separador " +
     "de miles", () => {
  // `monedas()` agrupa con la locale "es" (20.000.000 mm -> "20.000") y
  // `aMilimonedasConCero` lee el punto como DECIMAL, asi que el ida y
  // vuelta dividia por mil todo techo de 10.000 monedas para arriba. Y
  // como los DOS techos viajan en el mismo POST, guardar el techo por
  // pedido reescribia el del ciclo aunque Pedro no lo hubiera tocado.
  for (const mm of [0, 150_000, 9_999_000, 10_000_000, 20_000_000,
                    60_000_000, 1_234_567_000, 1_500]) {
    assert.equal(aMilimonedasConCero(monedasEditable(mm)), mm,
                 `el ida y vuelta perdio ${mm}`);
  }
  assert.equal(monedasEditable(1_500), "1,5");
  assert.equal(monedasEditable(20_000_000), "20000");
});

test("los dos inputs del techo se pintan con el valor exacto, no formateado",
     () => {
  // el fixture del repo usa 10.000 monedas de techo del ciclo: justo el
  // primer valor que el formato agrupado rompia
  const config = {...CONFIG, departamentos: [
    {...CONFIG.departamentos[0], techo_preseed_mm: 1_234_567_000,
     techo_preseed_ciclo_mm: 20_000_000},
    CONFIG.departamentos[1]]};
  const html = textoDeAjustes(config);
  const form = html.match(
    /<form class="ajuste" data-perillas="techo-preseed"[\s\S]*?<\/form>/)[0];
  const monto = form.match(/name="monto"[^>]*value="([^"]*)"/)[1];
  const ciclo = form.match(/name="ciclo"[^>]*value="([^"]*)"/)[1];
  assert.equal(aMilimonedasConCero(monto), 1_234_567_000);
  assert.equal(aMilimonedasConCero(ciclo), 20_000_000);
});

test("lo pedido y sin financiar se ve, y dice que descartarlo suelta el cupo",
     () => {
  // el acumulado del ciclo puede estar en CERO con el jefe frenado: lo que
  // lo frena es el pedido en pie, y hasta hoy ese numero no se veia en
  // ninguna pantalla -- ni nada sugeria que descartarlo es lo que lo suelta
  const config = {...CONFIG, departamentos: [
    {...CONFIG.departamentos[0], preseed_ciclo_mm: 0,
     techo_preseed_ciclo_mm: 60_000_000, preseed_pendiente_mm: 60_000_000},
    CONFIG.departamentos[1]]};
  const html = textoDeAjustes(config);
  assert.match(html, /ya entro este ciclo: 0 de 60\.000/);
  assert.match(html, /60\.000 pedidas y sin financiar en la mesa/);
  assert.match(html, /descartes/);
});

test("la nota del techo del ciclo cuenta lo mismo que el numero de abajo",
     () => {
  // tres textos sobre el mismo techo: la nota, el "ya entro este ciclo" y
  // el freno de `bus.financiar`. Los tres cuentan SOLO lo financiado; la
  // nota decia "mas lo que sigue en la mesa", que es la regla del JEFE
  const html = textoDeAjustes(CONFIG);
  assert.ok(!/contando lo que ya financiaste mas lo que sigue en la mesa/
            .test(html), "la nota sigue prometiendo el numero del jefe");
  assert.match(html, /lo que ya financiaste, que es el numero de abajo/);
  assert.match(html, /El jefe se frena antes que vos/);
});

test("sin nada pedido en la mesa, el renglon de la reserva no se dibuja", () => {
  assert.ok(!textoDeAjustes(CONFIG).includes("pedidas y sin financiar"));
});
