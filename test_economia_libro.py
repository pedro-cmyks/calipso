"""Tests del kernel de economia: tipos, libro y balances."""
import pytest

from calipso.economia import tipos as t


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
