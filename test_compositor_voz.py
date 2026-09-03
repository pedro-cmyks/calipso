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
    # chat "nuevo" aparece PRIMERO en el dict pero es "viejo" el que tiene el
    # mensaje mas antiguo -- si el codigo usara reversed() (orden estructural)
    # daria el chat "viejo" primero, mal; por ts da "nuevo" primero, bien.
    data = {"active": None, "chats": {
        "nuevo": {"messages": [{"role": "user", "text": "mensaje nuevo largo de verdad", "ts": "2026-09-01T10:00:00"}]},
        "viejo": {"messages": [{"role": "user", "text": "mensaje viejo largo de verdad", "ts": "2026-01-01T10:00:00"}]}}}
    ej = ejemplos_de_voz(data)
    assert ej[0] == "mensaje nuevo largo de verdad"


def test_los_guardados_van_primero():
    # con /mia guardados, esos ejemplos van ANTES que los mensajes de chat.
    data = _chats([("user", "un mensaje de chat largo cualquiera")])
    guardados = [{"texto": "Hola Ana, confirmo la reunion del jueves", "ts": "2026-09-03T10:00:00"}]
    ej = ejemplos_de_voz(data, guardados)
    assert ej[0] == "Hola Ana, confirmo la reunion del jueves"
    assert "un mensaje de chat largo cualquiera" in ej   # rellena con el chat


def test_guardados_llenos_desplazan_al_chat():
    # con n o mas guardados, los mensajes de chat ya no entran.
    data = _chats([("user", "orden vieja de chat que no deberia entrar")])
    guardados = [{"texto": f"ejemplo real de voz numero {i} escrito por pedro", "ts": f"2026-09-03T10:0{i}:00"}
                 for i in range(3)]
    ej = ejemplos_de_voz(data, guardados, n=3)
    assert len(ej) == 3
    assert "orden vieja de chat que no deberia entrar" not in ej


def test_guardados_ordenados_por_ts():
    data = _chats()
    guardados = [
        {"texto": "el mas viejo de los guardados largo", "ts": "2026-01-01T10:00:00"},
        {"texto": "el mas nuevo de los guardados largo", "ts": "2026-09-03T10:00:00"}]
    ej = ejemplos_de_voz(data, guardados)
    assert ej[0] == "el mas nuevo de los guardados largo"


def test_sin_guardados_identico_a_hoy():
    data = _chats([("user", "che como andas todo bien por aca")])
    assert ejemplos_de_voz(data) == ejemplos_de_voz(data, [])
