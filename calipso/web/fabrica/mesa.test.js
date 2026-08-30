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

test("si el dueno no esta en la lista, igual queda una opcion seleccionada", () => {
  // sin esto el navegador elige la primera opcion sola y financiar paga
  // desde ahi sin que nada lo diga
  const ajena = {...P1, departamento: "dep:finanzas"};
  const html = textoDeMesa(datos([ajena]));
  assert.match(html, /<option value="dep:atlas" selected/,
              "ninguna opcion quedo seleccionada de forma explicita");
});

test("si el dueno no esta en la lista, se nota", () => {
  const ajena = {...P1, departamento: "dep:finanzas"};
  const html = textoDeMesa(datos([ajena]));
  assert.match(html, /dep:finanzas.*no esta en la lista|no esta en la lista.*dep:finanzas/is);
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

// --- El filtro por departamento (punto 4): tocar un edificio en el mapa
// acota la mesa a lo suyo. ---

const P2 = {id: "p2", estado: "alta", departamento: "dep:mercado",
            titulo: "campana de lanzamiento", presupuesto_mm: 5000,
            retorno_mm: 8000, criterio: {}, gastado_mm: 0, aportes: {}};

test("sin filtro se ven las propuestas de todos los departamentos, como hoy",
     () => {
  const html = textoDeMesa(datos([P1, P2]));
  assert.match(html, /radar de precios/);
  assert.match(html, /campana de lanzamiento/);
  assert.ok(!html.includes('class="filtro"'),
            "aparecio el encabezado de filtro sin ningun filtro activo");
});

test("con filtro solo aparecen las propuestas de ese departamento", () => {
  const html = textoDeMesa(datos([P1, P2]), "dep:atlas");
  assert.match(html, /radar de precios/);
  assert.ok(!html.includes("campana de lanzamiento"),
            "una propuesta de otro departamento se colo en el filtro");
});

test("con filtro aparece el encabezado con el nombre del departamento y " +
     "un boton para ver todas", () => {
  const html = textoDeMesa(datos([P1, P2]), "dep:atlas");
  assert.match(html, /<div class="filtro">/);
  assert.match(html, /<b>atlas<\/b>/);
  assert.match(html, /data-accion="ver-todas"/);
});

test("un departamento sin propuestas en el filtro no deja a Pedro sin " +
     "salida: el vacio se ve, pero el boton de volver sigue ahi", () => {
  // Si el boton de "ver todas" desaparece junto con las propuestas, tocar
  // un edificio sin nada pendiente le rompe la pantalla: no hay forma de
  // volver a ver el resto salvo recargar.
  const html = textoDeMesa(datos([P1]), "dep:mercado");
  assert.match(html, /data-accion="ver-todas"/,
              "desaparecio la salida del filtro con la mesa vacia");
  assert.match(html, /vacio/);
});

test("el filtro tambien alcanza a un departamento sin plata: solo cambia " +
     "que propuestas se listan, no como se calcula cada una", () => {
  const html = textoDeMesa(datos([{...P1, departamento: "dep:mercado"}]),
                           "dep:mercado");
  assert.match(html, /sin saldo|no alcanza/i);
});

test("el id del departamento filtrado se escapa: no es texto libre, pero " +
     "nada que entra por innerHTML queda exento", () => {
  const malo = '<img src=x onerror="alert(1)">';
  const html = textoDeMesa(datos([P1]), malo);
  assert.ok(!html.includes("<img"), "se colo una etiqueta por el filtro");
  assert.match(html, /&lt;img/);
});

test("sin economia activa, un filtro no cambia el mensaje", () => {
  assert.match(textoDeMesa({activa: false}, "dep:atlas"),
               /economia no esta activa/i);
});

test("el selector y los dos botones van en filas separadas, no sueltos " +
     "juntos en la misma", () => {
  // Bug reportado: en escritorio la fila de acciones se parte sola
  // ("paga [selector] [financiar]" en una linea, "descartar" en la
  // siguiente) porque los botones comparten fila con el selector y con
  // flex-wrap. La correccion es estructural: "pagar" (la etiqueta y el
  // selector) y "botones" (financiar y descartar) son dos contenedores
  // propios, cada uno su fila, para que los botones nunca tengan de que
  // envolver.
  const html = textoDeMesa(datos([P1]));
  assert.match(html, /<div class="pagar">paga <select class="paga"/);
  assert.match(html,
    /<div class="botones"><button data-accion="financiar"[^]*?<button data-accion="descartar"/);
});

// -- la ronda pre-seed -----------------------------------------------------
// Una propuesta de tipo "preseed" se financia contra el TESORO y contra
// nada mas: `bus.financiar` rechaza cualquier billetera de departamento.
// Dibujarle el selector de siempre seria un menu donde todas las opciones
// fallan.
const PS = {id: "ps1", estado: "alta", tipo: "preseed",
            departamento: "dep:atlas", titulo: "arrancamos de cero",
            presupuesto_mm: 120000, retorno_mm: 120000,
            criterio: {}, gastado_mm: 0, aportes: {}};

test("un pre-seed no ofrece selector: paga el tesoro y lo dice", () => {
  const html = textoDeMesa(datos([PS], {tesoro_mm: 500000}));
  assert.ok(!html.includes("select"), "dibujo un selector que no sirve");
  assert.match(html, /data-cuenta="tesoro"/);
  assert.match(html, /ronda pre-seed/);
  assert.match(html, /paga <b>el tesoro<\/b>/);
});

test("una propuesta de trabajo sigue con su selector", () => {
  const html = textoDeMesa(datos([P1], {tesoro_mm: 500000}));
  assert.match(html, /select class="paga"/);
  assert.ok(!html.includes('data-cuenta="tesoro"'),
            "le puso el tesoro a un trabajo");
});

test("avisa cuando el tesoro no llega al monto pedido", () => {
  const html = textoDeMesa(datos([PS], {tesoro_mm: 1000}));
  assert.match(html, /el tesoro no tiene tanto/);
});

test("sin el saldo del tesoro no inventa un aviso", () => {
  // una respuesta vieja del servidor, sin `tesoro_mm`: mejor callarse que
  // decirle a Pedro que no alcanza cuando no se sabe
  const html = textoDeMesa(datos([PS]));
  assert.ok(!html.includes("no tiene tanto"));
});

test("un pre-seed financiado no miente con un 'gastado 0'", () => {
  // la plata quedo en la cuenta del departamento, no en trabajo:<id>: no
  // hay gasto que medir (situacion.py dice lo mismo del lado del jefe)
  const html = textoDeMesa(datos([{...PS, estado: "financiada"}],
                                 {tesoro_mm: 500000}));
  assert.match(html, /capital entregado/);
  assert.ok(!html.includes("gastado"));
});

test("el sello sale del campo tipo, no del titulo que escribe el modelo", () => {
  const disfrazado = {...P1, titulo: "ronda pre-seed de verdad, en serio"};
  const html = textoDeMesa(datos([disfrazado], {tesoro_mm: 500000}));
  assert.ok(!html.includes('class="sello preseed"'),
            "un titulo alcanzo para disfrazarse de pre-seed");
});
