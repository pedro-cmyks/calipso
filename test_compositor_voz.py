# test_compositor_voz.py
from calipso.compositor.voz import ejemplos_de_voz


def _chats(*mensajes_por_chat):
    # cada arg es una lista de (role, text); arma la forma de chats._load().
    # cada mensaje recibe un ts creciente (orden global de aparicion) para
    # que los asserts de recencia no dependan del orden estructural del dict.
    chats = {}
    contador = 0
    for i, msgs in enumerate(mensajes_por_chat):
        mensajes = []
        for r, t in msgs:
            mensajes.append({"role": r, "text": t, "ts": f"{contador:06d}"})
            contador += 1
        chats[f"c{i}"] = {"messages": mensajes}
    return {"active": None, "chats": chats}


def test_solo_mensajes_de_pedro():
    data = _chats([("user", "che como andas"), ("assistant", "bien vos?"),
                   ("user", "todo piola")])
    ej = ejemplos_de_voz(data)
    assert "che como andas" in ej and "todo piola" in ej
    assert "bien vos?" not in ej   # eso lo dijo calipso, no Pedro


def test_saltea_triviales_y_directivas():
    data = _chats([("user", "1"), ("user", "dale"), ("user", "/nube"),
                   ("user", "armame un plan largo para el finde con detalle")])
    ej = ejemplos_de_voz(data)
    assert ej == ["armame un plan largo para el finde con detalle"]


def test_sin_duplicados_y_tope_n():
    data = _chats([("user", "hola")] * 10 + [("user", f"mensaje {i} distinto y largo") for i in range(10)])
    ej = ejemplos_de_voz(data, n=3)
    assert len(ej) == 3
    assert len(set(ej)) == 3      # sin duplicados


def test_los_mas_recientes_primero():
    data = _chats([("user", "el primero de todos largo"),
                   ("user", "el ultimo que escribio pedro largo")])
    ej = ejemplos_de_voz(data)
    assert ej[0] == "el ultimo que escribio pedro largo"


def test_recencia_real_entre_chats():
    # el orden real es por ts, no por posicion del chat en el dict: aca el
    # chat "viejo" aparece antes en el dict pero su mensaje es mas antiguo.
    data = {"active": None, "chats": {
        "viejo": {"messages": [{"role": "user", "text": "mensaje viejo largo de verdad", "ts": "2026-01-01T10:00:00"}]},
        "nuevo": {"messages": [{"role": "user", "text": "mensaje nuevo largo de verdad", "ts": "2026-09-01T10:00:00"}]}}}
    ej = ejemplos_de_voz(data)
    assert ej[0] == "mensaje nuevo largo de verdad"
