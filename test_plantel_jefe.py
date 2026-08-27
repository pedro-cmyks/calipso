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
from calipso.plantel import interruptor as it
from calipso.plantel import jefe as j

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


def armar(tmp_path, respuesta="nada\nno hay nada", saldo=400_000):
    eco = tmp_path / "economia"
    eco.mkdir(parents=True, exist_ok=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000,
                             techo_api_ciclo_mm=3_000, agresividad_pct=40))
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
        contratar=lambda s, a, ref, m="": contratos.append((a, ref, m)) or {"ok": True},
        publicar=lambda evento, **c: eventos.append((evento, c)))
    return ctx, contratos, eventos


def test_en_ensayo_decide_y_publica_pero_no_contrata(tmp_path):
    """Es el modo en el que arranca: la unica forma de mirar que decide
    antes de soltarlo con la billetera."""
    ctx, contratos, eventos = armar(tmp_path, "proponer\nhay hueco en precios")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "proponer"
    assert out["actuo"] is False
    assert "ensayo" in out["freno"]
    assert contratos == []
    assert [e for e, _ in eventos] == ["inicio", "razonando", "fin"]
    assert set(out) == CLAVES


def test_en_vivo_contrata(tmp_path):
    ctx, contratos, _ = armar(tmp_path, "proponer\nhay hueco")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True and contratos == [("proponer", None, "hay hueco")]
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
    prompt."""
    ctx, contratos, _ = armar(tmp_path, "proponer\ndale", saldo=0)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is False and "saldo" in out["freno"]
    assert contratos == []


def test_la_agresividad_frena_proponer_pero_no_trabajar(tmp_path):
    """La perilla deja de ser decoracion: con el presupuesto de la semana ya
    comprometido, el departamento no abre apuestas nuevas — pero sigue
    pudiendo terminar lo que empezo."""
    ctx, contratos, _ = armar(tmp_path, "proponer\notra apuesta")
    it.poner_modo(tmp_path, "vivo")
    # agresividad 40% de 25.000 = 10.000; sacamos 12.000 de la semana
    ctx.kernel.destruir(TS, W, "dep:atlas", 12_000, motivo="api")
    assert j.tic(ctx, "dep:atlas", W)["actuo"] is False
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
                     pensar=lambda _p: "proponer\nordenar los gastos del mes",
                     contratar=lambda s, a, ref, m="": contratos.append((a, ref, m)),
                     publicar=lambda e, **c: None)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "personal:finanzas", W)
    assert out["accion"] == "proponer" and out["actuo"] is True
    assert contratos == [("proponer", None, "ordenar los gastos del mes")]
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

    ctx, contratos, eventos = armar(tmp_path, "proponer\nhay hueco")
    ctx.memoria = MemoriaQueRevienta()
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True
    assert out["resultado"] == {"ok": True}
    assert contratos == [("proponer", None, "hay hueco")]
    assert ("fin", {"resultado": "error"}) in eventos


def test_el_motivo_del_parser_llega_al_contratista(tmp_path):
    """El titulo con el que la propuesta aterriza en el bus es el motivo
    que el jefe razono, no relleno del planificador: es literalmente lo
    que Pedro lee para decidir si financia."""
    ctx, contratos, _ = armar(tmp_path, "proponer\nhay hueco en precios de GPU")
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert contratos == [("proponer", None, "hay hueco en precios de GPU")]


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
    ctx, contratos, _ = armar(tmp_path, "proponer\notra idea mas")
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
    ctx, contratos, _ = armar(tmp_path, "proponer\notra idea mas")
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
    assert contratos == [("proponer", None, "otra idea mas")]


def test_con_menos_propuestas_que_el_techo_sigue_pudiendo_proponer(tmp_path):
    """El techo no puede volverse un cero disfrazado: por debajo, proponer
    sigue pasando."""
    ctx, contratos, _ = armar(tmp_path, "proponer\notra idea mas")
    for i in range(j.TECHO_PROPUESTAS - 1):
        ctx.bus.alta(TS, W, f"p{i}", "dep:atlas", f"propuesta {i}", 1_000,
                    2_000, {"gasto_max_mm": 5_000})
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True
    assert contratos == [("proponer", None, "otra idea mas")]


def test_el_techo_de_propuestas_no_tapa_la_agresividad(tmp_path):
    """El chequeo nuevo va primero por ser mas barato, pero no puede dejar
    inalcanzable el de agresividad: con pocas propuestas en pie, la perilla
    sigue frenando proponer y el freno lo sigue diciendo."""
    ctx, contratos, _ = armar(tmp_path, "proponer\notra apuesta")
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
