"""El contrato de la marca + el indice de lo consultable (spec seccion 5/7)."""
from calipso.abismo import contrato, marca


def test_ensena_la_sintaxis_de_las_tres_fuentes():
    b = contrato.bloque_contrato(("calipso", "atlas"))
    for fuente in marca.FUENTES:
        assert f"{marca.ABRE}abismo:{fuente}" in b
    assert "calipso" in b and "atlas" in b
    assert "Maximo 3" in b


def test_respeta_el_techo_con_muchos_proyectos():
    nombres = tuple(f"proyecto-con-nombre-largo-{i:03d}" for i in range(60))
    b = contrato.bloque_contrato(nombres)
    assert len(b) <= contrato.INDICE_MAX
    assert "mas" in b  # la cola "y N mas" en vez de un corte a la mitad
    assert b.endswith("CONSULTA.")


def test_sin_proyectos_sigue_siendo_valido():
    b = contrato.bloque_contrato(())
    assert len(b) <= contrato.INDICE_MAX
    assert f"{marca.ABRE}abismo:memoria" in b
