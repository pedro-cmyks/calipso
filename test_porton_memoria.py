"""El porton de la memoria con procedencia (experimentos/porton_memoria.py)
no se corre en la suite (levanta servers y habla con Ollama); lo que se
prueba aca es lo que se puede probar en seco: el worktree de main de la
condicion `antes`."""
from __future__ import annotations

from experimentos import porton_memoria as porton


def test_el_worktree_de_main_se_crea_despues_de_un_prune(monkeypatch, tmp_path):
    """Un worktree huerfano (el script murio por SIGKILL y alguien borro
    /tmp/calipso-main-porton a mano) sigue registrado en git y hace fallar
    `git worktree add` ("missing but already registered"). `prune` antes
    del `add` lo tolera; el chequeo del directorio sigue siendo previo."""
    llamadas = []

    def _git_doble(raiz, *args):
        llamadas.append(args)
        return "279dfb0"

    monkeypatch.setattr(porton, "_git", _git_doble)
    monkeypatch.setattr(porton, "WORKTREE_MAIN", tmp_path / "calipso-main-porton")
    assert porton.worktree_main_crear() == tmp_path / "calipso-main-porton"
    assert llamadas[0] == ("worktree", "prune")
    assert llamadas[1] == ("worktree", "add", "--detach",
                           str(tmp_path / "calipso-main-porton"), "main")
    assert llamadas.index(("worktree", "prune")) < llamadas.index(llamadas[1])


def test_el_worktree_de_main_se_niega_si_el_directorio_ya_existe(monkeypatch, tmp_path):
    import pytest
    llamadas = []
    monkeypatch.setattr(porton, "_git", lambda raiz, *args: llamadas.append(args) or "")
    existente = tmp_path / "calipso-main-porton"
    existente.mkdir()
    monkeypatch.setattr(porton, "WORKTREE_MAIN", existente)
    with pytest.raises(SystemExit):
        porton.worktree_main_crear()
    assert llamadas == []   # no toca git si el directorio esta ahi


def test_la_condicion_antes_no_pasa_memoria_presentar_y_a_b_si(monkeypatch, tmp_path):
    """`antes` es main exacto (ruling 11): el server de esa condicion no
    recibe MEMORIA_PRESENTAR (main no la lee, y la variante `off` que se le
    pasaba murio en el cierre); tampoco hereda la que Pedro tenga exportada.
    A y B la reciben con su letra."""
    monkeypatch.setenv("MEMORIA_PRESENTAR", "B")   # lo exportado no viaja
    assert "off" not in porton.CONDICIONES.values()
    env = porton.entorno_server(tmp_path, tmp_path / "raiz", "tok", porton.CONDICIONES["antes"])
    assert "MEMORIA_PRESENTAR" not in env
    assert env["CALIPSO_HOME"] == str(tmp_path)
    assert env["CALIPSO_ROOT"] == str(tmp_path / "raiz")
    assert env["CALIPSO_TOKEN"] == "tok" and env["CALIPSO_NO_TOTP"] == "1"
    for condicion in ("A", "B"):
        env = porton.entorno_server(tmp_path, tmp_path, "tok", porton.CONDICIONES[condicion])
        assert env["MEMORIA_PRESENTAR"] == condicion
