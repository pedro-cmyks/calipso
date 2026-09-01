#!/usr/bin/env python3
"""
experimentos/carta_vs_sin_carta.py -- la medicion que decide la Fase 2.

La hipotesis de todo este trabajo: un jefe con contexto propone mejor que uno
sin contexto. Es razonable y no esta probada, y probarla es barato -- el
modelo local es un POST a Ollama que no gasta cuota ni plata.

Este script arma situaciones sinteticas, renderiza el prompt CON y SIN los dos
bloques nuevos, se los manda al mismo modelo y muestra las dos decisiones al
lado. No decide nada solo: lo lee Pedro.

Cada situacion corre con DOS sesgos (50 y 75), no uno: con sesgo 50
("mantener el equilibrio") el jefe casi siempre contesta `nada` de los dos
lados, y un empate en `nada` no dice nada sobre la hipotesis -- hace falta
tambien un sesgo que empuje a `proponer` (75, "explorar cosas nuevas") para
que la mitad de las corridas caiga en el regimen donde comparar sirve de
algo.

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

# 50 es "mantener el equilibrio" y 75 cae en "explorar cosas nuevas"
# (`decision.prompt` traduce >=60 asi). Sin el 75 casi todo empata en `nada`
# de los dos lados y la comparacion no dice nada sobre la hipotesis.
SESGOS = (50, 75)


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


def resultado(p: str) -> tuple[str, str | None]:
    """La accion, y la CLAVE normalizada del objeto si la accion fue
    `proponer` Y la ficha se pudo leer (`None` en cualquier otro caso,
    incluida una ficha ilegible).

    La clave -- no el `sobre` crudo -- es lo que hay que comparar para saber
    si dos propuestas hablan del mismo objeto: es el mismo campo que
    `ficha.py` disena para eso ("explicable el dia que Pedro revoque"), y
    normaliza orden de palabras y articulos.
    """
    accion, _ref, _motivo = dec.parsear(p)
    if accion != "proponer":
        return accion, None
    f = ficha.parsear_ficha(p)
    return "proponer", (f["clave"] if f else None)


def legible(resultado_par: tuple[str, str | None]) -> bool:
    """Si esta rama produjo una ficha que se puede leer y comparar.

    `proponer` con clave `None` (ficha ilegible) NO es legible: hay una
    accion pero no un objeto contra el cual comparar, y el conteo final
    necesita distinguir eso de un objeto de verdad."""
    accion, clave = resultado_par
    return accion == "proponer" and clave is not None


def main() -> int:
    try:
        pensar("hola")
    except Exception as exc:
        print(f"No hay modelo local disponible: {exc}")
        print("Levanta Ollama con qwen2.5:7b y volve a correr.")
        return 1

    # Particion COMPLETA de las comparaciones -- las 12 caen en exactamente
    # una de las cinco categorias, ninguna se descarta. "ninguna legible"
    # incluye tanto un empate en `nada` como dos fichas ilegibles: en los
    # dos casos no hay un objeto real del que hablar, y separarlos en el
    # conteo (en vez de en la letra chica de un comentario) es lo que evita
    # que alguien lea "objetos DISTINTOS: 6" y crea que hubo seis
    # comparaciones reales cuando la mayoria eran basura de los dos lados.
    mismo_objeto = 0
    objetos_distintos = 0
    solo_con_legible = 0
    solo_sin_legible = 0
    ninguna_legible = 0
    legibles_con = 0
    legibles_sin = 0
    total_corridas = 0

    for nombre, s in situaciones():
        for sesgo in SESGOS:
            total_corridas += 1
            con = dec.prompt(s, sesgo, carta=CARTA, proyectos=PROYECTOS)
            sin = dec.prompt(s, sesgo, carta=SIN_CARTA, proyectos=[])
            crudo_con = pensar(con)
            crudo_sin = pensar(sin)

            print(f"\n=== {nombre} (sesgo {sesgo})")
            print(f"    prompt con carta: {len(con):5d} chars | "
                  f"sin carta: {len(sin):5d} chars")
            print(f"    la carta esta en el prompt: {CARTA['texto'][:20] in con}")
            print(f"    CON carta -> {decidir(crudo_con)}")
            print(f"    SIN carta -> {decidir(crudo_sin)}")

            res_con = resultado(crudo_con)
            res_sin = resultado(crudo_sin)
            legible_con = legible(res_con)
            legible_sin = legible(res_sin)
            if legible_con:
                legibles_con += 1
            if legible_sin:
                legibles_sin += 1

            if legible_con and legible_sin:
                if res_con[1] == res_sin[1]:
                    mismo_objeto += 1
                else:
                    objetos_distintos += 1
            elif legible_con:
                solo_con_legible += 1
            elif legible_sin:
                solo_sin_legible += 1
            else:
                ninguna_legible += 1

    print(f"\n=== conteo final ({total_corridas} comparaciones)")
    # El numero que no depende de como se definan las categorias de abajo:
    # cuantas veces cada lado, solo, produjo algo que se pudiera leer.
    print(f"    fichas legibles: CON carta {legibles_con}/{total_corridas} "
          f"| SIN carta {legibles_sin}/{total_corridas}")
    print(f"    las dos legibles, MISMO objeto: {mismo_objeto}")
    print(f"    las dos legibles, objetos DISTINTOS: {objetos_distintos}")
    print(f"    SOLO la rama CON carta es legible: {solo_con_legible}")
    print(f"    SOLO la rama SIN carta es legible: {solo_sin_legible}")
    print(f"    NINGUNA legible (empate en nada, o ficha ilegible de un "
          f"lado o de los dos): {ninguna_legible}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
