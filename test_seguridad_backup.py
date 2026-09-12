"""Revision de seguridad 2026-09-07, C6: el backup no respalda la credencial
del servidor (se regenera), no arrastra logs, nace 0600, y el motor de
permisos trata backups/ entero como credencial (los zips viejos la traen
adentro). Y capa de sesion, invariante 7: `sesiones.json` entra a las dos
listas por lo mismo."""
import stat
import zipfile

from calipso import backup
from calipso.permisos import acciones


def _sembrar_home(tmp_path):
    (tmp_path / "token").write_text("secreto", encoding="utf-8")
    (tmp_path / "totp_secret").write_text("semilla", encoding="utf-8")
    (tmp_path / "chats.json").write_text("{}", encoding="utf-8")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "server.log").write_text("GET /?token=secreto",
                                                  encoding="utf-8")
    (tmp_path / "global" / "core").mkdir(parents=True)
    (tmp_path / "global" / "core" / "perfil.md").write_text("- hecho\n",
                                                            encoding="utf-8")


def test_backup_sin_secretos_ni_logs_y_0600(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "CALIPSO_HOME", tmp_path)
    _sembrar_home(tmp_path)
    r = backup.create_backup(stamp="test")
    assert r["ok"]
    with zipfile.ZipFile(r["path"]) as zf:
        nombres = set(zf.namelist())
    assert "chats.json" in nombres
    assert "global/core/perfil.md" in nombres
    assert "token" not in nombres
    assert "totp_secret" not in nombres
    assert not any(n.startswith("logs/") for n in nombres)
    modo = stat.S_IMODE((tmp_path / "backups" /
                         "calipso-backup-test.zip").stat().st_mode)
    assert modo == 0o600


def test_el_cache_del_tokenizador_no_se_respalda(tmp_path, monkeypatch):
    """Ola de fix del cierre (punto 8): tokenizador/ son 11-23 MB que se
    regeneran desde el GGUF; no van al zip."""
    monkeypatch.setattr(backup, "CALIPSO_HOME", tmp_path)
    _sembrar_home(tmp_path)
    (tmp_path / "tokenizador").mkdir()
    (tmp_path / "tokenizador" / "sha256-abc.json").write_text("{}", encoding="utf-8")
    # la exclusion es de la RAIZ (ahi vive el cache): un "tokenizador" dentro
    # de un proyecto es una carpeta comun y se respalda
    anidado = tmp_path / "projects" / "x" / "tokenizador"
    anidado.mkdir(parents=True)
    (anidado / "f.json").write_text("{}", encoding="utf-8")
    r = backup.create_backup(stamp="test")
    assert r["ok"]
    with zipfile.ZipFile(r["path"]) as zf:
        nombres = set(zf.namelist())
    assert "chats.json" in nombres
    assert not any(n.startswith("tokenizador/") for n in nombres)
    assert "projects/x/tokenizador/f.json" in nombres


def test_logs_anidado_si_se_respalda(tmp_path, monkeypatch):
    # La exclusion de logs/ es de la RAIZ (ahi vive el access log con el
    # token); un logs/ dentro de un proyecto es una carpeta comun.
    monkeypatch.setattr(backup, "CALIPSO_HOME", tmp_path)
    d = tmp_path / "projects" / "x" / "logs"
    d.mkdir(parents=True)
    (d / "run.log").write_text("normal", encoding="utf-8")
    r = backup.create_backup(stamp="logsanidado")
    with zipfile.ZipFile(r["path"]) as zf:
        assert "projects/x/logs/run.log" in zf.namelist()


def test_un_token_anidado_si_se_respalda(tmp_path, monkeypatch):
    # La exclusion es de la RAIZ del home: un archivo que se llame "token"
    # dentro de un proyecto es un archivo comun.
    monkeypatch.setattr(backup, "CALIPSO_HOME", tmp_path)
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "token").write_text("no es LA credencial",
                                                 encoding="utf-8")
    r = backup.create_backup(stamp="anidado")
    with zipfile.ZipFile(r["path"]) as zf:
        assert "projects/token" in zf.namelist()


def test_backups_es_credencial_del_servidor(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    assert acciones.es_credencial_del_servidor(tmp_path / "token")
    assert acciones.es_credencial_del_servidor(tmp_path / "backups")
    assert acciones.es_credencial_del_servidor(
        tmp_path / "backups" / "calipso-backup-x.zip")
    assert not acciones.es_credencial_del_servidor(tmp_path / "chats.json")


def test_sesiones_json_fuera_del_backup(tmp_path, monkeypatch):
    # El almacen de sesiones tampoco se respalda (invariante 7): un zip
    # viejo con los hashes y los id_pedido adentro es la misma puerta de al
    # lado que ya abrio el token en C6. Se regenera solo: los aparatos
    # vuelven a golpear.
    monkeypatch.setattr(backup, "CALIPSO_HOME", tmp_path)
    (tmp_path / "sesiones.json").write_text("[]", encoding="utf-8")
    (tmp_path / "chats.json").write_text("{}", encoding="utf-8")
    r = backup.create_backup(stamp="sesiones")
    with zipfile.ZipFile(r["path"]) as zf:
        nombres = set(zf.namelist())
    assert "sesiones.json" not in nombres
    assert "chats.json" in nombres


def test_sesiones_json_es_credencial_del_servidor(tmp_path, monkeypatch):
    # Escribirlo es fabricar una sesion viva sin pasar por Pedro (el disco
    # guarda sha256(id): un agente elige el id y planta su hash); leerlo
    # entrega los id_pedido pendientes. Por eso entra al NUNCA.
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    assert acciones.es_credencial_del_servidor(tmp_path / "sesiones.json")
    # El NUNCA es la ruta exacta del almacen: un archivo homonimo dentro de
    # un proyecto de Pedro sigue siendo un archivo comun.
    assert not acciones.es_credencial_del_servidor(
        tmp_path / "projects" / "sesiones.json")
