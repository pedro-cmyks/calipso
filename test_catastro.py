#!/usr/bin/env python3
"""
test_catastro.py - el escaneo de proyectos (calipso/catastro.py) y la
seccion "Proyectos" que arma calipso/prompt_compiler.py:proyectos_brief.

Aisla CALIPSO_HOME por test (fixture `home`, via monkeypatch): ningun test
de este archivo toca ~/.calipso real ni sus datos, y cada raiz declarada
en catastro.json tambien es un directorio temporal propio del test.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile

import pytest

from calipso import catastro
from calipso import prompt_compiler
from calipso import routines


def _git(args: list[str], cwd: pathlib.Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _repo(path: pathlib.Path, con_readme: str | None = None) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], path)
    _git(["config", "user.email", "pedro@example.com"], path)
    _git(["config", "user.name", "Pedro"], path)
    if con_readme is not None:
        (path / "README.md").write_text(con_readme, encoding="utf-8")
        _git(["add", "README.md"], path)
    _git(["commit", "-q", "--allow-empty", "-m", "inicial"], path)
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    calipso_home = tmp_path / "calipso_home"
    calipso_home.mkdir()
    monkeypatch.setattr(catastro, "CALIPSO_HOME", calipso_home)
    return calipso_home


def _declarar_raiz(home: pathlib.Path, raiz: pathlib.Path,
                   profundidad: int = 3) -> None:
    data = {"raices": [{"ruta": str(raiz), "profundidad": profundidad}],
           "proyectos": []}
    (home / "catastro.json").write_text(json.dumps(data), encoding="utf-8")


# --- 3.2: el criterio, y el escaneo de raices declaradas -------------------

def test_encuentra_carpeta_con_git_y_no_encuentra_carpeta_sin_git(tmp_path, home):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    _repo(raiz / "proyecto_real")
    sin_git = raiz / "no_es_proyecto"
    sin_git.mkdir()
    (sin_git / "archivo.txt").write_text("hola")
    _declarar_raiz(home, raiz)

    proyectos = catastro.escanear()

    nombres = {p["nombre"] for p in proyectos}
    assert "proyecto_real" in nombres
    assert "no_es_proyecto" not in nombres


def test_raiz_por_defecto_es_el_home_con_profundidad_3():
    raices = catastro.raices()
    assert len(raices) == 1
    assert raices[0]["profundidad"] == 3
    assert pathlib.Path(raices[0]["ruta"]) == pathlib.Path.home().resolve()


# --- 3.3: que se guarda, y que NO se lee ------------------------------------

def test_no_lee_ningun_archivo_del_proyecto_salvo_las_dos_lineas_del_readme(
        tmp_path, home):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    proyecto = _repo(
        raiz / "proyecto",
        con_readme="Titulo del proyecto\nResumen corto de una linea.\n"
                   "Tercera linea que no deberia entrar nunca.\n")
    (proyecto / "secreto.txt").write_text(
        "ESTO_NO_SE_DEBERIA_LEER_NUNCA_POR_EL_ESCANEO")
    _declarar_raiz(home, raiz)

    proyectos = catastro.escanear()

    p = next(p for p in proyectos if p["nombre"] == "proyecto")
    assert "Titulo del proyecto" in p["resumen"]
    assert "Resumen corto de una linea" in p["resumen"]
    assert "Tercera linea" not in p["resumen"]
    assert "ESTO_NO_SE_DEBERIA_LEER_NUNCA" not in json.dumps(p)


def test_rama_y_ultimo_commit_salen_de_git(tmp_path, home):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    _repo(raiz / "proyecto")
    _declarar_raiz(home, raiz)

    proyectos = catastro.escanear()

    p = next(p for p in proyectos if p["nombre"] == "proyecto")
    assert p["rama"] in ("main", "master")
    assert p["ultimo_commit"] is not None


def test_departamento_lo_escribe_pedro_y_sobrevive_al_reescaneo(tmp_path, home):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    _repo(raiz / "proyecto")
    _declarar_raiz(home, raiz)
    catastro.escanear()

    # Pedro (no el escaneo) le pone un departamento
    data = catastro._cargar_json()
    for p in data["proyectos"]:
        if p["nombre"] == "proyecto":
            p["departamento"] = "atlas"
    catastro._guardar_json(data)

    proyectos = catastro.escanear()  # un segundo escaneo no lo pisa
    p = next(p for p in proyectos if p["nombre"] == "proyecto")
    assert p["departamento"] == "atlas"


# --- la trampa del worktree: .git es un archivo, no una carpeta ------------

def test_worktree_con_git_como_archivo_se_reconoce_y_se_lee_con_git(
        tmp_path):
    principal = _repo(tmp_path / "principal")
    wt = tmp_path / "worktree"
    _git(["worktree", "add", "-q", "-b", "rama-secundaria", str(wt)],
        principal)

    assert (wt / ".git").is_file(), "la trampa: aca .git NO es una carpeta"
    assert catastro._es_repo(wt)

    rama, commit = catastro._rama_y_commit(wt)
    assert rama == "rama-secundaria"
    assert commit is not None


def test_worktree_anidado_se_encuentra_por_reconciliacion_de_slugs(
        tmp_path, home):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    principal = _repo(raiz / "principal")
    # el worktree vive ADENTRO del repo principal, en una carpeta oculta --
    # exactamente como calipso/.claude/worktrees/<rama> en esta maquina.
    wt = principal / ".oculto" / "worktrees" / "rama-x"
    wt.parent.mkdir(parents=True)
    _git(["worktree", "add", "-q", "-b", "rama-x", str(wt)], principal)
    _declarar_raiz(home, raiz)

    # el escaneo normal (profundidad 3, sin carpetas ocultas) NO lo
    # encuentra: esta adentro de ".oculto".
    directo = catastro._escanear_bajo(raiz, 3)
    assert wt.resolve() not in {p.resolve() for p in directo}

    # la memoria hibrida ya conoce el slug del worktree (memory.py ya lo
    # uso alguna vez): con eso, la reconciliacion de slugs SI lo encuentra.
    slug = catastro._slug(wt.resolve())
    (home / "projects" / slug).mkdir(parents=True)

    proyectos = catastro.escanear()
    nombres = {p["nombre"] for p in proyectos}
    assert "rama-x" in nombres


# --- la trampa del symlink: /home -> /var/home en esta maquina -------------

def test_raiz_declarada_via_symlink_se_compara_resuelta(tmp_path, home):
    real = tmp_path / "home_real"
    real.mkdir()
    _repo(real / "proyecto")
    enlace = tmp_path / "home_enlace"
    enlace.symlink_to(real)
    _declarar_raiz(home, enlace)  # la raiz se declaro via el symlink

    # dentro_de_alguna_raiz tiene que dar lo mismo entrando por la ruta
    # real o por el symlink: si compara sobre texto en vez de resuelto, se
    # corre sola con solo escribir la ruta distinto (3.2 del spec).
    assert catastro.dentro_de_alguna_raiz(real / "proyecto")
    assert catastro.dentro_de_alguna_raiz(enlace / "proyecto")
    assert not catastro.dentro_de_alguna_raiz(tmp_path / "afuera")


def test_una_raiz_no_puede_ser_barra(tmp_path, home):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    _declarar_raiz(home, raiz)
    assert not catastro.dentro_de_alguna_raiz(pathlib.Path("/"))


# --- el piso de ejecucion: git blindado contra el repo que lee -------------

def test_git_config_malicioso_no_se_ejecuta(tmp_path):
    marcador = tmp_path / "PRUEBA_EJECUTADA"
    repo = _repo(tmp_path / "repo_malicioso")
    _git(["config", "core.fsmonitor", f"touch {marcador}; false"], repo)

    catastro._rama_y_commit(repo)

    assert not marcador.exists(), (
        "el .git/config del repo ejecuto un comando via catastro._git")


# --- 3.4: el bloque de prompt, techo duro y "en foco" -----------------------

def _proyecto_sintetico(i: int, nombre: str | None = None,
                        rama: str = "main", departamento: str | None = None,
                        largo: bool = False) -> dict:
    sufijo = "-" + "x" * 40 if largo else ""
    return {
        "ruta": f"/tmp/proyecto{i}{sufijo}",
        "nombre": nombre or f"proyecto{i}{sufijo}",
        "rama": rama + ("-" + "y" * 40 if largo else ""),
        "ultimo_commit": "2026-08-01T00:00:00-05:00",
        "resumen": "",
        "departamento": departamento,
        "visto": f"2026-08-{(i % 28) + 1:02d}T00:00:00",
    }


def test_bloque_de_prompt_corta_en_20_proyectos_y_avisa_cuantos_quedan(home):
    proyectos = [_proyecto_sintetico(i) for i in range(25)]
    catastro._guardar_json({"raices": catastro.raices(), "proyectos": proyectos})

    texto = prompt_compiler.proyectos_brief()

    # dos techos independientes (3.4): 20 proyectos Y 1200 caracteres. Con
    # 25 sinteticos puede cortar antes de llegar a 20 si el texto ya no
    # entra -- lo que no puede pasar es mostrar mas de 20, ni superar el
    # techo de caracteres, ni omitir el aviso de cuantos quedaron afuera.
    mostrados = texto.count(", sin departamento")
    assert mostrados <= 20
    assert f"y {25 - mostrados} proyecto(s) mas; preguntame por nombre." in texto
    assert len(texto) <= prompt_compiler.PROYECTOS_BRIEF_MAX


def test_bloque_de_prompt_corta_justo_en_20_cuando_el_texto_entra(home):
    # sinteticos cortos: entran los 20 en el techo de caracteres, asi que
    # lo unico que puede estar cortando es el techo de 20 proyectos.
    proyectos = [{
        "ruta": f"/t/{i}", "nombre": f"p{i}", "rama": "m",
        "ultimo_commit": "2026-08-01T00:00:00-05:00", "resumen": "",
        "departamento": None, "visto": f"2026-08-{(i % 28) + 1:02d}T00:00:00",
    } for i in range(23)]
    catastro._guardar_json({"raices": catastro.raices(), "proyectos": proyectos})

    texto = prompt_compiler.proyectos_brief()

    assert texto.count(", sin departamento") == 20
    assert "y 3 proyecto(s) mas; preguntame por nombre." in texto
    assert len(texto) <= prompt_compiler.PROYECTOS_BRIEF_MAX


def test_bloque_de_prompt_corta_por_caracteres_aunque_haya_menos_de_20(home):
    proyectos = [_proyecto_sintetico(i, largo=True) for i in range(20)]
    catastro._guardar_json({"raices": catastro.raices(), "proyectos": proyectos})

    texto = prompt_compiler.proyectos_brief()

    assert len(texto) <= prompt_compiler.PROYECTOS_BRIEF_MAX
    assert "proyecto(s) mas" in texto


def test_proyecto_en_foco_no_muestra_departamento(home):
    proyectos = [_proyecto_sintetico(0, nombre="actual", departamento="atlas")]
    proyectos[0]["ruta"] = "/tmp/actual"
    catastro._guardar_json({"raices": catastro.raices(), "proyectos": proyectos})

    texto = prompt_compiler.proyectos_brief("/tmp/actual")

    assert "en foco" in texto
    assert "dep atlas" not in texto


def test_proyecto_sin_departamento_no_inventa_uno(home):
    proyectos = [_proyecto_sintetico(0, nombre="otro")]
    catastro._guardar_json({"raices": catastro.raices(), "proyectos": proyectos})

    texto = prompt_compiler.proyectos_brief("/tmp/no-es-este")

    assert "sin departamento" in texto


def test_sin_proyectos_dice_la_verdad_en_vez_de_nada(home):
    catastro._guardar_json({"raices": catastro.raices(), "proyectos": []})
    texto = prompt_compiler.proyectos_brief()
    assert "no encontro ninguno" in texto


# --- routines.KINDS suma "catastro" (3.2) -----------------------------------

def test_routines_kinds_incluye_catastro():
    assert "catastro" in routines.KINDS


def test_routines_seed_incluye_catastro_habilitada(tmp_path, monkeypatch):
    calipso_home = tmp_path / "rt_home"
    monkeypatch.setattr(routines, "CALIPSO_HOME", calipso_home)
    seeded = routines.load()
    catastro_rt = next(r for r in seeded if r["kind"] == "catastro")
    assert catastro_rt["enabled"] is True
    # las tres viejas siguen naciendo apagadas -- este cambio no las toca.
    for r in seeded:
        if r["kind"] != "catastro":
            assert r["enabled"] is False


# --- la primera lectura de la vida del catastro escanea sola ---------------

def test_cargar_sin_forzar_escanea_solo_si_no_existe_el_archivo(
        tmp_path, home, monkeypatch):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    _repo(raiz / "proyecto")
    # sin catastro.json todavia: la raiz que se usa es la por defecto
    # (el home de Pedro). Para esta prueba, "el home" pasa a ser `raiz`,
    # en vez de escribir un catastro.json a mano -- eso creaba el archivo
    # que este test necesita que todavia NO exista.
    monkeypatch.setattr(pathlib.Path, "home", lambda: raiz)

    assert not (home / "catastro.json").exists()
    proyectos = catastro.cargar()  # primera lectura: escanea sola
    assert any(p["nombre"] == "proyecto" for p in proyectos)

    # un segundo proyecto que aparece despues NO se ve sin forzar: cargar()
    # ya no vuelve a escanear el disco (eso es trabajo de la rutina).
    _repo(raiz / "proyecto_nuevo")
    proyectos2 = catastro.cargar()
    assert not any(p["nombre"] == "proyecto_nuevo" for p in proyectos2)

    proyectos3 = catastro.cargar(forzar_escaneo=True)
    assert any(p["nombre"] == "proyecto_nuevo" for p in proyectos3)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
