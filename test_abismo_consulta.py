"""El resolvedor: ruteo por fuente, armado bajo techo, fallo cerrado."""
from calipso.abismo import anillos, consulta, fuentes, marca


def test_pescado_arma_bloque_etiquetado(monkeypatch):
    monkeypatch.setattr(fuentes, "chats_viejos",
                        lambda resto, **kw: [("[t 2026-08-01] hola", anillos.MEDIA_AGUA)])
    r = consulta.resolver(marca.Marca("chats", "hola"))
    assert r["estado"] == "pescado" and r["fuente"] == "chats"
    assert "=== Lo que subio del abismo (fuente: chats) ===" in r["texto"]
    assert "[anillo 2]" in r["texto"]
    assert r["aviso"] == ""


def test_etiquetar_es_el_armado_compartido_del_bloque():
    """El armado del bloque etiquetado vive aca, junto a ABISMO_BLOQUE_MAX, y
    lo comparten el resolvedor y `viaje.etiquetar`: si hubiera dos copias, el
    modelo terminaria viendo dos formatos para lo mismo."""
    texto = consulta.etiquetar("chats", [("hola", anillos.MEDIA_AGUA),
                                         ("  chau  ", anillos.ORILLA)])
    assert texto == ("=== Lo que subio del abismo (fuente: chats) ===\n"
                     "[anillo 2]\nhola\n"
                     "[anillo 1]\nchau")
    largo = consulta.etiquetar("chats", [("x" * (consulta.ABISMO_BLOQUE_MAX + 100),
                                          anillos.MEDIA_AGUA)])
    assert len(largo) == consulta.ABISMO_BLOQUE_MAX


def test_techo_de_caracteres(monkeypatch):
    monkeypatch.setattr(fuentes, "chats_viejos",
                        lambda resto, **kw: [("x" * 5000, anillos.MEDIA_AGUA)])
    r = consulta.resolver(marca.Marca("chats", "x"))
    assert len(r["texto"]) <= consulta.ABISMO_BLOQUE_MAX


def test_fuente_que_revienta_es_fallo_suave(monkeypatch):
    def bomba(resto, **kw):
        raise RuntimeError("chats.json roto")
    monkeypatch.setattr(fuentes, "chats_viejos", bomba)
    r = consulta.resolver(marca.Marca("chats", "x"))
    assert r["estado"] == "fallo" and "roto" in r["aviso"]
    assert r["texto"] == "" and r["bloques"] == []


def test_pesca_vacia_es_fallo_con_aviso(monkeypatch):
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto, **kw: [])
    r = consulta.resolver(marca.Marca("chats", "zzz"))
    assert r["estado"] == "fallo"
    assert "no trajo nada" in r["aviso"]


def test_memoria_recibe_las_dependencias(monkeypatch):
    visto = {}

    def falsa(pregunta, mem, consolidado=None, zona_chat="fabrica"):
        visto.update(mem=mem, zona=zona_chat)
        return [("algo", anillos.MEDIA_AGUA)]
    monkeypatch.setattr(fuentes, "memoria", falsa)
    consulta.resolver(marca.Marca("memoria", "q"), mem="MEM", zona_chat="personal")
    assert visto == {"mem": "MEM", "zona": "personal"}
