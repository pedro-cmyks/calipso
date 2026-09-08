import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDeAparatos, contadorDeAparatos, alcanceDe,
        fechaLegible} from "./aparatos.js";

const GOLPE = {
  hash_id: null, id_pedido: "ped_ABC-123_xyz", aparato: "Musnap Neo C",
  tipo: "lector", creada: "2026-09-08T10:00:00+00:00",
  ultima_vez: "2026-09-08T10:00:00+00:00", estado: "golpeando",
  efectivo: "golpeando",
};

const VIVA = {
  hash_id: "a1b2c3d4", id_pedido: "ped_vieja", aparato: "Celular de Pedro",
  tipo: "navegador", creada: "2026-08-01T09:00:00+00:00",
  ultima_vez: "2026-09-07T21:15:00+00:00", estado: "viva", efectivo: "viva",
};

function datos(aparatos = []) {
  return {aparatos};
}

// --- alcanceDe: lo que cada tipo abre, en castellano --------------------

test("cada tipo tiene su alcance escrito, sin inventar ninguno", () => {
  assert.equal(alcanceDe("lector"),
               "Solo sus endpoints de lectura (/api/lectura)");
  assert.equal(alcanceDe("tablero"),
               "Ve toda la fabrica y firma la mesa y los permisos. Jamas " +
               "archivos, comandos ni configuracion");
  assert.equal(alcanceDe("navegador"), "Todo: la PWA completa, como la Ally");
});

test("un tipo que no esta en la tabla no se disfraza de inofensivo", () => {
  // el server valida el tipo, asi que esto no deberia pasar nunca; si pasa,
  // la UI no puede decir "no abre nada" sobre algo que no sabe que abre
  assert.match(alcanceDe("administrador"), /no se conoce/i);
  assert.match(alcanceDe(undefined), /no se conoce/i);
});

// --- fechaLegible: la hora del almacen es ISO en UTC --------------------

test("una fecha ISO se muestra como dia y hora locales", () => {
  const cuando = new Date(2026, 8, 8, 14, 30);   // local, sin depender del TZ
  assert.equal(fechaLegible(cuando.toISOString()), "2026-09-08 14:30");
});

test("una fecha que no se puede leer se muestra tal cual, no en blanco", () => {
  assert.equal(fechaLegible("basura"), "basura");
  assert.equal(fechaLegible(null), "");
  assert.equal(fechaLegible(undefined), "");
});

// --- contadorDeAparatos: solo lo que espera respuesta de Pedro ----------

test("el contador cuenta los golpes vigentes y nada mas", () => {
  const html = contadorDeAparatos(datos([
    GOLPE, {...GOLPE, id_pedido: "ped_2"}, VIVA,
    {...GOLPE, id_pedido: "ped_3", efectivo: "caduca"},
    {...VIVA, hash_id: "z9", efectivo: "revocada"},
  ]));
  assert.equal(html, 2);
});

test("el contador no revienta sin datos", () => {
  assert.equal(contadorDeAparatos(datos()), 0);
  assert.equal(contadorDeAparatos(null), 0);
  assert.equal(contadorDeAparatos(undefined), 0);
});

// --- la tarjeta del golpe ----------------------------------------------

test("el golpe muestra el nombre del aparato y el tipo que sugiere", () => {
  const html = textoDeAparatos(datos([GOLPE]));
  assert.match(html, /Musnap Neo C/);
  assert.match(html, /sugiere: lector/);
});

test("el nombre del aparato es input no autenticado: sale escapado", () => {
  const html = textoDeAparatos(datos([
    {...GOLPE, aparato: '<script>alert(1)</script>'},
    {...VIVA, aparato: '<img src=x onerror=alert(2)>'},
  ]));
  assert.ok(!html.includes("<script>"), "el nombre del golpe salio crudo");
  assert.ok(!html.includes("<img"), "el nombre de la lista salio crudo");
  assert.match(html, /&lt;script&gt;/);
});

test("el golpe muestra el alcance del tipo sugerido, no una etiqueta sola",
     () => {
  const html = textoDeAparatos(datos([GOLPE]));
  assert.match(html, /Solo sus endpoints de lectura/);
});

test("el selector de tipo trae los tres tipos, con el sugerido elegido",
     () => {
  const html = textoDeAparatos(datos([{...GOLPE, tipo: "tablero"}]));
  assert.match(html, /<select data-tipo-de="ped_ABC-123_xyz"/);
  for (const tipo of ["lector", "tablero", "navegador"]) {
    assert.ok(html.includes(`value="${tipo}"`), `falta el tipo ${tipo}`);
  }
  assert.match(html, /<option value="tablero" selected>/);
  assert.equal((html.match(/ selected>/g) || []).length, 1,
               "quedo mas de un tipo preseleccionado");
});

test("un tipo sugerido que no existe no preselecciona nada", () => {
  const html = textoDeAparatos(datos([{...GOLPE, tipo: "administrador"}]));
  assert.ok(!html.includes(" selected>"),
            "se preselecciono un tipo que la tabla no tiene");
});

test("el golpe trae aprobar y rechazar con el id_pedido, no el hash", () => {
  const html = textoDeAparatos(datos([GOLPE]));
  assert.match(
    html, /<button data-aparato="aprobar" data-id="ped_ABC-123_xyz"/);
  assert.match(
    html, /<button data-aparato="rechazar" data-id="ped_ABC-123_xyz"/);
  assert.ok(!html.includes('data-aparato="revocar"'),
            "un golpe no tiene nada que revocar todavia");
});

// --- la lista de aparatos ----------------------------------------------

test("una sesion viva se revoca por su hash, no por el id_pedido", () => {
  const html = textoDeAparatos(datos([VIVA]));
  assert.match(html, /<button data-aparato="revocar" data-id="a1b2c3d4"/);
  assert.ok(!html.includes("ped_vieja"),
            "el id_pedido de una sesion viva no tiene por que viajar a la UI");
});

test("la lista muestra el tipo, el estado efectivo y la ultima vez", () => {
  const html = textoDeAparatos(datos([VIVA]));
  assert.match(html, /Celular de Pedro/);
  assert.match(html, /navegador/);
  assert.match(html, /viva/);
  assert.match(html, new RegExp(fechaLegible(VIVA.ultima_vez)));
});

test("solo las vivas se revocan: caduca, revocada y rechazada no", () => {
  for (const efectivo of ["caduca", "revocada", "rechazada"]) {
    const html = textoDeAparatos(datos([{...VIVA, efectivo}]));
    assert.ok(!html.includes('data-aparato="revocar"'),
              `se ofrecio revocar una sesion ${efectivo}`);
    assert.ok(html.includes(efectivo), `no se ve la etiqueta ${efectivo}`);
  }
});

test("una aprobacion que el aparato todavia no canjeo lo dice y no se revoca",
     () => {
  const html = textoDeAparatos(datos([{...VIVA, hash_id: null}]));
  assert.match(html, /esperando al aparato/i);
  assert.ok(!html.includes('data-aparato="revocar"'),
            "no hay hash con que revocar: el boton mentiria");
});

test("un golpe vencido cae en la lista y ya no se aprueba", () => {
  const html = textoDeAparatos(datos([{...GOLPE, efectivo: "caduca"}]));
  assert.ok(!html.includes('data-aparato="aprobar"'),
            "se ofrecio aprobar un golpe que ya vencio");
  assert.match(html, /caduca/);
});

// --- lo vacio, el aviso y los bordes ------------------------------------

test("sin nada, las dos secciones lo dicen en vez de quedar en blanco", () => {
  const html = textoDeAparatos(datos());
  assert.match(html, /Ningun aparato esta pidiendo entrar/i);
  assert.match(html, /Ningun aparato dado de alta/i);
});

test("null o undefined no revientan: se leen como que no hay nada", () => {
  assert.match(textoDeAparatos(null), /Ningun aparato/i);
  assert.match(textoDeAparatos(undefined), /Ningun aparato/i);
});

test("el aviso de la ultima accion se muestra arriba y escapado", () => {
  const html = textoDeAparatos(datos(), "listo: <b>quedo</b> aprobado");
  assert.match(html, /class="listo"/);
  assert.ok(!html.includes("<b>"), "el aviso salio sin escapar");
});

test("con un golpe y una sesion viva, cada uno cae en su seccion", () => {
  const html = textoDeAparatos(datos([VIVA, GOLPE]));
  const secciones = html.indexOf("Musnap Neo C") < html.indexOf("Celular de Pedro");
  assert.ok(secciones,
            "el golpe que espera respuesta tiene que ir arriba de la lista");
  assert.ok(!html.includes("Ningun aparato"), "no habia nada vacio que decir");
});
