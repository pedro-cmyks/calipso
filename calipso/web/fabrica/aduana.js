import {escapar} from "./paneles.js";

// La sexta sub-pestana: Aduana -- cuantos cruces a internet hubo hoy, quien
// los disparo, a donde y con que carga (spec de la aduana, seccion 9).
// Modulo PURO como aparatos.js: devuelve HTML como string, no toca DOM ni
// fetch. TODO texto del libro pasa por escapar(): nada del libro es de
// confianza (las URLs de fetch salen del href que devolvio DuckDuckGo).
// Sin badge: la aduana no le pide nada a Pedro.

const FILTROS = ["origen", "proyecto", "desde"];

export function desdeClave(desde) {
  if (!desde || typeof desde !== "object") return "?";
  if (desde.credencial === "sesion") return `sesion:${desde.tipo || "?"}`;
  return String(desde.credencial || "?");
}

export function claveDe(cruce, filtro) {
  const quien = cruce?.quien || {};
  if (filtro === "origen") return String(quien.origen ?? "?");
  if (filtro === "proyecto") return String(quien.proyecto ?? "?");
  return desdeClave(quien.desde);
}

export function filtrar(cruces, filtros = {}) {
  return (cruces || []).filter(c =>
    FILTROS.every(f => !filtros[f] || claveDe(c, f) === filtros[f]));
}

function horaDe(ts) {
  const crudo = String(ts ?? "");
  return crudo.length >= 16 && crudo[10] === "T" ? crudo.slice(11, 16) : crudo;
}

function quienLegible(quien) {
  const q = quien || {};
  const partes = [q.origen || "?"];
  if (q.chat) partes.push(`chat ${q.chat}`);
  if (q.rutina) partes.push(`rutina ${q.rutina.kind || "?"} ${q.rutina.id || ""}`.trim());
  if (q.endpoint) partes.push(q.endpoint);
  if (q.gesto) partes.push(q.gesto);
  if (q.ruta) partes.push(q.ruta);
  if (q.departamento) partes.push(`dep ${q.departamento}`);
  return partes.map(escapar).join(" · ");
}

function desdeLegible(desde) {
  if (!desde || desde.credencial !== "sesion") return escapar(desdeClave(desde));
  return escapar(`sesion ${desde.tipo || "?"}` +
    (desde.aparato ? ` (${desde.aparato}` + (desde.hash ? ` ${desde.hash}` : "") + ")" : ""));
}

function cargaLegible(carga) {
  if (carga === undefined) return "";            // recortada (tablero)
  if (!carga || carga.tipo === "nada") return `<div class="nota">carga: nada</div>`;
  if (carga.tipo === "cuerpo") {
    return `<div class="fila"><span>cuerpo</span>` +
      `<span>${escapar(carga.tamano)} bytes · sha ${escapar(carga.sha256)}</span></div>` +
      `<pre class="carga">${escapar(carga.lineas)}</pre>`;
  }
  return `<pre class="carga">${escapar(carga.texto)}</pre>`;
}

function estadoLegible(cruce) {
  if (cruce.declarado) return `<span class="etiqueta declarado">declarado</span>`;
  const r = cruce.resultado || {};
  const extra = [];
  if (r.ms !== undefined && r.ms !== null) extra.push(`${escapar(r.ms)} ms`);
  if (r.bytes !== undefined && r.bytes !== null) extra.push(`${escapar(r.bytes)} bytes`);
  if (r.estado === "fallo") extra.push(escapar(r.error || ""));
  return `<span class="etiqueta ${r.estado === "fallo" ? "fallo" : "ok"}">` +
    `${escapar(r.estado || "?")}</span> <span>${extra.join(" · ")}</span>`;
}

function tarjetaDeCruce(c) {
  const d = c.destino || {};
  const clases = ["cruce"];
  if (c.declarado) clases.push("declarado");
  if (c.resultado?.estado === "fallo") clases.push("fallo");
  const url = d.url && d.url !== d.host
    ? `<div class="url">${escapar(d.url)}</div>` : "";
  return `<div class="${clases.join(" ")}">` +
    `<div class="fila"><span class="hora">${escapar(horaDe(c.ts))}</span>` +
    `<span class="quien">${quienLegible(c.quien)}</span></div>` +
    `<div class="fila"><span>destino</span><span>${escapar(d.host ?? "?")}</span></div>` +
    url +
    `<div class="proposito">${escapar(c.proposito)}` +
    (c.motivo ? ` <span class="nota">(${escapar(c.motivo)})</span>` : "") + `</div>` +
    cargaLegible(c.carga) +
    `<div class="fila"><span>desde</span><span>${desdeLegible(c.quien?.desde)}</span></div>` +
    `<div class="fila"><span>estado</span><span>${estadoLegible(c)}</span></div>` +
    `</div>`;
}

function bloqueDeTotales(titulo, mapa) {
  const pares = Object.entries(mapa || {}).sort((a, b) => b[1] - a[1]);
  const filas = pares.length
    ? pares.map(([k, n]) => `<div class="fila"><span>${escapar(k)}</span>` +
                             `<span>${escapar(n)}</span></div>`).join("")
    : `<div class="nota">nada</div>`;
  return `<div class="totales"><div class="subtitulo">${escapar(titulo)}</div>${filas}</div>`;
}

function selectorDeFiltro(filtro, claves, elegido) {
  const opciones = [`<option value="">todos</option>`]
    .concat(claves.map(k => `<option value="${escapar(k)}"` +
                             `${k === elegido ? " selected" : ""}>${escapar(k)}</option>`));
  return `<label>${filtro}<select data-filtro="${filtro}">${opciones.join("")}</select></label>`;
}

/** La linea "la maquina" de la pestana (spec carga 2026-09-11, seccion 4):
 *  la medicion actual de GET /api/carga y las cuentas del dia de telemetria.
 *  `maquina` es {medicion, hoy}; sin el (endpoint caido, fuera de alcance),
 *  "" y la aduana se pinta igual. La clase es .maquina y no .carga: `carga`
 *  ya es el PAYLOAD de un cruce en esta pestana. Los nombres de modelos
 *  vienen de /api/ps: texto no confiable, pasan por escapar(). */
export function textoDeMaquina(maquina) {
  const m = maquina?.medicion;
  if (!m || typeof m !== "object") return "";
  const hoy = maquina.hoy || {};
  const medido = m.medido || {};
  const nivel = Object.values(medido).some(Boolean) ? (m.nivel || "?") : "sin medir";
  const memoria = `${escapar(m.mem_disponible_mb ?? "?")} MB libres, necesita ` +
    `${escapar(m.necesidad_mb ?? "?")}` + (m.motivo ? ` (${escapar(m.motivo)})` : "");
  const presion = `mem ${escapar(m.psi_mem_some10 ?? 0)}/${escapar(m.psi_mem_full10 ?? 0)}, ` +
    `cpu ${escapar(m.psi_cpu_some10 ?? 0)}, load1 ${escapar(m.load1 ?? 0)}/${escapar(m.ncpu ?? "?")}, ` +
    `swap usado ${escapar(m.swap_usado_mb ?? 0)} MB`;
  const cargados = (m.modelos_cargados || []).length
    ? m.modelos_cargados.map(escapar).join(", ") : "ninguno";
  const cuentas = `${escapar(hoy.suscripcion || 0)} a suscripcion, ` +
    `${escapar(hoy.local_con_aviso || 0)} local con aviso, ` +
    `${escapar(hoy.descarga || 0)} descarga(s), ${escapar(hoy.pospone || 0)} pospuesta(s)`;   // pospone: rutinas distintas, no ticks (cuentas_del_dia)
  return `<div class="maquina"><div class="subtitulo">la maquina</div>` +
    `<div class="fila"><span>nivel</span><span>${escapar(nivel)}</span></div>` +
    `<div class="fila"><span>memoria</span><span>${memoria}</span></div>` +
    `<div class="fila"><span>presion</span><span>${presion}</span></div>` +
    `<div class="fila"><span>cargados</span><span>${cargados}</span></div>` +
    `<div class="fila"><span>hoy</span><span>${cuentas}</span></div></div>`;
}

export function textoDeAduana(datos, filtros = {}, maquina = null) {
  const cruces = datos?.cruces || [];
  const totales = datos?.totales || {};
  const sinLibro = datos?.sin_libro;
  const ilegibles = Number(datos?.ilegibles || 0);
  const aviso = sinLibro && Number(sinLibro.n) > 0
    ? `<div class="aviso">${escapar(sinLibro.n)} cruce(s) sin anotar desde ` +
      `${escapar(sinLibro.desde)}: ${escapar(sinLibro.ultimo_error)}</div>` : "";
  const rotas = ilegibles > 0
    ? `<div class="nota">${escapar(ilegibles)} linea(s) ilegible(s) en el libro</div>` : "";
  const cabecera = `<div class="fila resumen"><span>cruces hoy</span>` +
    `<span>${escapar(cruces.length)} (${escapar(totales.declarados || 0)} declarados)</span></div>`;
  const bloques = bloqueDeTotales("por origen", totales.por_origen) +
    bloqueDeTotales("por proyecto", totales.por_proyecto) +
    bloqueDeTotales("por desde", totales.por_desde) +
    bloqueDeTotales("por destino", totales.por_destino);
  const clavesDe = f => Array.from(new Set(cruces.map(c => claveDe(c, f)))).sort();
  const selectores = `<div class="filtros">` +
    FILTROS.map(f => selectorDeFiltro(f, clavesDe(f), filtros[f] || "")).join("") + `</div>`;
  const visibles = filtrar(cruces, filtros);
  const lista = visibles.length
    ? visibles.slice().reverse().map(tarjetaDeCruce).join("")
    : (cruces.length
        ? `<div class="vacio">Ningun cruce con ese filtro.</div>`
        : `<div class="vacio">Ningun cruce hoy.</div>`);
  return textoDeMaquina(maquina) + aviso + rotas + cabecera + bloques + selectores +
    `<div class="subtitulo">cruces del dia</div>` + lista;
}
