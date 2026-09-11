"""El porton de la letra de la reentrada (experimentos/porton_reentrada.py)
no se corre en la suite (levanta servers y habla con Ollama); lo que se
prueba aca es lo que se puede probar en seco: que una fila cuenta solo si
la contesto el 7b bajo prueba, que los totales (y el veredicto) excluyen
las otras y las reportan aparte, y que el informe se regenera desde el
JSONL sin Ollama."""
from __future__ import annotations

import json

from experimentos import porton_reentrada as porton

AVISO = ("[Calipso] no puedo contestar esto con el modelo local: Ollama no "
         "esta disponible. No lo mando a la nube.")


def _clasificar(texto: str) -> str:
    return "sin_dato" if "no trae el dato" in texto else "dato"


def _r(texto: str, ruta: str | None = "local/qwen2.5:7b") -> dict:
    return {"chat": "c", "ruta": ruta, "abismo": [{"fase": "consulta", "fuente": "chats"}],
            "canario": {"anclaje": {"sin_anclaje": [], "aplica": True}, "degeneracion": []},
            "ms": 10, "texto": texto}


def _fila(condicion: str, clave: str, texto: str, ruta: str | None = "local/qwen2.5:7b",
          pasada: int = 1, bloques: list[str] | None = None) -> dict:
    tele = {"contexto": {"bloques": bloques or []}} if bloques is not None else {}
    return porton.fila_de(condicion, pasada, clave, "msg", _r(texto, ruta), tele,
                          _clasificar, "abc1234")


def test_una_fila_cuenta_solo_si_la_contesto_el_7b_local():
    """Ruta local/ y no el aviso del server: un turno que fue a la nube
    (Ollama caido, el filtro de force_route cae al ranking entero) o que
    contesto el server por el 7b no es una medicion del 7b bajo prueba."""
    assert porton.es_valida("local/qwen2.5:7b", "Mariana Quintero te presto el libro rosa.")
    assert not porton.es_valida("subscription/opus", "Lo que subio no trae el dato.")
    assert not porton.es_valida("local/qwen2.5:7b", AVISO)
    assert not porton.es_valida("local/qwen2.5:7b", "  " + AVISO)
    assert not porton.es_valida(None, "hola")
    assert not porton.es_valida("", "hola")


def test_fila_de_lleva_valida():
    assert _fila("nueva", "libro_rosa", "Mariana Quintero te presto el libro rosa.")["valida"]
    assert not _fila("nueva", "mariana", "Mariana y el libro", "subscription/opus")["valida"]
    assert not _fila("nueva", "presupuesto", AVISO)["valida"]


def test_los_totales_excluyen_las_invalidas_y_el_veredicto_no_depende_de_ellas():
    """El escenario del hallazgo: Opus (no bajo prueba) dice la frase
    inducida en `nueva`; si contara, mandaria LETRA_DEFAULT a vieja."""
    filas = [
        _fila("vieja", "libro_rosa", "Mariana Quintero te presto el libro rosa."),
        _fila("vieja", "presupuesto", "no tengo el detalle"),
        _fila("nueva", "libro_rosa", "Mariana Quintero te presto el libro rosa."),
        _fila("nueva", "presupuesto", AVISO),
        _fila("nueva", "mariana", "Lo que subio no trae el dato de si ya lo devolviste",
              "subscription/opus", bloques=["mariana quintero te presto el libro rosa"]),
    ]
    # la fila de Opus, sola, es un sin_dato falso con todas las letras
    assert filas[-1]["sin_dato"] and filas[-1]["sin_dato_falso"]
    t = porton.totales(filas)
    assert t["vieja"] == {"turnos": 2, "dato": 1, "confabula": 1, "sin_anclaje": 0,
                          "sin_dato": 0, "sin_dato_falso": 0, "consulto": 2,
                          "degeneracion": 0, "excluidas": 0}
    assert t["nueva"]["turnos"] == 1 and t["nueva"]["excluidas"] == 2
    assert t["nueva"]["sin_dato"] == 0 and t["nueva"]["sin_dato_falso"] == 0
    assert t["nueva"]["confabula"] == 0        # el aviso del server no es confabula del 7b
    assert porton.aterriza_nueva(t) is True
    # contadas, el veredicto cambiaria por un modelo que no esta bajo prueba
    t_sucio = porton.totales([dict(f, valida=True) for f in filas])
    assert t_sucio["nueva"]["sin_dato"] == 1 and porton.aterriza_nueva(t_sucio) is False
    assert porton.filas_excluidas(filas) == [filas[3], filas[4]]


def test_aterriza_nueva_sin_una_condicion_no_decide():
    assert porton.aterriza_nueva(porton.totales([_fila("nueva", "libro", "x")])) is None


def test_el_informe_muestra_la_ruta_y_lista_las_excluidas_aparte():
    filas = [
        _fila("vieja", "libro_rosa", "Mariana Quintero te presto el libro rosa."),
        _fila("nueva", "libro_rosa", "Mariana Quintero te presto el libro rosa."),
        _fila("nueva", "presupuesto", AVISO, pasada=2),
        _fila("nueva", "mariana", "Lo que subio no trae el dato", "subscription/opus", pasada=2),
    ]
    md = porton.resumen(filas)
    assert "| condicion | pasada | pregunta | clase | ruta | valida |" in md
    assert "| nueva | 2 | mariana | sin_dato | subscription/opus | no |" in md
    assert "| nueva | 2 | presupuesto | confabula | local/qwen2.5:7b | no |" in md
    assert "| nueva | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 2 |" in md      # totales sin las excluidas
    assert "## Filas excluidas" in md
    assert "nueva/2/presupuesto" in md and "nueva/2/mariana" in md
    assert 'queda `LETRA_DEFAULT = "nueva"`' in md
    assert "Se leyo con 2 filas excluidas" in md


def test_el_informe_se_regenera_desde_el_jsonl_sin_ollama(monkeypatch, tmp_path):
    """`--informe` relee el JSONL de una corrida (aunque sea anterior a la
    columna `valida`: se deriva de ruta y texto) y reescribe el MD; no
    levanta server ni pregunta por Ollama."""
    jsonl, md = tmp_path / "r.jsonl", tmp_path / "r.md"
    filas = [_fila("vieja", "libro_rosa", "Mariana Quintero te presto el libro rosa."),
             _fila("nueva", "libro_rosa", "Mariana Quintero te presto el libro rosa."),
             _fila("nueva", "mariana", "Lo que subio no trae el dato", "subscription/opus", pasada=2)]
    with jsonl.open("w", encoding="utf-8") as f:
        for fila in filas:
            fila = dict(fila)
            fila.pop("valida")          # como las escribio la corrida del 2026-09-11
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    monkeypatch.setattr(porton, "SALIDA_JSONL", jsonl)
    monkeypatch.setattr(porton, "SALIDA_MD", md)
    monkeypatch.setattr(porton, "_ollama_listo", lambda: (_ for _ in ()).throw(AssertionError("Ollama")))
    monkeypatch.setattr(porton, "correr", lambda *a, **k: (_ for _ in ()).throw(AssertionError("correr")))
    assert porton.main(["--informe"]) == 0
    texto = md.read_text(encoding="utf-8")
    assert "| nueva | 2 | mariana | sin_dato | subscription/opus | no |" in texto
    assert "| nueva | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 1 |" in texto
    assert [f["valida"] for f in porton.cargar_filas(jsonl)] == [True, True, False]
