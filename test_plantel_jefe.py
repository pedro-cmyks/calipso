"""El bucle del jefe, entero, sin un solo modelo (spec seccion 4)."""
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.bus import Bus
from calipso.economia.capacidad import Suscripcion
from calipso.economia.cola import Cola
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.plantel import decision as dec
from calipso.plantel import ficha
from calipso.plantel import ilegibles as ilg
from calipso.plantel import interruptor as it
from calipso.plantel import jefe as j
from calipso.plantel import promesas
from calipso.plantel import reacciones
from calipso.plantel import situacion as sit

TS = "2026-08-26T10:00:00"
W = "2026-W35"

CLAVES = {"cuenta", "accion", "ref", "motivo", "sesgo_pct", "actuo", "freno",
          "resultado"}


class MemoriaFalsa:
    def __init__(self, nucleo="", recientes=()):
        self.recordado = []
        self._nucleo = nucleo
        self._recientes = recientes

    def load_core(self):
        return self._nucleo

    def recent(self, limit=20):
        return list(self._recientes)

    def remember(self, texto, **meta):
        self.recordado.append(texto)


def armar(tmp_path, respuesta="nada\nno hay nada", saldo=400_000,
         presupuesto_semanal_mm=25_000, techo_preseed_mm=0,
         techo_preseed_ciclo_mm=10_000_000, carta=None, proyectos=None):
    eco = tmp_path / "economia"
    eco.mkdir(parents=True, exist_ok=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=presupuesto_semanal_mm,
                             techo_api_ciclo_mm=3_000, agresividad_pct=40,
                             techo_preseed_mm=techo_preseed_mm,
                             techo_preseed_ciclo_mm=techo_preseed_ciclo_mm))
    pt.emitir_semana(k, TS, W, 4_000, 1_000)
    if saldo:
        k.acunar(TS, W, "dep:atlas", saldo, t.SubtipoAcunacion.CAPITAL,
                 {"tipo": "firma_pedro"})
    contratos, eventos = [], []
    ctx = j.Contexto(
        base=tmp_path, kernel=k, registro=r,
        bus=Bus(eco / "bus.jsonl"), cola=Cola(eco / "cola.jsonl"),
        suscripciones={"claude_max": Suscripcion(
            nombre="claude_max", costo_mensual_mm=200_000,
            capacidad_ciclo=2_000, reserva_personal=200,
            costo_api_mm_por_unidad=500)},
        memoria=MemoriaFalsa(),
        pensar=lambda _p: respuesta,
        contratar=lambda s, a, ref, m="", ficha=None: (
            contratos.append((a, ref, m)) or {"ok": True}),
        carta=carta or {"estado": "ausente", "texto": ""},
        proyectos=proyectos or [],
        publicar=lambda evento, **c: eventos.append((evento, c)))
    return ctx, contratos, eventos


def test_la_carta_del_contexto_llega_al_prompt(tmp_path):
    visto = {}
    ctx, _, _ = armar(tmp_path, carta={"estado": "escrita",
                                       "texto": "SOY EL TALLER"})
    ctx.pensar = lambda p: visto.setdefault("p", p) or "nada\nx"
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert "SOY EL TALLER" in visto["p"]


def test_los_proyectos_del_contexto_llegan_filtrados_por_cuenta(tmp_path):
    """El jefe de `dep:atlas` no puede ver los proyectos de otro."""
    visto = {}
    ctx, _, _ = armar(tmp_path, proyectos=[
        {"nombre": "mio", "departamento": "dep:atlas", "linea": "el mio"},
        {"nombre": "ajeno", "departamento": "dep:taller", "linea": "el ajeno"}])
    ctx.pensar = lambda p: visto.setdefault("p", p) or "nada\nx"
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert "el mio" in visto["p"] and "el ajeno" not in visto["p"]


def test_sin_carta_ni_proyectos_el_tic_sigue_andando(tmp_path):
    """Los 44 tests viejos construyen el Contexto sin los campos nuevos."""
    ctx, contratos, _ = armar(tmp_path, "nada\ntodo tranquilo")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "nada" and contratos == []


def test_en_ensayo_decide_y_publica_pero_no_contrata(tmp_path):
    """Es el modo en el que arranca: la unica forma de mirar que decide
    antes de soltarlo con la billetera."""
    ctx, contratos, eventos = armar(
        tmp_path,
        "proponer\nsobre: hueco en precios\npromete: medir\ntarda: corto\n"
        "porque: no sabemos cuanto perdemos")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "proponer"
    assert out["actuo"] is False
    assert "ensayo" in out["freno"]
    assert contratos == []
    assert [e for e, _ in eventos] == ["inicio", "razonando", "fin"]
    assert set(out) == CLAVES


def test_en_vivo_contrata(tmp_path):
    ctx, contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: hay hueco\npromete: medir\ntarda: corto\n"
        "porque: conviene mirarlo")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True
    assert contratos == [("proponer", None, "sobre: hay hueco")]
    assert ctx.memoria.recordado, "no dejo rastro en su memoria"


def test_el_interruptor_apagado_no_deja_ni_pensar(tmp_path):
    """Parar tiene que cortar ANTES del modelo: si no, apagar la fabrica
    sigue costando el tiempo y la RAM de un tic por departamento."""
    llamadas = []
    ctx, _, eventos = armar(tmp_path)
    ctx.pensar = lambda p: llamadas.append(p) or "proponer\nx"
    it.parar(tmp_path)
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "apagado"
    assert set(out) == CLAVES
    assert llamadas == [] and eventos == []


def test_sin_cuerda_no_despierta(tmp_path):
    """El techo de tics tiene que cortar ANTES del modelo, igual que el
    interruptor apagado: si no, un techo movido debajo de `ctx.pensar` deja
    pasar los diez tests igual y el techo deja de ser un techo."""
    llamadas = []
    ctx, _, eventos = armar(tmp_path)
    ctx.pensar = lambda p: llamadas.append(p) or "nada\nno hay nada"
    it.escribir(tmp_path, it.Estado(encendido=True, modo="vivo", techo_tics=1))
    assert j.tic(ctx, "dep:atlas", W)["accion"] != "sin_cuerda"
    llamadas.clear()
    eventos.clear()
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "sin_cuerda"
    assert set(out) == CLAVES
    assert llamadas == [] and eventos == []


def test_sin_saldo_no_actua(tmp_path):
    """El freno duro: no hay prompt que lo evite porque no lo decide el
    prompt. Frena lo que GASTA -trabajar, que contrata sobre un trabajo ya
    financiado- no lo que solo PIDE (eso lo cubren los tests de pre-seed de
    mas abajo: proponer y pedir no gastan un peso)."""
    ctx, contratos, _ = armar(tmp_path, "trabajar p1\ndale", saldo=0)
    ctx.bus.alta(TS, W, "p1", "dep:atlas", "ya en marcha", 1_000, 2_000,
                {"gasto_max_mm": 5_000})
    ctx.bus.marcar(TS, W, "p1", "financiada")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False and "saldo" in out["freno"]
    assert contratos == []


def test_sin_saldo_si_puede_proponer(tmp_path):
    """Freno 1 verificado y corregido: el chequeo de saldo estaba ANTES de
    la rama de `proponer`, asi que un departamento sin plata no podia ni
    pedir plata. Proponer no gasta -solo escribe en el bus- asi que el
    freno de saldo no le corresponde."""
    ctx, contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: necesito arrancar\npromete: construir\n"
        "tarda: corto\nporque: sin capital no arranca", saldo=0)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True
    assert contratos == [("proponer", None, "sobre: necesito arrancar")]


def test_presupuesto_semanal_cero_no_frena_proponer_por_agresividad(tmp_path):
    """Freno 2 verificado y corregido: con presupuesto_semanal_mm=0 (un
    departamento recien dado de alta), el tope de agresividad daba
    25.000*0//100... no, daba presupuesto*agresividad//100 = 0, y
    `salidas_semana_mm >= 0` es siempre verdadero -nunca podia proponer, y
    el freno registrado hablaba de agresividad, que no tenia nada que ver."""
    ctx, contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: arranco de cero\npromete: construir\n"
        "tarda: corto\nporque: sin presupuesto todavia",
        saldo=100_000, presupuesto_semanal_mm=0)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True
    assert contratos == [("proponer", None, "sobre: arranco de cero")]


def test_pedir_es_la_ronda_preseed_y_no_gasta(tmp_path):
    """El jefe ahora puede decir "pido un stake de N": `pedir <monto>` es
    una accion nueva, separada de `proponer`, para que el modelo declare
    cuanto pide sin que nadie tenga que inventarle una formula."""
    ctx, contratos, _ = armar(tmp_path, "pedir 50000\nnecesito arrancar",
                              saldo=0, presupuesto_semanal_mm=0,
                              techo_preseed_mm=50_000)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True
    assert contratos == [("pedir", "50000", "necesito arrancar")]


def test_sin_techo_de_preseed_el_pedido_no_llega_al_bus(tmp_path):
    """El monto del pre-seed sale de la perilla `techo_preseed_mm`, no del
    modelo. En cero, Pedro todavia no dijo cuanto puede pedir este
    departamento: el jefe puede decidir `pedir` -sigue en el menu- pero el
    freno corta antes de contratar, y por lo tanto antes del bus y antes de
    la memoria. Sin este freno el jefe quemaria un tic por semana en un
    no-op que igual se anotaria como que actuo."""
    ctx, contratos, _ = armar(tmp_path, "pedir 50000\nnecesito arrancar",
                              saldo=0, presupuesto_semanal_mm=0,
                              techo_preseed_mm=0)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "pedir"      # decidio bien
    assert out["actuo"] is False         # pero no se ejecuto
    assert "techo de pre-seed" in out["freno"]
    assert contratos == []
    assert ctx.memoria.recordado == []


def test_pedir_sin_monto_valido_cae_en_nada(tmp_path):
    """El parser sigue siendo estricto con la forma: pedir sin numero, o con
    algo que no es un entero positivo, no pide nada."""
    ctx, contratos, _ = armar(tmp_path, "pedir mucho\nporfa", saldo=0)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "nada"
    assert contratos == []


def test_pedir_tambien_respeta_el_techo_de_propuestas(tmp_path):
    """El techo de propuestas sin financiar es compartido entre `proponer`
    y `pedir`: sin esto, un departamento sin plata podria llenar el bus de
    pedidos de pre-seed a 200 tics por semana igual que con propuestas de
    trabajo."""
    ctx, contratos, _ = armar(tmp_path, "pedir 10000\notro pedido",
                              saldo=0, presupuesto_semanal_mm=0)
    for i in range(j.TECHO_PROPUESTAS):
        ctx.bus.alta(TS, W, f"p{i}", "dep:atlas", f"pedido {i}", 1_000, 2_000,
                    {"gasto_max_mm": 5_000}, tipo="preseed")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False
    assert "propuestas sin financiar" in out["freno"]
    assert contratos == []


def test_dia_uno_pide_preseed_en_el_bus_y_pedro_lo_financia(tmp_path):
    """El entregable: un departamento con saldo cero y presupuesto cero -el
    estado real del dia 1, recien dado de alta- ahora si puede publicar su
    pedido de pre-seed en el bus, y despues de que Pedro lo financia contra
    el tesoro (no contra la billetera de otro departamento), la plata esta
    en SU cuenta (no en trabajo:<id>: un pre-seed no es un trabajo)."""
    from calipso.economia import bus as bus_mod
    from calipso.economia import mercado as mkt

    ctx, contratos, _ = armar(tmp_path, "pedir 200000\narrancamos de cero",
                              saldo=0, presupuesto_semanal_mm=0,
                              techo_preseed_mm=200_000)
    it.poner_modo(tmp_path, "vivo")

    # 1. el dia 1: sin un peso y sin presupuesto semanal, publica su pedido.
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True
    assert out["accion"] == "pedir" and out["ref"] == "200000"
    assert contratos == [("pedir", "200000", "arrancamos de cero")]

    # el "contratar" de produccion vive en server.py (fuera de este scope);
    # aca se ejercita el mismo camino que va a tomar: una propuesta de
    # tipo="preseed" en el bus, con el monto que el jefe pidio.
    propuesta_id = "atlas-preseed-1"
    ctx.bus.alta(TS, W, propuesta_id, "dep:atlas", "arrancamos de cero",
                200_000, 200_000, {"gasto_max_mm": 200_000, "semanas_max": 8},
                tipo="preseed")
    assert bus_mod.aportes(ctx.kernel.libro.asientos(), propuesta_id) == {}
    assert ctx.bus.estado(propuesta_id) == "alta"
    assert [p["id"] for p in
           sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                        ctx.suscripciones, W, "dep:atlas")["propuestas_propias"]
           ] == [propuesta_id]

    # 2. Pedro elige: lo financia contra el tesoro, no contra otro
    # departamento.
    ctx.kernel.acunar(TS, W, t.TESORO, 200_000, t.SubtipoAcunacion.CAPITAL,
                      {"tipo": "firma_pedro"})
    m = mkt.Mercado(ctx.kernel, ctx.registro, ctx.suscripciones)
    bus_mod.financiar(m, ctx.bus, TS, W, propuesta_id, t.TESORO, 200_000)

    # 3. la plata esta en SU cuenta, no en trabajo:<id>, y el pedido queda
    # CERRADO: la ronda ya se pago, no hay nada mas que decidir sobre ella
    # y por eso sale de la mesa y de `activas()`.
    assert ctx.bus.estado(propuesta_id) == "cerrada"
    assert ctx.kernel.saldo("dep:atlas") == 200_000
    assert ctx.kernel.saldo(bus_mod.cuenta_trabajo(propuesta_id)) == 0

    # y no cuenta contra el umbral del mandato semanal: un pre-seed no es
    # presupuesto (spec de direccion.asignado_semana).
    from calipso.economia import direccion
    assert direccion.asignado_semana(ctx.kernel.libro.asientos(),
                                     "dep:atlas", W) == 0


def test_la_agresividad_frena_proponer_pero_no_trabajar(tmp_path):
    """La perilla deja de ser decoracion: con el presupuesto de la semana ya
    comprometido, el departamento no abre apuestas nuevas — pero sigue
    pudiendo terminar lo que empezo."""
    ctx, contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: otra apuesta\npromete: construir\ntarda: corto\n"
        "porque: probar algo nuevo")
    it.poner_modo(tmp_path, "vivo")
    # agresividad 40% de 25.000 = 10.000; sacamos 12.000 de la semana
    ctx.kernel.destruir(TS, W, "dep:atlas", 12_000, motivo="api")
    out1 = j.tic(ctx, "dep:atlas", W)
    assert out1["actuo"] is False
    # la ficha es valida, asi que si esto pasara por accidente (por ejemplo
    # porque la valvula la interceptara antes de llegar a `_puede`) el freno
    # diria "ilegible" y no "agresividad": esta linea es la que prueba que
    # el freno de verdad se ejercito.
    assert "agresividad" in out1["freno"]
    ctx.bus.alta(TS, W, "p1", "dep:atlas", "ya en marcha", 1_000, 2_000,
                {"gasto_max_mm": 5_000})
    ctx.bus.marcar(TS, W, "p1", "financiada")
    ctx.pensar = lambda _p: "trabajar p1\nya esta financiado"
    assert j.tic(ctx, "dep:atlas", W)["actuo"] is True


def test_nada_no_contrata_pero_igual_se_publica(tmp_path):
    """Invariante 6: un jefe que decide en silencio es indistinguible de uno
    colgado."""
    ctx, contratos, eventos = armar(tmp_path, "nada\ntodo tranquilo")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "nada" and contratos == []
    assert [e for e, _ in eventos] == ["inicio", "razonando", "fin"]


def test_un_modelo_que_revienta_no_voltea_el_tic(tmp_path):
    ctx, contratos, eventos = armar(tmp_path)
    def explotar(_p):
        raise RuntimeError("ollama caido")
    ctx.pensar = explotar
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "nada" and "ollama caido" in out["motivo"]
    assert contratos == []
    assert ("fin", {"resultado": "error"}) in eventos


def test_un_departamento_personal_corre_el_mismo_bucle(tmp_path):
    """Spec seccion 8: `trabajo` y `finanzas` llevan el mismo jefe. Lo que
    cambia es quien paga, no el bucle — y eso se decide en el contratista,
    no aca."""
    eco = tmp_path / "economia"
    eco.mkdir(parents=True, exist_ok=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL,
                             presupuesto_semanal_mm=5_000, agresividad_pct=50,
                             explorar_explotar_pct=70))
    pt.emitir_semana(k, TS, W, 4_000, 1_000)
    k.acunar(TS, W, "personal:finanzas", 50_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    contratos = []
    ctx = j.Contexto(base=tmp_path, kernel=k, registro=r,
                     bus=Bus(eco / "bus.jsonl"), cola=Cola(eco / "cola.jsonl"),
                     suscripciones={}, memoria=MemoriaFalsa(),
                     pensar=lambda _p: (
                         "proponer\nsobre: ordenar los gastos del mes\n"
                         "promete: arreglar\ntarda: corto\n"
                         "porque: ayuda a planificar"),
                     contratar=lambda s, a, ref, m="", ficha=None: (
                         contratos.append((a, ref, m))),
                     publicar=lambda e, **c: None)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "personal:finanzas", W)
    assert out["accion"] == "proponer" and out["actuo"] is True
    assert contratos == [("proponer", None, "sobre: ordenar los gastos del mes")]
    # sin suscripciones el sesgo es la perilla pelada, sin modular por precio
    # (70, no 50: si el modulo leyera agresividad_pct en vez de
    # explorar_explotar_pct, este assert lo agarraria igual)
    assert out["sesgo_pct"] == dec.sesgo_efectivo(70, 0, 0) == 70


def test_un_modelo_que_alucina_no_gasta(tmp_path):
    ctx, contratos, _ = armar(tmp_path, "Claro! Con gusto te ayudo con eso.")
    it.poner_modo(tmp_path, "vivo")
    assert j.tic(ctx, "dep:atlas", W)["accion"] == "nada"
    assert contratos == []


def test_comentar_en_ensayo_llega_a_la_memoria(tmp_path):
    """Opinar no gasta, asi que ni siquiera el modo ensayo lo frena — y es
    justo el modo en el que arranca la fabrica, donde ver el nucleo
    formarse importa mas."""
    ctx, contratos, _ = armar(tmp_path, "comentar p2\nno me cierra el precio")
    ctx.bus.alta(TS, W, "p2", "dep:otro", "propuesta ajena", 1_000, 2_000,
                {"gasto_max_mm": 5_000})
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "comentar" and out["actuo"] is True
    assert contratos == [("comentar", "p2", "no me cierra el precio")]
    assert ctx.memoria.recordado, "no dejo rastro en su memoria"


def test_comentar_no_le_toca_un_pelo_al_bus(tmp_path):
    """Guardia de regresion, no cobertura del diseno de `comentar` (eso lo
    cubre test_comentar_en_ensayo_llega_a_la_memoria): el `contratar`
    inyectado en este arnes no toca el bus para ninguna accion, asi que este
    test pasaria igual con `_puede("comentar")` roto. Lo que vigila es que
    nadie agregue mas adelante una llamada directa al bus dentro de
    `jefe.py` — la superficie de comentarios que el docstring del modulo
    dice que no existe."""
    ctx, _, _ = armar(tmp_path, "comentar p2\nno me cierra el precio")
    j.tic(ctx, "dep:atlas", W)
    assert ctx.bus.ids() == []


def test_memoria_que_revienta_no_borra_la_contratacion(tmp_path):
    """Si `remember` revienta DESPUES de que `contratar` ya salio bien y ya
    se cobro, decir `actuo: False` seria mentir sobre plata que salio:
    perder la nota es feo, mentir sobre la plata es peor."""
    class MemoriaQueRevienta(MemoriaFalsa):
        def remember(self, texto, **meta):
            raise RuntimeError("disco lleno")

    ctx, contratos, eventos = armar(
        tmp_path,
        "proponer\nsobre: hay hueco\npromete: medir\ntarda: corto\n"
        "porque: hace falta mirarlo")
    ctx.memoria = MemoriaQueRevienta()
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True
    assert out["resultado"] == {"ok": True}
    assert contratos == [("proponer", None, "sobre: hay hueco")]
    assert ("fin", {"resultado": "error"}) in eventos


def test_la_ficha_no_el_motivo_crudo_llega_al_contratista(tmp_path):
    """Lo que aterriza en el contratista es la FICHA, no el motivo crudo del
    parser: esta prueba afirmaba lo contrario -que el titulo del bus era el
    motivo tal cual salio de `dec.parsear`- y eso es justo lo que la
    gramatica de proponer (seccion 7 del spec) deroga."""
    capturado = []
    ctx, _contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: hueco en precios de GPU\npromete: medir\n"
        "tarda: corto\nporque: hay que cuantificarlo")
    ctx.contratar = lambda s, a, ref, m="", ficha=None: (
        capturado.append(ficha) or {"ok": True})
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert capturado and capturado[0] is not None
    assert capturado[0]["sobre"] == "hueco en precios de GPU"
    assert capturado[0]["promete"] == "medir"
    assert capturado[0]["tarda"] == "corto"


def test_una_ficha_ilegible_no_contrata_pero_deja_aviso(tmp_path):
    """La valvula: la prosa que no entra en la ficha no cae en `nada`, cae
    en un aviso con la prosa cruda adentro."""
    ctx, contratos, _ = armar(tmp_path, "proponer\nhay hueco en precios")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "proponer"
    assert out["actuo"] is False
    assert "ilegible" in out["freno"]
    assert contratos == []
    filas = ilg.colapsados(tmp_path, W)
    # la fila lleva la respuesta ENTERA que salio del modelo, no solo el
    # segundo renglon (`dec.parsear` define `motivo` como `lineas[1]`, y
    # con eso se perderia contenido de una prosa mas larga)
    assert len(filas) == 1
    assert filas[0]["crudo"] == "proponer\nhay hueco en precios"


def test_una_ficha_ilegible_SI_escribe_memoria(tmp_path):
    """El arreglo de la semana congelada. `nada` no anota -el modelo eligio
    no hacer nada- y un freno tampoco -la maquina lo paro-. Pero una ficha
    ilegible es el modelo intentando y fallando: sin anotarla, el prompt del
    tic siguiente es identico, y a temperatura 0 la respuesta tambien. El
    primer tic que no parsea le termina la semana al departamento."""
    ctx, _, _ = armar(tmp_path, "proponer\nhay hueco en precios")
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert ctx.memoria.recordado != []


def test_nada_sigue_sin_escribir_memoria(tmp_path):
    """El otro lado de la distincion: elegir no hacer nada no es fallar."""
    ctx, _, _ = armar(tmp_path, "nada\ntodo tranquilo")
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert ctx.memoria.recordado == []


def test_una_ficha_buena_contrata_y_le_llega_al_contratista(tmp_path):
    ctx, contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: el radar de precios\npromete: descartar\n"
        "tarda: corto\nporque: no rindio")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "proponer" and out["actuo"] is True
    assert contratos and contratos[0][0] == "proponer"


def test_el_pulso_y_la_memoria_muestran_el_titulo_no_el_nombre_del_campo(tmp_path):
    """Con `dec.parsear` sin cambios, `motivo` es la SEGUNDA linea de la
    respuesta -el renglon `sobre: ...` en una ficha bien formada- y sin
    este arreglo el pulso mostraba el nombre de un campo interno en vez
    del titulo que Pedro tiene que leer. En modo ensayo, que es el
    default, ese evento es lo UNICO que Pedro ve de una propuesta."""
    texto = ("proponer\nsobre: el radar de precios\npromete: descartar\n"
             "tarda: corto\nporque: no rindio")
    ctx, _, eventos = armar(tmp_path, texto)
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    esperado = ficha.titulo_de(ficha.parsear_ficha(texto))
    razonando = next(c for e, c in eventos if e == "razonando")
    assert esperado in razonando["texto"]
    assert "sobre: el radar de precios" not in razonando["texto"]
    assert any(esperado in nota for nota in ctx.memoria.recordado)


def test_sin_ficha_el_pulso_sigue_mostrando_motivo(tmp_path):
    """Las otras cuatro acciones no tienen ficha: ahi no cambia nada."""
    ctx, _, eventos = armar(tmp_path, "nada\ntodo tranquilo")
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    razonando = next(c for e, c in eventos if e == "razonando")
    assert "todo tranquilo" in razonando["texto"]


def test_un_aviso_que_revienta_no_voltea_el_tic(tmp_path, monkeypatch):
    """Mismo trato que la memoria: el rastro no puede volverse una forma de
    tumbar el tic. Sin su propio try/except, el `except Exception` de `tic`
    lo reporta como 'reviento actuando'."""
    def explota(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(ilg, "anotar", explota)
    ctx, contratos, eventos = armar(tmp_path, "proponer\nhay hueco")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "proponer" and out["actuo"] is False
    assert "reviento" not in (out["motivo"] or "")
    assert "disco lleno" in out["motivo"]
    # mismo trato que `test_memoria_que_revienta_no_borra_la_contratacion`:
    # el `fin` tiene que salir como error, o esta linea se puede borrar del
    # codigo de produccion y la suite sigue en verde
    assert ("fin", {"resultado": "error"}) in eventos


def test_trabajar_con_id_inventado_no_actua(tmp_path):
    """El jefe solo puede referirse a lo que su propia situacion le mostro:
    un modelo de 3b nombra ids que no existen -se lo vio contestar
    "trabajar 1" con la lista de trabajos vivos vacia."""
    ctx, contratos, _ = armar(tmp_path, "trabajar p9\nsigo con esto")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False
    assert "no existe" in out["freno"] and "p9" in out["freno"]
    assert contratos == []


def test_comentar_con_id_inventado_no_actua(tmp_path):
    """Comentar es gratis, pero no gratis para inventar un id: si no esta
    en ninguna de las tres listas que el jefe vio (propuestas propias,
    ajenas o trabajos), se frena igual."""
    ctx, contratos, _ = armar(tmp_path, "comentar p9\nesto no me cierra")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False
    assert "no existe" in out["freno"] and "p9" in out["freno"]
    assert contratos == []

def test_el_techo_de_propuestas_frena_proponer(tmp_path):
    """A 200 tics por semana, el modelo ve sus propias propuestas sin
    financiar y propone otra igual: el bus de Pedro se llena de duplicados
    y deja de servir para lo unico que sirve, que Pedro elija."""
    ctx, contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: otra idea mas\npromete: construir\ntarda: corto\n"
        "porque: seguir probando")
    for i in range(j.TECHO_PROPUESTAS):
        ctx.bus.alta(TS, W, f"p{i}", "dep:atlas", f"propuesta {i}", 1_000,
                    2_000, {"gasto_max_mm": 5_000})
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False
    assert "propuestas sin financiar" in out["freno"]
    assert contratos == []


def test_descartar_una_propuesta_destraba_el_techo(tmp_path):
    """La razon de ser de todo esto (spec seccion 8): con la bandeja llena el
    jefe queda frenado, y descartar una -la salida que le da la mesa de
    Pedro- tiene que devolverle el lugar para volver a proponer. El
    escalon de abajo (que la propuesta desaparezca de propuestas_propias) ya
    esta cubierto en test_plantel_situacion.py; esto prueba el circuito
    entero via j.tic."""
    from calipso.economia import bus as bus_mod
    ctx, contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: otra idea mas\npromete: construir\ntarda: corto\n"
        "porque: seguir probando")
    for i in range(j.TECHO_PROPUESTAS):
        ctx.bus.alta(TS, W, f"p{i}", "dep:atlas", f"propuesta {i}", 1_000,
                    2_000, {"gasto_max_mm": 5_000})
    it.poner_modo(tmp_path, "vivo")
    frenado = j.tic(ctx, "dep:atlas", W)
    assert frenado["actuo"] is False
    assert "propuestas sin financiar" in frenado["freno"]
    assert contratos == []

    bus_mod.descartar(ctx.bus, TS, W, "p0")

    destrabado = j.tic(ctx, "dep:atlas", W)
    assert destrabado["actuo"] is True
    assert contratos == [("proponer", None, "sobre: otra idea mas")]


def test_con_menos_propuestas_que_el_techo_sigue_pudiendo_proponer(tmp_path):
    """El techo no puede volverse un cero disfrazado: por debajo, proponer
    sigue pasando."""
    ctx, contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: otra idea mas\npromete: construir\ntarda: corto\n"
        "porque: seguir probando")
    for i in range(j.TECHO_PROPUESTAS - 1):
        ctx.bus.alta(TS, W, f"p{i}", "dep:atlas", f"propuesta {i}", 1_000,
                    2_000, {"gasto_max_mm": 5_000})
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True
    assert contratos == [("proponer", None, "sobre: otra idea mas")]


def test_el_techo_de_propuestas_no_tapa_la_agresividad(tmp_path):
    """El chequeo nuevo va primero por ser mas barato, pero no puede dejar
    inalcanzable el de agresividad: con pocas propuestas en pie, la perilla
    sigue frenando proponer y el freno lo sigue diciendo."""
    ctx, contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: otra apuesta\npromete: construir\ntarda: corto\n"
        "porque: probar algo nuevo")
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "una nomas", 1_000, 2_000,
                {"gasto_max_mm": 5_000})
    it.poner_modo(tmp_path, "vivo")
    # agresividad 40% de 25.000 = 10.000; sacamos 12.000 de la semana
    ctx.kernel.destruir(TS, W, "dep:atlas", 12_000, motivo="api")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False
    assert "agresividad" in out["freno"]
    assert contratos == []


def test_el_techo_de_propuestas_no_afecta_comentar_ni_nada(tmp_path):
    """El techo nuevo es especifico de `proponer`: con la bandeja llena,
    `comentar` sobre un id real y `nada` siguen sin verse afectados."""
    ctx, contratos, _ = armar(tmp_path, "nada\ntodo tranquilo")
    for i in range(j.TECHO_PROPUESTAS):
        ctx.bus.alta(TS, W, f"p{i}", "dep:atlas", f"propuesta {i}", 1_000,
                    2_000, {"gasto_max_mm": 5_000})
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "nada" and out["freno"] == "no hay nada que hacer"

    ctx.pensar = lambda _p: "comentar p0\nopino sobre esta"
    out2 = j.tic(ctx, "dep:atlas", W)
    assert out2["actuo"] is True
    assert contratos == [("comentar", "p0", "opino sobre esta")]


def test_el_jefe_le_pasa_las_recientes_al_prompt(tmp_path):
    """Sin esto el jefe le pregunta al modelo desde cero en cada tic y
    propone lo mismo una y otra vez -se lo vio pasar ocho de ocho veces con
    el modelo real, porque no tiene idea de lo que decidio antes."""
    prompts = []
    ctx, _, _ = armar(tmp_path)
    ctx.memoria = MemoriaFalsa(recientes=["proponer: radar de precios"])
    ctx.pensar = lambda p: prompts.append(p) or "nada\nnada nuevo"
    j.tic(ctx, "dep:atlas", W)
    assert prompts and "radar de precios" in prompts[0]


def test_una_memoria_cuyo_recent_revienta_no_propaga(tmp_path):
    """El armado del prompt sigue blindado: una falla de Chroma al leer lo
    episodico no puede reventar el tic."""
    class MemoriaQueRevientaAlLeer(MemoriaFalsa):
        def recent(self, limit=20):
            raise RuntimeError("chroma caido")

    ctx, contratos, _ = armar(tmp_path)
    ctx.memoria = MemoriaQueRevientaAlLeer()
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["freno"] == "fallo antes de pensar"
    assert "chroma caido" in out["motivo"]
    assert contratos == []


def test_el_preseed_es_para_arrancar_sin_plata(tmp_path):
    """El techo ACUMULADO. `techo_preseed_mm` recortaba cada pedido y nada
    miraba el total: el unico freno de caudal (TECHO_PROPUESTAS) no ve los
    pre-seed ya financiados -`situacion` los saca de las dos listas- asi
    que cada financiacion vaciaba el contador y habilitaba otras tres
    rondas. El techo real terminaba siendo `techo_preseed_mm` x 200 tics
    por semana mientras Pedro siguiera tocando financiar."""
    ctx, contratos, _ = armar(tmp_path, "pedir 50000\nmas capital",
                              saldo=100_000, presupuesto_semanal_mm=0,
                              techo_preseed_mm=50_000)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "pedir"      # decidio bien
    assert out["actuo"] is False
    assert "arrancar sin plata" in out["freno"]
    assert contratos == []


def test_los_pedidos_en_pie_cuentan_contra_el_techo_de_la_ronda(tmp_path):
    """Y lo que ya pidio cuenta igual que lo que ya tiene: sin esto,
    publicar tres pedidos y que Pedro los financie a los tres da tres veces
    el techo -- el freno de TECHO_PROPUESTAS deja pasar los tres, porque
    mide cantidad de propuestas y no plata."""
    ctx, contratos, _ = armar(tmp_path, "pedir 50000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=50_000)
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 50_000, 50_000,
                {"gasto_max_mm": 50_000}, tipo="preseed")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False
    assert "en pie" in out["freno"]      # y no el de "3 propuestas"
    assert contratos == []


def test_lo_que_pedro_descarto_le_llega_al_jefe(tmp_path, monkeypatch):
    """Descartar libera el cupo A PROPOSITO (spec seccion 8: con la bandeja
    llena el jefe queda frenado, y la salida que le da la mesa de Pedro
    tiene que devolverle el lugar), asi que el "no" NO puede ser un freno
    sin romper eso. Lo que si faltaba: que el "no" llegue -- y ahora llega
    por el registro durable (`reacciones.anotar`, que escribe la mesa) y no
    por `situacion`: `jefe.tic` lo lee con el nombre PELADO del `dep:` (el
    mismo criterio que la carta) y se lo pasa a `dec.prompt`."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    visto = {}
    ctx, _contratos, _ = armar(tmp_path)
    ctx.pensar = lambda p: visto.setdefault("p", p) or "nada\nx"
    reacciones.anotar("atlas", "descarto",
                      {"sobre": "radar de precios", "clave": "radar+precios",
                       "promete": "medir", "tarda": "corto"},
                      "muy caro", "p0")
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert "Pedro reacciono" in visto["p"]
    assert "radar de precios" in visto["p"]


def test_una_reaccion_de_otra_semana_sigue_pesando(tmp_path, monkeypatch):
    """A diferencia del viejo `descartadas_semana` (que se armaba de nuevo
    en cada tic y solo con lo de la semana en curso), el registro durable
    NO se evapora al cambiar de semana: una reaccion anotada en W35 le
    sigue llegando al jefe en W36."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    visto = {}
    ctx, _contratos, _ = armar(tmp_path)
    ctx.pensar = lambda p: visto.setdefault("p", p) or "nada\nx"
    reacciones.anotar("atlas", "descarto",
                      {"sobre": "radar de precios", "clave": "radar+precios",
                       "promete": "medir", "tarda": "corto"},
                      "muy caro", "p0")
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", "2026-W36")
    assert "Pedro reacciono" in visto["p"]
    assert "radar de precios" in visto["p"]


def test_un_tema_vetado_con_no_mas_no_llega_al_bus(tmp_path, monkeypatch):
    """El piso determinista del "no mas": si Pedro veto la CLAVE de un tema
    en este departamento, la propuesta no llega al bus pase lo que pase con
    el modelo -- ni reencuadrando la promesa (`medir` por `acelerar` aca)
    la esquiva, porque la identidad sale solo del `sobre`."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    reacciones.anotar(
        "atlas", "no_mas",
        {"sobre": "el radar de precios",
         "clave": ficha.normalizar("el radar de precios"),
         "promete": "medir", "tarda": "corto"},
        "no mas", "p0")
    # el modelo del jefe propone el MISMO tema, reencuadrado con otra
    # promesa: misma clave -> vetada igual.
    crudo = ("proponer\nsobre: el radar de precios\npromete: acelerar\n"
             "tarda: corto\nporque: x")
    ctx, contratos, _ = armar(tmp_path, crudo)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False
    assert "vetast" in (out["freno"] + out["motivo"]).lower()
    assert contratos == []


def test_un_tema_no_vetado_si_llega(tmp_path, monkeypatch):
    """El otro lado del piso: sin un `no_mas` sobre esa clave (aca hay uno,
    pero sobre otra), la propuesta llega al bus como siempre."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    reacciones.anotar(
        "atlas", "no_mas",
        {"sobre": "otro tema", "clave": ficha.normalizar("otro tema"),
         "promete": "medir", "tarda": "corto"},
        "no mas", "p0")
    crudo = ("proponer\nsobre: el radar de precios\npromete: descartar\n"
             "tarda: corto\nporque: no rindio")
    ctx, contratos, _ = armar(tmp_path, crudo)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "proponer" and out["actuo"] is True
    assert contratos and contratos[0][0] == "proponer"


def test_el_prompt_lleva_el_standing_de_promesas(tmp_path, monkeypatch):
    """El jefe lee su propio historial de promesas (el PvP, Tarea 1) con el
    mismo criterio que lee las reacciones: nombre PELADO del `dep:`, dentro
    del mismo try de fallo cerrado. Aca se anotan dos veredictos -uno
    cumplido, uno no- y se verifica que `dec.prompt` los reciba."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    visto = {}
    ctx, _contratos, _ = armar(tmp_path)
    ctx.pensar = lambda p: visto.setdefault("p", p) or "nada\nx"
    promesas.anotar("atlas", "atlas-1",
                    {"sobre": "el radar de precios",
                     "clave": ficha.normalizar("el radar de precios"),
                     "promete": "medir", "tarda": "corto"},
                    True, "cumplio a tiempo")
    promesas.anotar("atlas", "atlas-2",
                    {"sobre": "otro tema",
                     "clave": ficha.normalizar("otro tema"),
                     "promete": "medir", "tarda": "corto"},
                    False, "no llego")
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert "historial de promesas" in visto["p"].lower()
    assert "1" in visto["p"] and "2" in visto["p"]


# -- el segundo techo del pre-seed: el acumulado por CICLO -----------------

def test_sin_techo_de_ciclo_el_jefe_no_pide(tmp_path):
    """Cero es "todavia no", no "sin limite": la misma regla que la otra
    perilla de pre-seed y que `techo_api_ciclo_mm`. Un departamento con
    techo por pedido puesto y techo de ciclo en cero no pide -- ruidoso a
    proposito, porque la unica forma de que un techo no se cruce en
    silencio es que no exista un default que autorice nada."""
    ctx, contratos, _ = armar(tmp_path, "pedir 10000\nnecesito arrancar",
                              saldo=0, presupuesto_semanal_mm=0,
                              techo_preseed_mm=50_000,
                              techo_preseed_ciclo_mm=0)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "pedir"       # decidio bien
    assert out["actuo"] is False
    assert "techo de pre-seed acumulado" in out["freno"]
    assert contratos == []
    assert ctx.memoria.recordado == []


def test_lo_ya_financiado_en_el_ciclo_frena_al_jefe(tmp_path):
    """Lo FINANCIADO cuenta contra el techo acumulado, y cuenta aunque la
    propuesta ya no este en ninguna lista: `situacion` saca los pre-seed
    pagados de las dos, asi que el unico rastro es el libro. Sin esto, el
    jefe gasta su tic publicando un pedido que `bus.financiar` va a
    rechazar con Pedro ya mirandolo."""
    from calipso.economia import bus as bus_mod
    from calipso.economia import mercado as mkt

    # los numeros aislan el techo NUEVO: con 20.000 en la billetera y un
    # techo por pedido de 50.000, el freno viejo ("arrancar sin plata") no
    # llega a disparar. El unico que puede frenar aca es el del ciclo.
    ctx, contratos, _ = armar(tmp_path, "pedir 50000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=50_000,
                              techo_preseed_ciclo_mm=20_000)
    ctx.kernel.acunar(TS, W, t.TESORO, 500_000, t.SubtipoAcunacion.CAPITAL,
                      {"tipo": "firma_pedro"})
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 20_000, 20_000,
                {"gasto_max_mm": 20_000}, tipo="preseed")
    m = mkt.Mercado(ctx.kernel, ctx.registro, ctx.suscripciones)
    bus_mod.financiar(m, ctx.bus, TS, W, "p0", t.TESORO, 20_000)

    # la propuesta quedo `cerrada`: no esta ni en propuestas_propias ni en
    # trabajos, y sin embargo esos 50.000 ya entraron
    s = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                     ctx.suscripciones, W, "dep:atlas")
    assert s["propuestas_propias"] == [] and s["trabajos"] == []
    assert s["preseed_ventana_mm"] == 20_000

    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False
    assert "techo de la ventana" in out["freno"]
    assert contratos == []


def test_lo_pedido_en_pie_tambien_cuenta_contra_el_techo_del_ciclo(tmp_path):
    """Las DOS cosas cuentan del lado del jefe, y por motivos distintos. Lo
    financiado ya salio del tesoro y el libro no lo desescribe: piso duro.
    Lo pedido todavia no es plata, pero es plata que Pedro suelta con un
    toque, asi que vale como reserva mientras siga en pie -- sin eso,
    publicar dos pedidos que juntos pasan el techo es gratis y el freno
    llega recien en la mesa. Aca el departamento no tiene saldo (asi que el
    techo POR PEDIDO no lo frena) y sin embargo no pide."""
    ctx, contratos, _ = armar(tmp_path, "pedir 30000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=100_000,
                              techo_preseed_ciclo_mm=40_000)
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 40_000, 40_000,
                {"gasto_max_mm": 40_000}, tipo="preseed")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False
    assert "techo de la ventana" in out["freno"]
    assert contratos == []


def test_descartar_le_devuelve_el_cupo_del_ciclo_al_jefe(tmp_path):
    """Lo pedido es una RESERVA, no un cargo: el "no" de Pedro la libera
    entera. Es la misma decision de spec que ya vale para el techo de
    propuestas -- descartar existe justamente para que el jefe frenado
    vuelva a tener lugar-- y el techo nuevo no la puede romper."""
    from calipso.economia import bus as bus_mod

    ctx, contratos, _ = armar(tmp_path, "pedir 30000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=100_000,
                              techo_preseed_ciclo_mm=40_000)
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 40_000, 40_000,
                {"gasto_max_mm": 40_000}, tipo="preseed")
    bus_mod.descartar(ctx.bus, TS, W, "p0")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True, out["freno"]
    assert contratos == [("pedir", "30000", "otra ronda")]


def test_el_techo_del_ciclo_no_revienta_con_la_semana_sin_abrir(tmp_path):
    """El jefe corre desatendido y no puede reventar por una semana que
    todavia no emitio su PT -- que es el estado de TODO lunes, porque abrir
    la semana es un boton manual. Y no solo no revienta: el acumulado del
    ciclo tiene que seguir contando, o el techo se reseteaba solo cada vez
    que Pedro tardaba en abrir."""
    from calipso.economia import bus as bus_mod
    from calipso.economia import mercado as mkt

    ctx, contratos, _ = armar(tmp_path, "pedir 50000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=50_000,
                              techo_preseed_ciclo_mm=20_000)
    ctx.kernel.acunar(TS, W, t.TESORO, 500_000, t.SubtipoAcunacion.CAPITAL,
                      {"tipo": "firma_pedro"})
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 20_000, 20_000,
                {"gasto_max_mm": 20_000}, tipo="preseed")
    m = mkt.Mercado(ctx.kernel, ctx.registro, ctx.suscripciones)
    bus_mod.financiar(m, ctx.bus, TS, W, "p0", t.TESORO, 20_000)

    # el lunes siguiente: nadie abrio 2026-W36 todavia
    siguiente = "2026-W36"
    s = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                     ctx.suscripciones, siguiente, "dep:atlas")
    assert s["preseed_ventana_mm"] == 20_000, "la ventana se reseteo sola"

    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", siguiente)
    assert out["freno"] != "fallo antes de decidir", out["motivo"]
    assert out["actuo"] is False
    assert "techo de la ventana" in out["freno"]
    assert contratos == []


def test_el_freno_del_ciclo_no_le_manda_a_esperar_lo_que_no_llega(tmp_path):
    """El consejo del freno tiene que ser el que desbloquea de verdad.

    Lo FINANCIADO caduca por si solo: `preseed_en_ventana` mira las semanas
    de la ventana deslizante, asi que sale cuando la semana en que entro
    queda atras. Lo PEDIDO no sale de ahi: mientras siga en pie descuenta
    del techo de la ventana en la que Pedro lo pague, asi que ninguna
    rodada lo suelta y mandarlo a esperar es un consejo falso -- la ventana
    siguiente saca el mismo mensaje, palabra por palabra.

    La reserva en si NO se toca: contarla es correcto, porque ese pedido se
    financia contra el cupo de la ventana en la que Pedro lo pague (lo
    comprueba la ultima parte del test). Lo que estaba mal era el consejo.

    Las dos semanas del bucle son los dos extremos de la ventana del propio
    pedido (W35, donde nace, y W38, la ultima en la que sigue adentro): eso
    es exactamente lo que dura la reserva. Antes el bucle iba mas lejos
    para mostrar que el mensaje se repetia "tres ciclos despues", y eso ya
    no pasa -- una semana operativa mas y el pedido VENCE y deja de
    reservar, que es el arreglo de `bus.preseed_vencido`. Lo que este test protege sigue vivo entero:
    mientras el pedido este en pie, la rodada de la ventana no lo suelta y
    el freno no puede decir que si."""
    from calipso.economia import bus as bus_mod
    from calipso.economia import mercado as mkt

    ctx, contratos, _ = armar(tmp_path, "pedir 30000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=150_000,
                              techo_preseed_ciclo_mm=60_000)
    ctx.kernel.acunar(TS, W, t.TESORO, 500_000, t.SubtipoAcunacion.CAPITAL,
                      {"tipo": "firma_pedro"})
    # el pedido se publica en W35, la primera operativa (la abre `armar`)
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda",
                 60_000, 60_000, {"gasto_max_mm": 60_000}, tipo="preseed")
    # las semanas se abren EN ORDEN y ninguna queda por delante de la que
    # el test simula: `financiar` lee el vencimiento con el reloj de hoy
    # -- la ultima operativa -- y no con la fecha que le pasa el llamador,
    # asi que un libro con semanas abiertas "en el futuro" ya no es un
    # estado que la maquina de Pedro pueda tener
    for w in ["2026-W36", "2026-W37", "2026-W38"]:
        pt.expirar_pools(ctx.kernel, TS, w)
        pt.emitir_semana(ctx.kernel, TS, w, 4_000, 1_000)
    it.poner_modo(tmp_path, "vivo")

    # los dos extremos de la ventana del pedido: donde nace y la ultima
    # semana operativa en la que sigue adentro
    for semana in (W, "2026-W38"):
        s = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                          ctx.suscripciones, semana, "dep:atlas")
        assert s["preseed_ventana_mm"] == 0, "no se financio nada"
        assert s["preseed_pendiente_mm"] == 60_000
        out = j.tic(ctx, "dep:atlas", semana)
        assert out["actuo"] is False
        assert "techo de la ventana" in out["freno"]
        # las dos mitades por separado, no un total que las confunde
        assert "lo financiado (0 mm)" in out["freno"], out["freno"]
        assert "pedido en pie (60000 mm)" in out["freno"], out["freno"]
        # y el consejo verdadero, no el que no desbloquea nunca
        assert "descarte" in out["freno"], out["freno"]
        assert "la rodada no lo suelta" in out["freno"], out["freno"]
        assert "la ventana rueda" not in out["freno"], out["freno"]
        # y la TERCERA salida, la que arregla la condena: el pedido vence
        # cuando su semana sale de la ventana, sin que Pedro toque nada
        assert "queda fuera de la ventana con la que se lo podria pagar" in out["freno"], out["freno"]
    assert contratos == []

    # por que la reserva se sigue contando: ese pedido de W30 se financia
    # tal cual tres semanas operativas mas tarde, y ahi si come el cupo de
    # la ventana de W33
    m = mkt.Mercado(ctx.kernel, ctx.registro, ctx.suscripciones)
    bus_mod.financiar(m, ctx.bus, TS, "2026-W38", "p0", t.TESORO, 60_000)
    s2 = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                       ctx.suscripciones, "2026-W38", "dep:atlas")
    assert s2["preseed_ventana_mm"] == 60_000
    assert s2["preseed_pendiente_mm"] == 0
    # sin la reserva, el jefe habria publicado otra ronda en W38 creyendo
    # que tenia la ventana entera libre, y esta habria sido impagable
    out2 = j.tic(ctx, "dep:atlas", "2026-W38")
    assert out2["actuo"] is False
    assert "la ventana rueda" in out2["freno"], out2["freno"]


def test_sin_nada_en_la_mesa_el_freno_del_ciclo_si_manda_a_esperar(tmp_path):
    """La otra mitad del consejo: con todo el techo FINANCIADO y la mesa
    despejada, esperar SI desbloquea -- el acumulado se mide sobre las
    semanas de la ventana, no sobre el libro entero, y la ventana rueda
    sola a medida que se abren semanas operativas."""
    from calipso.economia import bus as bus_mod
    from calipso.economia import mercado as mkt

    ctx, contratos, _ = armar(tmp_path, "pedir 30000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=150_000,
                              techo_preseed_ciclo_mm=20_000)
    ctx.kernel.acunar(TS, W, t.TESORO, 500_000, t.SubtipoAcunacion.CAPITAL,
                      {"tipo": "firma_pedro"})
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 20_000, 20_000,
                {"gasto_max_mm": 20_000}, tipo="preseed")
    m = mkt.Mercado(ctx.kernel, ctx.registro, ctx.suscripciones)
    bus_mod.financiar(m, ctx.bus, TS, W, "p0", t.TESORO, 20_000)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False
    assert "lo financiado (20000 mm)" in out["freno"], out["freno"]
    assert "pedido en pie (0 mm)" in out["freno"], out["freno"]
    assert "la ventana rueda" in out["freno"], out["freno"]
    assert contratos == []


def test_el_freno_del_ciclo_dice_cuanto_cupo_devuelve_la_proxima_semana(tmp_path):
    """El consejo "espera" ahora dice CUANTO y CUANDO, que es lo unico
    bueno de haber perdido el reset en bloque: con la ventana fija el cupo
    volvia entero, de golpe y en una fecha que nada anunciaba -- el jefe no
    tenia ninguna senal de que la ventana acababa de rodar, y Pedro
    tampoco. Deslizante, la semana que sale y lo que se lleva con ella son
    dos numeros que se pueden decir."""
    from calipso.economia import bus as bus_mod
    from calipso.economia import mercado as mkt

    ctx, contratos, _ = armar(tmp_path, "pedir 30000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=150_000,
                              techo_preseed_ciclo_mm=20_000)
    ctx.kernel.acunar(TS, W, t.TESORO, 500_000, t.SubtipoAcunacion.CAPITAL,
                      {"tipo": "firma_pedro"})
    # el techo entero entra en W35, la mas vieja de las cuatro de la ventana
    # (`armar` ya la abrio). Las siguientes se abren DESPUES de financiar:
    # el libro no puede tener semanas operativas por delante de la que el
    # test simula -- `financiar` lee el vencimiento con la ultima operativa.
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 20_000,
                 20_000, {"gasto_max_mm": 20_000}, tipo="preseed")
    m = mkt.Mercado(ctx.kernel, ctx.registro, ctx.suscripciones)
    bus_mod.financiar(m, ctx.bus, TS, W, "p0", t.TESORO, 20_000)
    for w in ("2026-W36", "2026-W37", "2026-W38"):
        pt.expirar_pools(ctx.kernel, TS, w)
        pt.emitir_semana(ctx.kernel, TS, w, 4_000, 1_000)

    s = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                      ctx.suscripciones, "2026-W38", "dep:atlas")
    assert s["preseed_ventana_mm"] == 20_000
    assert s["preseed_libera_al_salir"] == W
    assert s["preseed_libera_mm"] == 20_000

    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", "2026-W38")
    assert out["actuo"] is False
    assert "la ventana rueda" in out["freno"], out["freno"]
    assert "sale 2026-W35 de la ventana y se liberan 20000 mm" in out["freno"], \
        out["freno"]
    assert contratos == []


def test_con_una_miga_pendiente_el_freno_no_borra_el_alivio_de_la_ventana(
        tmp_path):
    """EL CONSEJO FALSO. `_puede` arma el consejo bueno -- cuanto cupo
    vuelve y cuando -- y despues lo pisaba entero con "esperar no lo
    suelta" en cuanto habia UN mm pendiente, sin mirar QUE parte llena el
    techo.

    Cuando lo que bloquea es lo FINANCIADO (que si caduca con la ventana) y
    lo pendiente es una miga, esperar SI destraba: basta con que lo pedido
    en pie sea menor que el techo para que la frase sea falsa. Y el primer
    remedio que ofrecia era "que Pedro suba la perilla", o sea que empujaba
    a agrandar el techo cuando alcanzaba con dejar rodar la ventana. Encima
    borraba el `sale ... se liberan ...` que `situacion` ya tenia
    calculado, que es justamente el dato que la ventana deslizante permite
    dar y la fija no.

    El caso en que la frase SI es cierta -- lo pedido solo ya llena el
    techo -- lo fija `test_el_freno_del_ciclo_no_le_manda_a_esperar_lo_que_no_llega`
    y no se toca: ahi esperar no alcanza nunca."""
    from calipso.economia import bus as bus_mod
    from calipso.economia import mercado as mkt

    ctx, contratos, _ = armar(tmp_path, "pedir 30000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=150_000,
                              techo_preseed_ciclo_mm=20_000)
    ctx.kernel.acunar(TS, W, t.TESORO, 500_000, t.SubtipoAcunacion.CAPITAL,
                      {"tipo": "firma_pedro"})
    # 15.000 FINANCIADOS en W35, la mas vieja de la ventana de W38 (la abre
    # `armar`). Las que siguen se abren DESPUES de financiar: ver el
    # comentario gemelo en el test de arriba.
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 15_000,
                 15_000, {"gasto_max_mm": 15_000}, tipo="preseed")
    m = mkt.Mercado(ctx.kernel, ctx.registro, ctx.suscripciones)
    bus_mod.financiar(m, ctx.bus, TS, W, "p0", t.TESORO, 15_000)
    for w in ("2026-W36", "2026-W37", "2026-W38"):
        pt.expirar_pools(ctx.kernel, TS, w)
        pt.emitir_semana(ctx.kernel, TS, w, 4_000, 1_000)
    # y 5.000 pedidos y sin financiar: la miga
    ctx.bus.alta(TS, "2026-W38", "p1", "dep:atlas", "segunda ronda", 5_000,
                 5_000, {"gasto_max_mm": 5_000}, tipo="preseed")

    s = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                      ctx.suscripciones, "2026-W38", "dep:atlas")
    assert s["preseed_ventana_mm"] == 15_000
    assert s["preseed_pendiente_mm"] == 5_000
    assert s["preseed_libera_al_salir"] == W
    assert s["preseed_libera_mm"] == 15_000

    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", "2026-W38")
    assert out["actuo"] is False
    assert "lo financiado (15000 mm)" in out["freno"], out["freno"]
    assert "pedido en pie (5000 mm)" in out["freno"], out["freno"]
    # el alivio que el freno tenia calculado y tiraba a la basura
    assert "la ventana rueda" in out["freno"], out["freno"]
    assert "sale 2026-W35 de la ventana y se liberan 15000 mm" in out["freno"], \
        out["freno"]
    # y sin mentir para el otro lado: la miga sigue siendo suya
    assert "descarte" in out["freno"], out["freno"]
    assert "la rodada no lo suelta" not in out["freno"], out["freno"]
    assert contratos == []

    # y era verdad: una semana operativa despues, sin que Pedro financie ni
    # descarte nada, W35 sale de la ventana y el jefe actua sin freno
    pt.expirar_pools(ctx.kernel, TS, "2026-W39")
    pt.emitir_semana(ctx.kernel, TS, "2026-W39", 4_000, 1_000)
    s2 = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                       ctx.suscripciones, "2026-W39", "dep:atlas")
    assert s2["preseed_ventana_mm"] == 0
    assert s2["preseed_pendiente_mm"] == 5_000
    out2 = j.tic(ctx, "dep:atlas", "2026-W39")
    assert out2["freno"] == "", out2["freno"]
    assert out2["actuo"] is True


def test_un_pedido_viejo_deja_de_apretar_cuando_su_ventana_pasa(tmp_path):
    """EL SINTOMA, entero y de punta a punta.

    Un pedido de pre-seed que Pedro no mira reservaba cupo PARA SIEMPRE: el
    unico camino fuera de la bandeja era que el lo financiara o lo
    descartara, y desde la pantalla el acumulado se veia en cero, asi que
    nada le sugeria que ese pedido era lo que tenia frenado al
    departamento.

    Lo que lo suelta ahora es el paso de la ventana, que es la misma
    maquinaria que ya acota el techo: el pedido vive exactamente la ventana
    en la que nacio -- lo que dura su financiabilidad-- y despues deja de
    reservar. Pedro no toca NADA en este test: ni financiar, ni descartar,
    ni la perilla. Solo abre las semanas, que es lo que ya hace para operar
    la fabrica.

    Cuidado con el otro lado: mientras la semana del alta siga en la
    ventana, el pedido tiene que seguir apretando (lo cubre
    `test_los_pedidos_en_pie_cuentan_contra_el_techo_de_la_ronda`)."""
    ctx, contratos, _ = armar(tmp_path, "pedir 50000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=50_000)
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 50_000, 50_000,
                {"gasto_max_mm": 50_000}, tipo="preseed")
    it.poner_modo(tmp_path, "vivo")
    frenado = j.tic(ctx, "dep:atlas", W)
    assert frenado["actuo"] is False
    assert "en pie" in frenado["freno"]
    assert contratos == []

    # Pedro abre las semanas siguientes y nada mas. W35 sale de la ventana.
    for sem in ["2026-W36", "2026-W37", "2026-W38", "2026-W39"]:
        pt.expirar_pools(ctx.kernel, TS, sem)
        pt.emitir_semana(ctx.kernel, TS, sem, 4_000, 1_000)
    assert ctx.bus.estado("p0") == "alta"   # el libro no desescribe nada

    s = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                     ctx.suscripciones, "2026-W39", "dep:atlas")
    assert s["preseed_pendiente_mm"] == 0
    assert s["propuestas_propias"] == []

    destrabado = j.tic(ctx, "dep:atlas", "2026-W39")
    assert destrabado["actuo"] is True
    assert contratos == [("pedir", "50000", "otra ronda")]


def test_el_freno_no_dice_que_la_rodada_no_lo_suelta_cuando_la_rodada_lo_suelta(
        tmp_path):
    """LA MENTIRA EN EL FRENO, invertida. El freno decia "la rodada no lo
    suelta" y a continuacion ofrecia, como tercera salida, "hasta que su
    semana salga de la ventana y venza" -- y salir de la ventana era
    exactamente lo que hacia la rodada. Las dos mitades de la misma oracion
    se contradecian, y el efecto practico era peor que la contradiccion: de
    los remedios que Pedro podia leer, los unicos que le ofrecian eran
    subir la perilla o financiar/descartar, cuando abrir la semana lo
    soltaba entero.

    Ya no. El vencimiento se mide con `bus.ventana_pagable`, que cuenta la
    semana de hoy como si ya estuviera abierta: cuando el pedido va a
    vencer al rodar, ya vencio ANTES -- el freno no aparece ni una vez. Y
    donde el freno si aparece, "la rodada no lo suelta" es cierto: abrir la
    semana no cambia nada.

    Es la misma clase de mentira que arreglaron c3e3ed6 y 9995676, que el
    freno no puede volver a cometer."""
    ctx, contratos, _ = armar(tmp_path, "pedir 30000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=60_000,
                              techo_preseed_ciclo_mm=50_000)
    # W35 la abre `armar`; tres mas y hoy pasa a ser W39, sin abrir
    for w in ("2026-W36", "2026-W37", "2026-W38"):
        pt.expirar_pools(ctx.kernel, TS, w)
        pt.emitir_semana(ctx.kernel, TS, w, 4_000, 1_000)
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 50_000, 50_000,
                 {"gasto_max_mm": 50_000}, tipo="preseed")
    it.poner_modo(tmp_path, "vivo")

    s = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                      ctx.suscripciones, "2026-W39", "dep:atlas")
    assert s["preseed_pendiente_mm"] == 0, "reservaba cupo un pedido que la " \
        "proxima rodada suelta entero"
    assert j.freno_preseed(s) is None

    # y la rodada, que es lo que el freno le pedia a Pedro que no hiciera,
    # no cambia ninguna de las dos respuestas
    pt.expirar_pools(ctx.kernel, TS, "2026-W39")
    pt.emitir_semana(ctx.kernel, TS, "2026-W39", 4_000, 1_000)
    s2 = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                       ctx.suscripciones, "2026-W39", "dep:atlas")
    assert s2["preseed_pendiente_mm"] == 0
    assert j.freno_preseed(s2) is None


def test_donde_el_freno_dice_que_la_rodada_no_lo_suelta_es_verdad(tmp_path):
    """El otro lado: cuando el freno SI sale, lo que dice tiene que ser
    cierto. El pedido en pie llena el techo el solo y abrir la semana no lo
    afloja -- ni un milimon, ni antes ni despues."""
    ctx, contratos, _ = armar(tmp_path, "pedir 30000\notra ronda", saldo=0,
                              presupuesto_semanal_mm=0,
                              techo_preseed_mm=60_000,
                              techo_preseed_ciclo_mm=50_000)
    ctx.bus.alta(TS, W, "p0", "dep:atlas", "primera ronda", 50_000, 50_000,
                 {"gasto_max_mm": 50_000}, tipo="preseed")
    it.poner_modo(tmp_path, "vivo")

    antes = j.freno_preseed(sit.situacion(
        ctx.kernel, ctx.registro, ctx.bus, ctx.cola, ctx.suscripciones,
        "2026-W36", "dep:atlas"))
    assert "la rodada no lo suelta" in antes, antes
    # y la frase ya no se contradice a si misma: lo que suelta al pedido no
    # es la rodada, es que su semana quede fuera de la ventana con la que se
    # lo podria pagar
    assert "eso no lo hace la rodada" in antes, antes

    pt.expirar_pools(ctx.kernel, TS, "2026-W36")
    pt.emitir_semana(ctx.kernel, TS, "2026-W36", 4_000, 1_000)
    despues = j.freno_preseed(sit.situacion(
        ctx.kernel, ctx.registro, ctx.bus, ctx.cola, ctx.suscripciones,
        "2026-W36", "dep:atlas"))
    assert "la rodada no lo suelta" in despues, despues
