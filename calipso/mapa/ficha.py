"""
calipso/mapa/ficha.py — De un edificio a contexto y a una cuenta que paga.

El departamento no es otro interlocutor (invariante 7): es un objetivo del
cerebro. Este modulo hace las dos traducciones que eso necesita — el bloque
de texto que Calipso recibe, y la cuenta que va a pagar el turno — y las
hace puras, sobre el modelo de ciudad que el mapa ya deriva.
"""
from __future__ import annotations


def id_de_nombre(nombre: str, edificios: list[dict]) -> str | None:
    """`atlas` -> `dep:atlas`. None si ese departamento no existe: el modelo
    se puede inventar un nombre y la camara no vuela a la nada."""
    if not nombre:
        return None
    buscado = nombre.strip().lower()
    for e in edificios:
        if e["id"].lower() == buscado or (e.get("nombre") or "").lower() == buscado:
            return e["id"]
    return None


CUENTA_PERSONAL = "personal"
PREFIJO_FABRICA = "dep:"


def _monedas(mm: int) -> str:
    """El libro guarda milimonedas; el que lee el prompt lee monedas."""
    return f"{(mm or 0) / 1000:.2f}"


def cuenta_pagadora(id_edificio: str | None) -> str:
    """La cuenta que paga el turno. Solo un departamento de la fabrica paga.

    La casa de Pedro (`cuenta_pedro`) y cualquier cosa que no sea un
    departamento de la fabrica caen en `personal`, que queda FUERA del libro
    de la fabrica. El id llega del cliente, asi que esto es tambien la
    validacion: `tesoro` no puede pagar un chat.

    Un `personal:` COLAPSA a `personal` en vez de quedarse como esta: la zona
    personal no compra capacidad ni API de la fabrica (invariante 12), asi
    que un cargo a `personal:finanzas` lo rechaza el mercado y queda pendiente
    para siempre. `personal` no manda el cargo a `usar_reserva_personal`:
    `_cobrar_turno` corta antes y no llama al pagador. El efecto es el mismo
    -el uso personal queda fuera del libro de la fabrica, que es donde lo
    lleva calipso/costs.py- pero por otro camino."""
    if not id_edificio:
        return CUENTA_PERSONAL
    if id_edificio.startswith(PREFIJO_FABRICA):
        return id_edificio
    return CUENTA_PERSONAL


def edificio_de(modelo: dict | None, id_edificio: str) -> dict | None:
    if not modelo:
        return None
    for e in modelo.get("edificios", ()):
        if e["id"] == id_edificio:
            return e
    return None


def bloque(edificio: dict) -> str:
    """El contexto que recibe Calipso cuando Pedro toca un edificio.

    No lo convierte en el departamento: lo pone a hablar CON Pedro SOBRE el
    departamento (invariante 7)."""
    efi = edificio.get("eficiencia_pormil")
    trabajos = edificio.get("trabajos") or []
    return "\n".join([
        "=== Departamento en foco ===",
        f"Pedro esta mirando {edificio['nombre']} (id {edificio['id']}, "
        f"zona {edificio['zona']}, estado {edificio['estado']}).",
        f"Saldo: {_monedas(edificio['saldo_mm'])} monedas. "
        f"Gasto del ciclo: {_monedas(edificio['gasto_ciclo_mm'])}. "
        f"Ventas de la ventana: {_monedas(edificio['ventas_ventana_mm'])}. "
        + ("Eficiencia: sin dato." if efi is None
           else f"Eficiencia: {efi / 10:.1f}%."),
        f"Trabajos vivos: {', '.join(trabajos) if trabajos else 'ninguno'}. "
        f"Compuertas pendientes: {edificio.get('compuertas', 0)}.",
        f"Lo que se gaste en este turno lo paga la cuenta "
        f"{cuenta_pagadora(edificio['id'])}.",
        "Hablas con Pedro SOBRE este departamento. No hablas en su nombre ni "
        "le hablas a el: la conversacion es siempre con Calipso.",
    ])
