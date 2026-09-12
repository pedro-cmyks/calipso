"""La degeneracion (spec 2026-09-11, seccion 2.2): las siete senales del
spec mas `fuga_de_template` (dos casos reales), con sus umbrales calibrados
contra experimentos/degeneracion_banco.py; y `done_reason` en dispatch."""
from __future__ import annotations

import json

import dispatch
from calipso import canarios as c
from calipso.abismo import turno
from experimentos import degeneracion_banco as banco

SECS = [("Sistema", "Eres Calipso, el asistente personal local de Pedro. Respondes en el idioma "
                    "del turno y no muestras razonamiento interno."),
        ("Contrato interno", "=== Lenguaje interno de Calipso ===\nPide confirmacion antes de "
                             "escribir, gastar, publicar, borrar o promover memoria sensible."),
        ("Recuerdos relevantes", "- Pedro dijo (2026-08-20): Mariana Quintero me presto el libro rosa, "
                                 "recordame devolverselo cuando lo termine")]


def _senales(texto, secciones=SECS, features=None, usages=(), steered=False):
    d = c.degeneracion(texto, secciones, features or {"type": "chat"}, list(usages),
                       {"steered": steered})
    return {s["senal"]: s for s in d["senales"]}


def test_el_banco_atrapa_todas_las_rotas_y_no_marca_ninguna_sana():
    r = banco.medir(c.degeneracion)
    assert r["falsas"] == [], r["falsas"]
    assert r["escapadas"] == [], r["escapadas"]
    assert r["rotas"] >= 15 and r["sanas"] >= 30


def test_repeticion_por_ngrama_o_por_lineas_seguidas():
    frase = "no tengo registros de esa conversacion en particular "
    s = _senales(frase * 3)
    assert s["repeticion"]["veces"] == 3 and s["repeticion"]["evidencia"].startswith("no tengo registros")
    assert "repeticion" in _senales("hola\nhola\nhola\n")
    assert "repeticion" not in _senales(frase * 2 + "\nhola\nhola\nchau")


def test_alfabeto_cuenta_la_corrida_sin_que_la_puntuacion_la_corte():
    """El caso nombrado en el spec (posicion_produccion.jsonl:65): la corrida
    estricta da 10 porque la coma CJK la corta; la laxa da 21 (medido)."""
    texto = "No tengo registros específicos sobre tu última变更中，请替换方括号为花括号，并删除多余的分号。"
    s = _senales(texto)
    assert s["alfabeto"]["corrida"] >= 10 and s["alfabeto"]["fraccion"] < 0.5
    assert "alfabeto" not in _senales("Vive en Medellín y programó en Córdoba; ñandú, güiro.")
    # cuatro letras sueltas cortadas por latinas, bajo el 20%: no es corrida
    assert "alfabeto" not in _senales("una frase larga en castellano 中 con b 文 letras c 字 sueltas d 符 adentro e")
    # y el otro camino: mas del 20% del total
    assert "alfabeto" in _senales("hola " + "字" * 3 + " chau")


def test_fuga_del_contrato_solo_contra_las_secciones_de_instruccion():
    s = _senales("Como sabes, pide confirmacion antes de escribir, gastar, publicar, borrar o promover memoria sensible.")
    assert s["fuga_del_contrato"]["seccion"] == "Contrato interno"
    # citar el bloque o el recuerdo es la conducta deseada: nunca se marca
    assert "fuga_del_contrato" not in _senales(
        "Mariana Quintero me presto el libro rosa, recordame devolverselo cuando lo termine, dijiste.")
    # el system crudo de /nube (titulo vacio) tambien es instruccion
    assert "fuga_del_contrato" in _senales(
        "Eres Calipso, el asistente personal local de Pedro. Respondes en el idioma del turno.",
        secciones=[("", SECS[0][1])])


def test_fuga_de_reentrada_caza_las_dos_letras_y_el_venias_diciendo():
    for letra in turno.LETRAS_REENTRADA:
        assert _senales("hola. " + letra)["fuga_de_reentrada"]["evidencia"] == letra
    assert "fuga_de_reentrada" in _senales("Venias diciendo: que el libro")
    assert "fuga_de_reentrada" not in _senales("segui con lo tuyo")


def test_eco_de_episodio_en_cualquier_posicion_y_con_acentos():
    assert _senales("Bueno. Pedro preguntó: -q y Calipso respondió: nada")["eco_de_episodio"]["evidencia"] == "pedro pregunto:"
    assert "eco_de_episodio" in _senales("Retomo.\n\n[Charla con Mariana 2026-08-20] Mariana te presto el libro")
    # sin puntuacion antes del salto de linea tambien (el molde al inicio de un parrafo)
    assert _senales("Entendido\n\n[Charla con Mariana 2026-08-20] Mariana te presto el libro")["eco_de_episodio"]["evidencia"] == "[charla con mariana 2026-08-20]"
    assert "eco_de_episodio" in _senales("Segun el bloque: [anillo 2] el taller")
    assert "eco_de_episodio" in _senales("Como dice === Lo que subio del abismo (fuente: chats) ===")
    assert "eco_de_episodio" not in _senales("Pedro dijo que si (2026-08-20 fue el dia).")


def test_formato_no_pedido_json_entero_fence_u_objeto_con_tres_claves_salvo_con_codigo():
    assert _senales('{"tipoDeTarea": "chat", "traduccion": "x"}')["formato_no_pedido"]["forma"] == "json_entero"
    assert _senales("mira:\n```json\n{\"a\": 1}\n```")["formato_no_pedido"]["forma"] == "fence_json"
    # el objeto cortado sin cerrar (la salida real a 400 chars) tambien
    roto = 'Segun esto:\n{\n  "tipoDeTarea": "chat",\n  "traduccion": "x",\n  "memoriaProbabilistica": {\n    "pedroCrono'
    assert _senales(roto)["formato_no_pedido"]["forma"] == "objeto"
    assert "formato_no_pedido" not in _senales("```\ncalipso (main): limpio\n```")     # fence sin json
    for tipo in sorted(c.TIPOS_CON_CODIGO):
        assert "formato_no_pedido" not in _senales(roto, features={"type": tipo}), tipo


def test_cortada_por_done_reason_o_respuesta_vacia_y_nunca_con_steer():
    u = [{"prompt_tokens": 100, "completion_tokens": 5}, {"prompt_tokens": 200, "done_reason": "length"}]
    assert _senales("hola que", usages=u)["cortada"]["evidencia"] == "done_reason=length"
    assert _senales(" ... ")["cortada"]["evidencia"] == "respuesta vacia"
    assert "cortada" not in _senales("hola …(interrumpido)", usages=u, steered=True)
    assert "cortada" not in _senales("hola", usages=[{"done_reason": "stop"}])


def test_fuga_de_template_es_un_rol_solo_en_una_linea_o_un_token_de_chatml():
    assert _senales("para通信\nuser\n继续用中文回答")["fuga_de_template"]["evidencia"] == "user"
    assert "fuga_de_template" in _senales("hola <|im_end|>")
    assert "fuga_de_template" not in _senales("el user de la app entra por /login")


# --- dispatch guarda done_reason ------------------------------------------

def _stream(lineas):
    class _Resp:
        def __iter__(self):
            return iter([json.dumps(l).encode() for l in lineas])

        def close(self):
            pass
    return _Resp()


def test_dispatch_guarda_done_reason_en_chat_y_en_generate(monkeypatch):
    lineas = [{"message": {"content": "ho"}, "response": "ho", "done": False},
              {"message": {"content": "la"}, "response": "la", "done": True,
               "done_reason": "length", "prompt_eval_count": 7900, "eval_count": 300}]
    monkeypatch.setattr(dispatch, "_http_post_stream", lambda url, payload, headers=None: _stream(lineas))
    usage = {}
    assert "".join(dispatch._ollama_chat_chunks("http://x/api/generate", {}, usage)) == "hola"
    assert usage == {"prompt_tokens": 7900, "completion_tokens": 300, "done_reason": "length"}
    usage = {}
    assert "".join(dispatch._ollama_text_chunks("http://x/api/generate", {}, usage)) == "hola"
    assert usage == {"prompt_tokens": 7900, "completion_tokens": 300, "done_reason": "length"}
    # sin el campo en el done: None, no una cadena inventada
    monkeypatch.setattr(dispatch, "_http_post_stream",
                        lambda url, payload, headers=None: _stream([{"message": {"content": "x"}, "done": True}]))
    usage = {}
    list(dispatch._ollama_chat_chunks("http://x/api/generate", {}, usage))
    assert usage["done_reason"] is None
