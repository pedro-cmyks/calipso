# test_compositor_voz.py
from calipso.compositor.voz import ejemplos_de_voz


def _chats(*mensajes_por_chat):
    # cada arg es una lista de (role, text); arma la forma de chats._load()
    chats = {}
    for i, msgs in enumerate(mensajes_por_chat):
        chats[f"c{i}"] = {"messages": [{"role": r, "text": t} for r, t in msgs]}
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
