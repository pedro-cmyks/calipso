/**
 * calipso/web/fabrica/carga.js -- la marca de la carga, pura.
 *
 * Una senal, unos textos (el mismo patron que canarios.js): a partir de la
 * marca que manda el /ws/chat como `{type: "carga", nivel, mem_disponible_mb,
 * motivo, ruta, gesto, aviso}` -o que viene en `meta.carga` de un mensaje
 * guardado- devuelve la marca chica que va como CABECERA del mensaje de
 * Calipso: [{texto, detalle}]. El texto lo compone el server (carga.AVISOS,
 * spec 3.2: "maquina cargada (N MB libres): contesto por X" / "...: <gesto>
 * es local, puede tardar o fallar"); aca solo se muestra, y el detalle son
 * los numeros. La PWA (index.html) y la fabrica (app.js) pintan lo que sale
 * de aca, asi que dicen lo mismo. Sin DOM, sin red. Es informacion, no una
 * compuerta: sin colores de alarma.
 */

export function textosDeCarga(marca) {
  if (!marca || typeof marca !== "object") return [];
  const nivel = marca.nivel ? String(marca.nivel) : "";
  const mb = (marca.mem_disponible_mb === null || marca.mem_disponible_mb === undefined)
    ? null : Number(marca.mem_disponible_mb);
  const texto = marca.aviso ||
    (nivel ? `maquina ${nivel}` + (mb !== null ? ` (${mb} MB libres)` : "") : "");
  if (!texto) return [];
  const partes = [];
  if (nivel) partes.push(`nivel ${nivel}`);
  if (mb !== null) partes.push(`${mb} MB libres`);
  if (marca.motivo) partes.push(`motivo: ${marca.motivo}`);
  if (marca.ruta) partes.push(`ruta: ${marca.ruta}`);
  if (marca.gesto) partes.push(`gesto: ${marca.gesto}`);
  return [{texto, detalle: partes.join(", ")}];
}
