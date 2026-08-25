/**
 * calipso/web/fabrica/ciudad.js — El modelo, del lado del cliente.
 *
 * Trae la ciudad, la indexa y responde las dos preguntas que hace la
 * interfaz: que dice la ficha de este edificio, y que edificio hay debajo
 * de este punto de la pantalla. Nada de dibujo.
 */
import {medidas} from "./sprites.js";
import {aPantalla, escalaEntera} from "./camara.js";

// useGrouping "always" es obligatorio: sin el, esta locale devuelve "1148"
// en vez de "1.148" para los numeros de cuatro digitos.
const FORMATO = new Intl.NumberFormat("es", {maximumFractionDigits: 2,
                                             useGrouping: "always"});

export async function cargarCiudad(buscar = fetch) {
  const r = await buscar("/api/mapa/ciudad");
  if (!r.ok) throw new Error("no se pudo leer la ciudad: " + r.status);
  return await r.json();
}

export function indice(ciudad) {
  const porId = new Map();
  for (const e of ciudad.edificios) porId.set(e.id, e);
  const avisosPorId = new Map();
  for (const a of ciudad.avisos) {
    if (!a.sobre) continue;      // las cartas no cuelgan de ningun edificio
    avisosPorId.set(a.sobre, (avisosPorId.get(a.sobre) || 0) + 1);
  }
  return {porId, avisosPorId};
}

/** El libro guarda milimonedas; la gente lee monedas. */
export function monedas(mm) {
  return FORMATO.format(Math.round(mm) / 1000);
}

export function fichaDe(ciudad, id) {
  const e = ciudad.edificios.find(x => x.id === id);
  if (!e) return null;
  const efi = e.eficiencia_pormil;
  return {
    id: e.id, nombre: e.nombre, zona: e.zona, estado: e.estado,
    saldo: monedas(e.saldo_mm),
    gasto_ciclo: monedas(e.gasto_ciclo_mm),
    ventas_ventana: monedas(e.ventas_ventana_mm),
    // null no es cero: sin estado de suscripciones no hay eficiencia
    eficiencia: (efi === null || efi === undefined)
      ? "sin dato" : FORMATO.format(efi / 10) + "%",
    trabajos: e.trabajos.length,
    compuertas: e.compuertas,
  };
}

/** El sprite se apoya con su base en el punto del edificio. */
export function centroDe(edificio) {
  return {x: edificio.x, y: edificio.y};
}

/** De atras hacia adelante: el de mas abajo tapa al de mas arriba. */
export function ordenDePintado(edificios) {
  return [...edificios].sort((a, b) => (a.y - b.y) || (a.id < b.id ? -1 : 1));
}

export function enPunto(ciudad, cam, vista, px, py) {
  const esc = escalaEntera(cam);
  const orden = ordenDePintado(ciudad.edificios);
  for (let i = orden.length - 1; i >= 0; i--) {   // el de adelante primero
    const e = orden[i];
    const m = medidas(e);
    const p = aPantalla(cam, centroDe(e), vista);
    const x0 = p.x - (m.ancho * esc) / 2;
    const y0 = p.y - m.alto * esc;
    if (px >= x0 && px < x0 + m.ancho * esc &&
        py >= y0 && py < y0 + m.alto * esc) return e.id;
  }
  return null;
}
