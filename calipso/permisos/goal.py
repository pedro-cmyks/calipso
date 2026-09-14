"""
calipso/permisos/goal.py -- la familia `goal` del motor de permisos (spec
goals 2026-09-13, seccion 8, ruling 15.11): el goal es el PRIMER productor
del camino desatendido (estaciona, pared de corrida, retoma).

Operaciones y formas CONCRETAS (nunca clases abiertas):

  dale        {"goal": id}                       la propuesta: si arranca, no cancela
  cerrar      {"goal": id, "n": n}               el checkpoint cumplido: si = complete
  pregunta    {"goal": id, "n": n, "pregunta"}   la pregunta del veredicto
  raiz_nueva  {"goal": id, "raiz": ruta}         una raiz fuera del repo
  retomar     {"goal": id, "motivo", "vez": k}   un waiting sin nada que sondear (tope, cuota,
                                                 no convergencia, parado, server reiniciado):
                                                 si = seguir (tope ampliado si era tope), no = cancelar
  compuerta   {"goal": id, "familia", "forma"}   una familia de la tabla (instalar_home, ...)
  comando     {"goal": id, "argv": [...], "comando"}  lo que decide el hook, por el motor
  archivo     {"goal": id, "tool", "ruta"}       idem para las herramientas de archivo

Las cinco primeras preguntan SIEMPRE (siempre_pregunta): un "si para
siempre" sobre "arrancar cualquier goal" no existe. `compuerta` va por la
tabla del goal (`detalle["niveles"]`): directo/pregunta/nunca. `comando` y
`archivo` reusan las MISMAS funciones puras del hook (goals_hook.familia_de_
argv, decidir_archivo) sobre `detalle["compuertas"]` (el JSON del goal):
asi el motor y el hook nunca se contradicen; lo que el hook no sabe parsear
cae en pregunta (no en directo). Lo NUNCA se mapea por NOMBRE (la etiqueta
"NUNCA" y las familias de goals_hook.FAMILIAS_NUNCA), antes de mirar la
tabla: un compuertas.json relajado no lo abre, ni aca ni en el hook.

Nada de esta familia se concede para siempre (`cubre_goal` es False): la
preautorizacion que Pedro da a un goal vive en `compuertas.json`
(`preautorizadas`) y expira con el goal.
"""
from __future__ import annotations

from calipso import goals_hook
from .acciones import (Accion, Veredicto, NIVEL_DIRECTO, NIVEL_NUNCA, NIVEL_PREGUNTA,
                       registrar_clasificador, registrar_cobertura)

FAMILIA = "goal"
OPERACIONES = ("dale", "cerrar", "pregunta", "compuerta", "raiz_nueva", "retomar", "comando", "archivo")
# La tabla de Pedro (goals.COMPUERTAS), copiada para no importar `goals`
# desde el paquete permisos (que tiene que poder negar aunque el resto del
# repo no importe); test_goals_permisos la compara con la de goals.py.
_NIVELES_DEFECTO = {
    "repo": "directo", "web": "directo", "instalar_en_goal": "directo", "raices": "directo",
    "merge": "pregunta", "push": "pregunta", "borrar_fuera": "pregunta", "raiz_nueva": "pregunta",
    "instalar_home": "pregunta", "instalar_sistema": "pregunta",
    "gastar": "nunca", "publicar": "nunca", "correo": "nunca", "datos_de_pedro": "nunca",
    "rpm_ostree_rebase": "nunca", "flatpak_remote_delete": "nunca",
}
_NIVEL_DE_TABLA = {"directo": NIVEL_DIRECTO, "pregunta": NIVEL_PREGUNTA, "nunca": NIVEL_NUNCA}


def _es_nunca(familia: str | None) -> bool:
    return familia == "NUNCA" or familia in goals_hook.FAMILIAS_NUNCA


def _nivel_de_familia(familia: str | None, niveles: dict) -> str:
    if familia is None:
        return NIVEL_DIRECTO
    if _es_nunca(familia):
        return NIVEL_NUNCA
    if familia == "DENEGAR":
        return NIVEL_PREGUNTA
    return _NIVEL_DE_TABLA.get((niveles or {}).get(familia), NIVEL_PREGUNTA)


def _preautorizada(familia: str | None, forma: dict | None, compuertas: dict) -> bool:
    """La forma EXACTA que Pedro aprobo para este goal (compuertas.json,
    `preautorizadas`): misma familia y misma forma, nunca por categoria."""
    if not familia or _es_nunca(familia) or familia == "DENEGAR":
        return False
    return any(p.get("familia") == familia and p.get("forma") == forma
               for p in (compuertas or {}).get("preautorizadas") or [])


def nivel_de_comando(argv: list[str], compuertas: dict) -> tuple[str, str | None, dict | None]:
    """(nivel, familia, forma) de un argv por las reglas del hook y la
    tabla del goal; con `preautorizadas` que tapen la forma, directo."""
    compuertas = compuertas or {}
    familia, motivo, forma = goals_hook.familia_de_argv(list(argv or []), compuertas)
    nivel = _nivel_de_familia(familia, compuertas.get("niveles") or _NIVELES_DEFECTO)
    if nivel == NIVEL_PREGUNTA and _preautorizada(familia, forma, compuertas):
        return NIVEL_DIRECTO, familia, forma
    return nivel, familia, forma


def nivel_de_archivo(tool: str, tool_input: dict, compuertas: dict) -> tuple[str, str | None, dict | None]:
    d = goals_hook.decidir_archivo(tool, tool_input, compuertas or {})
    if d.permitir:
        return NIVEL_DIRECTO, d.familia, d.forma
    if _es_nunca(d.familia) or d.motivo.startswith("NUNCA"):
        return NIVEL_NUNCA, d.familia, d.forma
    return NIVEL_PREGUNTA, d.familia, d.forma


def _etiqueta(nivel: str, familia: str | None) -> str | None:
    """Lo que ve Pedro en el motivo: la familia, NUNCA marcado, y lo que
    el hook no sabe parsear dicho como lo que es (abierto)."""
    if nivel == NIVEL_NUNCA:
        return "NUNCA" if familia in (None, "NUNCA") else f"NUNCA ({familia})"
    if familia == "DENEGAR":
        return "abierto (el hook no lo deja pasar)"
    return familia


def clasificar_goal(a: Accion, techos: dict) -> Veredicto:
    op = a.operacion
    forma = a.forma or {}
    detalle = a.detalle or {}
    if op in ("dale", "cerrar", "pregunta", "raiz_nueva", "retomar"):
        return Veredicto(NIVEL_PREGUNTA, f"goal {op}: lo decide Pedro, cada vez", True)
    if op == "compuerta":
        familia = forma.get("familia")
        if not familia:
            return Veredicto(NIVEL_PREGUNTA, "compuerta sin familia", True)
        nivel = _nivel_de_familia(familia, detalle.get("niveles") or _NIVELES_DEFECTO)
        if nivel == NIVEL_NUNCA:
            return Veredicto(NIVEL_NUNCA, f"compuerta {familia}: NUNCA (la tabla de Pedro)")
        if nivel == NIVEL_DIRECTO:
            return Veredicto(NIVEL_DIRECTO, f"compuerta {familia}: directo")
        return Veredicto(NIVEL_PREGUNTA, f"compuerta {familia}: pregunta (la tabla de Pedro)", True)
    if op == "comando":
        argv = forma.get("argv")
        if not argv:
            return Veredicto(NIVEL_PREGUNTA, "comando sin argv (compuesto o vacio): abierto -> pregunta", True)
        compuertas = detalle.get("compuertas") or {}
        nivel, familia, f = nivel_de_comando(list(argv), compuertas)
        pre = ""
        if nivel == NIVEL_DIRECTO and _preautorizada(familia, f, compuertas):
            pre = " (preautorizada por Pedro para este goal)"
        return Veredicto(nivel, f"comando {' '.join(argv)[:80]}: {_etiqueta(nivel, familia) or 'simple'}{pre}",
                         nivel == NIVEL_PREGUNTA)
    if op == "archivo":
        ruta = forma.get("ruta")
        if not ruta:
            return Veredicto(NIVEL_PREGUNTA, "archivo sin ruta: abierto -> pregunta", True)
        tool = str(forma.get("tool") or "Write")
        nivel, familia, f = nivel_de_archivo(tool, {"file_path": ruta}, detalle.get("compuertas") or {})
        return Veredicto(nivel, f"archivo {tool} {ruta}: {_etiqueta(nivel, familia) or 'alcance'}",
                         nivel == NIVEL_PREGUNTA)
    return Veredicto(NIVEL_PREGUNTA, f"operacion desconocida del goal: {op!r}", True)


def cubre_goal(forma_permiso: dict, forma_accion: dict) -> bool:
    """Nunca: nada de la familia goal se concede para siempre."""
    return False


def registrar() -> None:
    registrar_clasificador(FAMILIA, clasificar_goal)
    registrar_cobertura(FAMILIA, cubre_goal)
