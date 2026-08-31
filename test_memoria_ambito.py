"""Donde aterriza lo que Calipso recuerda, y en que estado.

No es un test de una feature: es la prueba de que tres agujeros concretos
siguen cerrados. Los tres son la misma clase de error -- lo que se guarda mal
se recupera mal, y nadie se entera porque no levanta ninguna excepcion -- y
los tres vivian en la misma linea del turno de chat:

1. El literal tenia mojibake, asi que la cadena rota se EMBEBIA tal cual.
2. Guardaba con `scope="auto"`, que es "el proyecto si hay proyecto", y el
   chat siempre tiene proyecto: la vida de Pedro se archivaba bajo el repo
   que tuviera abierto, y el ambito global quedo en cero filas.
3. Corria sobre el event loop, a diferencia del `remember` de la meta ocho
   lineas mas arriba, que ya iba por hilo.

Los tres se comprueban sin cargar el modelo de embeddings: el ruteo se prueba
sobre `Memory.remember` con ambitos falsos, y el sitio de llamada se lee del
fuente, porque vive adentro de un handler de websocket.
"""
import pathlib
import re

import pytest

from calipso import memory


class _AmbitoFalso:
    """Un Scope de mentira: solo anota que le pidieron guardar."""

    def __init__(self, nombre):
        self.nombre = nombre
        self.guardados = []

    def remember(self, text, **meta):
        self.guardados.append((text, meta))
        return f"{self.nombre}-{len(self.guardados)}"


@pytest.fixture
def mem():
    """Una Memory sin construir: `__init__` carga los pesos del embebedor
    (unos siete segundos) y aca no hace falta ni uno."""
    m = memory.Memory.__new__(memory.Memory)
    m.glob = _AmbitoFalso("global")
    m.project = _AmbitoFalso("proyecto")
    return m


# --- el ruteo de ambito ----------------------------------------------------

def test_global_explicito_va_a_global_aunque_haya_proyecto(mem):
    mem.remember("algo de Pedro", scope="global")
    assert len(mem.glob.guardados) == 1
    assert not mem.project.guardados


def test_auto_con_proyecto_abierto_va_al_proyecto(mem):
    """El comportamiento documentado, que no se cambia: lo que cambio es
    quien lo usa. `auto` es un default, no un enrutador."""
    mem.remember("algo", scope="auto")
    assert len(mem.project.guardados) == 1
    assert not mem.glob.guardados


def test_sin_proyecto_auto_cae_en_global(mem):
    mem.project = None
    mem.remember("algo", scope="auto")
    assert len(mem.glob.guardados) == 1


def test_el_docstring_avisa_de_la_trampa_de_auto():
    """La trampa costo dos meses de memoria global vacia. Si alguien reescribe
    el docstring y saca el aviso, el proximo llamador la repite."""
    doc = memory.Memory.remember.__doc__ or ""
    assert "auto" in doc and "default" in doc


# --- el sitio de llamada del turno de chat ---------------------------------
# Vive adentro del handler del websocket de chat, asi que se lee del fuente:
# es el mismo criterio que test_seguridad_puertas usa para el bind.

@pytest.fixture
def turno():
    """El bloque que recuerda el intercambio, del fuente del servidor.

    Acotado por los DOS extremos y no por una cuenta de caracteres: el
    archivo tiene mojibake en otros comentarios, asi que una ventana que se
    pasa de largo da un falso positivo; y una que se queda corta se pierde
    el `except`. Empieza en el comentario del paso 5 y termina donde arranca
    el paso siguiente, que guarda el mensaje en el chat."""
    fuente = pathlib.Path(
        memory.__file__).with_name("server.py").read_text(encoding="utf-8")
    i = fuente.index("recordar el intercambio")
    j = fuente.index("chats.append(chat_id, \"assistant\"", i)
    bloque = fuente[i:j]
    assert "mem.remember" in bloque, "el bloque no es el que se cree"
    return bloque


def test_el_intercambio_se_guarda_en_global(turno):
    """Pedro es la constante de la conversacion; el repo es la variable."""
    assert re.search(r'scope\s*=\s*"global"', turno), \
        "el turno de chat volvio a archivarse en el ambito del proyecto"


def test_el_intercambio_no_bloquea_el_turno(turno):
    """Calcular el embedding sobre el event loop congela el chat."""
    assert "asyncio.to_thread" in turno


def test_no_hay_mojibake_en_lo_que_se_embebe(turno):
    """La marca del doble encodeo: una A con tilde donde iba una vocal
    acentuada. Si vuelve, vuelve a embeberse la cadena rota."""
    assert "Ã" not in turno, "volvio el mojibake al texto que se guarda"
    assert "pregunto" in turno and "respondio" in turno


def test_recordar_no_puede_voltear_un_turno_ya_contestado(turno):
    """El intercambio ya se le mando a Pedro: que falle guardarlo no puede
    romper el turno."""
    assert "except Exception" in turno


# --- que un episodio se pueda corregir alguna vez ------------------------
# Las dos decisiones de `Scope.remember` deciden si esta memoria es
# reparable, y las dos estaban del lado que no. Ya hay 13 documentos
# guardados con el texto roto: si `add` los ignora al reescribirlos, esos 13
# son para siempre.

class _ColeccionFalsa:
    """Una coleccion de Chroma de mentira: anota que metodo le pidieron."""

    def __init__(self):
        self.llamadas = []
        self.docs = {}

    def count(self):
        return len(self.docs)

    def add(self, documents, metadatas, ids):
        self.llamadas.append("add")
        self.docs.setdefault(ids[0], documents[0])   # add NO pisa

    def upsert(self, documents, metadatas, ids):
        self.llamadas.append("upsert")
        self.docs[ids[0]] = documents[0]             # upsert SI pisa


@pytest.fixture
def ambito():
    s = memory.Scope.__new__(memory.Scope)
    s._col = _ColeccionFalsa()
    return s


def test_guardar_pisa_en_vez_de_ignorar(ambito):
    """Comprobado sobre chromadb 1.5.9: `add` con un id repetido conserva el
    documento viejo EN SILENCIO -- no levanta y el count ni se mueve. Con
    `add`, reparar el corpus es imposible: reindexar no corrige, ignora."""
    ambito.remember("un episodio")
    assert ambito._col.llamadas == ["upsert"], \
        "volvio `add`: un episodio mal guardado seria permanente otra vez"


def test_dos_escrituras_a_la_vez_no_se_pisan(ambito, monkeypatch):
    """El id era `m{count}-{ts}` y `count()` se lee ANTES de escribir.

    Dos escritores que leen el contador antes de que ninguno haya escrito
    -- el turno de chat y el jefe de un departamento, por ejemplo -- ven el
    MISMO count, y en el mismo segundo arman el MISMO id. Con `add`, la
    segunda escritura se perdia sin una sola excepcion.

    Se reproduce clavando las dos lecturas que el id viejo usaba: el reloj y
    el contador. Sin clavar el contador este test pasa con el id viejo
    tambien, porque en un solo hilo el count crece entre una escritura y la
    otra -- y entonces no probaria nada de lo que dice."""
    monkeypatch.setattr(memory.datetime, "datetime", datetime_congelado())
    monkeypatch.setattr(type(ambito._col), "count", lambda self: 13)
    a = ambito.remember("lo que escribio el chat")
    b = ambito.remember("lo que escribio el jefe")
    assert a != b, "dos episodios distintos comparten id: uno se pierde"
    assert len(ambito._col.docs) == 2


def test_reescribir_el_mismo_episodio_es_idempotente(ambito, monkeypatch):
    """El otro lado de la moneda: reintentar la MISMA escritura no duplica.
    Es lo que hace reparable al corpus."""
    congelado = datetime_congelado()
    monkeypatch.setattr(memory.datetime, "datetime", congelado)
    a = ambito.remember("mismo episodio", kind="chat")
    b = ambito.remember("mismo episodio", kind="chat")
    assert a == b
    assert len(ambito._col.docs) == 1


def datetime_congelado():
    """Un `datetime` con `now()` clavado, para reproducir dos escrituras en
    el mismo segundo sin dormir el test."""
    import datetime as _dt

    class Congelado(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime(2026, 8, 31, 12, 0, 0)

    return Congelado
