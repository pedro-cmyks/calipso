"""La capa de lenguaje humano del juez de privacidad: una llamada al modelo
local (Ollama) que marca datos sensibles que ningun regex agarra (nombres,
direcciones, telefonos, condiciones de salud, DNI en contexto).

Corre LOCAL: el texto a juzgar nunca sale de la maquina. Temperatura 0 (fiabilidad
sobre creatividad) y `format: json` para una salida parseable. Si Ollama no
responde o devuelve basura, `ok=False`: sin poder verificar, el llamador falla
cerrado -- no se manda nada a la nube.
"""
import json

import dispatch

_TIPOS = ("identidad", "credencial", "salud", "ubicacion", "financiero", "contacto")

# El prompt validado en experimentos/juez_privacidad.py (seccion 10 del spec).
JUEZ_SISTEMA = """\
Sos un filtro de privacidad local. Recibis el mensaje de un usuario y marcas
que trozos contienen datos personales sensibles, para taparlos antes de que el
mensaje salga de la maquina. Trabajas local justamente para que estos datos no
salgan.

Marca un trozo si es alguno de estos tipos:
- identidad: DNI, cedula, pasaporte, numero de identificacion, nombre completo
  de una persona real junto a otro dato que la identifique.
- credencial: contrasena, clave, token, API key, clave SSH/privada, secreto,
  cadena de conexion con clave. Estos NUNCA pueden salir.
- salud: diagnostico, enfermedad, medicamento recetado, resultado de estudio,
  condicion fisica o mental, discapacidad, embarazo.
- ubicacion: direccion de domicilio, coordenadas, un lugar preciso donde vive
  o esta la persona.
- financiero: numero de tarjeta, cuenta bancaria, CBU/IBAN, salario, ingreso.
- contacto: telefono, email, usuario de contacto directo.

Reglas:
- Copia el trozo TAL CUAL aparece en el mensaje, sin reformular ni recortar de
  mas. Debe poder encontrarse por busqueda exacta en el texto.
- Ante la duda entre marcar o no una credencial o un dato de salud, MARCALO.
  Dejar pasar una clave o una condicion de salud es el peor error.
- No marques palabras genericas que no son un dato concreto ("mi contrasena es
  segura" no tiene contrasena; "la clave del exito" no es una credencial).
- Si no hay ningun dato sensible, devolve la lista vacia.

Devolve SOLO un JSON con esta forma exacta:
{"tramos": [{"texto": "<el trozo literal>", "tipo": "<uno de los seis>"}]}

Ejemplo de formato (solo para la forma, no para que categorias buscar):
Mensaje: "escribime al 11-2233-4455 cuando puedas"
Salida: {"tramos": [{"texto": "11-2233-4455", "tipo": "contacto"}]}
"""


def juzgar_llm(texto: str, base_url: str | None = None,
               modelo: str | None = None) -> dict:
    """Marca los tramos sensibles de `texto` con el modelo local. Devuelve
    {"tramos": [...], "ok": bool}. ok=False si el modelo no responde o su
    salida no parsea -- el llamador lo trata como fallo cerrado."""
    cfg = dispatch.CONFIG["local"]
    payload = {
        "model": modelo or cfg["model"],
        "system": JUEZ_SISTEMA,
        "prompt": texto,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_ctx": 4096},
    }
    try:
        data = dispatch._http_post_json(base_url or cfg["base_url"], payload)
        obj = json.loads(data.get("response", ""))
        crudos = obj.get("tramos", []) if isinstance(obj, dict) else []
        tramos = [{"texto": str(t["texto"]), "tipo": str(t.get("tipo", ""))}
                  for t in crudos
                  if isinstance(t, dict) and str(t.get("texto", "")).strip()]
    except Exception:
        # Fallo cerrado ante CUALQUIER respuesta no confiable, no solo
        # OSError/ValueError/JSONDecodeError: tambien una forma inesperada
        # como `data` no-dict (AttributeError en .get) o `"tramos": null`
        # (json.loads lo vuelve None, y "for t in None" es TypeError). El
        # parseo entero vive adentro del try justamente para que cualquier
        # tropiezo ahi caiga en el mismo ok=False -- la funcion no tiene
        # otro efecto que su valor de retorno, asi que atrapar amplio no
        # oculta nada, es el contrato del modulo.
        return {"tramos": [], "ok": False}
    return {"tramos": tramos, "ok": True}
