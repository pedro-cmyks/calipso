"""Tests del kernel de economia: tipos, libro y balances."""
import pytest

from calipso.economia import tipos as t
from calipso.economia.libro import Libro, LibroCorrupto
from calipso.economia import balances as bal


def test_asiento_roundtrip_json():
    """Un asiento sobrevive el viaje a JSON y de vuelta, campo por campo."""
    a = t.Asiento(
        seq=1, ts="2026-08-24T10:00:00", semana="2026-W35",
        tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
        monto=2_500, origen="dep:mercado", destino=t.DIRECCION,
        ref="cap-001", detalle={"motivo": "capacidad"},
    )
    b = t.Asiento.de_json(a.a_json())
    assert b == a


def test_acunacion_exige_subtipo_y_evidencia():
    """Invariantes 1 y 4: acunar sin subtipo o sin evidencia es invalido."""
    base = dict(seq=1, ts="2026-08-24T10:00:00", semana="2026-W35",
                tipo=t.TipoAsiento.ACUNACION, divisa=t.Divisa.MONEDA,
                monto=25_000, destino=t.TESORO)
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base).validar()  # sin subtipo
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, subtipo="venta").validar()  # sin evidencia
    ok = t.Asiento(**base, subtipo="capital",
                   detalle={"evidencia": {"tipo": "firma_pedro"}})
    ok.validar()  # no levanta


def test_monto_debe_ser_entero_positivo():
    base = dict(seq=1, ts="2026-08-24T10:00:00", semana="2026-W35",
                tipo=t.TipoAsiento.DESTRUCCION, divisa=t.Divisa.MONEDA,
                origen=t.TESORO)
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, monto=0).validar()
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, monto=-5).validar()
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, monto=1.5).validar()


def test_transferencia_exige_origen_y_destino_distintos():
    base = dict(seq=1, ts="2026-08-24T10:00:00", semana="2026-W35",
                tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
                monto=100)
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, origen="a").validar()  # sin destino
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, origen="a", destino="a").validar()  # iguales


def test_semana_exige_formato_iso_con_cero():
    """El orden lexicografico de semanas solo funciona con cero a la izquierda."""
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(seq=1, ts="2026-08-24T10:00:00", semana="2026-W5",
                  tipo=t.TipoAsiento.APUNTE, divisa=t.Divisa.MONEDA,
                  monto=1, detalle={"nota": "x"}).validar()


def _libro(tmp_path):
    return Libro(tmp_path / "libro.jsonl")


def test_append_asigna_seq_correlativo_y_persiste(tmp_path):
    lb = _libro(tmp_path)
    a1 = lb.append(ts="2026-08-24T10:00:00", semana="2026-W35",
                   tipo=t.TipoAsiento.ACUNACION, divisa=t.Divisa.MONEDA,
                   monto=1_200_000, destino=t.TESORO, subtipo="capital",
                   detalle={"evidencia": {"tipo": "firma_pedro"}})
    a2 = lb.append(ts="2026-08-24T10:01:00", semana="2026-W35",
                   tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
                   monto=100_000, origen=t.TESORO, destino="dep:mercado")
    assert (a1.seq, a2.seq) == (1, 2)
    # reabrir desde disco reproduce exactamente lo mismo
    lb2 = _libro(tmp_path)
    assert lb2.asientos() == [a1, a2]


def test_append_invalido_no_persiste(tmp_path):
    lb = _libro(tmp_path)
    with pytest.raises(t.AsientoInvalido):
        lb.append(ts="2026-08-24T10:00:00", semana="2026-W35",
                  tipo=t.TipoAsiento.ACUNACION, divisa=t.Divisa.MONEDA,
                  monto=5, destino=t.TESORO)  # sin subtipo ni evidencia
    assert lb.asientos() == []
    assert _libro(tmp_path).asientos() == []


def test_ultima_linea_truncada_se_ignora_con_aviso(tmp_path):
    """Un corte de luz a mitad de un append no puede tumbar el libro entero."""
    lb = _libro(tmp_path)
    a1 = lb.append(ts="2026-08-24T10:00:00", semana="2026-W35",
                   tipo=t.TipoAsiento.ACUNACION, divisa=t.Divisa.MONEDA,
                   monto=1_000, destino=t.TESORO, subtipo="capital",
                   detalle={"evidencia": {"tipo": "firma_pedro"}})
    ruta = tmp_path / "libro.jsonl"
    with ruta.open("a", encoding="utf-8") as f:
        f.write('{"seq": 2, "ts": "2026-08-2')  # linea cortada
    lb2 = _libro(tmp_path)
    assert lb2.asientos() == [a1]
    # y el proximo append sigue la numeracion sana
    a2 = lb2.append(ts="2026-08-24T11:00:00", semana="2026-W35",
                    tipo=t.TipoAsiento.DESTRUCCION, divisa=t.Divisa.MONEDA,
                    monto=100, origen=t.TESORO)
    assert a2.seq == 2


def test_linea_corrupta_en_el_medio_es_error(tmp_path):
    """Corrupcion que NO es la ultima linea no se tolera: hay que mirar."""
    ruta = tmp_path / "libro.jsonl"
    ruta.write_text('esto no es json\n{"tampoco": 1}\n', encoding="utf-8")
    with pytest.raises(LibroCorrupto):
        Libro(ruta)


def _acuna(lb, monto, destino=t.TESORO):
    return lb.append(ts="2026-08-24T09:00:00", semana="2026-W35",
                     tipo=t.TipoAsiento.ACUNACION, divisa=t.Divisa.MONEDA,
                     monto=monto, destino=destino, subtipo="capital",
                     detalle={"evidencia": {"tipo": "firma_pedro"}})


def test_reserva_en_pt_es_invalida():
    """El escrow solo existe en monedas, nunca en PT."""
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(seq=1, ts="2026-08-24T10:00:00", semana="2026-W35",
                  tipo=t.TipoAsiento.RESERVA, divisa=t.Divisa.PT,
                  monto=50_000, origen=t.POOL_PT_FABRICA, ref="res-1").validar()
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(seq=1, ts="2026-08-24T10:00:00", semana="2026-W35",
                  tipo=t.TipoAsiento.EJECUCION_RESERVA, divisa=t.Divisa.PT,
                  monto=50_000, origen=t.POOL_PT_FABRICA,
                  destino=t.CUENTA_PEDRO, ref="res-1").validar()


def test_saldos_pliegan_acunacion_transferencia_destruccion(tmp_path):
    lb = _libro(tmp_path)
    _acuna(lb, 1_000_000)
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
              monto=300_000, origen=t.TESORO, destino="dep:mercado")
    lb.append(ts="2026-08-24T09:02:00", semana="2026-W35",
              tipo=t.TipoAsiento.DESTRUCCION, divisa=t.Divisa.MONEDA,
              monto=50_000, origen="dep:mercado", detalle={"motivo": "api"})
    s = bal.saldos(lb.asientos())
    assert s[(t.TESORO, t.Divisa.MONEDA)] == 700_000
    assert s[("dep:mercado", t.Divisa.MONEDA)] == 250_000


def test_suma_cero_las_transferencias_no_crean_ni_destruyen(tmp_path):
    """Propiedad del spec 4.1: lo interno mueve, nunca crea."""
    lb = _libro(tmp_path)
    _acuna(lb, 500_000)
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
              monto=200_000, origen=t.TESORO, destino="dep:a")
    lb.append(ts="2026-08-24T09:02:00", semana="2026-W35",
              tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
              monto=80_000, origen="dep:a", destino="dep:b")
    s = bal.saldos(lb.asientos())
    total = sum(v for (cta, div), v in s.items() if div is t.Divisa.MONEDA)
    assert total == 500_000  # exactamente lo acunado


def test_reserva_no_mueve_saldo_pero_baja_disponible(tmp_path):
    lb = _libro(tmp_path)
    _acuna(lb, 100_000, destino="dep:a")
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.RESERVA, divisa=t.Divisa.MONEDA,
              monto=60_000, origen="dep:a", ref="res-1")
    s = bal.saldos(lb.asientos())
    assert s[("dep:a", t.Divisa.MONEDA)] == 100_000
    assert bal.disponible(lb.asientos(), "dep:a", t.Divisa.MONEDA) == 40_000
    assert bal.reservas_activas(lb.asientos()) == {"res-1": ("dep:a", 60_000)}


def test_liberacion_devuelve_disponible(tmp_path):
    lb = _libro(tmp_path)
    _acuna(lb, 100_000, destino="dep:a")
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.RESERVA, divisa=t.Divisa.MONEDA,
              monto=60_000, origen="dep:a", ref="res-1")
    lb.append(ts="2026-08-24T09:02:00", semana="2026-W35",
              tipo=t.TipoAsiento.LIBERACION, divisa=t.Divisa.MONEDA,
              monto=60_000, ref="res-1")
    assert bal.disponible(lb.asientos(), "dep:a", t.Divisa.MONEDA) == 100_000
    assert bal.reservas_activas(lb.asientos()) == {}


def test_ejecucion_de_reserva_transfiere_y_cancela(tmp_path):
    lb = _libro(tmp_path)
    _acuna(lb, 100_000, destino="dep:a")
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.RESERVA, divisa=t.Divisa.MONEDA,
              monto=60_000, origen="dep:a", ref="res-1")
    lb.append(ts="2026-08-24T09:02:00", semana="2026-W35",
              tipo=t.TipoAsiento.EJECUCION_RESERVA, divisa=t.Divisa.MONEDA,
              monto=60_000, origen="dep:a", destino=t.CUENTA_PEDRO, ref="res-1")
    s = bal.saldos(lb.asientos())
    assert s[("dep:a", t.Divisa.MONEDA)] == 40_000
    assert s[(t.CUENTA_PEDRO, t.Divisa.MONEDA)] == 60_000
    assert bal.reservas_activas(lb.asientos()) == {}


def test_apunte_y_acreencia_no_mueven_saldos(tmp_path):
    lb = _libro(tmp_path)
    _acuna(lb, 10_000)
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.APUNTE, divisa=t.Divisa.MONEDA,
              monto=5_000, detalle={"nota": "costo de oportunidad atlas"})
    lb.append(ts="2026-08-24T09:02:00", semana="2026-W35",
              tipo=t.TipoAsiento.ACREENCIA, divisa=t.Divisa.MONEDA,
              monto=3_000, ref="acr-1",
              detalle={"acreedor": t.DIRECCION, "deudor": "dep:a"})
    s = bal.saldos(lb.asientos())
    assert s[(t.TESORO, t.Divisa.MONEDA)] == 10_000
    assert ("dep:a", t.Divisa.MONEDA) not in s
