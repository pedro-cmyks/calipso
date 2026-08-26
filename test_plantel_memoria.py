"""La memoria propia de un departamento (spec de la economia, seccion 6)."""
import calipso.memory as memoria


def test_cada_departamento_tiene_su_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(memoria, "CALIPSO_HOME", tmp_path)
    m = memoria.Memory()
    atlas = m.departamento("atlas")
    mercado = m.departamento("mercado")
    assert atlas.name == "departamento:atlas"
    assert atlas.core_dir != mercado.core_dir


def test_el_scope_se_memoiza(tmp_path, monkeypatch):
    """Cada Scope abre un cliente de Chroma y el jefe lo pide en cada tic."""
    monkeypatch.setattr(memoria, "CALIPSO_HOME", tmp_path)
    m = memoria.Memory()
    assert m.departamento("atlas") is m.departamento("atlas")


def test_lo_que_recuerda_un_departamento_no_se_filtra_al_chat(tmp_path, monkeypatch):
    """_scopes es la lectura combinada del chat: si el departamento entrara,
    la memoria de cada uno aparecería en todas las conversaciones."""
    monkeypatch.setattr(memoria, "CALIPSO_HOME", tmp_path)
    m = memoria.Memory()
    atlas = m.departamento("atlas")
    m.remember("pedro prefiere respuestas cortas", scope="global")
    atlas.remember("atlas decidio explorar precios", kind="jefe")
    assert atlas not in m._scopes
    hits = m.recall("atlas decidio explorar precios", n=5)
    assert hits, "sin nada en el chat la asercion de abajo pasaria por vacuidad"
    assert all("atlas decidio" not in (h.get("text") or "") for h in hits)


def test_los_nombres_que_slugean_igual_son_el_mismo_departamento(tmp_path, monkeypatch):
    """No es un descuido: _slug normaliza, asi que "Atlas" y "atlas" son el
    mismo departamento a proposito, y el scope se llama por la clave para que
    el nombre no mienta sobre que memoria devolvio."""
    monkeypatch.setattr(memoria, "CALIPSO_HOME", tmp_path)
    m = memoria.Memory()
    assert m.departamento("Atlas") is m.departamento("atlas")
    assert m.departamento("Atlas").name == "departamento:atlas"
