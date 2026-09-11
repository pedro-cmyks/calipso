/**
 * calipso/web/fabrica/canarios.js -- las marcas del canario, puras.
 *
 * Una senal, unos textos (el mismo patron que textoDeAbismo): a partir del
 * veredicto que manda el /ws/chat como `{type: "canario", anclaje,
 * degeneracion, ventana}` -o que viene en `meta.canarios` de un mensaje
 * guardado- devuelve las marcas chicas que van al pie del mensaje de
 * Calipso: [{texto, detalle}]. La PWA (index.html) y la fabrica (app.js)
 * pintan lo que sale de aca, asi que dicen lo mismo. Sin DOM, sin red.
 * Es informacion, no una compuerta: sin colores de alarma.
 */

const SENALES = {
  repeticion: "repeticion",
  alfabeto: "cambio de alfabeto",
  fuga_del_contrato: "fuga del contrato",
  fuga_de_reentrada: "fuga de reentrada",
  eco_de_episodio: "eco del molde",
  formato_no_pedido: "formato no pedido",
  cortada: "respuesta cortada",
  fuga_de_template: "fuga del template",
};

const RECORTES = {
  "historial:2": "el historial viejo",
  "historial:1": "el historial viejo",
  "recuerdo:1": "recuerdos",
  repo: "el brief del repo",
  web: "los resultados web",
  "bloque:1": "un bloque viejo del abismo",
};

/** "el historial viejo (4 mensajes), recuerdos (2), el brief del repo" */
export function textoDeRecorte(recorte) {
  const cuentas = new Map();
  for (const r of recorte || []) {
    const clave = RECORTES[r] || r;
    const n = r.startsWith("historial:") ? Number(r.split(":")[1]) : 1;
    cuentas.set(clave, (cuentas.get(clave) || 0) + n);
  }
  const partes = [];
  for (const [clave, n] of cuentas) {
    if (clave === "el historial viejo") partes.push(`${clave} (${n} mensajes)`);
    else if (clave === "recuerdos") partes.push(`${clave} (${n})`);
    else partes.push(clave);
  }
  return partes.join(", ");
}

export function textosDeCanario(veredicto) {
  const marcas = [];
  if (!veredicto || typeof veredicto !== "object") return marcas;
  if (veredicto.error) {
    marcas.push({texto: `canario: no corrio (${veredicto.error})`,
                 detalle: veredicto.detalle || ""});
    return marcas;
  }
  const a = veredicto.anclaje;
  const sin = (a && a.sin_anclaje) || [];
  if (a && a.aplica && sin.length) {
    marcas.push({texto: `sin verificar (${sin.length})`,
                 detalle: sin.map(s => (s.tipo === "accion" ? "accion: " :
                                        s.tipo === "recuerdo" ? "recuerdo: " : "") +
                                       (s.texto || "")).join("\n")});
  }
  for (const s of veredicto.degeneracion || []) {
    marcas.push({texto: `respuesta rara: ${SENALES[s.senal] || s.senal}`,
                 detalle: s.evidencia || ""});
  }
  const ventana = veredicto.ventana || [];
  const varias = ventana.length > 1;
  for (const f of ventana) {
    const pasada = varias ? ` (pasada ${f.pasada})` : "";
    if (f.no_cabe) {
      marcas.push({texto: `contexto: no cupo aun recortando${pasada}`,
                   detalle: `estimado ${f.estimado} tokens, techo ${f.num_ctx}`});
    } else if ((f.recorte || []).length) {
      marcas.push({texto: `contexto: se recorto ${textoDeRecorte(f.recorte)}${pasada}`,
                   detalle: `de ${f.estimado_sin_recorte} a ${f.estimado} tokens, techo ${f.num_ctx}`});
    }
    // solo en local: ahi el techo es CHAT_NUM_CTX y el evaluado lo cuenta
    // Ollama; en api/suscripcion truncado viene null (no se juzga)
    if (f.truncado === true && f.ruta === "local") {
      marcas.push({texto: `Ollama trunco la pasada ${f.pasada}`,
                   detalle: `estimado ${f.estimado}, evaluado ${f.evaluado}, techo ${f.num_ctx}`});
    }
  }
  return marcas;
}
