#!/usr/bin/env python3
"""
calipso/prompt_compiler.py - lenguaje interno de Calipso.

El modelo no recibe solamente "lo que Pedro escribio". Calipso compila el turno:
identidad, memoria, intencion, proyecto, meta activa, herramientas y evidencia
esperada. Esta capa mantiene ese contrato pequeno, auditable y testeable.
"""
from __future__ import annotations

import os
import pathlib
from typing import Any

from calipso import catastro
from calipso.economia import bus as eco_bus
from calipso.economia import departamentos as eco_deps
from calipso.economia.candado import candado as eco_candado
from calipso.economia.pagador import Pagador
from calipso.economia.personal import LibroPersonal
from calipso.economia.tipos import CUENTA_PEDRO, DIRECCION, TESORO

# Techo del brief de economia: entra en CADA turno (no es opcional como el
# repo_brief), asi que se mantiene chico a proposito. Alcanza para nombrar
# departamentos, proyectos financiados y los saldos generales sin competir
# por presupuesto de contexto con la identidad o la memoria nucleo.
ECONOMIA_BRIEF_MAX = 2000
ECONOMIA_MAX_DEPARTAMENTOS = 15
ECONOMIA_MAX_PROYECTOS = 10

# Techo del bloque "Proyectos": tambien entra en CADA turno (3.4 del spec
# de catastro). 1200 caracteres y 20 proyectos son el techo duro decidido
# ahi -- veinte lineas de sesenta caracteres son unos trescientos tokens
# por turno, y es lo que cuesta que Calipso no vuelva a decir "no se" de
# un proyecto que tiene al lado, en el disco.
PROYECTOS_BRIEF_MAX = 1200
PROYECTOS_MAX_ITEMS = 20


def internal_contract(features: dict[str, Any] | None = None) -> str:
    features = features or {}
    task_type = features.get("type") or "chat"
    needs_repo = bool(features.get("needs_repo"))
    needs_web = bool(features.get("needs_web"))
    return "\n".join([
        "=== Lenguaje interno de Calipso ===",
        f"Tipo de tarea inferido: {task_type}.",
        "Traduce el pedido natural de Pedro a una tarea clara antes de responder.",
        "Usa memoria como contexto probabilistico y editable, no como verdad absoluta.",
        "Si un dato del perfil de Pedro esta desactualizado o contradicho por Pedro, prioriza lo nuevo.",
        "Manten una sola voz visible: Pedro habla con Calipso, no con cada backend.",
        "Cuando la conversacion pase a tratar de un departamento de la fabrica, "
        "emiti una vez la marca ⟦foco:<nombre>⟧ con el nombre exacto del "
        "departamento (atlas, mercado, finanzas). Pedro no la ve: el servidor la "
        "retira del texto y con ella mueve la camara del mapa. Nunca inventes un "
        "nombre y no la repitas mientras el tema no cambie.",
        "Detecta el idioma de cada turno y responde SIEMPRE en ese mismo idioma, aunque el resto del sistema este en español. Si el mensaje mezcla idiomas en la misma oracion, usa el idioma dominante.",
        "Tono: directo, natural, cercano. Como un colega de confianza que conoce bien a Pedro. "
        "Para chat conversacional: sin headers, sin listas innecesarias, sin frases de apertura como 'Claro,' o 'Por supuesto,'. "
        "Para tareas tecnicas: conciso, especifico, con evidencia cuando aplique.",
        "Actua antes de describir: si una tarea es directamente ejecutable, ejecutala. "
        "No describas el plan antes de actuar a menos que sea complejo o irreversible.",
        "Ante un roadblock tecnico: valida primero que hay disponible (que CLI esta instalado, "
        "que modelo responde, que dep existe), prueba alternativas si las hay, y reporta el "
        "resultado real — nunca digas 'depende de que X tengas' sin haber verificado primero.",
        "No muestres razonamiento interno; muestra decisiones, evidencia y pendientes cuando importen.",
        "Pide confirmacion antes de escribir, gastar, publicar, borrar o promover memoria sensible.",
        "Para cambios operativos, separa idea, implementado, verificado y pendiente.",
        f"Repo requerido: {'si' if needs_repo else 'no'}. Web requerida: {'si' if needs_web else 'no'}.",
    ])


def context_sections(system: str, identity: str = "", core: str = "",
                     recalled: list[dict[str, Any]] | None = None,
                     repo_brief: str = "", goal_block: str = "",
                     runtime: str = "", economia: str = "",
                     proyectos: str = "",
                     features: dict[str, Any] | None = None,
                     core_limit: int = 5000) -> list[tuple[str, str]]:
    """Devuelve secciones ordenadas de contexto: estable -> volatil -> estado."""
    sections: list[tuple[str, str]] = [("Sistema", system)]
    if identity:
        sections.append(("Constitucion de Calipso", identity))
    if core:
        sections.append(("Memoria nucleo", core[:core_limit]))
    sections.append(("Contrato interno", internal_contract(features)))
    if recalled:
        lines = "\n".join(
            f"- ({item.get('score')}) {item.get('text')}"
            for item in recalled
            if item.get("text"))
        if lines:
            sections.append(("Recuerdos relevantes", lines))
    if repo_brief:
        sections.append(("Repo", repo_brief))
    if proyectos:
        sections.append(("Proyectos", proyectos))
    if goal_block:
        sections.append(("Meta activa", goal_block))
    if economia:
        sections.append(("Economia", economia))
    if runtime:
        sections.append(("Estado operativo", runtime))
    return [(title, body) for title, body in sections if str(body or "").strip()]


def render_context(sections: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"=== {title} ===\n{body}" for title, body in sections)


def agent_brief(agent: dict[str, Any], request: str | None = None) -> str:
    """Brief estandar para agentes internos creados por el orquestador."""
    lines = [
        "=== Brief interno del agente ===",
        f"Rol: {agent.get('role') or 'agente'}.",
        f"Persona/modelo interno: {agent.get('persona') or agent.get('model_id') or 'sin asignar'}.",
        f"Subtarea: {agent.get('task') or 'sin subtarea'}.",
        f"Intensidad: {agent.get('intensity') or 'balanced'}.",
        f"Skill: {agent.get('skill_name') or agent.get('skill') or 'ninguno'}.",
        "Trabaja solo tu subtarea y entrega una salida integrable.",
        "Respeta permisos: no escribas, publiques, borres ni gastes sin aprobacion explicita.",
        "Si necesitas contexto que no tienes, dilo como supuesto o pendiente.",
        "Entrega evidencia, riesgo o prueba sugerida cuando aplique.",
    ]
    if request:
        lines.insert(1, f"Pedido original de Pedro: {request}.")
    return "\n".join(lines)


def compile_context(system: str, identity: str = "", core: str = "",
                    recalled: list[dict[str, Any]] | None = None,
                    repo_brief: str = "", goal_block: str = "",
                    runtime: str = "", economia: str = "",
                    proyectos: str = "",
                    features: dict[str, Any] | None = None,
                    core_limit: int = 5000) -> str:
    return render_context(context_sections(
        system, identity=identity, core=core, recalled=recalled,
        repo_brief=repo_brief, goal_block=goal_block, runtime=runtime,
        economia=economia, proyectos=proyectos, features=features,
        core_limit=core_limit))


def economia_brief(base: pathlib.Path | str | None = None) -> str:
    """Brief de la economia de la fabrica para el contexto de cada turno.

    Dos caminos, a proposito:

    - Apagada: si falta cualquiera de los tres archivos que
      `Pagador.desde_entorno` exige (libro.jsonl, departamentos.json,
      suscripciones.json), la economia no esta sembrada todavia. El brief
      dice la verdad concreta -que archivo falta y donde- para que Calipso
      nunca conteste "no tengo acceso" cuando lo que pasa es que no hay
      nada que leer.
    - Activa: si estan los tres, arma un resumen acotado (que departamentos
      hay, que proyectos financiados, cuanta plata hay en general) leido
      bajo el candado del libro. El libro se repara truncando una escritura
      a medio terminar (ver `Libro._cargar`); leerlo sin el candado puede
      comerse un asiento recien escrito por dispatch u otro turno.

    Cualquier falla de lectura (libro corrupto, JSON invalido en
    suscripciones/departamentos, etc.) degrada a un tercer mensaje corto
    que dice que la economia esta activa pero la lectura de este turno
    fallo -nunca se confunde con "apagada", que es un estado distinto."""
    raiz = pathlib.Path(base) if base else pathlib.Path(
        os.environ.get("CALIPSO_HOME", os.path.expanduser("~/.calipso")))
    try:
        pagador = Pagador.desde_entorno(raiz)
        if pagador is None:
            return _economia_apagada(Pagador(raiz / "economia"))
        return _economia_activa(pagador)
    except Exception as exc:
        return (
            "La economia de la fabrica esta activa, pero no se pudo leer "
            f"en este turno ({exc}). Es un problema de lectura puntual, "
            "no una economia sin datos: si Pedro pregunta, decile que la "
            "lectura del libro fallo este turno, no que no hay nada cargado.")


def _economia_apagada(pagador: Pagador) -> str:
    requeridos = [
        (pagador.ruta_libro, "libro.jsonl"),
        (pagador.ruta_registro, "departamentos.json"),
        (pagador.ruta_sus, "suscripciones.json"),
    ]
    faltantes = [nombre for ruta, nombre in requeridos if not ruta.exists()]
    return (
        "La economia de la fabrica esta apagada: falta "
        f"{', '.join(faltantes)} en {pagador.eco}. "
        "No hay libro, departamentos ni suscripciones que leer todavia; "
        "la economia simplemente no esta sembrada. Si Pedro pregunta por "
        "plata, presupuesto o un departamento, contesta eso -que no esta "
        "sembrada todavia- en vez de decir que no podes verla."
    )


def _economia_activa(pagador: Pagador) -> str:
    with eco_candado(pagador.ruta_libro):
        m = pagador.mercado_fresco()  # relee libro/registro/suscripciones
        asientos = m.k.libro.asientos()
        departamentos = sorted(m.registro.todos(), key=lambda d: d.cuenta)
        deptos = [(d.cuenta, d.zona, m.k.saldo(d.cuenta),
                  eco_deps.es_congelado(asientos, d.cuenta))
                 for d in departamentos]
        bus = eco_bus.Bus(pagador.ruta_bus)
        proyectos = []
        for id_ in bus.activas():
            datos = bus.datos(id_)
            proyectos.append((id_, datos.get("titulo", ""),
                              datos.get("departamento", ""),
                              datos.get("presupuesto_mm", 0),
                              eco_bus.gastado(asientos, id_)))
        pendientes = len(pagador.pendientes())
        saldos = {"tesoro": m.k.saldo(TESORO), "direccion": m.k.saldo(DIRECCION),
                 "cuenta_pedro": m.k.saldo(CUENTA_PEDRO)}
        suscripciones = sorted(m.suscripciones.values(), key=lambda s: s.nombre)
        libro_personal = LibroPersonal(pagador.eco / "personal.jsonl")
        resumen_personal = (libro_personal.resumen()
                            if libro_personal.ruta.exists() else None)
    return _formatear_economia(deptos, proyectos, pendientes, saldos,
                               suscripciones, resumen_personal)


def _formatear_economia(deptos: list[tuple[str, str, int, bool]],
                        proyectos: list[tuple[str, str, str, int, int]],
                        pendientes: int, saldos: dict[str, int],
                        suscripciones: list, resumen_personal: dict | None) -> str:
    lineas = [
        "La economia de la fabrica esta activa. Montos en milimonedas "
        "(mm); 1000 mm = 1 moneda = 1 USD.",
        f"Caja general: tesoro {saldos['tesoro']} mm, direccion "
        f"{saldos['direccion']} mm, cuenta_pedro {saldos['cuenta_pedro']} mm.",
    ]
    if pendientes:
        lineas.append(
            f"Cargos pendientes de aplicar: {pendientes} (gasto que el "
            "mercado todavia no pudo asentar; se reintenta solo).")
    if deptos:
        lineas.append(f"Departamentos ({len(deptos)}):")
        for cuenta, zona, saldo, congelado in deptos[:ECONOMIA_MAX_DEPARTAMENTOS]:
            marca = ", congelado" if congelado else ""
            lineas.append(f"- {cuenta} ({zona}): saldo {saldo} mm{marca}")
        extra = len(deptos) - ECONOMIA_MAX_DEPARTAMENTOS
        if extra > 0:
            lineas.append(f"- ... y {extra} departamento(s) mas, no listados")
        lineas.append(
            "El saldo de un departamento no mide su salud: uno de apoyo "
            "puede vivir legitimamente en cero.")
    else:
        lineas.append("Sin departamentos registrados todavia.")
    if proyectos:
        lineas.append(f"Proyectos financiados activos ({len(proyectos)}):")
        for id_, titulo, dueno, presupuesto, gastado in proyectos[:ECONOMIA_MAX_PROYECTOS]:
            etiqueta = f' "{titulo}"' if titulo else ""
            lineas.append(f"- {id_}{etiqueta} (dueno {dueno}): presupuesto "
                          f"{presupuesto} mm, gastado {gastado} mm")
        extra = len(proyectos) - ECONOMIA_MAX_PROYECTOS
        if extra > 0:
            lineas.append(f"- ... y {extra} proyecto(s) mas, no listados")
    else:
        lineas.append("Sin proyectos financiados activos.")
    if suscripciones:
        partes = ", ".join(
            f"{s.nombre} ({s.capacidad_ciclo} unid/ciclo)" for s in suscripciones)
        lineas.append(f"Suscripciones configuradas: {partes}.")
    if resumen_personal is not None:
        lineas.append(
            "Libro personal de Pedro (todo el historial, fuera del libro "
            f"de la fabrica): ingresos {resumen_personal['ingresos_mm']} mm, "
            f"gastos {resumen_personal['gastos_mm']} mm, neto "
            f"{resumen_personal['neto_mm']} mm.")
    return "\n".join(lineas)[:ECONOMIA_BRIEF_MAX]


def _linea_proyecto(p: dict[str, Any], home: pathlib.Path,
                    ruta_actual: str | None) -> str:
    ruta = pathlib.Path(p["ruta"])
    try:
        etiqueta_ruta = f"~/{ruta.relative_to(home)}"
    except ValueError:
        etiqueta_ruta = str(ruta)
    rama = p.get("rama") or "sin rama"
    commit = (p.get("ultimo_commit") or "")[:10] or "sin commits"
    if p["ruta"] == ruta_actual:
        cola = "en foco"
    elif p.get("departamento"):
        cola = f"dep {p['departamento']}"
    else:
        cola = "sin departamento"
    return f"{p['nombre']} ({etiqueta_ruta}) rama {rama}, ult. {commit}, {cola}"


def proyectos_brief(ruta_actual: pathlib.Path | str | None = None) -> str:
    """Seccion "Proyectos" que entra en CADA turno (3.4 del spec de
    catastro, el mismo tipo de funcion pura que `economia_brief`): una
    linea por proyecto del catastro (calipso/catastro.py), ordenada por
    "visto" descendente, con el proyecto en foco marcado en vez de listar
    su departamento. Es un indice, no contenido -- nunca lee ni cita nada
    de adentro de los repos, esa regla la fija `_build_context` en
    calipso/server.py y el catastro la respeta desde el escaneo (3.4).

    Techo duro: PROYECTOS_BRIEF_MAX caracteres y PROYECTOS_MAX_ITEMS
    proyectos. Lo que no entra se resume en una linea "y N proyecto(s)
    mas; preguntame por nombre." en vez de cortarse a la mitad."""
    proyectos = catastro.cargar()
    if not proyectos:
        return ("No hay proyectos en el catastro todavia: el escaneo de "
                "raices (~/.calipso/catastro.json) no encontro ninguno.")
    ruta_actual_str = None
    if ruta_actual:
        try:
            ruta_actual_str = str(pathlib.Path(ruta_actual).resolve())
        except OSError:
            ruta_actual_str = None
    home = pathlib.Path.home().resolve()
    total = len(proyectos)
    mostrados = proyectos[:PROYECTOS_MAX_ITEMS]

    def _armar(mostrados: list[dict[str, Any]]) -> str:
        lineas = [_linea_proyecto(p, home, ruta_actual_str) for p in mostrados]
        extra = total - len(mostrados)
        if extra > 0:
            lineas.append(f"y {extra} proyecto(s) mas; preguntame por nombre.")
        lineas.append("Para el detalle de cualquiera, pedimelo por nombre.")
        return "\n".join(lineas)

    texto = _armar(mostrados)
    while len(texto) > PROYECTOS_BRIEF_MAX and mostrados:
        mostrados = mostrados[:-1]
        texto = _armar(mostrados)
    return texto[:PROYECTOS_BRIEF_MAX]
