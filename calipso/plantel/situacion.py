"""
calipso/plantel/situacion.py — Del libro al estado del departamento.

Lo que el jefe mira antes de decidir. Pura y gratis: pliega asientos y
archivos de estado, no llama a ningun modelo, no abre red y no lee el reloj
del sistema. Misma clase de funcion que calipso/mapa/ciudad.py, y se testea
igual: contra un libro sintetico, campo por campo.
"""
from __future__ import annotations

from calipso.economia import balances as bal
from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import mercado as mercado_mod
from calipso.economia.tipos import Divisa, TipoAsiento

# Que asientos sacan plata de una cuenta. Mismo criterio que bus.gastado y
# que mapa/ciudad.py: dos lecturas del mismo libro no pueden discrepar sobre
# que es gasto.
_SALIDAS = (TipoAsiento.DESTRUCCION, TipoAsiento.TRANSFERENCIA,
            TipoAsiento.EJECUCION_RESERVA)


def salidas_de(asientos, cuenta: str, semanas: list[str]) -> int:
    """Todo lo que salio de la cuenta en esas semanas."""
    return sum(a.monto for a in asientos
               if a.tipo in _SALIDAS and a.origen == cuenta
               and a.semana in semanas and a.divisa is Divisa.MONEDA)


def _capacidad(asientos, suscripciones, semana, ops):
    """La suscripcion mas barata ahora mismo, con su precio y su ritmo.

    El jefe no elige proveedor —eso es el spec de mezcla multi-proveedor—
    pero si necesita saber si sobra capacidad barata, porque es lo que hace
    racional explorar a fin de ciclo."""
    if not suscripciones or not ops or semana not in ops:
        return None
    ciclo, fraccion = cap.posicion_ciclo(semana, ops)
    semanas = cap.semanas_del_ciclo(ciclo, ops)
    mejor = None
    for nombre, sus in sorted(suscripciones.items()):
        # por CICLO estampado y no por semana: el consumo no espera al boton
        # de abrir, asi que el de una semana sin abrir no cae en las semanas
        # de ningun ciclo y el jefe veia "consumido 0" con la cuota casi
        # agotada. Es el mismo pliegue que mira el guardia de cuota.
        consumido = cap.consumo_fabrica_ciclo(asientos, nombre, ciclo, semanas)
        fila = {"nombre": nombre,
                "precio_mm": cap.precio_unidad_mm(sus, consumido, fraccion),
                "precio_base_mm": sus.precio_base_mm,
                "consumido": consumido,
                "capacidad_fabrica": sus.capacidad_fabrica,
                "fraccion_ciclo_pct": fraccion}
        if mejor is None or fila["precio_mm"] < mejor["precio_mm"]:
            mejor = fila
    return mejor


def situacion(kernel, registro, bus, cola, suscripciones, semana: str,
              cuenta: str) -> dict:
    """Todo lo que el jefe necesita para decidir, plegado del libro."""
    asientos = kernel.libro.asientos()
    dep = registro.obtener(cuenta.split(":", 1)[1])
    ops = cap.semanas_operativas(asientos)
    # `semanas_del_ciclo_de_hoy` y no `if semana in ops`: una semana se
    # vuelve operativa recien cuando alguien aprieta el boton de abrir, asi
    # que todo lunes empieza afuera de `ops`. Preguntando con `in ops`, el
    # jefe veia el ciclo vacio esa ventana entera -- el gasto de API del
    # ciclo daba cero y el pre-seed ya entrado tambien, o sea que el techo
    # del ciclo se reseteaba solo cada vez que Pedro tardaba en abrir la
    # semana. Un techo que se reinicia por no tocar un boton no es un
    # techo. Es la misma funcion que mira `server` para el consumido de
    # las suscripciones y su guardia: dos respuestas distintas a "en que
    # ciclo estoy" serian dos techos. (`bus.financiar` NO la mira: el
    # techo de pre-seed se mide sobre la ventana deslizante de abajo.)
    semanas_ciclo = cap.semanas_del_ciclo_de_hoy(ops, semana)
    # y la OTRA ventana, la del caudal de capital. El techo acumulado de
    # pre-seed no se mide sobre el ciclo de facturacion: se mide sobre las
    # ultimas `bus.VENTANA_PRESEED_SEMANAS` semanas operativas, deslizante.
    # Con el ciclo, el acumulado se reseteaba de golpe en la quinta semana
    # y el techo entero entraba dos veces en dos semanas de calendario
    # seguidas. Son dos preguntas distintas y por eso dos listas distintas:
    # `semanas_ciclo` sigue siendo la del gasto de API, que factura por
    # ciclo de verdad. Ver `bus.ventana_preseed`.
    semanas_ventana = bus_mod.ventana_preseed(ops, semana)
    sale_de_ventana, libera_mm = bus_mod.libera_preseed(
        asientos, cuenta, ops, semana)

    # OJO con los estados del bus: `alta` es una propuesta sin financiar y
    # `financiada` es un trabajo vivo. `bus.activas()` devuelve SOLO las
    # financiadas, asi que iterar por ahi dejaria al jefe sin ver ninguna
    # propuesta — y `comentar` sin nada sobre lo que opinar.
    trabajos, propias, ajenas, descartadas = [], [], [], []
    preseed_pendiente = 0
    for id_ in bus.ids():
        estado = bus.estado(id_)
        datos = bus.datos(id_)
        mio = datos.get("departamento") == cuenta
        if estado == "descartada":
            # el "no" de Pedro, de ESTA semana. Descartar libera el cupo
            # (para eso existe: sin eso el jefe se frena al llegar a su
            # techo), pero sin esto el "no" no se pegaba a nada: la
            # propuesta desaparecia de la situacion y el mismo pedido volvia
            # al tic siguiente -- a 200 tics por semana, 200 veces. Lo unico
            # que lo separaba de repetir era la buena voluntad de un modelo
            # de 3b leyendo "no repitas lo mismo".
            if mio and datos.get("semana_descartada") == semana:
                descartadas.append({"id": id_,
                                    "titulo": datos.get("titulo", "")})
            continue
        if estado not in ("alta", "financiada"):
            continue                       # muerta, cerrada o liquidada
        if estado == "alta" and bus_mod.preseed_vencido(datos, ops, semana):
            # un pedido de pre-seed que ya salio de su ventana. `financiar`
            # no lo paga mas, asi que no hay nada que reservarle: contarlo
            # aca es lo que convertia la inaccion de Pedro en una condena
            # -- el pedido seguia comiendo cupo del techo acumulado y el
            # unico camino afuera era que Pedro lo mirara. Ahora se suelta
            # solo, con la misma ventana que ya acota el techo.
            #
            # Sale de las TRES listas: no es propia (el departamento tiene
            # que poder volver a pedir), no es ajena (no hay nada sobre lo
            # que opinar) y no suma al pendiente. Sigue en el bus, en
            # `alta`: no se borro nada, dejo de contar.
            continue
        base = {"id": id_, "titulo": datos.get("titulo", ""),
                "presupuesto_mm": datos.get("presupuesto_mm", 0)}
        if estado == "financiada":
            # un pre-seed financiado no es un trabajo: la plata ya esta en
            # la cuenta del departamento (no en trabajo:<id>), asi que no
            # tiene gasto que mostrar ni nada pendiente que el jefe deba
            # seguir mirando.
            if mio and datos.get("tipo") != "preseed":
                trabajos.append({**base,
                                 "gastado_mm": bus_mod.gastado(
                                     asientos, id_, suscripciones)})
            continue
        if mio:
            propias.append(base)           # ya la propuso: no la repita
            if datos.get("tipo") == "preseed":
                # lo que ya pidio y todavia esta en la mesa. `_puede` lo
                # suma al saldo para el techo acumulado de la ronda: sin
                # esto, publicar tres pedidos y que Pedro los financie a
                # los tres da tres veces el techo.
                preseed_pendiente += datos.get("presupuesto_mm", 0)
        else:
            ajenas.append({**base, "dueno": datos.get("departamento", "")})

    return {
        "cuenta": cuenta,
        "nombre": dep.nombre,
        "zona": dep.zona,
        "saldo_mm": bal.saldos(asientos).get((cuenta, Divisa.MONEDA), 0),
        "disponible_mm": kernel.disponible(cuenta),
        "presupuesto_semanal_mm": dep.presupuesto_semanal_mm,
        "explorar_explotar_pct": dep.explorar_explotar_pct,
        "agresividad_pct": dep.agresividad_pct,
        "techo_api_ciclo_mm": dep.techo_api_ciclo_mm,
        # el techo de la ronda pre-seed: cuanto puede PEDIR, no cuanto
        # tiene. Cero es "Pedro todavia no autorizo", y `_puede` lo frena
        # ahi -- ver el freno de `pedir` en jefe.py.
        "techo_preseed_mm": dep.techo_preseed_mm,
        # el segundo techo: cuanto capital puede ENTRAR por pre-seed en la
        # ventana deslizante. Cero tambien frena aca (ver departamentos.py).
        "techo_preseed_ciclo_mm": dep.techo_preseed_ciclo_mm,
        # lo que ya pidio y sigue en la mesa, sin financiar
        "preseed_pendiente_mm": preseed_pendiente,
        # lo que YA le entro por pre-seed en la ventana, del libro. Con lo
        # pendiente de arriba es lo que `jefe._puede` compara contra el
        # techo acumulado: financiado (irreversible) + pedido en pie
        # (reservado mientras siga en la mesa). Se llamaba
        # `preseed_ciclo_mm` cuando la ventana era el ciclo; el nombre
        # viejo mentia sobre lo unico que hay que entender del techo.
        "preseed_ventana_mm": bus_mod.preseed_en_ventana(
            asientos, cuenta, semanas_ventana),
        # y cuanto cupo devuelve la proxima rodada de la ventana, con el
        # nombre de la semana que sale. Es lo que la deslizante permite
        # decir y la fija no: el jefe lo pone en su freno para que el
        # consejo sea "esperar sirve, y sirve esto" y no un reset
        # invisible. `None`/0 mientras todavia no salga ninguna.
        "preseed_libera_mm": libera_mm,
        "preseed_libera_al_salir": sale_de_ventana,
        # lo que Pedro descarto esta semana. NO cuenta contra ningun techo
        # y no frena nada: alimenta solo el renglon del prompt que arma
        # `decision.py`. Descartar LIBERA el cupo a proposito -- es la
        # salida cuando la bandeja de tres esta llena -- asi que el "no" no
        # puede ser un freno de cupo sin romper eso. El freno que falta es
        # de identidad ("esto ya lo rechazaste"), es una regla aparte, y
        # todavia no se puede escribir: necesita que la propuesta tenga una
        # forma comparable, y hoy lo unico que la identifica es un titulo
        # de prosa libre cortado a 120 caracteres.
        "descartadas_semana": descartadas,
        "gasto_api_ciclo_mm": mercado_mod.gasto_api_ciclo(
            asientos, cuenta, semanas_ciclo) if semanas_ciclo else 0,
        "salidas_semana_mm": salidas_de(asientos, cuenta, [semana]),
        "trabajos": trabajos,
        "propuestas_propias": propias,
        "propuestas_ajenas": ajenas,
        "compuertas_pendientes": sum(
            1 for c in cola.pendientes() if c.get("departamento") == cuenta),
        "capacidad": _capacidad(asientos, suscripciones, semana, ops),
    }
