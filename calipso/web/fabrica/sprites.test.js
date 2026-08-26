import test from "node:test";
import assert from "node:assert/strict";

import {FRENTE, LATERAL, TECHO, VENTANA, PRENDIDA, GRIETA, TRANSPARENTE,
        OCUPADO, ESCRITORIO, ESPERA, PISO, rampaDe, RAMPAS} from "./paleta.js";
import {edificioSprite, medidas, alturaDe, fnv1a, ANCHO, PROF,
        interiorSprite, plazasDe} from "./sprites.js";

function edi(extra = {}) {
  return {id: "dep:atlas", nombre: "atlas", zona: "fabrica", tamano: 4,
          estado: "activo", actividad: 2, ...extra};
}

function cuenta(sprite, valor) {
  let n = 0;
  for (const v of sprite.pix) if (v === valor) n++;
  return n;
}

test("el mismo edificio da el mismo sprite", () => {
  const a = edificioSprite(edi());
  const b = edificioSprite(edi());
  assert.equal(a.ancho, b.ancho);
  assert.equal(a.alto, b.alto);
  assert.deepEqual(Array.from(a.pix), Array.from(b.pix));
});

test("la matriz mide exactamente lo que dicen sus medidas", () => {
  const e = edi({tamano: 7});
  const s = edificioSprite(e);
  const m = medidas(e);
  assert.equal(s.ancho, m.ancho);
  assert.equal(s.alto, m.alto);
  assert.equal(s.pix.length, m.ancho * m.alto);
});

test("el tamano manda en la altura y es monotono", () => {
  let previo = 0;
  for (let t = 1; t <= 9; t++) {
    const alto = alturaDe(t);
    assert.ok(alto > previo, `tamano ${t} no crecio`);
    previo = alto;
  }
});

test("hay volumen: techo, frente y lateral aparecen los tres", () => {
  const s = edificioSprite(edi());
  assert.ok(cuenta(s, FRENTE) > 0, "sin cara frontal");
  assert.ok(cuenta(s, LATERAL) > 0, "sin cara lateral");
  assert.ok(cuenta(s, TECHO) > 0, "sin techo");
});

test("el sprite tiene aire alrededor de la perspectiva", () => {
  // la esquina de abajo a la derecha queda fuera del cuerpo: el lateral se
  // corrio hacia arriba. Si no hay transparencia ahi, no hay perspectiva.
  const s = edificioSprite(edi());
  assert.equal(s.pix[(s.alto - 1) * s.ancho + (s.ancho - 1)], TRANSPARENTE);
});

test("mas actividad prende mas ventanas, y nunca menos", () => {
  let previo = -1;
  for (let a = 0; a <= 3; a++) {
    const n = cuenta(edificioSprite(edi({actividad: a})), PRENDIDA);
    assert.ok(n >= previo, `actividad ${a} prendio menos que la anterior`);
    previo = n;
  }
  assert.ok(cuenta(edificioSprite(edi({actividad: 3})), PRENDIDA) > 0,
            "con actividad 3 no prendio ninguna");
});

test("sin actividad no hay una sola ventana prendida", () => {
  const s = edificioSprite(edi({actividad: 0}));
  assert.equal(cuenta(s, PRENDIDA), 0);
  assert.ok(cuenta(s, VENTANA) > 0, "tampoco hay ventanas apagadas");
});

test("un congelado no prende luz y le salen grietas", () => {
  const vivo = edificioSprite(edi({estado: "activo", actividad: 3}));
  const muerto = edificioSprite(edi({estado: "congelado", actividad: 3}));
  assert.equal(cuenta(muerto, PRENDIDA), 0, "un congelado prendio una luz");
  assert.ok(cuenta(muerto, GRIETA) > 0, "un congelado sin grietas");
  assert.equal(cuenta(vivo, GRIETA), 0, "un edificio sano con grietas");
});

test("la grieta es una sola linea continua, no salpicadura", () => {
  const s = edificioSprite(edi({estado: "congelado"}));
  const filas = new Map();
  s.pix.forEach((v, i) => {
    if (v !== GRIETA) return;
    const y = Math.floor(i / s.ancho);
    filas.set(y, (filas.get(y) || 0) + 1);
  });
  for (const [y, n] of filas) assert.equal(n, 1, `la fila ${y} tiene ${n} grietas`);
  const ys = [...filas.keys()].sort((a, b) => a - b);
  for (let i = 1; i < ys.length; i++) {
    assert.equal(ys[i], ys[i - 1] + 1, "la grieta se corta");
  }
});

test("la grieta zigzaguea de a un pixel, no salta", () => {
  // sin esto, un paso de cinco pixeles por fila pasaria por "continua":
  // el test de arriba solo mira que no falte ninguna fila
  const s = edificioSprite(edi({estado: "congelado", tamano: 9}));
  const xs = [];
  s.pix.forEach((v, i) => {
    if (v === GRIETA) xs.push([Math.floor(i / s.ancho), i % s.ancho]);
  });
  xs.sort((a, b) => a[0] - b[0]);
  assert.ok(xs.length > 3, "no hay grieta que medir");
  let pasos = 0;
  for (let i = 1; i < xs.length; i++) {
    const d = Math.abs(xs[i][1] - xs[i - 1][1]);
    // cero es legitimo: es la grieta apoyada contra el borde, que no puede
    // seguir avanzando para ese lado
    assert.ok(d <= 1, `salto de ${d} en la fila ${xs[i][0]}`);
    if (d === 1) pasos++;
  }
  assert.ok(pasos > 0, "la grieta es una linea recta, no zigzaguea");
});

test("dos edificios distintos no prenden el mismo patron de ventanas", () => {
  const a = edificioSprite(edi({id: "dep:atlas"}));
  const b = edificioSprite(edi({id: "dep:mercado"}));
  assert.notDeepEqual(Array.from(a.pix), Array.from(b.pix));
});

test("cada zona tiene su rampa y el congelado pisa a la zona", () => {
  const f = rampaDe(edi({zona: "fabrica"}));
  const p = rampaDe(edi({zona: "personal"}));
  assert.notEqual(f[FRENTE], p[FRENTE], "fabrica y personal se ven igual");
  const congelado = rampaDe(edi({zona: "personal", estado: "congelado"}));
  assert.equal(congelado[FRENTE], RAMPAS.congelado[FRENTE]);
});

test("una zona desconocida cae en la de fabrica en vez de romper", () => {
  assert.equal(rampaDe(edi({zona: "marte"}))[FRENTE], RAMPAS.fabrica[FRENTE]);
});

test("el tamano se recorta a la escala 1-9 en vez de reventar", () => {
  assert.equal(alturaDe(0), alturaDe(1));
  assert.equal(alturaDe(99), alturaDe(9));
});

test("fnv1a es estable y distingue", () => {
  assert.equal(fnv1a("atlas"), fnv1a("atlas"));
  assert.notEqual(fnv1a("atlas"), fnv1a("mercado"));
  assert.ok(Number.isInteger(fnv1a("atlas")) && fnv1a("atlas") >= 0);
});

test("el interior es el mismo edificio sin techo y con escritorios", () => {
  const edificio = {id: "dep:atlas", zona: "fabrica", estado: "activo",
                    tamano: 2, actividad: 3};
  const fuera = edificioSprite(edificio);
  const dentro = interiorSprite(edificio, ["razonando", "liberado"]);
  assert.equal(dentro.ancho, fuera.ancho);
  assert.equal(dentro.alto, fuera.alto);
  // el techo se fue: la fila de arriba del sprite queda transparente
  assert.ok(dentro.pix.slice(0, dentro.ancho).every(v => v === TRANSPARENTE));
  assert.ok(fuera.pix.slice(0, fuera.ancho).some(v => v !== TRANSPARENTE));
  // hay al menos un escritorio ocupado y uno vacio, que es lo que se pidio
  assert.ok(dentro.pix.includes(OCUPADO));
  assert.ok(dentro.pix.includes(ESCRITORIO));
});

test("los tres estados del spec se dibujan distintos", () => {
  const edificio = {id: "dep:atlas", zona: "fabrica", estado: "activo",
                    tamano: 2, actividad: 0};
  const s = interiorSprite(edificio, ["razonando", "esperando", "liberado"]);
  // razonando prendido, esperando ocupado pero apagado, liberado vacio: si
  // dos de los tres comparten indice, el mapa no distingue "esta pensando"
  // de "esta esperando", que es la mitad de para que sirve entrar
  assert.ok(s.pix.includes(OCUPADO), "falta el que razona");
  assert.ok(s.pix.includes(ESPERA), "falta el que espera");
  assert.ok(s.pix.includes(ESCRITORIO), "falta el escritorio vacio");
});

test("el mismo interior da siempre el mismo bitmap", () => {
  const edificio = {id: "dep:atlas", zona: "fabrica", estado: "activo",
                    tamano: 4, actividad: 1};
  assert.deepEqual(interiorSprite(edificio, ["razonando"]).pix,
                   interiorSprite(edificio, ["razonando"]).pix);
});

test("mas empleados que escritorios no desborda el sprite", () => {
  const edificio = {id: "dep:atlas", zona: "fabrica", estado: "activo",
                    tamano: 1, actividad: 0};
  const estados = new Array(50).fill("razonando");
  const dentro = interiorSprite(edificio, estados);
  assert.equal(dentro.pix.length, dentro.ancho * dentro.alto);
});
