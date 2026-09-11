"""El ~/.calipso real de Pedro no se toca al correr la suite.

Es una regla dura del proyecto y estaba rota: `catastro.py` ya la
documenta como incidente vivido ("~/.calipso/catastro.json de la maquina
real terminaba pisado por tests que se pensaban aislados") y seguia
pasando. Media docena de modulos congela `CALIPSO_HOME` en una constante
AL IMPORTARSE, y `memory.Scope.__init__` crea directorios y una base de
chroma en cuanto se construye, asi que alcanza con que UN test importe
`calipso.server` sin la variable puesta para que la suite entera escriba
en la memoria real del asistente.

Estos tests son el guardarrail de esa regla: si alguien saca el conftest
de la raiz, o lo rompe, esto cae.
"""
import os
import pathlib
import sys

import conftest

REAL = pathlib.Path(os.path.expanduser("~/.calipso"))


def _fuera_del_home_real(ruta: pathlib.Path) -> bool:
    ruta = pathlib.Path(ruta).absolute()
    return ruta != REAL and REAL not in ruta.parents


def test_la_variable_apunta_a_un_home_desechable():
    assert os.environ.get("CALIPSO_HOME"), "CALIPSO_HOME sin fijar: la suite escribe en el home real"
    assert _fuera_del_home_real(pathlib.Path(os.environ["CALIPSO_HOME"]))
    assert _fuera_del_home_real(conftest.home_de_la_suite())


def test_los_modulos_que_lo_congelan_al_importar_no_apuntan_al_real():
    import calipso.backup      # noqa: F401
    import calipso.chats       # noqa: F401
    import calipso.jobs        # noqa: F401
    import calipso.librarian   # noqa: F401
    import calipso.sessions    # noqa: F401
    congelados = [m for m in sys.modules.values()
                  if getattr(m, "__name__", "").startswith("calipso")
                  and isinstance(getattr(m, "CALIPSO_HOME", None),
                                 pathlib.Path)]
    assert congelados
    for m in congelados:
        assert _fuera_del_home_real(m.CALIPSO_HOME), m.__name__


def test_el_token_y_el_totp_tampoco_apuntan_al_home_real():
    """Las dos unicas rutas del paquete que resolvian `~/.calipso` sin
    mirar CALIPSO_HOME, y las dos ESCRIBEN: `_load_token` genera y guarda
    un token si no existe. La red del conftest no las cubria -- fija la
    variable, y estas dos lineas no la leian -- asi que un import de
    `calipso.server` sin archivo de token escribia en el home REAL."""
    import calipso.server as srv
    assert _fuera_del_home_real(srv._TOKEN_FILE)
    assert _fuera_del_home_real(srv._TOTP_SECRET_FILE)


def test_la_aduana_resuelve_su_libro_por_llamada_y_fuera_del_home_real():
    """`calipso.aduana` no congela CALIPSO_HOME al importar (molde
    `sesiones._ruta`): `_ruta()` se resuelve en cada escritura y cae en el
    home desechable. El test 2 de arriba no lo veria: solo mira modulos con
    un atributo `CALIPSO_HOME`, y la aduana no debe tener ninguno."""
    import calipso.aduana as aduana
    assert _fuera_del_home_real(aduana._ruta())
    assert not isinstance(getattr(aduana, "CALIPSO_HOME", None), pathlib.Path)
