"""Tests de los secretos en disco: el token y el secreto TOTP van en 0600.

El token no es solo un segundo factor. El shell de escritorio entra con el
(`/?token=...`) en vez de saltear el TOTP, asi que es LA credencial de la
instalacion: quien lo lee entra a un servidor con acceso a todos los archivos
de Pedro y a los endpoints de la economia.
"""
import pathlib

import pytest

import calipso.server as srv


def modo(ruta: pathlib.Path) -> int:
    return ruta.stat().st_mode & 0o777


def test_un_token_nuevo_nace_en_0600(tmp_path, monkeypatch):
    ruta = tmp_path / ".calipso" / "token"
    monkeypatch.setattr(srv, "_TOKEN_FILE", ruta)
    monkeypatch.delenv("CALIPSO_TOKEN", raising=False)
    tok = srv._load_token()
    assert tok and ruta.read_text(encoding="utf-8").strip() == tok
    assert modo(ruta) == 0o600, f"nacio en {oct(modo(ruta))}"


def test_un_token_viejo_y_abierto_se_cierra_al_leerlo(tmp_path, monkeypatch):
    """El caso real: la instalacion de Pedro ya tenia el token en 0644."""
    ruta = tmp_path / ".calipso" / "token"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("secreto-viejo", encoding="utf-8")
    ruta.chmod(0o644)
    monkeypatch.setattr(srv, "_TOKEN_FILE", ruta)
    monkeypatch.delenv("CALIPSO_TOKEN", raising=False)
    assert srv._load_token() == "secreto-viejo"   # no lo rota, solo lo cierra
    assert modo(ruta) == 0o600


def test_el_secreto_totp_tambien(tmp_path, monkeypatch):
    ruta = tmp_path / ".calipso" / "totp_secret"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("JBSWY3DPEHPK3PXP", encoding="utf-8")
    ruta.chmod(0o644)
    monkeypatch.setattr(srv, "_TOTP_SECRET_FILE", ruta)
    assert srv._get_totp_secret() == "JBSWY3DPEHPK3PXP"
    assert modo(ruta) == 0o600


def test_endurecer_no_toca_lo_que_ya_estaba_cerrado(tmp_path):
    ruta = tmp_path / "x"
    ruta.touch(mode=0o600)
    srv._endurecer(ruta)
    assert modo(ruta) == 0o600


def test_endurecer_sobre_un_archivo_que_no_existe_no_revienta(tmp_path):
    """Se llama en el arranque: no puede ser una fuente de fallas nueva."""
    srv._endurecer(tmp_path / "no-existe")
