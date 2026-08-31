"""El agregador del inbox: junta las cuatro bandejas en una sola lista.

No sabe nada de ninguna bandeja. Cada origen declara lo suyo -- sus verbos,
su reloj, su clase -- y se traduce a si mismo; aca solo se los llama y se
junta el resultado. Agregar el correo manana es agregarlo a las llamadas
de abajo.

Una bandeja rota no puede voltear a las otras tres: cuatro fuentes son
cuatro veces la chance de que una falle, y un inbox que desaparece entero
porque una fuente se cayo es peor que uno incompleto que lo dice.

Ese mismo principio se extiende un nivel mas afuera, a la IMPORTACION. Los
cuatro modulos de abajo se importan bajo try/except, no al desnudo: en
`calipso/server.py` (cerca de la linea 3592) los imports de economia ya
estan envueltos asi, y en el except quedan en None -- una degradacion a
proposito, no un olvido. Un `from calipso import inbox` sin la misma
guarda convertiria esa caida elegante en una caida del arranque del
servidor entero: el inbox pasaria a poder voltear no solo a sus cuatro
bandejas, sino al server que ni siquiera lo pidio.
"""
from __future__ import annotations

try:
    from calipso import librarian
except Exception:  # una bandeja que ni siquiera importa no tira el server
    librarian = None

try:
    from calipso.economia import bus as eco_bus
except Exception:
    eco_bus = None

try:
    from calipso.economia import cola as eco_cola
except Exception:
    eco_cola = None

try:
    from calipso.permisos import motor as permisos_motor
except Exception:
    permisos_motor = None


def descriptores() -> dict:
    """Un descriptor por modulo que pudo importarse.

    El modulo cuyo import fallo simplemente no aparece: no hay forma de
    pedirle su descriptor a algo que es None, y omitirlo es la misma
    logica de "una bandeja rota no voltea a las otras tres" aplicada a
    esta lista."""
    modulos = (eco_bus, permisos_motor, librarian, eco_cola)
    return {d["origen"]: d for d in
           (m.descriptor() for m in modulos if m is not None)}


def juntar(obtener_bus, obtener_permisos, obtener_memoria, proyecto: str,
           obtener_cola) -> tuple[list[dict], list[str]]:
    """Devuelve (items, origenes_que_fallaron).

    El orden de la lista es el de los origenes y dentro de cada uno el que
    trae la bandeja. Ordenar por urgencia es el PvP, y va en el plan 2.

    Los cuatro `obtener_*` son CALLABLES sin argumentos, no datos ya
    traidos. Es a proposito: la primera version de este modulo recibia los
    datos ya obtenidos, y la guarda de abajo cubria solo la TRADUCCION
    (`como_items`) -- traerlos (`api_eco_bus()`, que adentro llama a
    `mercado_fresco()` y puede levantar `json.JSONDecodeError` si
    `suscripciones.json` esta corrupto, un error que `_ERRORES_ECONOMICOS`
    no incluye) quedaba AFUERA, sin capturar, en el endpoint. Un archivo de
    economia corrupto tumbaba las cuatro bandejas juntas -- exactamente lo
    que "una bandeja rota no voltea a las otras tres" prometia evitar, y no
    lo cumplia. Metiendo la llamada a `obtener_*()` DENTRO del mismo
    try/except que traduce, las dos mitades quedan bajo una sola guarda por
    origen, y no se puede volver a partir en dos por accidente.

    Un origen falla por tres motivos distintos y los tres terminan en el
    mismo lugar de `fallaron`: el modulo no pudo importarse (es None),
    `obtener_*()` revento trayendo el dato, o `como_items` revento
    traduciendolo. Ninguno de los tres frena a los otros tres origenes.
    """
    fallaron: list[str] = []
    items: list[dict] = []
    llamadas = [
        ("mesa", eco_bus, lambda: eco_bus.como_items(obtener_bus())),
        ("permisos", permisos_motor,
         lambda: permisos_motor.como_items(obtener_permisos())),
        ("biblioteca", librarian,
         lambda: librarian.como_items(obtener_memoria(), proyecto)),
        ("cartas", eco_cola, lambda: eco_cola.como_items(obtener_cola())),
    ]
    for nombre, modulo, fn in llamadas:
        if modulo is None:
            fallaron.append(nombre)
            continue
        try:
            items.extend(fn())
        except Exception:
            fallaron.append(nombre)
    return items, fallaron


def cuenta_de_decisiones(items: list[dict]) -> int:
    """El badge cuenta decisiones, nunca avisos. Un aviso no espera a nadie."""
    return sum(1 for i in items if i.get("clase") == "decision")
