# test_contrato_departamentos.py
"""Los departamentos que el contrato interno le nombra al modelo.

La lista estaba escrita a mano en `internal_contract` (atlas, mercado,
finanzas) y ninguno de los tres existe en el registro -atlas ni siquiera es
un departamento, es un proyecto-, asi que cada turno le afirmaba al modelo
tres departamentos inventados y lo invitaba a marcar el foco con un nombre
que `_resolver_foco` descarta: la camara no vuela a ningun lado.

Lo que se prueba aca es el contrato de esa lista: sale del registro real,
dice la verdad cuando la economia todavia no esta sembrada (el estado
NORMAL hasta que Pedro siembre), no inventa nombres cuando el registro no se
puede leer, y no vuelve a leer el JSON en cada turno.
"""
import json

from calipso import prompt_compiler
from calipso.economia import departamentos as deps
from calipso.mapa import ficha


def _sembrar(tmp_path, *nombres_fabrica, personales=()):
    """Lo minimo que `Pagador.desde_entorno` exige, mas el registro.

    El libro vacio y las suscripciones vacias estan porque sin los tres
    archivos la economia no existe para el resolvedor del foco; lo que
    importa aca es departamentos.json."""
    eco = tmp_path / "economia"
    eco.mkdir(parents=True, exist_ok=True)
    (eco / "libro.jsonl").write_text("", encoding="utf-8")
    (eco / "suscripciones.json").write_text("{}", encoding="utf-8")
    r = deps.Registro(eco / "departamentos.json")
    for n in nombres_fabrica:
        r.alta(deps.Departamento(n, deps.ZONA_FABRICA))
    for n in personales:
        r.alta(deps.Departamento(n, deps.ZONA_PERSONAL))
    return eco


def _edificios(eco):
    """La misma forma que `_edificios_livianos` en calipso/server.py."""
    return [{"id": d.cuenta, "nombre": d.nombre}
            for d in deps.Registro(eco / "departamentos.json").todos()]


# -- economia sin sembrar: el estado normal hasta que Pedro siembre ---------

def test_sin_economia_el_contrato_no_nombra_ningun_departamento(tmp_path):
    texto = prompt_compiler.internal_contract({}, base=tmp_path)
    assert prompt_compiler.departamentos_conocidos(tmp_path) == []
    assert "no hay ningun departamento que enfocar" in texto
    for inventado in ("atlas", "mercado", "finanzas"):
        assert inventado not in texto.lower()


def test_sin_economia_la_marca_se_sigue_explicando(tmp_path):
    """El contrato es el unico lugar donde vive la sintaxis de la marca
    (spec seccion 8): callarla mientras no haya departamentos dejaria un
    texto que hay que acordarse de restaurar el dia de la siembra."""
    texto = prompt_compiler.internal_contract({}, base=tmp_path)
    assert "⟦foco:<nombre>⟧" in texto
    assert "no la ve" in texto
    assert "No la emitas" in texto


def test_economia_a_medio_sembrar_es_lo_mismo_que_ninguna(tmp_path):
    """Con departamentos.json pero sin libro, `Pagador.desde_entorno`
    devuelve None y `_edificios_livianos` (server.py) devuelve []: el
    resolvedor no resuelve nada, asi que nombrarlos seria la misma mentira
    en otro lugar."""
    eco = tmp_path / "economia"
    eco.mkdir()
    deps.Registro(eco / "departamentos.json").alta(
        deps.Departamento("cristal", deps.ZONA_FABRICA))
    assert prompt_compiler.departamentos_conocidos(tmp_path) == []
    assert "cristal" not in prompt_compiler.internal_contract({}, base=tmp_path)


def test_registro_ilegible_no_inventa_nombres(tmp_path):
    eco = _sembrar(tmp_path, "cristal")
    (eco / "departamentos.json").write_text("{no es json", encoding="utf-8")
    assert prompt_compiler.departamentos_conocidos(tmp_path) == []
    texto = prompt_compiler.internal_contract({}, base=tmp_path)
    assert "no hay ningun departamento que enfocar" in texto


# -- economia sembrada ------------------------------------------------------

def test_los_nombres_salen_del_registro_y_no_de_la_lista_vieja(tmp_path):
    _sembrar(tmp_path, "cristal", "taller", personales=("hogar",))
    texto = prompt_compiler.internal_contract({}, base=tmp_path)
    assert prompt_compiler.departamentos_conocidos(tmp_path) == [
        ("cristal", "fabrica"), ("hogar", "personal"), ("taller", "fabrica")]
    for real in ("cristal", "taller", "hogar"):
        assert real in texto
    for inventado in ("atlas", "mercado", "finanzas"):
        assert inventado not in texto.lower()


def test_un_departamento_personal_no_se_anuncia_como_de_la_fabrica(tmp_path):
    """La fabrica y lo personal son dos zonas con reglas distintas -la
    invariante 12 le prohibe a una cuenta personal comprar capacidad o API
    de la fabrica-, y `finanzas` va a ser personal el dia uno de la siembra.

    La primera version de este arreglo decia "los departamentos de la
    fabrica son estos" y listaba los dos, o sea que cambiaba una mentira
    (tres nombres inventados) por otra mas chica (la zona equivocada). El
    nombre se sigue ofreciendo -tiene edificio y la marca resuelve-, pero
    con su zona al lado."""
    _sembrar(tmp_path, "cristal", personales=("finanzas",))
    texto = prompt_compiler.internal_contract({}, base=tmp_path)
    assert "cristal (fabrica)" in texto
    assert "finanzas (personal)" in texto
    assert "departamentos de la fabrica son estos" not in texto


def test_solo_un_departamento_personal_no_inventa_una_fabrica(tmp_path):
    """El caso que hace obvio el bug: si lo unico sembrado es personal, la
    frase vieja afirmaba que la fabrica tenia un departamento que no tiene."""
    _sembrar(tmp_path, personales=("finanzas",))
    texto = prompt_compiler.internal_contract({}, base=tmp_path)
    assert "finanzas (personal)" in texto
    assert "departamentos de la fabrica" not in texto


def test_cada_nombre_ofrecido_lo_resuelve_el_servidor(tmp_path):
    """Los dos extremos atados: lo que el contrato ofrece es exactamente lo
    que `ficha.id_de_nombre` acepta sobre el registro. Un nombre de la zona
    personal tambien resuelve -tiene edificio y camara-; lo que colapsa a
    `personal` es su cuenta, que es otra pregunta."""
    eco = _sembrar(tmp_path, "cristal", personales=("hogar",))
    edificios = _edificios(eco)
    for nombre, _zona in prompt_compiler.departamentos_conocidos(tmp_path):
        assert ficha.id_de_nombre(nombre, edificios) is not None
    assert ficha.id_de_nombre("atlas", edificios) is None


def test_la_lista_tiene_techo_y_dice_cuantos_quedaron_afuera(tmp_path):
    """El contrato entra en cada turno: la lista no puede crecer sin techo.
    Lo que no entra se declara, no se calla."""
    n = prompt_compiler.CONTRATO_MAX_DEPARTAMENTOS + 5
    _sembrar(tmp_path, *[f"dep{i:02d}" for i in range(n)])
    texto = prompt_compiler.internal_contract({}, base=tmp_path)
    assert "dep00" in texto and "dep14" in texto
    assert "dep15" not in texto
    assert "y 5 mas que no entran en esta lista" in texto


# -- costo: esto corre en CADA turno ---------------------------------------

def test_el_registro_se_lee_una_vez_por_cambio(tmp_path, monkeypatch):
    """Tres turnos seguidos sin tocar el registro: un solo json.loads.

    Cuando el registro cambia (alta de departamento: archivo nuevo por el
    os.replace de `escribir_json_atomico`, o sea mtime y tamano nuevos) la
    lectura vuelve a pasar y el nombre nuevo aparece en el turno siguiente,
    sin que nadie limpie el cache a mano."""
    _sembrar(tmp_path, "cristal")
    lecturas = []
    real = deps.Registro

    def espia(ruta):
        lecturas.append(str(ruta))
        return real(ruta)

    monkeypatch.setattr(prompt_compiler.eco_deps, "Registro", espia)
    for _ in range(3):
        assert prompt_compiler.departamentos_conocidos(tmp_path) == [
            ("cristal", "fabrica")]
    assert len(lecturas) == 1

    real(tmp_path / "economia" / "departamentos.json").alta(
        deps.Departamento("taller", deps.ZONA_FABRICA))
    assert prompt_compiler.departamentos_conocidos(tmp_path) == [
        ("cristal", "fabrica"), ("taller", "fabrica")]
    assert len(lecturas) == 2


def test_el_cache_no_crece_con_cada_escritura(tmp_path):
    """Una sola entrada viva: el cache es del registro de ahora, no un
    historial de todos los que hubo."""
    _sembrar(tmp_path, "cristal")
    ruta = tmp_path / "economia" / "departamentos.json"
    for i in range(4):
        prompt_compiler.departamentos_conocidos(tmp_path)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        deps.Registro(ruta).alta(deps.Departamento(f"otro{i}",
                                                   deps.ZONA_FABRICA))
        assert len(datos) == i + 1
    prompt_compiler.departamentos_conocidos(tmp_path)
    assert len(prompt_compiler._CACHE_REGISTRO) == 1


# -- el camino de produccion -----------------------------------------------

def test_compile_context_usa_el_registro_del_home(tmp_path, monkeypatch):
    """`_build_context` (server.py) llama a `compile_context` sin pasar
    base: el contrato tiene que resolver el registro por CALIPSO_HOME, que
    es de donde sale `_ECO_BASE`."""
    _sembrar(tmp_path, "cristal")
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    texto = prompt_compiler.compile_context("Eres Calipso.")
    assert "cristal" in texto
    assert "atlas" not in texto.lower()


def test_las_dos_secciones_del_prompt_leen_la_misma_economia(tmp_path,
                                                             monkeypatch):
    """La seccion Economia y la del contrato tienen que salir del MISMO home.

    `_build_context` le pasaba `_ECO_BASE` a `economia_brief` y no se lo
    pasaba al contrato, que resolvia CALIPSO_HOME por su cuenta. En
    produccion las dos daban lo mismo, asi que la invariante -todo nombre
    que el contrato ofrece es un nombre que `_resolver_foco` acepta- se
    sostenia por coincidencia y no por construccion. Este test mueve una
    sola de las dos autoridades: si el contrato vuelve a resolver el home
    por su cuenta, las dos secciones describen dos economias distintas y
    esto se pone en rojo.
    """
    import calipso.server as srv

    home = tmp_path / "otro-home"
    home.mkdir()
    _sembrar(home, "cristal")
    monkeypatch.setattr(srv, "_ECO_BASE", home)
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))   # el home que NO manda

    prompt = srv._build_context("hola", "runtime")
    assert "cristal" in prompt
    assert "no hay ningun departamento que enfocar" not in prompt
