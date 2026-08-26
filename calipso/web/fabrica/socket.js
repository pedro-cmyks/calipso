/**
 * calipso/web/fabrica/socket.js — El ciclo de vida de un WebSocket que
 * reconecta solo.
 *
 * `chat.js` habla con /ws/chat y `pulso.js` con /ws/mapa, pero abrir,
 * escuchar y reconectar es identico en los dos: ese pedazo comun vive aca
 * una sola vez. Quien llama solo aporta que hacer con la apertura, con un
 * mensaje que llega y con el cierre; la ruta y el backoff son de aca.
 */

export function crearSocketQueReconecta(ruta, {alAbrir, alMensaje, alCerrar},
                                        ConstructorWS = WebSocket) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let ws = null;

  function conectar() {
    try {
      ws = new ConstructorWS(`${proto}://${location.host}${ruta}`);
    } catch (e) {
      // el constructor puede tirar sincronicamente (URL invalida, politica
      // de seguridad del navegador). Adentro del setTimeout del reintento no
      // hay nadie que agarre esa excepcion: escapa del timer y la cadena de
      // reconexion muere para siempre, en silencio.
      ws = null;
      alCerrar();
      setTimeout(conectar, 2000);
      return;
    }
    ws.addEventListener("open", () => alAbrir());
    ws.addEventListener("message", ev => {
      let dato;
      try { dato = JSON.parse(ev.data); } catch { return; }
      alMensaje(dato);
    });
    // si se cae, se reintenta. Que hacer mientras tanto lo decide quien
    // llama: el chat lo dice sin vueltas, el mapa sigue mostrando la foto.
    ws.addEventListener("close", () => {
      alCerrar();
      setTimeout(conectar, 2000);
    });
  }
  conectar();

  // Solo el chat necesita alcanzar el socket vivo (para saber si esta
  // OPEN antes de mandar); el pulso no manda nada y no lo toca.
  return {socket: () => ws};
}
