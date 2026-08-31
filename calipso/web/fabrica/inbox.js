// La lista unificada de las cuatro bandejas. Modulo PURO: lo que decide QUE
// se muestra vive aca; el DOM y los fetch viven en app.js.
//
// El inbox no sabe nada de ninguna bandeja. Dibuja los verbos que el item
// declara validos y nada mas: un boton que el origen no declaro es un boton
// que miente -- financiar sobre un vencido da 400, y `si_siempre` sobre una
// solicitud con siempre_pregunta tambien.

export function escapar(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

const ETIQUETA_ORIGEN = {
  mesa: "la fabrica", permisos: "permiso",
  biblioteca: "memoria", cartas: "el cierre",
};

export function contadorDeInbox(datos) {
  return (datos?.items || []).filter(i => i.clase === "decision").length;
}

function fila(item, descriptores) {
  const desc = descriptores?.[item.origen];
  const validos = item.cuerpo?.verbos_validos || [];
  const botones = (desc?.verbos || [])
    .filter(v => validos.includes(v.nombre))
    .map(v => `<button data-inbox="responder" data-verbo="${escapar(v.nombre)}"` +
              ` data-id="${escapar(item.id)}"` +
              ` data-origen="${escapar(item.origen)}" type="button">` +
              `${escapar(v.etiqueta)}</button>`)
    .join("");
  const cuenta = item.cuerpo?.cuenta_fija
    ? ` <span class="nota">paga el tesoro</span>` : "";
  return `<div class="fila" data-id="${escapar(item.id)}"` +
         ` data-origen="${escapar(item.origen)}">` +
         `<span class="etiqueta">${escapar(ETIQUETA_ORIGEN[item.origen] || item.origen)}</span> ` +
         `<span class="titulo">${escapar(item.titulo)}</span>${cuenta}` +
         `<div class="acciones">${botones}</div></div>`;
}

export function textoDeInbox(datos) {
  const items = datos?.items || [];
  const fallaron = datos?.fallaron || [];
  const aviso = fallaron.length
    ? `<div class="nota">no se pudo leer: ${escapar(fallaron.join(", "))}</div>`
    : "";
  if (!items.length) {
    return aviso + `<div class="nota">Nada esperando.</div>`;
  }
  return aviso + items.map(i => fila(i, datos.descriptores)).join("");
}
