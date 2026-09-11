"""La estructura del turno (spec canarios 2026-09-11, seccion 2.3): el
system viaja como secciones hasta el payload, y SIN recorte el string que
llega al modelo es BYTE A BYTE el de main (el snapshot se arma aca con la
formula de main: `compile_context` + los appends con `\\n\\n`).

`_system_de_main` es una TRANSCRIPCION de server.py:3782-3812 de main
b120bb0 (vision :3794, aviso :3798-3803, adjuntos :3807-3808,
departamento :3809-3810, web :3811-3812, con los mismos gates
`not a_la_nube_tapado`), no una captura: si la transcripcion tuviera un
error el test pasaria contra si mismo. La evidencia INDEPENDIENTE a nivel
ws es el harness: test_abismo_chat.py:308-309, :349 y :432 miran
`llamadas[i]["messages"][0]["content"]` (system + bloques) y no cambian."""
from __future__ import annotations

import calipso.server as srv
from calipso import prompt_compiler
from calipso.abismo import turno

VISION = "Una foto de un gato."
ADJUNTOS = ("=== Adjuntos del turno ===\n--- adjunto notas.txt (texto, text/plain, id=abc) ---\n"
            "hola\n\n--- adjunto otro.md (texto, text/markdown, id=def) ---\n# titulo")
DEP = "=== Departamento en foco ===\nPedro esta mirando atlas (id dep:atlas, zona norte, estado activo)."
WEB = {"query": "bazzite", "results": [{"title": "Bazzite", "url": "https://bazzite.gg", "snippet": "un so"}],
       "pages": []}
SECCIONES = [("Sistema", "S"), ("Memoria nucleo", "M"), ("Contrato interno", "=== Lenguaje interno ===\nC"),
             ("Recuerdos relevantes", "- Pedro dijo (2026-08-20): a"), ("Estado operativo", "=== Estado real ===\nO")]


def _system_de_main(secciones, *, vision="", aviso=False, adjuntos="", dep="", web=None, nube=False):
    """La formula de main b120bb0 (server.py:3782-3812), tal cual."""
    system = prompt_compiler.render_context(secciones) if secciones[0][0] else secciones[0][1]
    if vision:
        system += "\n\n=== Vision de imagen adjunta ===\n" + vision
    elif aviso:
        system += ("\n\n[Imagen adjunta registrada. Para análisis visual automático: "
                   "instala 'ollama pull moondream' o configura ANTHROPIC_API_KEY.]")
    if adjuntos and not nube:
        system += "\n\n" + adjuntos
    if dep and not nube:
        system += "\n\n" + dep
    if web and (web["results"] or web["pages"]):
        system += "\n\n" + srv.calipso_web.context_block(web)
    return system


def test_render_context_con_titulo_vacio_es_cruda_y_seccion_de_bloque_pela_el_encabezado():
    assert prompt_compiler.render_context([("", "crudo"), ("T", "b")]) == "crudo\n\n=== T ===\nb"
    assert prompt_compiler.seccion_de_bloque(ADJUNTOS) == ("Adjuntos del turno", ADJUNTOS.split("\n", 1)[1])
    assert prompt_compiler.seccion_de_bloque("=== Resultados web para: x ===\n- a") == ("Resultados web para: x", "- a")
    assert prompt_compiler.seccion_de_bloque("sin encabezado\nmas") == ("", "sin encabezado\nmas")
    assert prompt_compiler.seccion_de_bloque("=== ===\nx") == ("", "=== ===\nx")
    # render(seccion_de_bloque(b)) == b para todo bloque con encabezado
    for b in (ADJUNTOS, DEP, srv.calipso_web.context_block(WEB),
              "=== Lo que subio del abismo (fuente: chats) ===\n[anillo 2]\nx"):
        assert prompt_compiler.render_context([prompt_compiler.seccion_de_bloque(b)]) == b


def test_el_system_del_turno_es_byte_a_byte_el_de_main_sin_recorte():
    casos = [
        dict(),
        dict(vision=VISION),
        dict(aviso=True),
        dict(adjuntos=ADJUNTOS),
        dict(dep=DEP),
        dict(web=WEB),
        dict(vision=VISION, adjuntos=ADJUNTOS, dep=DEP, web=WEB),
        dict(aviso=True, adjuntos=ADJUNTOS, dep=DEP),
    ]
    for caso in casos:
        secciones = srv._secciones_del_turno(
            SECCIONES, vision_text=caso.get("vision", ""), aviso_imagen=caso.get("aviso", False),
            attachment_context=caso.get("adjuntos", ""), bloque_dep=caso.get("dep", ""),
            web_material=caso.get("web"))
        assert prompt_compiler.render_context(secciones) == _system_de_main(SECCIONES, **caso), caso
    # en /nube tapado: el system minimo crudo, sin adjuntos ni departamento
    nube = [("", srv._sistema_nube())]
    secciones = srv._secciones_del_turno(nube, attachment_context=ADJUNTOS, bloque_dep=DEP,
                                         a_la_nube_tapado=True)
    assert prompt_compiler.render_context(secciones) == srv._sistema_nube()
    assert secciones == nube


def test_la_reentrada_por_secciones_rinde_el_append_de_main():
    bloques = ["=== Lo que subio del abismo (fuente: chats) ===\n[anillo 2]\n[Charla 2026-08-20] libro",
               "=== Lo que subio del abismo (fuente: memoria) ===\n[anillo 3]\n- Pedro dijo (2026-08-20): x"]
    secciones, usuario = turno.prompt_reentrada(SECCIONES, bloques, ["Dejame ver "], "que libro")
    esperado = prompt_compiler.render_context(SECCIONES) + "".join("\n\n" + b for b in bloques)
    assert prompt_compiler.render_context(secciones) == esperado
    assert [t for t, _ in secciones[-2:]] == ["Lo que subio del abismo (fuente: chats)",
                                              "Lo que subio del abismo (fuente: memoria)"]
    assert usuario.startswith("que libro\n\nVenias diciendo: Dejame ver \n")
    # la letra del final es una de las medidas (con bloques, la Task 7 pone la nueva)
    assert usuario.split("\n")[-1] in turno.LETRAS_REENTRADA


def test_build_context_devuelve_secciones_y_sistema_del_turno_las_pasa(monkeypatch):
    monkeypatch.setattr(srv, "_build_context", lambda m, r, f=None: [("Sistema", "S"), ("Estado operativo", r)])
    assert srv._sistema_del_turno("m", "rt", {}, a_la_nube_tapado=False) == [("Sistema", "S"), ("Estado operativo", "rt")]
    assert srv._sistema_del_turno("m", "rt", {}, a_la_nube_tapado=True) == [("", srv._sistema_nube())]


def test_chunks_for_recibe_el_historial_prearmado_y_devuelve_los_messages(monkeypatch):
    llamado = {}

    def espia(url, payload, usage=None):
        llamado.update(payload)
        yield "ok"
    monkeypatch.setattr(srv.dispatch, "_ollama_chat_chunks", espia)
    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: True)
    monkeypatch.setattr(srv, "_history_messages", lambda chat_id, limit=12: [{"role": "user", "content": "del chat"}])
    hist = [{"role": "user", "content": "u"}, {"role": "assistant", "content": "a"}]
    gen, modelo, mensajes = srv._chunks_for("local", "SYS", "hola", {}, chat_id="c1", history=hist)
    assert "".join(gen) == "ok"
    assert mensajes == [{"role": "system", "content": "SYS"}, *hist, {"role": "user", "content": "hola"}]
    assert llamado["messages"] == mensajes and llamado["options"] == {"num_ctx": srv.CHAT_NUM_CTX}
    # sin `history`, se lee del chat como siempre
    _, _, mensajes = srv._chunks_for("local", "SYS", "hola", {}, chat_id="c1")
    assert mensajes[1] == {"role": "user", "content": "del chat"}
    # con Ollama caido: el generador del fallo cerrado y lo que HABRIA viajado
    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: False)
    gen, _, mensajes = srv._chunks_for("local", "SYS", "hola", {}, chat_id=None, history=[])
    assert "Ollama no esta disponible" in "".join(gen) and len(mensajes) == 2
