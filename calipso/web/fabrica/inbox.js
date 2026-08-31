// La lista unificada de las cuatro bandejas. Modulo PURO: lo que decide QUE
// se muestra vive aca; el DOM y los fetch viven en app.js.
//
// El inbox no sabe nada de ninguna bandeja. Dibuja los verbos que el item
// declara validos y nada mas: un boton que el origen no declaro es un boton
// que miente -- financiar sobre un vencido da 400, y `si_siempre` sobre una
// solicitud con siempre_pregunta tambien.
//
// Y uno que el origen SI declaro pero que nadie despacha miente igual: el
// despacho de data-inbox="responder" es del plan 2 (app.js no tiene
// listener para eso todavia), asi que estos botones salen `disabled` y con
// una nota que dice donde si se contesta hoy. Los `data-*` quedan intactos
// -el plan 2 los necesita tal cual estan.
import {escapar} from "./paneles.js";

const ETIQUETA_ORIGEN = {
  mesa: "la fabrica", permisos: "permiso",
  biblioteca: "memoria", cartas: "el cierre",
};

// Donde SI se contesta cada origen hoy, mientras el despacho desde el
// inbox no existe. Solo mesa y permisos tienen una sub-vista que ya
// responde de verdad; biblioteca y cartas no tienen ninguna todavia.
const SUBVISTA_QUE_YA_CONTESTA = {mesa: "Decidir", permisos: "Permisos"};

function notaDeDespacho(origen) {
  const alt = SUBVISTA_QUE_YA_CONTESTA[origen];
  return alt ? `todavia no se contesta desde aca: usa ${alt}`
             : "todavia no se contesta desde aca";
}

export function contadorDeInbox(datos) {
  return (datos?.items || []).filter(i => i.clase === "decision").length;
}

function fila(item, descriptores) {
  const desc = descriptores?.[item.origen];
  const validos = item.cuerpo?.verbos_validos || [];
  const verbosDelItem = (desc?.verbos || [])
    .filter(v => validos.includes(v.nombre));
  const botones = verbosDelItem
    .map(v => `<button data-inbox="responder" data-verbo="${escapar(v.nombre)}"` +
              ` data-id="${escapar(item.id)}"` +
              ` data-origen="${escapar(item.origen)}" disabled type="button">` +
              `${escapar(v.etiqueta)}</button>`)
    .join("");
  const nota = verbosDelItem.length
    ? `<div class="nota">${escapar(notaDeDespacho(item.origen))}</div>` : "";
  const cuenta = item.cuerpo?.cuenta_fija
    ? ` <span class="nota">paga el tesoro</span>` : "";
  return `<div class="fila" data-id="${escapar(item.id)}"` +
         ` data-origen="${escapar(item.origen)}">` +
         `<span class="etiqueta">${escapar(ETIQUETA_ORIGEN[item.origen] || item.origen)}</span> ` +
         `<span class="titulo">${escapar(item.titulo)}</span>${cuenta}` +
         `<div class="acciones">${botones}</div>${nota}</div>`;
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
