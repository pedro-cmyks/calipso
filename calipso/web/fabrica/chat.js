/**
 * calipso/web/fabrica/chat.js — La conversacion con Calipso.
 *
 * Habla con el /ws/chat que ya existe, sin cambiarle nada al servidor.
 * El reductor de eventos es puro y no muta lo que recibe: por eso se
 * puede testear el protocolo entero sin abrir un socket.
 */
import {crearSocketQueReconecta} from "./socket.js";

export function estadoInicial() {
  return {turnos: [], pensando: false, chatId: null, ruta: null,
          modelo: null, costo_usd: 0, tokens: 0, costo_mm: 0, cuenta: null,
          conectado: false, epoca: 0, streamViejo: false};
}

export function paquete(texto, chatId, departamento = null) {
  const p = {text: texto, chat_id: chatId};
  // el departamento va SOLO si hay uno: mandar null en cada turno haria que
  // el server tenga que distinguir "sin foco" de "foco borrado"
  if (departamento) p.departamento = departamento;
  return p;
}

export function turnosDeHistorial(mensajes) {
  return (mensajes || []).map(m => ({
    quien: m.role === "user" ? "pedro" : "calipso",
    texto: m.text || "", abierto: false}));
}

// Eventos del turno que `cargar()` deja en vuelo: el socket es uno solo y
// persistente, asi que el resto del stream del chat anterior sigue llegando
// despues de cargar otro. Un "chat" (accion "updated") es parte de esto: si
// se aplicara, el chatId volveria al chat viejo y el proximo mensaje de
// Pedro se guardaria en la conversacion equivocada. Y un "error" no es solo
// el caso de la conexion cortada: el servidor lo manda tambien en medio de
// un turno normal (ruta local sin fallback) y sigue con cost/done despues.
const EVENTOS_DEL_STREAM = new Set(["chunk", "done", "meta", "cost", "chat",
                                     "error"]);

export function aplicarEvento(estado, ev) {
  const e = {...estado, turnos: [...estado.turnos]};
  // Mientras el stream viejo este marcado, se descarta entero: no se pega
  // sobre el historial recien cargado. La marca se levanta con el proximo
  // "thinking", que solo llega cuando arranca un turno nuevo de verdad (o
  // sea, cuando Pedro le escribe al chat que acaba de abrir).
  if (e.streamViejo) {
    if (ev.type === "thinking") {
      e.streamViejo = false;
    } else if (EVENTOS_DEL_STREAM.has(ev.type)) {
      return e;
    }
  }
  switch (ev.type) {
    case "thinking":
      e.pensando = true;
      break;
    case "chunk": {
      const ultimo = e.turnos.at(-1);
      if (e.pensando && ultimo && ultimo.quien === "calipso" && ultimo.abierto) {
        e.turnos[e.turnos.length - 1] = {...ultimo,
                                         texto: ultimo.texto + (ev.text || "")};
      } else {
        e.turnos.push({quien: "calipso", texto: ev.text || "", abierto: true});
      }
      break;
    }
    case "done": {
      e.pensando = false;
      const ultimo = e.turnos.at(-1);
      if (ultimo && ultimo.abierto) {
        e.turnos[e.turnos.length - 1] = {...ultimo, abierto: false};
      }
      break;
    }
    case "meta":
      if (ev.route) e.ruta = ev.route;
      if (ev.model) e.modelo = ev.model;
      break;
    case "cost":
      // campos reales del /ws/chat: cost_usd y tokens (server.py), mas la
      // cuenta que pago y las milimonedas que se le cobraron
      e.costo_usd = e.costo_usd + (ev.cost_usd || 0);
      e.tokens = e.tokens + (ev.tokens || 0);
      e.costo_mm = e.costo_mm + (ev.mm || 0);
      if (ev.cuenta && ev.cuenta !== "personal") e.cuenta = ev.cuenta;
      break;
    case "error":
      e.pensando = false;
      e.turnos.push({quien: "error", texto: "error: " + (ev.text || ""),
                     abierto: false});
      break;
    case "chat":
      if (ev.chat && ev.chat.id) e.chatId = ev.chat.id;
      break;
    default:
      break;      // el /ws/chat manda mas cosas de las que este panel usa
  }
  return e;
}

// El `WebSocket` real solo existe en el navegador; el parametro deja
// pasar un doble en los tests sin abrir ninguna conexion de verdad.
export function crearChat(alCambiar, ConstructorWS = WebSocket) {
  let estado = estadoInicial();
  // El estado inicial dice "sin conexion" y hay que PINTARLO. Sin este
  // aviso, hasta el primer evento del socket la interfaz se ve conectada, y
  // si el handshake se cuelga sin llegar a cerrarse miente indefinidamente.
  // Va antes de abrir el socket para que un "open" no se lo pise.
  alCambiar(estado);

  const conexion = crearSocketQueReconecta("/ws/chat", {
    alAbrir() {
      estado = {...estado, conectado: true};
      alCambiar(estado);
    },
    alMensaje(dato) {
      estado = aplicarEvento(estado, dato);
      alCambiar(estado);
    },
    // si se cae, se reintenta: el mapa sigue andando mientras tanto. La
    // bandera se apaga antes de reintentar para que la interfaz sepa que
    // se cayo, no solo cuando vuelva a levantarse.
    alCerrar() {
      estado = {...estado, conectado: false};
      alCambiar(estado);
    },
  }, ConstructorWS);

  return {
    estado: () => estado,
    // Devuelve si el mensaje salio de verdad. Mientras el socket conecta
    // o reconecta no hay adonde mandarlo, y quien llama tiene que
    // enterarse en vez de que el texto desaparezca en silencio.
    enviar(texto, departamento = null) {
      const ws = conexion.socket();
      if (!texto.trim() || !ws || ws.readyState !== ConstructorWS.OPEN) {
        return false;
      }
      estado = {...estado,
                turnos: [...estado.turnos,
                         {quien: "pedro", texto, abierto: false}]};
      alCambiar(estado);
      ws.send(JSON.stringify(paquete(texto, estado.chatId, departamento)));
      return true;
    },
    /** Otro chat: los turnos se reemplazan enteros y la epoca sube para que
     *  quien pinta sepa que tiene que rehacer los nodos, no agregarles.
     *  El turno viejo puede seguir en vuelo -el socket es uno solo- asi que
     *  se marca para que el reductor descarte lo que quede de su stream, y
     *  se resetea lo que ese turno traia puesto (ruta, modelo, costo). */
    cargar(chat) {
      estado = {...estado, chatId: chat.id,
                turnos: turnosDeHistorial(chat.messages),
                epoca: estado.epoca + 1,
                pensando: false, ruta: null, modelo: null, costo_usd: 0,
                tokens: 0, costo_mm: 0, cuenta: null, streamViejo: true};
      alCambiar(estado);
    },
  };
}
