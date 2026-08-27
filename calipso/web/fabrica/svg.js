/**
 * calipso/web/fabrica/svg.js — Sanear y ubicar el SVG que trae el modelo.
 *
 * El SVG que devuelve un modelo es texto no confiable: puede traer
 * <script>, atributos on* (onload, onerror...), <foreignObject> con HTML
 * adentro, o <use href="..."> apuntando a otro host. Esta capa es higiene,
 * NO la frontera de seguridad real -esa la pone el iframe sandbox="" sin
 * allow-scripts ni allow-same-origin que arma app.js al insertarlo (ver el
 * comentario ahi: ese sandbox bloquea TODA ejecucion de script pase lo que
 * pase aca). Lo que este archivo hace es lo que el sandbox NO cubre por si
 * solo: que no salga ni una sola request de red a otro host (un <use>
 * remoto, una <image> remota) y que el marcado quede prolijo para mostrar.
 *
 * Es texto puro: sin DOM, sin jsdom (no hay y no lo va a haber en este
 * repo), asi que se testea con node --test como el resto de fabrica/.
 */

// Etiquetas sin ninguna razon para estar en un SVG que Calipso va a
// mostrar. Se sacan aunque el sandbox ya las neutralice: un parser HTML
// mas permisivo que el de SVG podria seguir interpretandolas como HTML
// real si en algun momento el marcado termina insertado de otra forma.
const ETIQUETAS_PROHIBIDAS = ["script", "foreignObject", "iframe", "object",
                               "embed", "link", "meta", "base"];

/** True si `texto` (recortado) es, de punta a punta, un documento <svg>. */
export function pareceSvg(texto) {
  const t = String(texto || "").trim();
  if (!t) return false;
  const sinPreambulo = t
    .replace(/^<\?xml[^>]*\?>\s*/i, "")
    .replace(/^<!DOCTYPE[^>]*>\s*/i, "");
  return /^<svg[\s\/>]/i.test(sinPreambulo) &&
         /<\/svg\s*>\s*$/i.test(sinPreambulo);
}

/**
 * Busca un SVG dentro de la respuesta del modelo: primero un bloque de
 * codigo con etiqueta ```svg, despues cualquier bloque de codigo cuyo
 * contenido sea un SVG completo, y por ultimo si el mensaje entero -sin
 * prosa alrededor- es el SVG. Devuelve el texto del SVG sin fences, o null.
 */
export function extraerSvgDelTexto(texto) {
  const cuerpo = String(texto || "");
  const conEtiqueta = /```svg\s*\n([\s\S]*?)```/i.exec(cuerpo);
  if (conEtiqueta && pareceSvg(conEtiqueta[1])) return conEtiqueta[1].trim();
  const generico = /```[a-zA-Z0-9]*\s*\n([\s\S]*?)```/g;
  let m;
  while ((m = generico.exec(cuerpo))) {
    if (pareceSvg(m[1])) return m[1].trim();
  }
  if (pareceSvg(cuerpo)) return cuerpo.trim();
  return null;
}

/**
 * Devuelve una version saneada de `textoCrudo`: sin <script>, sin
 * atributos on*, sin <foreignObject> ni otras etiquetas ajenas a SVG, y
 * sin href/xlink:href que no sea una referencia local (#algo) -asi que un
 * <use> o una <image> remotos pierden el atributo, y con el la request.
 */
export function sanearSvg(textoCrudo) {
  let s = String(textoCrudo || "")
    .replace(/^<\?xml[^>]*\?>\s*/i, "")
    .replace(/^<!DOCTYPE[^>]*>\s*/i, "");

  // los comentarios se sacan primero: nada de lo que venga adentro
  // sobrevive a los pasos siguientes escondido en uno.
  s = s.replace(/<!--[\s\S]*?-->/g, "");

  // bloques completos (apertura + contenido + cierre) de las etiquetas
  // prohibidas, y despues cualquier apertura o cierre suelto que haya
  // quedado (por ejemplo si el modelo mando un <script> sin cerrar).
  for (const nombre of ETIQUETAS_PROHIBIDAS) {
    const conCierre = new RegExp(`<${nombre}\\b[^>]*>[\\s\\S]*?<\\/${nombre}\\s*>`, "gi");
    s = s.replace(conCierre, "");
  }
  for (const nombre of ETIQUETAS_PROHIBIDAS) {
    const suelta = new RegExp(`<\\/?${nombre}\\b[^>]*>`, "gi");
    s = s.replace(suelta, "");
  }

  // atributos on-evento (onload=, onerror=, onclick=...) con comilla
  // doble, simple o sin comillas.
  s = s.replace(/\son\w+\s*=\s*"(?:[^"\\]|\\.)*"/gi, "");
  s = s.replace(/\son\w+\s*=\s*'(?:[^'\\]|\\.)*'/gi, "");
  s = s.replace(/\son\w+\s*=\s*[^\s"'>]+/gi, "");

  // href / xlink:href: solo sobreviven las referencias locales (#algo).
  // Esto es lo que le saca la salida de red a un <use>, <image> o <a>
  // apuntando afuera -y de paso a cualquier esquema javascript:/data:
  // metido ahi, porque deja de importar cual sea: el atributo entero
  // desaparece si no arranca con #.
  s = s.replace(/\s(?:xlink:)?href\s*=\s*"(?!\s*#)[^"]*"/gi, "");
  s = s.replace(/\s(?:xlink:)?href\s*=\s*'(?!\s*#)[^']*'/gi, "");
  s = s.replace(/\s(?:xlink:)?href\s*=\s*(?!["'#])[^\s>]+/gi, "");

  // esquemas ejecutables colados en cualquier otro atributo (por si
  // acaso: href/xlink:href ya quedaron cubiertos arriba).
  s = s.replace(/(\s[\w:-]+\s*=\s*)"[^"]*(?:javascript|vbscript):[^"]*"/gi, '$1""');
  s = s.replace(/(\s[\w:-]+\s*=\s*)'[^']*(?:javascript|vbscript):[^']*'/gi, "$1''");

  return s.trim();
}

/** Ancho/alto del SVG, de sus atributos o -si faltan- de su viewBox. */
export function dimensionesSvg(svgTexto) {
  const tag = /<svg\b[^>]*>/i.exec(String(svgTexto || ""));
  if (!tag) return null;
  const leer = nombre => {
    const m = new RegExp(`\\b${nombre}\\s*=\\s*["']\\s*([\\d.]+)\\s*(%?)`, "i").exec(tag[0]);
    if (!m || m[2] === "%") return null;
    const v = parseFloat(m[1]);
    return v > 0 ? v : null;
  };
  let ancho = leer("width");
  let alto = leer("height");
  if (!ancho || !alto) {
    const vb = /viewBox\s*=\s*["']([^"']+)["']/i.exec(tag[0]);
    if (vb) {
      const partes = vb[1].trim().split(/[\s,]+/).map(Number);
      if (partes.length === 4 && partes[2] > 0 && partes[3] > 0) {
        ancho = partes[2];
        alto = partes[3];
      }
    }
  }
  if (!ancho || !alto) return null;
  return {ancho, alto};
}
