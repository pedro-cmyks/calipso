#!/usr/bin/env python3
"""
experimentos/carta_vs_sin_carta.py -- la medicion que decide la Fase 2.

La hipotesis de todo este trabajo: un jefe con contexto propone mejor que uno
sin contexto. Es razonable y no esta probada, y probarla es barato -- el
modelo local es un POST a Ollama que no gasta cuota ni plata.

Este script arma situaciones sinteticas, renderiza el prompt CON y SIN los dos
bloques nuevos, se los manda al mismo modelo y muestra las dos decisiones al
lado. No decide nada solo: lo lee Pedro.

CALIPSO_HOME va a un temporal ANTES de importar el paquete: importar calipso
suelto escribe en el home real.
"""
import os
import pathlib
import sys
import tempfile

# ANTES de importar calipso: el paquete escribe en el home real.
os.environ["CALIPSO_HOME"] = tempfile.mkdtemp(prefix="carta-exp-")

# Este script vive en experimentos/, no en la raiz: sin esto, `import
# dispatch` y `import calipso` fallan con ModuleNotFoundError apenas se corre
# como archivo (el interprete solo pone en sys.path el directorio del
# script). pytest resuelve esto solo porque arranca desde la raiz; un script
# suelto tiene que decirlo a mano.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import dispatch                                          # noqa: E402
from calipso.plantel import decision as dec              # noqa: E402
from calipso.plantel import ficha                        # noqa: E402

CARTA = {"estado": "escrita", "texto":
         "El taller hace I+D para los proyectos de Pedro. Mira prototipos, "
         "bancos de prueba y hardware. No le toca mejorar a Calipso mismo."}

PROYECTOS = [{"nombre": "calipso-lector",
              "texto": "convertir el Musnap en la pantalla de Calipso; el "
                       "plugin arranca y falta el banco de pruebas",
              "fuente": "pedro"}]

SIN_CARTA = {"estado": "ausente", "texto": ""}


def _base() -> dict:
    """La misma `_situacion_minima()` de `test_plantel_decision.py`: lo
    minimo que `prompt` indexa con corchetes, para que cada situacion
    agregue solo lo que la distingue de las otras cinco."""
    return {"nombre": "taller", "disponible_mm": 400_000, "saldo_mm": 400_000,
            "presupuesto_semanal_mm": 25_000, "salidas_semana_mm": 7_000,
            "compuertas_pendientes": 2, "trabajos": [],
            "propuestas_ajenas": [], "capacidad": None}


def situaciones() -> list[tuple[str, dict]]:
    """Media docena de fotos distintas del mismo departamento.

    Se arman a mano y no salen del disco: el experimento no necesita
    economia sembrada, y asi cada corrida compara exactamente lo mismo.
    """
    sin_nada = _base()

    con_trabajo_vivo = _base()
    con_trabajo_vivo["trabajos"] = [
        {"id": "p1", "titulo": "el banco de pruebas del lector",
         "gastado_mm": 3_000, "presupuesto_mm": 12_000}]

    con_propuestas_propias = _base()
    con_propuestas_propias["propuestas_propias"] = [
        {"id": "p2", "titulo": "vieja", "presupuesto_mm": 0,
         "forma": {"sobre": "el radar de precios", "clave": "radar+precios",
                   "promete": "medir", "tarda": "medio"}},
        {"id": "p3", "titulo": "vieja", "presupuesto_mm": 0,
         "forma": {"sobre": "el banco del taller", "clave": "banco+taller",
                   "promete": "construir", "tarda": "largo"}},
    ]

    con_descartada = _base()
    con_descartada["descartadas_semana"] = [
        {"forma": {"sobre": "una encuesta de precios de la competencia",
                   "clave": "competencia+encuesta+precios",
                   "promete": "medir", "tarda": "corto"}}]

    bandeja_llena = _base()
    bandeja_llena["propuestas_propias"] = [
        {"id": "p4", "titulo": "vieja", "presupuesto_mm": 0,
         "forma": {"sobre": "el radar de precios", "clave": "radar+precios",
                   "promete": "medir", "tarda": "medio"}},
        {"id": "p5", "titulo": "vieja", "presupuesto_mm": 0,
         "forma": {"sobre": "el banco del taller", "clave": "banco+taller",
                   "promete": "construir", "tarda": "largo"}},
        {"id": "p6", "titulo": "vieja", "presupuesto_mm": 0,
         "forma": {"sobre": "un monitor de stock", "clave": "monitor+stock",
                   "promete": "construir", "tarda": "corto"}},
    ]

    con_catalogo = _base()
    con_catalogo["catalogo"] = ["el radar de precios", "el banco del lector",
                                "un monitor de stock"]

    return [
        ("sin nada", sin_nada),
        ("con un trabajo vivo", con_trabajo_vivo),
        ("con dos propuestas propias en pie", con_propuestas_propias),
        ("con una descartada de esta semana", con_descartada),
        ("con la bandeja llena (tres propuestas)", bandeja_llena),
        ("con el catalogo poblado", con_catalogo),
    ]


def pensar(prompt: str) -> str:
    """El mismo camino que `_pensar_local`, con el mismo `num_ctx`."""
    cfg = dispatch.CONFIG["local"]
    data = dispatch._http_post_json(
        cfg["base_url"],
        {"model": cfg["model"], "prompt": prompt, "stream": False,
         "options": {"temperature": 0, "num_ctx": 8192}})
    return (data or {}).get("response", "")


def decidir(p: str) -> str:
    """De la respuesta cruda a una linea legible: la accion, y la ficha si
    parseo."""
    accion, _ref, _motivo = dec.parsear(p)
    if accion != "proponer":
        return accion
    f = ficha.parsear_ficha(p)
    if f is None:
        return "proponer (ficha ilegible)"
    return f"proponer -> {f['promete']}: {f['sobre']} ({f['tarda']})"


def main() -> int:
    try:
        pensar("hola")
    except Exception as exc:
        print(f"No hay modelo local disponible: {exc}")
        print("Levanta Ollama con qwen2.5:7b y volve a correr.")
        return 1

    for nombre, s in situaciones():
        con = dec.prompt(s, 50, carta=CARTA, proyectos=PROYECTOS)
        sin = dec.prompt(s, 50, carta=SIN_CARTA, proyectos=[])
        print(f"\n=== {nombre}")
        print(f"    prompt con carta: {len(con):5d} chars | "
              f"sin carta: {len(sin):5d} chars")
        print(f"    la carta esta en el prompt: {CARTA['texto'][:20] in con}")
        print(f"    CON carta -> {decidir(pensar(con))}")
        print(f"    SIN carta -> {decidir(pensar(sin))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
