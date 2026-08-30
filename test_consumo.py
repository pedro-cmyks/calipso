#!/usr/bin/env python3
"""
test_consumo.py - el probe pasivo de consumo (calipso/consumo.py): lectura
incremental de los jsonl que Claude Code y Codex escriben solos, identidad
por `id` (no por linea), robustez ante lineas rotas, y la garantia dura del
encargo -- que nunca se filtre contenido de una conversacion.

Aisla CALIPSO_HOME/CLAUDE_HOME/CODEX_HOME por test (fixture `home`): ningun
test de este archivo lee ~/.claude o ~/.codex reales, ni escribe en el
~/.calipso real -- las tres apuntan a directorios temporales propios.
"""
from __future__ import annotations

import datetime
import json
import pathlib

import pytest

from calipso import consumo


@pytest.fixture
def home(tmp_path, monkeypatch):
    calipso_home = tmp_path / "calipso_home"
    claude_home = tmp_path / "claude_home"
    codex_home = tmp_path / "codex_home"
    calipso_home.mkdir()
    claude_home.mkdir()
    codex_home.mkdir()
    # setenv, no monkeypatch.setattr: consumo.calipso_home()/raiz_claude()/
    # raiz_codex() leen la variable de entorno EN CADA LLAMADA (mismo
    # patron que catastro.calipso_home(), y por la misma razon: no importa
    # cuando se fijo la variable, ni si otro archivo de la suite ya
    # importo este modulo antes).
    monkeypatch.setenv("CALIPSO_HOME", str(calipso_home))
    monkeypatch.setenv("CLAUDE_HOME", str(claude_home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    return {"calipso": calipso_home, "claude": claude_home, "codex": codex_home}


def _escribir(path: pathlib.Path, lineas: list[dict | str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for linea in lineas:
            if isinstance(linea, str):
                fh.write(linea)
            else:
                fh.write(json.dumps(linea, ensure_ascii=False))
            fh.write("\n")


def _linea_claude(mid: str, ts: str, output_tokens: int, *, input_tokens=10,
                  cache_creation=0, cache_read=0, thinking=0, modelo="claude-sonnet-5",
                  content_type="text") -> dict:
    usage = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
    }
    if thinking:
        usage["output_tokens_details"] = {"thinking_tokens": thinking}
    return {
        "type": "assistant",
        "timestamp": ts,
        "uuid": f"u-{mid}-{content_type}",
        "message": {
            "id": mid,
            "model": modelo,
            "usage": usage,
            "content": [{"type": content_type, "text": "(irrelevante para el probe)"}],
        },
    }


def _linea_codex_token_count(ts: str, *, input_tokens=100, output_tokens=10,
                             cached=0, reasoning=0, primary_pct=5.0,
                             secondary_pct=1.0, primary_resets_at=2_000_000_000,
                             secondary_resets_at=2_000_600_000, total=500,
                             plan="plus") -> dict:
    return {
        "type": "event_msg",
        "timestamp": ts,
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {"total_tokens": total},
                "last_token_usage": {
                    "input_tokens": input_tokens, "output_tokens": output_tokens,
                    "cached_input_tokens": cached, "reasoning_output_tokens": reasoning,
                },
            },
            "rate_limits": {
                "primary": {"used_percent": primary_pct, "window_minutes": 300,
                           "resets_at": primary_resets_at},
                "secondary": {"used_percent": secondary_pct, "window_minutes": 10080,
                             "resets_at": secondary_resets_at},
                "plan_type": plan,
            },
        },
    }


# ---------------------------------------------------------------------
# extraccion basica
# ---------------------------------------------------------------------

def test_escanear_claude_extrae_usage_de_una_linea_assistant(home):
    archivo = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    _escribir(archivo, [
        {"type": "user", "message": {"content": "hola"}},
        _linea_claude("msg_1", "2026-08-27T10:00:00.000Z", 42, thinking=5),
    ])
    n = consumo.escanear_claude()
    assert n == 1
    filas = consumo._leer_registro(consumo._registro_claude_file())
    assert len(filas) == 1
    fila = filas[0]
    assert fila["id"] == "msg_1"
    assert fila["output_tokens"] == 42
    assert fila["thinking_tokens"] == 5
    assert fila["modelo"] == "claude-sonnet-5"
    # nunca se guarda "content", ni ningun campo de texto libre
    assert "content" not in fila
    assert "text" not in fila


def test_escanear_ignora_lineas_sin_usage_o_de_otro_type(home):
    archivo = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    _escribir(archivo, [
        {"type": "user", "message": {"role": "user"}},
        {"type": "attachment", "attachment": {"foo": "bar"}},
        {"type": "assistant", "message": {"id": "msg_sin_usage"}},  # sin usage
    ])
    n = consumo.escanear_claude()
    assert n == 0


def test_escanear_codex_extrae_token_count_y_rate_limits(home):
    archivo = home["codex"] / "sessions" / "2026" / "08" / "27" / "rollout-x.jsonl"
    _escribir(archivo, [
        {"type": "session_meta", "timestamp": "2026-08-27T10:00:00.000Z", "payload": {}},
        _linea_codex_token_count("2026-08-27T10:05:00.000Z", input_tokens=200,
                                 output_tokens=20, primary_pct=9.0),
    ])
    n = consumo.escanear_codex()
    assert n == 1
    filas = consumo._leer_registro(consumo._registro_codex_file())
    assert len(filas) == 1
    fila = filas[0]
    assert fila["input_tokens"] == 200
    assert fila["output_tokens"] == 20
    assert fila["primary_used_percent"] == 9.0
    assert fila["plan_type"] == "plus"


# ---------------------------------------------------------------------
# identidad: el mismo message.id en varias lineas (thinking parcial,
# texto/tool_use final) no se sobrecuenta -- gana la ultima
# ---------------------------------------------------------------------

def test_mismo_message_id_en_dos_lineas_el_resumen_pliega_a_la_ultima(home):
    """Reproduce lo verificado en los jsonl reales de Pedro: la linea de
    "thinking" trae un usage PARCIAL (output_tokens bajo) y una linea
    posterior con el mismo id trae el usage final, mas completo."""
    archivo = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    _escribir(archivo, [
        _linea_claude("msg_dup", "2026-08-27T10:00:00.000Z", 7,
                      content_type="thinking"),
        _linea_claude("msg_dup", "2026-08-27T10:00:01.000Z", 405,
                      thinking=209, content_type="text"),
    ])
    consumo.escanear_claude()
    filas_crudas = consumo._leer_registro(consumo._registro_claude_file())
    assert len(filas_crudas) == 2  # el registro es append-only: las dos quedan

    plegadas = consumo._ultimo_por_id(filas_crudas)
    assert len(plegadas) == 1
    assert plegadas[0]["output_tokens"] == 405  # la ULTIMA, no la primera parcial

    r = consumo.resumen()
    assert r["claude"]["medicion"]["turnos_observados"] == 1
    assert r["claude"]["medicion"]["tokens"]["output_tokens"] == 405


def test_correr_el_probe_dos_veces_no_duplica_nada(home):
    archivo = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    _escribir(archivo, [_linea_claude("msg_a", "2026-08-27T10:00:00.000Z", 100)])
    consumo.escanear_claude()
    consumo.escanear_claude()
    consumo.escanear_claude()
    filas = consumo._leer_registro(consumo._registro_claude_file())
    assert len(filas) == 1  # el offset ya paso ese byte: no se relee


# ---------------------------------------------------------------------
# incrementalidad: una sesion viva recibe lineas nuevas al final
# ---------------------------------------------------------------------

def test_incremental_solo_procesa_lo_nuevo_al_agregar_lineas(home):
    archivo = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    _escribir(archivo, [_linea_claude("msg_1", "2026-08-27T10:00:00.000Z", 10)])
    assert consumo.escanear_claude() == 1

    _escribir(archivo, [_linea_claude("msg_2", "2026-08-27T10:01:00.000Z", 20)])
    assert consumo.escanear_claude() == 1  # solo la linea nueva

    filas = consumo._leer_registro(consumo._registro_claude_file())
    assert {f["id"] for f in filas} == {"msg_1", "msg_2"}


def test_linea_a_medio_escribir_se_completa_en_la_proxima_corrida(home):
    """El CLI puede tener el archivo abierto escribiendo mientras el probe
    lee: una linea sin "\\n" final no se cuenta todavia."""
    archivo = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    completa = json.dumps(_linea_claude("msg_1", "2026-08-27T10:00:00.000Z", 10))
    parcial = json.dumps(_linea_claude("msg_2", "2026-08-27T10:01:00.000Z", 20))
    with open(archivo, "w", encoding="utf-8") as fh:
        fh.write(completa + "\n")
        fh.write(parcial[:20])  # corte a mitad del JSON, sin "\n"

    assert consumo.escanear_claude() == 1  # solo msg_1

    with open(archivo, "a", encoding="utf-8") as fh:
        fh.write(parcial[20:])
        fh.write("\n")

    assert consumo.escanear_claude() == 1  # ahora aparece msg_2
    filas = consumo._leer_registro(consumo._registro_claude_file())
    assert {f["id"] for f in filas} == {"msg_1", "msg_2"}


# ---------------------------------------------------------------------
# robustez
# ---------------------------------------------------------------------

def test_linea_json_invalida_no_revienta_el_escaneo(home):
    archivo = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    _escribir(archivo, [
        "{esto no es json valido",
        _linea_claude("msg_ok", "2026-08-27T10:00:00.000Z", 10),
    ])
    n = consumo.escanear_claude()
    assert n == 1
    filas = consumo._leer_registro(consumo._registro_claude_file())
    assert filas[0]["id"] == "msg_ok"


def test_carpeta_raiz_inexistente_no_revienta(home):
    assert consumo.escanear_claude() == 0
    assert consumo.escanear_codex() == 0


def test_archivo_desaparece_entre_listado_y_lectura(home, monkeypatch):
    archivo = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    _escribir(archivo, [_linea_claude("msg_1", "2026-08-27T10:00:00.000Z", 10)])

    reales = consumo._archivos_jsonl

    def _listar_y_borrar(raiz):
        encontrados = reales(raiz)
        archivo.unlink()
        return encontrados

    monkeypatch.setattr(consumo, "_archivos_jsonl", _listar_y_borrar)
    assert consumo.escanear_claude() == 0  # no lanza


def test_registro_con_lineas_corruptas_se_ignoran_al_leer(home):
    reg = consumo._registro_claude_file()
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text('{"id": "a", "output_tokens": 1}\nno es json\n', encoding="utf-8")
    filas = consumo._leer_registro(reg)
    assert len(filas) == 1


# ---------------------------------------------------------------------
# resumen: capacidad_ventana_inferida de Codex, y capacidad_ciclo de Claude
# ---------------------------------------------------------------------

def test_resumen_codex_infiere_capacidad_de_ventana_desde_used_percent(home):
    ahora = datetime.datetime(2026, 8, 27, 12, 0, 0, tzinfo=datetime.timezone.utc)
    resets_at = int((ahora + datetime.timedelta(hours=1)).timestamp())
    archivo = home["codex"] / "sessions" / "2026" / "08" / "27" / "rollout-x.jsonl"
    # 4 turnos dentro de la ventana primaria (5h), used_percent = 8.0 ->
    # capacidad_ventana_inferida = round(4 / 0.08) = 50
    for i in range(4):
        ts = (ahora - datetime.timedelta(minutes=i)).isoformat().replace("+00:00", "Z")
        _escribir(archivo, [_linea_codex_token_count(
            ts, primary_pct=8.0, primary_resets_at=resets_at,
            secondary_pct=1.0, secondary_resets_at=resets_at, total=100 + i)])
    consumo.escanear_codex()
    r = consumo.resumen(ahora)
    primaria = r["codex"]["medicion"]["ventana_primaria_5h"]
    assert primaria["used_percent"] == 8.0
    assert primaria["turnos_en_la_ventana"] == 4
    assert primaria["capacidad_ventana_inferida"] == 50


def test_resumen_codex_sin_datos_no_revienta(home):
    r = consumo.resumen()
    assert r["codex"]["medicion"] is None


def test_resumen_claude_extrapola_el_ritmo_a_un_ciclo_de_4_semanas(home):
    archivo = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    base = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)
    # 8 turnos repartidos en exactamente 7 dias (dia 0 a dia 7) -> ritmo
    # = 8 turnos / (7 dias / 7) = 8.0 turnos por semana
    for i in range(8):
        ts = (base + datetime.timedelta(days=i)).isoformat().replace("+00:00", "Z")
        _escribir(archivo, [_linea_claude(f"msg_{i}", ts, 10)])
    consumo.escanear_claude()
    r = consumo.resumen()
    inf = r["claude"]["inferencia"]
    assert inf["ritmo_turnos_por_semana"] == pytest.approx(8.0)
    # capacidad_ciclo_propuesta = ritmo * SEMANAS_POR_CICLO (4) = 32
    assert inf["capacidad_ciclo_propuesta"] == 32
    assert "NO mide cuota real" in inf["nota"]


def test_resumen_claude_sin_historia_no_propone_capacidad(home):
    r = consumo.resumen()
    assert r["claude"]["inferencia"]["capacidad_ciclo_propuesta"] is None
    assert r["claude"]["medicion"]["turnos_observados"] == 0


def test_resumen_se_persiste_y_se_puede_recargar(home):
    consumo.resumen()
    cargado = consumo.cargar_resumen()
    assert cargado is not None
    assert "claude" in cargado and "codex" in cargado


# ---------------------------------------------------------------------
# LA GARANTIA DURA: nunca se filtra contenido de una conversacion
# ---------------------------------------------------------------------

FRASE_SECRETA = "el clave secreta de pedro es UNICORNIO-TURQUESA-4711"


def test_el_contenido_de_la_conversacion_nunca_aparece_en_ningun_archivo(home, capsys):
    claude_file = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    codex_file = home["codex"] / "sessions" / "2026" / "08" / "27" / "rollout-x.jsonl"

    linea_usuario = {
        "type": "user",
        "timestamp": "2026-08-27T09:59:00.000Z",
        "message": {"role": "user", "content": FRASE_SECRETA},
    }
    linea_assistant = _linea_claude("msg_secreto", "2026-08-27T10:00:00.000Z", 50)
    # la frase tambien escondida en un content block de la propia linea
    # assistant, y en una clave inventada que un extractor descuidado
    # podria recorrer con un for k,v in obj.items()
    linea_assistant["message"]["content"][0]["text"] = FRASE_SECRETA
    linea_assistant["campo_inventado_con_contenido"] = FRASE_SECRETA

    linea_rota = '{"type": "assistant", "message": {"id": "roto", ' + \
        json.dumps(FRASE_SECRETA) + ' esto no cierra bien el json'

    _escribir(claude_file, [linea_usuario, linea_assistant, linea_rota])

    linea_codex_evento = {
        "type": "response_item",
        "timestamp": "2026-08-27T10:05:00.000Z",
        "payload": {"type": "message", "role": "assistant",
                   "content": [{"type": "text", "text": FRASE_SECRETA}]},
    }
    linea_codex_tc = _linea_codex_token_count("2026-08-27T10:06:00.000Z")
    linea_codex_tc["nota_inventada"] = FRASE_SECRETA
    _escribir(codex_file, [linea_codex_evento, linea_codex_tc])

    resultado = consumo.escanear()
    r = consumo.resumen()

    assert resultado["claude"] == 1  # solo la linea assistant valida cuenta
    assert resultado["codex"] == 1

    # 1) nada impreso (stdout/stderr) contiene la frase
    capturado = capsys.readouterr()
    assert FRASE_SECRETA not in capturado.out
    assert FRASE_SECRETA not in capturado.err

    # 2) el resumen devuelto (y por lo tanto lo que se persistio) no la trae
    assert FRASE_SECRETA not in json.dumps(r, ensure_ascii=False)

    # 3) TODO archivo bajo CALIPSO_HOME -- posiciones, registros, resumen --
    #    se revisa a mano, byte a byte
    for archivo in home["calipso"].rglob("*"):
        if archivo.is_file():
            contenido = archivo.read_bytes()
            assert FRASE_SECRETA.encode("utf-8") not in contenido, archivo


def test_una_excepcion_durante_el_escaneo_no_puede_llevarse_la_frase(home):
    """Si algo revienta durante la extraccion, el mensaje de la excepcion
    tampoco puede citar la frase -- ni siquiera en un log que no se guarda,
    porque nada de este modulo debe construir semejante mensaje."""
    archivo = home["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    linea = _linea_claude("msg_1", "2026-08-27T10:00:00.000Z", 10)
    linea["message"]["content"][0]["text"] = FRASE_SECRETA
    _escribir(archivo, [linea])

    try:
        consumo.escanear_claude()
        consumo.resumen()
    except Exception as exc:  # no deberia pasar, pero si pasara: revisar
        assert FRASE_SECRETA not in str(exc)
        raise
