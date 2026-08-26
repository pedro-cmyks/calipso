"""El bucle del jefe, entero, sin un solo modelo (spec seccion 4)."""
import pytest

from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.bus import Bus
from calipso.economia.capacidad import Suscripcion
from calipso.economia.cola import Cola
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.plantel import interruptor as it
from calipso.plantel import jefe as j

TS = "2026-08-26T10:00:00"
W = "2026-W35"


class MemoriaFalsa:
    def __init__(self, nucleo=""):
        self.recordado = []
        self._nucleo = nucleo

    def load_core(self):
        return self._nucleo

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
        contratar=lambda s, a, ref: contratos.append((a, ref)) or {"ok": True},
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


def test_en_vivo_contrata(tmp_path):
    ctx, contratos, _ = armar(tmp_path, "proponer\nhay hueco")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["actuo"] is True and contratos == [("proponer", None)]
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
    assert llamadas == [] and eventos == []


def test_sin_cuerda_no_despierta(tmp_path):
    ctx, _, _ = armar(tmp_path)
    it.escribir(tmp_path, it.Estado(encendido=True, modo="vivo", techo_tics=1))
    assert j.tic(ctx, "dep:atlas", W)["accion"] != "sin_cuerda"
    assert j.tic(ctx, "dep:atlas", W)["accion"] == "sin_cuerda"


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
                             presupuesto_semanal_mm=5_000, agresividad_pct=50))
    pt.emitir_semana(k, TS, W, 4_000, 1_000)
    k.acunar(TS, W, "personal:finanzas", 50_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    contratos = []
    ctx = j.Contexto(base=tmp_path, kernel=k, registro=r,
                     bus=Bus(eco / "bus.jsonl"), cola=Cola(eco / "cola.jsonl"),
                     suscripciones={}, memoria=MemoriaFalsa(),
                     pensar=lambda _p: "proponer\nordenar los gastos del mes",
                     contratar=lambda s, a, ref: contratos.append((a, ref)),
                     publicar=lambda e, **c: None)
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "personal:finanzas", W)
    assert out["accion"] == "proponer" and out["actuo"] is True
    assert contratos == [("proponer", None)]
    # sin suscripciones el sesgo es la perilla pelada, sin modular por precio
    assert out["sesgo_pct"] == 50


def test_un_modelo_que_alucina_no_gasta(tmp_path):
    ctx, contratos, _ = armar(tmp_path, "Claro! Con gusto te ayudo con eso.")
    it.poner_modo(tmp_path, "vivo")
    assert j.tic(ctx, "dep:atlas", W)["accion"] == "nada"
    assert contratos == []
