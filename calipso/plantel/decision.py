"""
calipso/plantel/decision.py — El sesgo, el prompt y el parseo.

Todo lo que rodea a la llamada del modelo, sin la llamada. La aritmetica del
sesgo se hace ACA y no en el prompt: pedirle a un modelo de 3b que calcule un
porcentaje contra un precio es pedirle lo unico que no sabe hacer.
"""
from __future__ import annotations

from . import ficha

ACCIONES = ("nada", "proponer", "trabajar", "comentar", "pedir")


def sesgo_efectivo(explorar_pct: int, precio_mm: int,
                   precio_base_mm: int) -> int:
    """La perilla explorar/explotar, corrida por lo que cuesta la capacidad.

    100 es el precio de lista. Capacidad barata —la que esta por evaporarse—
    empuja a explorar; capacidad cara empuja a terminar lo empezado. El
    ajuste es la mitad de la desviacion, para que el precio incline la
    perilla sin reemplazarla."""
    if not precio_base_mm or precio_mm <= 0:
        return max(0, min(100, explorar_pct))
    rel = precio_mm * 100 // precio_base_mm
    return max(0, min(100, explorar_pct + (100 - rel) // 2))


def _como_se_ve(p: dict) -> str:
    """La ficha si la tiene, el titulo si no.

    Con `.get()` y no con corchetes a proposito: las propuestas escritas
    antes de que la forma existiera no traen la clave, y los tests del
    prompt arman sus dicts a mano sin ella. Un `p["forma"]` las reventaria
    con KeyError en vez de mostrar lo que hay.
    """
    f = p.get("forma")
    if not f:
        return p.get("titulo", "")
    return f"{f['promete']}: {f['sobre']} ({f['tarda']})"


def prompt(situacion: dict, sesgo_pct: int, nucleo: str = "",
          recientes: "list[str] | tuple" = ()) -> str:
    """Corto a proposito: corre seguido y en el escalon barato.

    `nucleo` es el markdown de la memoria del departamento. Sin el, el jefe
    escribiria en su memoria y no la leeria nunca — seria memoria de solo
    escritura, y la tercera pata del departamento no serviria de nada.

    `recientes` son las ultimas decisiones episodicas: sin ellas el jefe le
    pregunta al modelo desde cero en cada tic, y un modelo sin memoria de lo
    que ya decidio propone lo mismo una y otra vez."""
    s = situacion
    trabajos = "\n".join(
        f"  - {t['id']}: {t['titulo']} (gastado {t['gastado_mm']} de "
        f"{t['presupuesto_mm']} mm)" for t in s["trabajos"]) or "  (ninguno)"
    propias = "\n".join(
        f"  - {p['id']}: {_como_se_ve(p)}"
        for p in s.get("propuestas_propias", [])) or "  (ninguna)"
    ajenas = "\n".join(
        f"  - {p['id']}: {_como_se_ve(p)} (de {p['dueno']})"
        for p in s["propuestas_ajenas"]) or "  (ninguna)"
    # el "no" de Pedro, dicho con todas las letras -- y es lo UNICO que
    # hay. No existe ningun freno mecanico: `jefe._puede` no nombra
    # `descartadas_semana` por ningun lado, y una descartada ni siquiera
    # gasta cupo del techo de tres, porque `situacion` hace `continue`
    # antes de construir `propuestas_propias`. Lo unico que separa al jefe
    # de volver a proponer lo mismo es que un modelo de 3b lea este renglon
    # y le haga caso.
    rechazadas = "\n".join(f"  - {_como_se_ve(p)}"
                           for p in s.get("descartadas_semana", []))
    cap = s.get("capacidad")
    precio = (f"{cap['precio_mm']} mm por unidad de {cap['nombre']} "
              f"(lista {cap['precio_base_mm']})") if cap else "sin capacidad"
    inclinacion = ("explorar cosas nuevas" if sesgo_pct >= 60
                   else "terminar lo empezado" if sesgo_pct <= 40
                   else "mantener el equilibrio")
    aprendido = f"Lo que aprendiste antes:\n{nucleo.strip()}\n\n" if nucleo.strip() else ""
    ultimas = ("Lo que decidiste en los ultimos tics (no repitas lo mismo):\n"
              + "\n".join(f"  - {r}" for r in recientes) + "\n\n") if recientes else ""

    # los objetos que este departamento ya nombro, para que COPIE en vez de
    # reinventar: sin esto "radar de precios" y "monitor de precios" son dos
    # familias, ocupan dos lugares en la mesa y un "nunca mas" sobre una no
    # tapa la otra. Condicional como los otros dos: un encabezado sobre una
    # lista vacia le ensena al modelo que ese bloque no dice nada.
    objetos = s.get("catalogo") or []
    catalogo = ("Objetos que ya nombraste (si hablas de uno, escribilo "
                "igual):\n" + "\n".join(f"  - {o}" for o in objetos) + "\n\n"
                ) if objetos else ""

    # El menu se arma segun la situacion: ofrecer "trabajar" sin trabajos
    # vivos, o "comentar" sin nada para comentar, empuja al modelo a
    # elegirlas igual porque estan en la lista -se lo vio contestar
    # "trabajar 1" con la lista de trabajos vivos vacia, razonando sobre
    # proponer. ACCIONES sigue siendo el vocabulario completo que parsear
    # acepta: esto es solo lo que el prompt OFRECE.
    hay_para_comentar = bool(s.get("propuestas_propias") or
                             s["propuestas_ajenas"] or s["trabajos"])
    # "pedir" va siempre en el menu, con o sin presupuesto: es la ronda
    # pre-seed (spec del bus), y quien decide si hace falta o no es Pedro
    # desde la mesa, no este prompt.
    menu = ["  nada", "  proponer", "  pedir <monto>"]
    if s["trabajos"]:
        menu.append("  trabajar <id>")
    if hay_para_comentar:
        menu.append("  comentar <id>")

    return (
        aprendido +
        ultimas +
        catalogo +
        f"Sos el jefe del departamento {s['nombre']} de una fabrica de agentes.\n"
        f"Billetera: {s['disponible_mm']} milimonedas disponibles de "
        f"{s['saldo_mm']}.\n"
        f"Presupuesto de la semana: {s['presupuesto_semanal_mm']}. "
        f"Ya salieron {s['salidas_semana_mm']}.\n"
        "Si te hace falta capital para arrancar, podes pedirle al tesoro un "
        "monto en milimonedas con 'pedir <monto>'; lo decide Pedro desde su "
        "mesa, igual que con una propuesta.\n"
        f"Capacidad de computo: {precio}.\n"
        f"Tus trabajos vivos:\n{trabajos}\n"
        f"Propuestas tuyas todavia sin financiar:\n{propias}\n"
        f"Propuestas de otros departamentos:\n{ajenas}\n"
        + (f"Pedro DESCARTO esta semana (no las vuelvas a proponer):\n"
           f"{rechazadas}\n" if rechazadas else "") +
        f"Compuertas tuyas esperando la firma de Pedro: "
        f"{s['compuertas_pendientes']}.\n\n"
        f"Ahora inclinate a {inclinacion}.\n\n"
        "Elegi UNA accion. Primera linea, sin nada mas:\n"
        + "\n".join(menu) + "\n"
        "Segunda linea: un renglon con el motivo.\n\n"
        "Si elegis proponer, en vez del motivo van CUATRO renglones:\n"
        "  sobre:   <el objeto, en tus palabras>\n"
        "  promete: " + " | ".join(ficha.PROMESAS) + "\n"
        "  tarda:   " + " | ".join(ficha.PLAZOS) + "\n"
        "  porque:  <un renglon, opcional>\n"
        "IMPORTANTE: escribi TODO en castellano. Ni una sola palabra en chino,\n"
        "ingles ni ningun otro idioma."
    )


def parsear(texto: str) -> tuple[str, str | None, str]:
    """De lo que devolvio el modelo a una decision valida.

    Tolerante a proposito: lo que no se entiende es `nada`. Un modelo que
    alucina no puede gastar."""
    lineas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    if not lineas:
        return "nada", None, "no contesto"
    motivo = lineas[1] if len(lineas) > 1 else ""
    partes = lineas[0].replace(":", " ").lower().split()
    if not partes or partes[0] not in ACCIONES or len(partes) > 2:
        return "nada", None, motivo or "no se entendio la respuesta"
    accion = partes[0]
    ref = partes[1] if len(partes) > 1 else None
    if accion == "nada":
        return "nada", None, motivo
    if accion == "proponer":
        return "proponer", None, motivo
    if accion in ("trabajar", "comentar") and not ref:
        return "nada", None, motivo or f"{accion} sin id"
    if accion == "pedir" and not (ref and ref.isdecimal() and int(ref) > 0):
        # el mismo criterio que un modelo que alucina no gasta: uno que
        # pide sin numero, o un numero que no es un entero positivo, no
        # pide -cae en nada, no en un pedido invalido en el bus
        #
        # `.isdecimal()` y no `.isdigit()`: los dos aceptan los digitos
        # arabes ('٥', que `int()` lee bien), pero `isdigit` tambien acepta
        # los superindices ('²') -- Numeric_Type=Digit sin ser decimales --
        # y ahi el `int(ref)` de al lado revienta con ValueError. La
        # promesa de este parser es que lo que no se entiende es NADA; con
        # `isdigit`, un `pedir ²` salia por el `except` de `tic` y se
        # anotaba como "reviento actuando".
        return "nada", None, motivo or "pedir sin un monto valido"
    return accion, ref, motivo
