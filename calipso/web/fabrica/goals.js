// La pestana Goals de la fabrica (spec goals 2026-09-13, seccion 10): la
// lista con estado, tope consumido (golpes/minutos/unidades), lo que espera
// respuesta, el ledger del activo (golpes con veredicto, comandos, diff_stat,
// costo) y los botones dale / no / parar / segui con nota. Molde aduana.js:
// modulo PURO (devuelve HTML como string), TODO por escapar().
import {escapar} from "./paneles.js";

const MOTIVOS = {
  tope: "llego al tope", cuota: "cuota agotada", no_convergencia: "no converge",
  cumplido: "cumplido: cerrar?", pregunta: "pregunta", compuerta: "pide una compuerta",
  raiz_nueva: "pide una raiz nueva", "parado por Pedro": "parado", "server apagado": "server apagado",
  "server reiniciado": "server reiniciado", dale: "espera el dale",
};

function num(v) {
  return v === null || v === undefined ? "?" : String(v);
}

export function consumoDe(goal) {
  const c = goal?.consumo || {};
  const t = goal?.tope || {};
  return `${num(c.golpes || 0)}/${num(t.golpes)} golpes, ${num(c.minutos || 0)}/${num(t.minutos)} min, ` +
    `${num(c.unidades || 0)}/${num(t.unidades)} unidades`;
}

export function esperaDe(goal) {
  if (goal?.status !== "waiting") return "";
  const e = goal.espera || {};
  const partes = [MOTIVOS[e.motivo] || e.motivo || "esperando"];
  if (e.tope) partes.push(`tope: ${e.tope}`);
  if (e.pregunta) partes.push(e.pregunta);
  if (e.diagnostico) partes.push(e.diagnostico);
  if (e.resumen) partes.push(e.resumen);
  if (e.sin_veredicto_de_modelo) partes.push("sin veredicto de modelo (no hay otra familia)");
  if (e.resets_at) partes.push(`vuelve a las ${new Date(e.resets_at * 1000).toLocaleTimeString()}`);
  return partes.join(" - ");
}

function filaDeGolpe(g) {
  const v = g?.veredicto_del_golpe || {};
  const cabeza = g?.fase === "inicio"
    ? `golpe ${escapar(g.n)} (en curso)`
    : `golpe ${escapar(g?.n)}: ${escapar(v.estado || g?.motivo || "?")} - ${escapar(v.resumen || "")}`;
  const comandos = (g?.comandos || []).slice(0, 8).map(c =>
    `<div class="comando">$ ${escapar(c?.cmd)}` +
    (c?.resultado_tail ? ` <span class="tenue">-&gt; ${escapar(String(c.resultado_tail).slice(-80))}</span>` : "") +
    `</div>`).join("");
  const diff = g?.diff_stat ? `<pre class="carga">${escapar(g.diff_stat)}</pre>` : "";
  const costo = g?.fase === "fin"
    ? `<div class="tenue">${escapar(g?.manos || "")} - ${escapar(g?.unidades || 0)} unidades - ` +
      `${escapar(Math.round((g?.duracion_ms || 0) / 1000))} s` +
      (g?.cobro && g.cobro.cobrado === false ? " - sin cobrar (cuenta personal)" : "") + `</div>` : "";
  const juez = g?.juez ? `<div class="tenue">juez: ${escapar(JSON.stringify(g.juez).slice(0, 200))}</div>` : "";
  return `<div class="golpe"><div class="cabeza">${cabeza}</div>${comandos}${diff}${costo}${juez}</div>`;
}

/** Lo que Pedro ya tipeo en cada `input[data-nota-de]` de la caja, por id
 *  de goal (vacias o solo espacios no cuentan). app.js la llama ANTES de
 *  reemplazar el innerHTML y se lo pasa a textoDeGoals: el sondeo de 60 s y
 *  el aviso pasajero repintan la caja entera y el input nacia vacio, y ese
 *  campo es la unica via de la UI para `segui` con nota. Tolera una caja
 *  sin querySelectorAll (arranque.test.js). */
export function notasEscritas(caja) {
  const notas = {};
  const inputs = caja?.querySelectorAll ? caja.querySelectorAll("input[data-nota-de]") : [];
  for (const input of inputs || []) {
    const id = input?.dataset?.notaDe;
    const valor = String(input?.value ?? "");
    if (id && valor.trim()) notas[id] = valor;
  }
  return notas;
}

function botones(goal, nota = "") {
  const id = escapar(goal?.id);
  const s = goal?.status;
  const b = (accion, texto) => `<button data-goal="${accion}" data-id="${id}" type="button">${texto}</button>`;
  if (s === "proposed") return b("dale", "dale") + b("no", "no");
  if (s === "active") return b("parar", "parar") + b("no", "cancelar");
  if (s === "waiting") {
    const cerrar = goal?.espera?.motivo === "cumplido" ? b("dale", "dale: cerrar") : "";
    // el value repone lo que Pedro tenia escrito antes del repintado
    const valor = nota ? ` value="${escapar(nota)}"` : "";
    return cerrar +
      `<label>nota<input data-nota-de="${id}" type="text" placeholder="que cambio o que falta"${valor}></label>` +
      b("segui", "segui") + b("no", "cancelar");
  }
  return "";
}

export function tarjetaDeGoal(goal, golpes = [], notas = {}) {
  const titulo = goal?.title || goal?.objective || "sin titulo";
  const espera = esperaDe(goal);
  return `<div class="goal ${escapar(goal?.status || "")}">` +
    `<div class="fila"><span class="titulo-goal">${escapar(titulo)}</span>` +
    `<span class="estado ${escapar(goal?.status || "")}">${escapar(goal?.status || "?")}</span></div>` +
    `<div class="fila"><span class="tenue">${escapar(goal?.id || "")} - manos ${escapar(goal?.manos || "?")}</span>` +
    `<span>${escapar(consumoDe(goal))}</span></div>` +
    (goal?.criterio ? `<div class="tenue">criterio: ${escapar(JSON.stringify(goal.criterio))}</div>` : "") +
    (espera ? `<div class="espera">esperando a Pedro: ${escapar(espera)}</div>` : "") +
    (goal?.plan?.length ? `<div class="tenue">plan: ${escapar(goal.plan.join(" -> "))}</div>` : "") +
    ((golpes || []).length ? `<details><summary>ledger (${escapar((golpes || []).length)} golpes)</summary>` +
      (golpes || []).slice().reverse().map(filaDeGolpe).join("") + `</details>` : "") +
    `<div class="botones">${botones(goal, (notas || {})[goal?.id] || "")}</div>` +
    `</div>`;
}

export function contadorDeGoals(datos) {
  const todos = [];
  if (datos?.activo) todos.push(datos.activo);
  for (const g of datos?.goals || []) if (!todos.some(x => x?.id === g?.id)) todos.push(g);
  return todos.filter(g => g?.status === "waiting").length;
}

export function textoDeGoals(datos, golpesDelActivo = [], notas = {}) {
  const activo = datos?.activo || null;
  const otros = (datos?.goals || []).filter(g => !activo || g?.id !== activo.id);
  if (!activo && otros.length === 0) return `<div class="vacio">Ningun goal. Decile /goal &lt;texto&gt; al chat.</div>`;
  const cabeza = `<div class="fila resumen"><span>goals</span>` +
    `<span>${escapar(otros.length + (activo ? 1 : 0))} (${escapar(contadorDeGoals(datos))} esperando a Pedro)</span></div>`;
  const lista = (activo ? tarjetaDeGoal(activo, golpesDelActivo, notas) : "") +
    (otros.length ? `<div class="subtitulo">los demas</div>` + otros.map(g => tarjetaDeGoal(g, [], notas)).join("") : "");
  return cabeza + lista;
}
