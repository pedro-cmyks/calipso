import test from "node:test";
import assert from "node:assert/strict";

import {crearCamara} from "./camara.js";
import {cargarCiudad, indice, monedas, fichaDe, ordenDePintado,
        enPunto} from "./ciudad.js";

const VISTA = {ancho: 800, alto: 600};

function edi(id, extra = {}) {
  return {id, nombre: id.split(":")[1] || id, zona: "fabrica", orden: 0,
          tamano: 4, estado: "activo", saldo_mm: 1_148_000,
          gasto_ciclo_mm: 22_500, ventas_ventana_mm: 900_000,
          eficiencia_pormil: 1234, actividad: 2, trabajos: [], compuertas: 0,
          x: 0, y: 0, ...extra};
}

function ciudadDePrueba() {
  return {
    semana: "2026-W35", tesoro_mm: 0, cuenta_pedro_mm: 0, direccion_mm: 0,
    tipo_cambio_mm: 5000, linea_empleo_mm: 14450,
    edificios: [edi("dep:atlas", {x: 0, y: 0}),
                edi("dep:mercado", {x: 400, y: 200, trabajos: ["radar"],
                                    compuertas: 2})],
    calles: [{a: "dep:atlas", b: "dep:mercado", peso_mm: 250_000, ancho: 3,
              tipo: "calle"}],
    unidades: [{id: "radar", dueno: "dep:mercado", gastado_mm: 12_000,
                hacia: "dep:atlas"}],
    avisos: [{id: "c1", tipo: "gasto", sobre: "dep:mercado",
              monedas_en_juego_mm: 50_000},
             {id: "c2", tipo: "gasto", sobre: "dep:mercado",
              monedas_en_juego_mm: 10_000},
             {id: "carta", tipo: "renovacion", sobre: null,
              monedas_en_juego_mm: 0}],
  };
}

test("el indice encuentra cada edificio por su id", () => {
  const {porId} = indice(ciudadDePrueba());
  assert.equal(porId.get("dep:atlas").nombre, "atlas");
  assert.equal(porId.get("dep:nadie"), undefined);
});

test("los avisos se cuentan por edificio y los sueltos no rompen", () => {
  const {avisosPorId} = indice(ciudadDePrueba());
  assert.equal(avisosPorId.get("dep:mercado"), 2);
  assert.equal(avisosPorId.get("dep:atlas"), undefined);
});

test("las monedas se leen como monedas, no como milimonedas", () => {
  assert.equal(monedas(1_148_000), "1.148");
  assert.equal(monedas(0), "0");
  assert.equal(monedas(1_500), "1,5");
});

test("la ficha trae lo que la tarjeta muestra", () => {
  const f = fichaDe(ciudadDePrueba(), "dep:mercado");
  assert.equal(f.nombre, "mercado");
  assert.equal(f.saldo, "1.148");
  assert.equal(f.eficiencia, "123,4%");
  assert.equal(f.trabajos, 1);
  assert.equal(f.compuertas, 2);
});

test("sin eficiencia la ficha lo dice en vez de inventar un cero", () => {
  const c = ciudadDePrueba();
  c.edificios[0].eficiencia_pormil = null;
  assert.equal(fichaDe(c, "dep:atlas").eficiencia, "sin dato");
});

test("la ficha de un edificio que no existe es nula", () => {
  assert.equal(fichaDe(ciudadDePrueba(), "dep:fantasma"), null);
});

test("se pinta de atras hacia adelante", () => {
  const orden = ordenDePintado([edi("b", {y: 500}), edi("a", {y: 100})]);
  assert.deepEqual(orden.map(e => e.id), ["a", "b"]);
});

test("el orden de pintado desempata estable", () => {
  const orden = ordenDePintado([edi("z", {y: 0}), edi("a", {y: 0})]);
  assert.deepEqual(orden.map(e => e.id), ["a", "z"]);
});

test("tocar encima de un edificio lo encuentra", () => {
  const c = ciudadDePrueba();
  const cam = crearCamara(0, 0, 1);
  // el edificio de atlas esta en el mundo (0,0), o sea el centro de la vista;
  // el sprite se apoya con su base ahi, asi que unos pixeles mas arriba cae
  // adentro del cuerpo
  assert.equal(enPunto(c, cam, VISTA, 400, 290), "dep:atlas");
});

test("tocar el vacio no devuelve nada", () => {
  const c = ciudadDePrueba();
  const cam = crearCamara(0, 0, 1);
  assert.equal(enPunto(c, cam, VISTA, 10, 10), null);
});

test("cuando dos se superponen gana el de adelante", () => {
  const c = ciudadDePrueba();
  c.edificios = [edi("dep:atras", {x: 0, y: 0}),
                 edi("dep:adelante", {x: 0, y: 6})];
  const cam = crearCamara(0, 3, 1);
  // 290 cae DENTRO de las dos cajas; 300 cae solo en una y entonces el test
  // pasaria igual con el bucle recorrido al reves, que es el error que este
  // test existe para atrapar
  const id = enPunto(c, cam, VISTA, 400, 290);
  assert.equal(id, "dep:adelante");
});

test("cargarCiudad pide el endpoint y devuelve el modelo", async () => {
  let pedido = null;
  const falso = async (url) => {
    pedido = url;
    return {ok: true, status: 200,
            json: async () => ({activa: true, ciudad: ciudadDePrueba()})};
  };
  const r = await cargarCiudad(falso);
  assert.equal(pedido, "/api/mapa/ciudad");
  assert.equal(r.activa, true);
  assert.equal(r.ciudad.edificios.length, 2);
});

test("cargarCiudad pasa la respuesta de economia inactiva tal cual", async () => {
  const falso = async () => ({ok: true, status: 200,
                              json: async () => ({activa: false})});
  const r = await cargarCiudad(falso);
  assert.equal(r.activa, false);
});

test("cargarCiudad avisa cuando el servidor contesta mal", async () => {
  const falso = async () => ({ok: false, status: 401, json: async () => ({})});
  await assert.rejects(() => cargarCiudad(falso), /401/);
});
