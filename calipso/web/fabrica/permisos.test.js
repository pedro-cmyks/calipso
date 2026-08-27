import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDePermisos, contadorPendientes,
        motivoEnMonedas} from "./permisos.js";

const SOL_ACUNAR = {
  id: "sol_8b49901d70cc", ts: "2026-08-25T10:00:00", estado: "pendiente",
  accion: {familia: "plata", operacion: "acunar",
           forma: {subtipo: "capital", destino: "tesoro", monto_mm: 500_000},
           detalle: {evidencia: {tipo: "firma_pedro"}},
           titulo: "acunar 500000 mm (capital) a tesoro"},
  contexto: {origen: "pedro", chat: null, departamento: null, corrida: null},
  nivel: "pregunta", motivo: "500000 mm supera el techo de 100000 mm",
  siempre_pregunta: true, texto: "acunar 500000 mm (capital) a tesoro " +
    "(500000 mm supera el techo de 100000 mm)",
  estaciono_corrida: false, intentos: [], respondida: null, resultado: null,
};

function datos(extra = {}) {
  return {activo: true, pendientes: [], estacionadas: [], aprobadas: [],
          concedidos: [], techos: {plata_mm: 100_000}, registro: [],
          error: null, ...extra};
}

// --- motivoEnMonedas: el motivo del motor esta en milimonedas -----------

test("motivoEnMonedas convierte cada 'N mm' del texto a monedas", () => {
  assert.equal(
    motivoEnMonedas("500000 mm supera el techo de 100000 mm"),
    "500 monedas supera el techo de 100 monedas");
});

test("motivoEnMonedas no rompe un motivo sin milimonedas", () => {
  assert.equal(motivoEnMonedas("no se pudo leer el allowlist"),
              "no se pudo leer el allowlist");
});

test("motivoEnMonedas no revienta con null o undefined", () => {
  assert.equal(motivoEnMonedas(null), "");
  assert.equal(motivoEnMonedas(undefined), "");
});

// --- el motor no disponible / sin nada pendiente -------------------------

test("el motor no disponible lo dice y no ofrece nada", () => {
  const html = textoDePermisos({activo: false});
  assert.match(html, /no esta disponible/i);
  assert.ok(!html.includes("data-accion"));
});

test("null o undefined se tratan como no disponible, no revientan", () => {
  assert.match(textoDePermisos(null), /no esta disponible/i);
  assert.match(textoDePermisos(undefined), /no esta disponible/i);
});

test("activo pero sin nada pendiente lo dice, no queda en blanco", () => {
  const html = textoDePermisos(datos());
  assert.match(html, /nada esperando tu respuesta/i);
});

// --- una solicitud pendiente: la cuenta, el monto, el motivo -------------

test("una solicitud de acunar muestra el monto en monedas, no en milimonedas",
     () => {
  const html = textoDePermisos(datos({pendientes: [SOL_ACUNAR]}));
  assert.match(html, /acunar 500 monedas/);
  // la CABEZA -la frase armada, lo primero que se lee- no lleva mm: el
  // "500000 mm" crudo solo puede aparecer mas abajo, adentro de <details>,
  // que es a proposito el respaldo sin convertir (ver la forma exacta).
  const cabeza = html.split("<details")[0];
  assert.ok(!cabeza.includes("500000 mm"),
            "aparecio el monto crudo en milimonedas en el texto armado");
});

test("una solicitud de acunar muestra la cuenta destino", () => {
  const html = textoDePermisos(datos({pendientes: [SOL_ACUNAR]}));
  assert.match(html, /tesoro/);
  assert.match(html, /capital/);
});

test("el motivo tambien se muestra en monedas", () => {
  const html = textoDePermisos(datos({pendientes: [SOL_ACUNAR]}));
  assert.match(html, /500 monedas supera el techo de 100 monedas/);
});

test("quien pide se muestra", () => {
  const html = textoDePermisos(datos({pendientes: [SOL_ACUNAR]}));
  assert.match(html, /pedro/);
});

test("la forma exacta queda disponible cruda, no solo resumida", () => {
  const html = textoDePermisos(datos({pendientes: [SOL_ACUNAR]}));
  assert.match(html, /ver la forma exacta/);
  // escapado (es json dentro de un <pre>), pero el dato esta: la comilla
  // se ve como &quot; y el numero, entero.
  assert.match(html, /&quot;monto_mm&quot;: 500000/);
});

// --- una solicitud de movimiento (banco personal) ------------------------

test("una solicitud de movimiento arma su propia frase", () => {
  const sol = {...SOL_ACUNAR, id: "sol_mov",
    accion: {familia: "plata", operacion: "movimiento",
             forma: {tipo: "gasto", monto_mm: 300_000, categoria: "alquiler"},
             detalle: {nota: "agosto"}, titulo: "x"}};
  const html = textoDePermisos(datos({pendientes: [sol]}));
  assert.match(html, /registrar un gasto de 300 monedas en alquiler/);
});

// --- una familia sin vista propia no se disfraza --------------------------

test("una familia sin vista propia muestra el titulo del motor tal cual",
     () => {
  const sol = {...SOL_ACUNAR, id: "sol_cmd",
    accion: {familia: "comando", operacion: "correr",
             forma: {argv: ["git", "push"]}, detalle: {cwd: "/x"},
             titulo: "correr git push en /x"}};
  const html = textoDePermisos(datos({pendientes: [sol]}));
  assert.match(html, /correr git push en \/x/);
});

// --- las tres salidas de 5.4, y cuando una no esta disponible -------------

test("una solicitud siempre trae los botones si y no", () => {
  const html = textoDePermisos(datos({pendientes: [SOL_ACUNAR]}));
  assert.match(html, /data-accion="responder" data-id="sol_8b49901d70cc" data-respuesta="si"/);
  assert.match(html, /data-respuesta="no"/);
});

test("si siempre_pregunta es verdadero, no hay boton de permiso permanente " +
     "-se dice por que, no se dibuja un boton que miente", () => {
  const html = textoDePermisos(datos({pendientes: [SOL_ACUNAR]}));
  assert.ok(!html.includes('data-respuesta="si_siempre"'),
            "aparecio un boton de permiso permanente sobre algo que pregunta siempre");
  assert.match(html, /pregunta siempre/);
  assert.match(html, /no admite permiso permanente/);
});

test("si siempre_pregunta es falso, el boton de permiso permanente aparece",
     () => {
  const sol = {...SOL_ACUNAR, siempre_pregunta: false};
  const html = textoDePermisos(datos({pendientes: [sol]}));
  assert.match(html, /data-respuesta="si_siempre"/);
  assert.match(html, /no preguntes mas/);
});

// --- estacionadas: la misma respuesta, otra etiqueta ----------------------

test("una estacionada aparece con su propia etiqueta y los mismos botones",
     () => {
  const sol = {...SOL_ACUNAR, id: "sol_est", estado: "estacionada"};
  const html = textoDePermisos(datos({estacionadas: [sol]}));
  assert.match(html, /una rutina quedo parada/);
  assert.match(html, /data-id="sol_est" data-respuesta="si"/);
});

test("pendientes y estacionadas aparecen juntas, cada una con su etiqueta",
     () => {
  const est = {...SOL_ACUNAR, id: "sol_est", estado: "estacionada"};
  const html = textoDePermisos(datos({pendientes: [SOL_ACUNAR], estacionadas: [est]}));
  assert.match(html, /esperando tu respuesta/);
  assert.match(html, /una rutina quedo parada/);
});

// --- los intentos de rodeo, si los hay -------------------------------------

test("los intentos de rodeo se muestran cuando hay alguno", () => {
  const sol = {...SOL_ACUNAR, intentos: [{ts: "x", que: "rodeo de corrida"}]};
  const html = textoDePermisos(datos({pendientes: [sol]}));
  assert.match(html, /se intento sortear esta espera 1 vez/);
});

test("sin intentos no aparece la linea de rodeo", () => {
  const html = textoDePermisos(datos({pendientes: [SOL_ACUNAR]}));
  assert.ok(!html.includes("sortear"));
});

// --- aprobadas: informativas, sin botones ----------------------------------

test("una aprobada que espera a la rutina se ve, sin botones de respuesta",
     () => {
  const sol = {...SOL_ACUNAR, id: "sol_apr", estado: "aprobada"};
  const html = textoDePermisos(datos({aprobadas: [sol]}));
  assert.match(html, /esperando que la rutina la tome/);
  assert.ok(!html.includes('data-id="sol_apr" data-respuesta'));
});

// --- permisos permanentes: verlos y poder revocarlos -----------------------

test("sin permisos concedidos, lo dice: una firma en blanco que no se ve " +
     "no sirve, pero tampoco hay que inventar una lista vacia muda", () => {
  const html = textoDePermisos(datos());
  assert.match(html, /ningun permiso permanente concedido/i);
});

test("un permiso concedido se ve con su forma y su boton de revocar", () => {
  const permiso = {id: "per_123", familia: "archivo", operacion: "escribir",
                   forma: {raiz: "~/Downloads"}, chat: null, origen: "pedro",
                   ts: "2026-08-20T09:00:00", texto: "x"};
  const html = textoDePermisos(datos({concedidos: [permiso]}));
  assert.match(html, /archivo\/escribir/);
  assert.match(html, /Downloads/);
  assert.match(html, /data-accion="revocar" data-id="per_123"/);
});

// --- el techo: en monedas, y editable --------------------------------------

test("el techo se muestra en monedas, no en milimonedas", () => {
  const html = textoDePermisos(datos({techos: {plata_mm: 100_000}}));
  assert.match(html, /100 monedas/);
  assert.ok(!html.includes("100000 mm"));
});

test("el formulario del techo precarga el valor actual en monedas", () => {
  const html = textoDePermisos(datos({techos: {plata_mm: 250_000}}));
  assert.match(html, /<form data-accion="techo">/);
  assert.match(html, /value="250"/);
});

test("sin techos declarados, el default es 100 (spec: 100000 mm)", () => {
  const html = textoDePermisos(datos({techos: {}}));
  assert.match(html, /100 monedas/);
});

// --- el error de vista(): no mentir sobre "nada pendiente" -----------------

test("un error al leer las solicitudes se muestra, no se esconde", () => {
  const html = textoDePermisos(datos({error: "no se pueden leer las solicitudes"}));
  assert.match(html, /no se pudieron leer las solicitudes/);
  assert.match(html, /no se pueden leer las solicitudes/);
});

// --- el mensaje pasajero ("salio bien") -------------------------------------

test("un mensaje pasajero aparece cuando se lo pasan, y no cuando no", () => {
  const sinMensaje = textoDePermisos(datos());
  assert.ok(!sinMensaje.includes('class="listo"'));
  const conMensaje = textoDePermisos(datos(), "listo: se conto el techo");
  assert.match(conMensaje, /class="listo"/);
  assert.match(conMensaje, /listo: se conto el techo/);
});

// --- todo lo que entra por innerHTML se escapa ------------------------------

test("el titulo de una familia sin vista propia se escapa: lo puede " +
     "escribir un departamento", () => {
  const malo = {...SOL_ACUNAR, id: "sol_mal",
    accion: {familia: "app", operacion: "cerrar",
             forma: {}, detalle: {}, titulo: '<img src=x onerror="alert(1)">'}};
  const html = textoDePermisos(datos({pendientes: [malo]}));
  assert.ok(!html.includes("<img"), "se colo una etiqueta por el titulo");
  assert.match(html, /&lt;img/);
});

test("el motivo se escapa", () => {
  const malo = {...SOL_ACUNAR, motivo: '<script>alert(1)</script>'};
  const html = textoDePermisos(datos({pendientes: [malo]}));
  assert.ok(!html.includes("<script"), "se colo una etiqueta por el motivo");
  assert.match(html, /&lt;script/);
});

test("el chat y el departamento del contexto se escapan", () => {
  const malo = {...SOL_ACUNAR,
    contexto: {origen: "rutina", chat: '"><img src=x onerror=1>',
               departamento: 'dep:<script>x</script>', corrida: null}};
  const html = textoDePermisos(datos({pendientes: [malo]}));
  assert.ok(!html.includes("<img"), "se colo una etiqueta por el chat");
  assert.ok(!html.includes("<script"), "se colo una etiqueta por el departamento");
});

test("la forma cruda tambien se escapa: es json escrito por el motor a " +
     "partir de datos que puede haber mandado un departamento", () => {
  const malo = {...SOL_ACUNAR,
    accion: {familia: "archivo", operacion: "escribir",
             forma: {ruta: '<img src=x onerror="alert(1)">'}, detalle: {},
             titulo: "x"}};
  const html = textoDePermisos(datos({pendientes: [malo]}));
  assert.ok(!html.includes("<img"), "se colo una etiqueta por la ruta cruda");
});

test("la forma de un permiso concedido tambien se escapa", () => {
  const permiso = {id: "per_x", familia: "archivo", operacion: "escribir",
                   forma: {raiz: '<img src=x onerror="alert(1)">'},
                   chat: null, origen: "pedro", ts: "x", texto: "x"};
  const html = textoDePermisos(datos({concedidos: [permiso]}));
  assert.ok(!html.includes("<img"), "se colo una etiqueta por la forma del permiso");
});

// --- contadorPendientes: para un aviso que Pedro vea sin buscarlo ----------

test("contadorPendientes suma pendientes y estacionadas", () => {
  assert.equal(contadorPendientes(datos({pendientes: [SOL_ACUNAR],
                                         estacionadas: [SOL_ACUNAR, SOL_ACUNAR]})), 3);
});

test("contadorPendientes es 0 sin nada pendiente", () => {
  assert.equal(contadorPendientes(datos()), 0);
});

test("contadorPendientes es 0 si el motor no esta disponible, aunque " +
     "vengan listas colgando de otro lado", () => {
  assert.equal(contadorPendientes({activo: false, pendientes: [SOL_ACUNAR]}), 0);
});

test("contadorPendientes no revienta con null o undefined", () => {
  assert.equal(contadorPendientes(null), 0);
  assert.equal(contadorPendientes(undefined), 0);
});

test("las aprobadas no cuentan como pendientes: ya tienen el si de Pedro",
     () => {
  assert.equal(contadorPendientes(datos({aprobadas: [SOL_ACUNAR]})), 0);
});
