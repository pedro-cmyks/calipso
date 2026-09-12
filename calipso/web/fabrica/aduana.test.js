import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDeAduana, textoDeMaquina, filtrar, desdeClave, claveDe} from "./aduana.js";

const CRUCE = {
  ts: "2026-09-10T15:04:05", id: "cr_0123456789ab",
  quien: {origen: "turno", chat: "chat_x", proyecto: "calipso", gesto: "/web",
          ruta: "local", rutina: null, departamento: null, endpoint: null,
          desde: {credencial: "maquina"}},
  proposito: "buscar en la web",
  destino: {host: "html.duckduckgo.com", url: "https://html.duckduckgo.com/html/"},
  carga: {tipo: "consulta", texto: "precio del dolar hoy"},
  resultado: {estado: "ok", ms: 812, bytes: 48213}, declarado: false,
};

const DECLARADO = {
  ts: "2026-09-10T09:00:00", id: "cr_declarado0001",
  quien: {origen: "arranque", chat: null, proyecto: "calipso", gesto: null,
          ruta: null, rutina: null, departamento: null, endpoint: null,
          desde: {credencial: "maquina"}},
  proposito: "modelo de embeddings", motivo: "all-MiniLM-L6-v2",
  destino: {host: "huggingface.co", url: null},
  carga: {tipo: "nada"}, resultado: null, declarado: true,
};

const DESDE_CEL = {
  ...CRUCE, id: "cr_desde_cel_001", ts: "2026-09-10T16:00:00",
  quien: {...CRUCE.quien, origen: "ui", chat: null, gesto: null, ruta: null,
          endpoint: "/api/updates", proyecto: "otro",
          desde: {credencial: "sesion", tipo: "navegador", aparato: "Celular",
                  hash: "abcd1234"}},
  proposito: "version en npm",
  destino: {host: "registry.npmjs.org", url: "https://registry.npmjs.org/x/latest"},
  carga: {tipo: "nada"},
};

function datos(cruces = [], extra = {}) {
  const contar = (f) => cruces.reduce((m, c) => {
    const k = claveDe(c, f); m[k] = (m[k] || 0) + 1; return m; }, {});
  return {
    cruces,
    totales: {por_origen: contar("origen"), por_proyecto: contar("proyecto"),
              por_desde: contar("desde"),
              por_destino: cruces.reduce((m, c) => {
                const k = c.destino?.host ?? "?"; m[k] = (m[k] || 0) + 1; return m; }, {}),
              declarados: cruces.filter(c => c.declarado).length},
    sin_libro: {n: 0, desde: null, ultimo_error: null},
    ilegibles: 0,
    ...extra,
  };
}

// --- totales ------------------------------------------------------------------

test("los totales por origen, proyecto y desde se muestran arriba", () => {
  const html = textoDeAduana(datos([CRUCE, DECLARADO, DESDE_CEL]));
  assert.match(html, /cruces hoy/);
  assert.match(html, /3 \(1 declarados\)/);
  assert.match(html, /por origen/);
  assert.match(html, /turno<\/span><span>1/);
  assert.match(html, /por proyecto/);
  assert.match(html, /calipso<\/span><span>2/);
  assert.match(html, /por desde/);
  assert.match(html, /sesion:navegador<\/span><span>1/);
  assert.match(html, /por destino/);
  assert.ok(html.indexOf("por origen") < html.indexOf("cruces del dia"),
            "los totales van arriba de la lista");
});

// --- lista --------------------------------------------------------------------

test("cada cruce muestra hora, quien, destino, proposito, carga y estado", () => {
  const html = textoDeAduana(datos([CRUCE]));
  assert.match(html, /class="hora">15:04</);
  assert.match(html, /turno · chat chat_x · \/web · local/);
  assert.match(html, /html\.duckduckgo\.com/);
  assert.match(html, /buscar en la web/);
  assert.match(html, /<pre class="carga">precio del dolar hoy<\/pre>/);
  assert.match(html, /class="etiqueta ok">ok<\/span> <span>812 ms · 48213 bytes/);
  assert.match(html, /desde<\/span><span>maquina/);
});

test("un declarado lleva su marca y no inventa un resultado", () => {
  const html = textoDeAduana(datos([DECLARADO]));
  assert.match(html, /class="cruce declarado"/);
  assert.match(html, /class="etiqueta declarado">declarado</);
  assert.match(html, /modelo de embeddings/);
  assert.match(html, /\(all-MiniLM-L6-v2\)/);
  assert.match(html, /carga: nada/);
  assert.ok(!html.includes("undefined"), "un campo ausente salio como 'undefined'");
});

test("un fallo se distingue y dice la excepcion", () => {
  const html = textoDeAduana(datos([{...CRUCE, resultado: {estado: "fallo", ms: 3, bytes: null, error: "TimeoutError"}}]));
  assert.match(html, /class="cruce fallo"/);
  assert.match(html, /class="etiqueta fallo">fallo<\/span> <span>3 ms · TimeoutError/);
});

test("una sesion se muestra con tipo, aparato y hash", () => {
  const html = textoDeAduana(datos([DESDE_CEL]));
  assert.match(html, /sesion navegador \(Celular abcd1234\)/);
  assert.match(html, /ui · \/api\/updates/);
});

test("un cuerpo muestra tamano, hash y las lineas en monoespacio", () => {
  const html = textoDeAduana(datos([{...CRUCE, carga: {tipo: "cuerpo", tamano: 5120, sha256: "ab12cd34ef56", lineas: "titulo\nlinea dos"}}]));
  assert.match(html, /5120 bytes · sha ab12cd34ef56/);
  assert.match(html, /<pre class="carga">titulo\nlinea dos<\/pre>/);
});

test("un cruce recortado (tablero) no muestra carga ni chat", () => {
  const {carga, ...sinCarga} = CRUCE;
  const html = textoDeAduana(datos([{...sinCarga, quien: {...CRUCE.quien, chat: undefined}}]));
  assert.ok(!html.includes("class=\"carga\""), "no habia carga que mostrar");
  assert.ok(!html.includes("carga: nada"), "recortada no es lo mismo que nada");
  assert.ok(!html.includes("chat "), "el chat no viaja al tablero");
});

test("la lista va del mas reciente al mas viejo", () => {
  const html = textoDeAduana(datos([DECLARADO, CRUCE]));
  assert.ok(html.indexOf("buscar en la web") < html.indexOf("modelo de embeddings"));
});

// --- filtros ------------------------------------------------------------------

test("filtrar por origen, proyecto y desde", () => {
  const todos = [CRUCE, DECLARADO, DESDE_CEL];
  assert.deepEqual(filtrar(todos, {origen: "turno"}).map(c => c.id), [CRUCE.id]);
  assert.deepEqual(filtrar(todos, {proyecto: "otro"}).map(c => c.id), [DESDE_CEL.id]);
  assert.deepEqual(filtrar(todos, {desde: "maquina"}).map(c => c.id), [CRUCE.id, DECLARADO.id]);
  assert.deepEqual(filtrar(todos, {origen: "turno", desde: "sesion:navegador"}), []);
  assert.deepEqual(filtrar(todos, {}), todos);
  assert.equal(desdeClave(DESDE_CEL.quien.desde), "sesion:navegador");
  assert.equal(desdeClave(null), "?");
});

test("los selectores llevan las claves del dia y recuerdan lo elegido", () => {
  const html = textoDeAduana(datos([CRUCE, DESDE_CEL]), {origen: "ui"});
  assert.match(html, /<select data-filtro="origen">/);
  assert.match(html, /<option value="ui" selected>ui<\/option>/);
  assert.match(html, /<option value="turno">turno<\/option>/);
  assert.match(html, /<select data-filtro="proyecto">/);
  assert.match(html, /<select data-filtro="desde">/);
  assert.match(html, /<option value="sesion:navegador">/);
  // y la lista queda filtrada: solo el de la ui
  assert.ok(html.includes("version en npm") && !html.includes("buscar en la web"));
});

test("un filtro que no deja nada lo dice, distinto de un dia vacio", () => {
  assert.match(textoDeAduana(datos([CRUCE]), {origen: "rutina"}), /Ningun cruce con ese filtro/);
  assert.match(textoDeAduana(datos([])), /Ningun cruce hoy/);
});

// --- avisos -------------------------------------------------------------------

test("el aviso de sin_libro aparece con n > 0 y no con n = 0", () => {
  const con = textoDeAduana(datos([], {sin_libro: {n: 3, desde: "2026-09-10T12:00:00", ultimo_error: "ErrorCandado: tomado"}}));
  assert.match(con, /class="aviso">3 cruce\(s\) sin anotar desde 2026-09-10T12:00:00: ErrorCandado: tomado/);
  const sin = textoDeAduana(datos([]));
  assert.ok(!sin.includes("class=\"aviso\""), "con n = 0 no hay aviso");
});

test("las lineas ilegibles se cuentan, no se esconden", () => {
  assert.match(textoDeAduana(datos([], {ilegibles: 2})), /2 linea\(s\) ilegible\(s\)/);
  assert.ok(!textoDeAduana(datos([])).includes("ilegible"));
});

// --- escape -------------------------------------------------------------------

test("nada del libro es de confianza: carga y URL salen escapadas", () => {
  const malo = '<img src=x onerror=alert(1)>';
  const html = textoDeAduana(datos([{
    ...CRUCE,
    proposito: "<script>alert(2)</script>",
    destino: {host: malo, url: "https://x.com/" + malo},
    carga: {tipo: "consulta", texto: malo},
    quien: {...CRUCE.quien, chat: malo, proyecto: malo,
            desde: {credencial: "sesion", tipo: "navegador", aparato: malo, hash: malo}},
  }]));
  assert.ok(!html.includes("<img"), "algo del libro salio crudo");
  assert.ok(!html.includes("<script>"), "el proposito salio crudo");
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(html, /&lt;script&gt;/);
  // y los valores de <option> tambien
  assert.ok(!html.includes('value="<img'), "un valor de option salio crudo");
});

test("el aviso de sin_libro tambien se escapa", () => {
  const html = textoDeAduana(datos([], {sin_libro: {n: 1, desde: "x", ultimo_error: "<b>rojo</b>"}}));
  assert.ok(!html.includes("<b>"));
});

// --- robustez -----------------------------------------------------------------

test("null, undefined o un objeto sin cruces no revientan", () => {
  assert.match(textoDeAduana(null), /Ningun cruce hoy/);
  assert.match(textoDeAduana(undefined), /Ningun cruce hoy/);
  assert.match(textoDeAduana({activa: true, ciudad: {}}), /Ningun cruce hoy/);
  assert.match(textoDeAduana({cruces: [{}]}), /class="cruce"/);
});

// --- la maquina (spec carga 2026-09-11, seccion 4) ---------------------------

const MAQUINA = {medicion: {nivel: "cargada", motivo: "mem 480 < 5746", mem_disponible_mb: 480,
                            necesidad_mb: 5746, psi_mem_some10: 0.16, psi_mem_full10: 0.16,
                            psi_cpu_some10: 0.46, load1: 9.96, ncpu: 16, swap_usado_mb: 5819,
                            modelos_cargados: ["qwen2.5:7b", "<b>x</b>"],
                            medido: {meminfo: true, psi: true, loadavg: true, ollama: true}},
                 hoy: {suscripcion: 3, local_con_aviso: 1, descarga: 1, pospone: 2, sin_3b: 0, sin_vision: 0}};

test("la linea la maquina va adelante con nivel, memoria, presion, cargados y las cuentas del dia", () => {
  const html = textoDeAduana(datos([]), {}, MAQUINA);
  assert.ok(html.indexOf("la maquina") < html.indexOf("cruces hoy"));
  assert.match(html, /class="maquina"/);
  assert.match(html, /<span>nivel<\/span><span>cargada<\/span>/);
  assert.match(html, /480 MB libres, necesita 5746 \(mem 480 &lt; 5746\)/);
  assert.match(html, /mem 0\.16\/0\.16, cpu 0\.46, load1 9\.96\/16, swap usado 5819 MB/);
  assert.match(html, /qwen2\.5:7b, &lt;b&gt;x&lt;\/b&gt;/);
  assert.ok(!html.includes("<b>x</b>"));
  assert.match(html, /3 a suscripcion, 1 local con aviso, 1 descarga\(s\), 2 pospuesta\(s\)/);
});

test("sin maquina no hay linea ni undefined, y los filtros la conservan", () => {
  const sin = textoDeAduana(datos([CRUCE]), {});
  assert.ok(!sin.includes("la maquina") && !sin.includes("undefined"));
  assert.equal(textoDeMaquina(null), "");
  assert.equal(textoDeMaquina({hoy: {}}), "");
  const con = textoDeAduana(datos([CRUCE]), {origen: "turno"}, MAQUINA);
  assert.match(con, /la maquina/);
});

test("sin nada medido dice sin medir y ninguno cargado", () => {
  const html = textoDeMaquina({medicion: {nivel: "holgada", modelos_cargados: [],
                                          medido: {meminfo: false, psi: false, loadavg: false, ollama: false}},
                               hoy: {}});
  assert.match(html, /<span>nivel<\/span><span>sin medir<\/span>/);
  assert.match(html, /<span>cargados<\/span><span>ninguno<\/span>/);
  assert.match(html, /0 a suscripcion, 0 local con aviso, 0 descarga\(s\), 0 pospuesta\(s\)/);
});
