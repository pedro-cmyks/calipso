/**
 * calipso/web/fabrica/chat.js — La conversacion con Calipso.
 *
 * Habla con el /ws/chat que ya existe, sin cambiarle nada al servidor.
 * El reductor de eventos es puro y no muta lo que recibe: por eso se
 * puede testear el protocolo entero sin abrir un socket.
 */

export function estadoInicial() {
  return {turnos: [], pensando: false, chatId: null, ruta: null,
          modelo: null, costo_usd: 0, tokens: 0};
}

export function paquete(texto, chatId) {
  return {text: texto, chat_id: chatId};
}

export function aplicarEvento(estado, ev) {
  const e = {...estado, turnos: [...estado.turnos]};
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
      // campos reales del /ws/chat: cost_usd y tokens (server.py:2423)
      e.costo_usd = e.costo_usd + (ev.cost_usd || 0);
      e.tokens = e.tokens + (ev.tokens || 0);
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

export function crearChat(alCambiar) {
  let estado = estadoInicial();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let ws = null;

  function conectar() {
    ws = new WebSocket(`${proto}://${location.host}/ws/chat`);
    ws.addEventListener("message", ev => {
      let dato;
      try { dato = JSON.parse(ev.data); } catch { return; }
      estado = aplicarEvento(estado, dato);
      alCambiar(estado);
    });
    // si se cae, se reintenta: el mapa sigue andando mientras tanto
    ws.addEventListener("close", () => setTimeout(conectar, 2000));
  }
  conectar();

  return {
    estado: () => estado,
    enviar(texto) {
      if (!texto.trim() || !ws || ws.readyState !== WebSocket.OPEN) return;
      estado = {...estado,
                turnos: [...estado.turnos,
                         {quien: "pedro", texto, abierto: false}]};
      alCambiar(estado);
      ws.send(JSON.stringify(paquete(texto, estado.chatId)));
    },
  };
}
