"""
calipso/plantel/decision.py — El sesgo, el prompt y el parseo.

Todo lo que rodea a la llamada del modelo, sin la llamada. La aritmetica del
sesgo se hace ACA y no en el prompt: pedirle a un modelo de 3b que calcule un
porcentaje contra un precio es pedirle lo unico que no sabe hacer.
"""
from __future__ import annotations

ACCIONES = ("nada", "proponer", "trabajar", "comentar")


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


def prompt(situacion: dict, sesgo_pct: int, nucleo: str = "") -> str:
    """Corto a proposito: corre seguido y en el escalon barato.

    `nucleo` es el markdown de la memoria del departamento. Sin el, el jefe
    escribiria en su memoria y no la leeria nunca — seria memoria de solo
    escritura, y la tercera pata del departamento no serviria de nada."""
    s = situacion
    trabajos = "\n".join(
        f"  - {t['id']}: {t['titulo']} (gastado {t['gastado_mm']} de "
        f"{t['presupuesto_mm']} mm)" for t in s["trabajos"]) or "  (ninguno)"
    propias = "\n".join(
        f"  - {p['id']}: {p['titulo']}"
        for p in s.get("propuestas_propias", [])) or "  (ninguna)"
    ajenas = "\n".join(
        f"  - {p['id']}: {p['titulo']} (de {p['dueno']})"
        for p in s["propuestas_ajenas"]) or "  (ninguna)"
    cap = s.get("capacidad")
    precio = (f"{cap['precio_mm']} mm por unidad de {cap['nombre']} "
              f"(lista {cap['precio_base_mm']})") if cap else "sin capacidad"
    inclinacion = ("explorar cosas nuevas" if sesgo_pct >= 60
                   else "terminar lo empezado" if sesgo_pct <= 40
                   else "mantener el equilibrio")
    aprendido = f"Lo que aprendiste antes:\n{nucleo.strip()}\n\n" if nucleo.strip() else ""
    return (
        aprendido +
        f"Sos el jefe del departamento {s['nombre']} de una fabrica de agentes.\n"
        f"Billetera: {s['disponible_mm']} milimonedas disponibles de "
        f"{s['saldo_mm']}.\n"
        f"Presupuesto de la semana: {s['presupuesto_semanal_mm']}. "
        f"Ya salieron {s['salidas_semana_mm']}.\n"
        f"Capacidad de computo: {precio}.\n"
        f"Tus trabajos vivos:\n{trabajos}\n"
        f"Propuestas tuyas todavia sin financiar:\n{propias}\n"
        f"Propuestas de otros departamentos:\n{ajenas}\n"
        f"Compuertas tuyas esperando la firma de Pedro: "
        f"{s['compuertas_pendientes']}.\n\n"
        f"Ahora inclinate a {inclinacion}.\n\n"
        "Elegi UNA accion. Primera linea, sin nada mas:\n"
        "  nada\n  proponer\n  trabajar <id>\n  comentar <id>\n"
        "Segunda linea: un renglon con el motivo."
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
    if not partes or partes[0] not in ACCIONES:
        return "nada", None, motivo or "no se entendio la respuesta"
    accion = partes[0]
    ref = partes[1] if len(partes) > 1 else None
    if accion == "nada":
        return "nada", None, motivo
    if accion in ("trabajar", "comentar") and not ref:
        return "nada", None, motivo or f"{accion} sin id"
    return accion, ref, motivo
