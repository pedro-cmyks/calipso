"""
calipso/permisos/acciones.py — Que es una accion, y en que nivel cae.

Esta es la tabla de la seccion 5.3 del spec de ojos y manos, escrita una
sola vez. El nivel lo determina LA ACCION, no el humor del chat ni una
perilla que alguien se olvido de bajar: por eso vive aca, en datos y
funciones puras, y no repartido por los llamadores.

Tres niveles:

  directo   pasa sin preguntar, y queda escrito
  pregunta  pasa cuando Pedro dice que si, ahi mismo, con el texto exacto
  nunca     no hay prompt, hay negativa (5.7: token y totp_secret)

Y una marca aparte, `siempre_pregunta`, que es la de 5.4: hay acciones que
preguntan CADA VEZ aunque Pedro haya dado permiso permanente para el
resto de su familia, porque equivocarse no se deshace. `git push`,
`git reset --hard`, leer una clave privada -- y acunar monedas, que es la
familia que hoy se enchufa: el libro es append-only y un asiento no se
borra. Un si guardado para siempre sobre algo irreversible es un si que
Pedro no va a recordar haber dado.

Como se le enchufa una familia nueva (terminal, archivos, apps):
registrar en `_CLASIFICADORES` una funcion que devuelva un `Veredicto`, y
-- si la forma del permiso permanente no se compara por igualdad exacta --
otra en `_COBERTURAS`. El motor no se toca.
"""
from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Callable

NIVEL_DIRECTO = "directo"
NIVEL_PREGUNTA = "pregunta"
NIVEL_NUNCA = "nunca"

# Origenes con un humano del otro lado. Cualquier otro -- una rutina de
# departamento, un origen que nadie declaro -- es DESATENDIDO, y el camino
# desatendido nunca cae al prompt interactivo (5.6.3). El default es el
# lado seguro a proposito: si el llamador no dice quien es, se lo trata
# como si no hubiera nadie mirando, que es lo que impide que un prompt sin
# publico se convierta en un si automatico.
ORIGENES_ATENDIDOS = ("chat", "pedro")

# El techo de plata, en milimonedas (1 moneda = 1.000 mm, economia/tipos.py).
# Pedro lo eligio: 100 monedas. Por debajo Calipso acuna o mueve sin
# preguntar; por encima, pregunta. No es una constante escondida -- este es
# el DEFECTO, y `almacen.techos()` lo pisa con lo que haya en permisos.json,
# que se cambia por /api/permisos/techo.
TECHO_PLATA_MM_DEFECTO = 100_000

TECHOS_DEFECTO = {"plata_mm": TECHO_PLATA_MM_DEFECTO}


@dataclass(frozen=True)
class Accion:
    """Lo que esta por pasar, ya normalizado.

    `forma` es lo unico que se compara contra un permiso permanente: es la
    FORMA EXACTA de 5.4 (`["npm","test"]` en tal cwd, no "npm"). `detalle`
    es lo que ve Pedro en el prompt y no participa de ninguna comparacion:
    un monto, una ruta absoluta, si el archivo existe o se crea.
    """
    familia: str
    operacion: str
    forma: dict = field(default_factory=dict)
    detalle: dict = field(default_factory=dict)
    titulo: str = ""

    def clave(self) -> str:
        """Identidad estable de la forma, para comparar y para poner la
        pared de 5.6.4. json con sort_keys: dos dicts iguales escritos en
        distinto orden dan la misma clave, y una lista NUNCA se aplana a
        su primera palabra."""
        return json.dumps([self.familia, self.operacion, self.forma],
                          ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))

    def a_dict(self) -> dict:
        return {"familia": self.familia, "operacion": self.operacion,
                "forma": self.forma, "detalle": self.detalle,
                "titulo": self.titulo}

    @staticmethod
    def de_dict(d: dict) -> "Accion":
        return Accion(familia=d["familia"], operacion=d["operacion"],
                      forma=d.get("forma") or {},
                      detalle=d.get("detalle") or {},
                      titulo=d.get("titulo") or "")


@dataclass(frozen=True)
class Contexto:
    """Quien pide, y si hay alguien a quien preguntarle.

    `corrida` es el id de la corrida de una rutina: es lo que permite que
    una accion estacionada TERMINE esa corrida y que nada mas de esa misma
    corrida se cuele por otro lado (5.6.2 y 5.6.4).
    """
    origen: str = "desconocido"
    chat: str | None = None
    departamento: str | None = None
    corrida: str | None = None

    @property
    def desatendido(self) -> bool:
        return self.origen not in ORIGENES_ATENDIDOS

    def a_dict(self) -> dict:
        return {"origen": self.origen, "chat": self.chat,
                "departamento": self.departamento, "corrida": self.corrida}

    @staticmethod
    def de_dict(d: dict | None) -> "Contexto":
        d = d or {}
        return Contexto(origen=d.get("origen") or "desconocido",
                        chat=d.get("chat"), departamento=d.get("departamento"),
                        corrida=d.get("corrida"))


@dataclass(frozen=True)
class Veredicto:
    nivel: str
    motivo: str
    siempre_pregunta: bool = False


class ErrorPermisos(Exception):
    pass


# --------------------------------------------------------------------------
# El home, resuelto en CADA llamada
# --------------------------------------------------------------------------

def calipso_home() -> pathlib.Path:
    """Igual que `calipso.catastro.calipso_home`, y duplicado a proposito
    -- ver el docstring largo de ese archivo por el porque.

    Resumen: quince modulos del repo hacen
    `CALIPSO_HOME = pathlib.Path(os.environ.get(...))` a nivel de modulo, y
    eso se resuelve UNA sola vez, la primera vez que alguien importa el
    archivo. Como Python cachea modulos en sys.modules, un test que fija
    CALIPSO_HOME despues de que otro archivo ya importo la cadena se
    encuentra con el valor viejo, y termina escribiendo en el ~/.calipso
    REAL de Pedro. Paso de verdad con catastro.json.

    Se duplica en vez de importar `calipso.catastro` porque el motor de
    permisos no tiene nada que ver con el indice de proyectos y no puede
    depender de que ese modulo (y su cadena: calipso.config, subprocess)
    importe bien para poder negar una accion. Son tres lineas con un
    puntero, el mismo trato que catastro.py le da a `_slug`.
    """
    return pathlib.Path(os.environ.get(
        "CALIPSO_HOME", os.path.expanduser("~/.calipso")))


# --------------------------------------------------------------------------
# 5.7 -- credenciales
# --------------------------------------------------------------------------

# Los dos unicos NUNCA de todo el spec, y no son una carpeta de Pedro: son
# la credencial del propio servidor. Un agente que lee ~/.calipso/token
# llama a la API de Calipso como si fuera Pedro (auth_guard acepta
# ?token=) y desde ahi se concede a si mismo todos los permisos de esta
# seccion, aprueba sus propias solicitudes estacionadas y apaga el
# registro. Un prompt no alcanza, porque el punto entero es que el modelo
# no puede ser quien conteste. Aca se niega cualquier operacion sobre
# ellos -- no solo leer: escribirlos tambien seria fabricar la credencial.
NOMBRES_CREDENCIAL_DEL_SERVIDOR = ("token", "totp_secret")

# Credenciales de PEDRO. No estan prohibidas: son nivel pregunta, y el
# prompt las nombra y dice que son. Lo que no admiten es permiso
# permanente, por la misma razon que git push.
CARPETAS_CREDENCIAL = ("~/.ssh", "~/.gnupg", "~/.aws", "~/.config/gh")
ARCHIVOS_CREDENCIAL = ("~/.claude/.credentials.json",)
SUFIJOS_CREDENCIAL = (".pem", ".key", ".p12")
NOMBRES_CREDENCIAL = (".env",)
PREFIJOS_CREDENCIAL = ("id_",)


def _resolver(ruta) -> pathlib.Path:
    """Rutas siempre resueltas antes de compararlas: en esta maquina /home
    es symlink a /var/home, y una comparacion sobre texto se corre sola
    con solo escribir la ruta distinto (misma trampa que catastro.py).
    `strict=False` para que una ruta que todavia no existe -- un archivo
    que se va a crear -- tambien se normalice."""
    p = pathlib.Path(str(ruta)).expanduser()
    try:
        return p.resolve(strict=False)
    except OSError:
        return p


def _dentro_de(hijo: pathlib.Path, padre: pathlib.Path) -> bool:
    return hijo == padre or padre in hijo.parents


def es_credencial_del_servidor(ruta) -> bool:
    """Las rutas exactas del token/totp_secret Y todo backups/: un zip de
    backup viejo contiene ambos secretos adentro, y matchear solo las rutas
    exactas dejaba a un agente pedir POST /api/backup y leer el zip -- la
    credencial por la puerta de al lado (revision de seguridad 2026-09-07,
    C6). Los backups nuevos ya no llevan secretos, pero los viejos existen
    y un agente no tiene por que leer backups jamas."""
    p = _resolver(ruta)
    home = _resolver(calipso_home())
    if any(p == home / n for n in NOMBRES_CREDENCIAL_DEL_SERVIDOR):
        return True
    return _dentro_de(p, home / "backups")


def es_credencial_de_pedro(ruta) -> bool:
    p = _resolver(ruta)
    for c in CARPETAS_CREDENCIAL:
        if _dentro_de(p, _resolver(c)):
            return True
    if any(p == _resolver(a) for a in ARCHIVOS_CREDENCIAL):
        return True
    if p.suffix in SUFIJOS_CREDENCIAL:
        return True
    if p.name in NOMBRES_CREDENCIAL:
        return True
    return any(p.name.startswith(pre) for pre in PREFIJOS_CREDENCIAL)


def raices_de_escritura() -> list[pathlib.Path]:
    """Donde vive el trabajo: las raices del catastro (3.2) mas
    ~/.calipso. Escribir ahi adentro es directo; afuera es pregunta.

    El import de catastro va adentro de la funcion y con red: si el
    catastro no se puede importar o su json esta roto, el motor no puede
    caerse -- se queda con ~/.calipso, que es el conjunto MAS CHICO, asi
    que el error empuja hacia preguntar de mas, nunca hacia escribir de
    mas."""
    raices = [_resolver(calipso_home())]
    try:
        from calipso import catastro
        raices.extend(catastro.raices_resueltas())
    except Exception:
        pass
    return raices


# --------------------------------------------------------------------------
# Clasificadores por familia
# --------------------------------------------------------------------------

def _clasificar_plata(a: Accion, techos: dict) -> Veredicto:
    """Las acciones de plata: acunar, mover y REPRECIAR. La familia
    enchufada hoy.

    Por debajo del techo pasa sola; por encima pregunta, y pregunta
    SIEMPRE: el libro es append-only y un asiento acunado no se deshace,
    que es literalmente el criterio de 5.4 para la lista sin permiso
    permanente. Conceder "acunar al tesoro para siempre" seria firmar en
    blanco sobre la unica puerta por la que entra plata de afuera.

    La tercera operacion es `capacidad` (repreciar una suscripcion, ver
    `api_eco_suscripcion_capacidad`): no mueve un milimon en el momento,
    pero cambia el DENOMINADOR del precio de la capacidad, y ese precio se
    estampa en cada compra que el mercado escribe despues. El campo del
    json se puede volver a escribir; los asientos que se escribieron
    mientras tanto, no. Por eso entra por aca y no se queda del lado de
    las perillas reversibles (las de un departamento, que no pasan por el
    motor a proposito). Su `monto_mm` es el costo mensual de la
    suscripcion que se reprecia -- viaja en `detalle`, no en `forma`,
    porque no es parte de la identidad del cambio.
    """
    monto = a.forma.get("monto_mm", a.detalle.get("monto_mm", 0))
    try:
        monto = int(monto)
    except (TypeError, ValueError):
        # un monto que no es entero no se puede comparar con el techo:
        # cae del lado que pregunta, nunca del que pasa solo
        return Veredicto(NIVEL_PREGUNTA, "monto ilegible", True)
    techo = int(techos.get("plata_mm", TECHO_PLATA_MM_DEFECTO))
    if monto <= techo:
        return Veredicto(NIVEL_DIRECTO,
                         f"{monto} mm no supera el techo de {techo} mm")
    return Veredicto(NIVEL_PREGUNTA,
                     f"{monto} mm supera el techo de {techo} mm", True)


# Las operaciones de 5.3 donde equivocarse no se deshace: git push,
# git commit --amend, git reset --hard, git clean -fdx, rm -rf.
EJECUTABLES_IRREVERSIBLES = ("git", "rm")


def _banderas_cortas(argv: list[str]) -> str:
    """Las banderas de una letra, ya desarmadas: `-fdx` y `-f -d -x` son lo
    mismo y las dos formas se escriben."""
    return "".join(x[1:] for x in argv
                   if x.startswith("-") and not x.startswith("--"))


def es_irreversible(argv: list[str]) -> bool:
    """Verdadero cuando el argv es una de las operaciones de 5.3 donde
    equivocarse no se deshace.

    Se mira ELEMENTO POR ELEMENTO, nunca por la primera palabra ni por la
    cadena entera: `git -C /otro push` es un push igual que `git push`, y
    `rm -r -f` es lo mismo que `rm -rf`. El runner que ya existe corre
    `subprocess.run(args)` sin `shell=` (tools/commands.py:280-282), asi
    que el argv es literalmente lo que se va a ejecutar.

    Tampoco se mira solo argv[0]: `sudo rm -rf` sigue siendo un rm -rf, asi
    que el ejecutable se busca en cualquier posicion.

    Prefiere el falso positivo. `git log --grep push` cae como irreversible
    y por lo tanto pregunta cada vez; el costo de eso es una pregunta de
    mas, y el de fallar al otro lado es un push que nadie autorizo.
    """
    argv = [str(x) for x in argv]
    for i, tok in enumerate(argv):
        exe = pathlib.Path(tok).name
        if exe not in EJECUTABLES_IRREVERSIBLES:
            continue
        resto = argv[i + 1:]
        if exe == "git":
            if "push" in resto or "clean" in resto:
                return True
            if "commit" in resto and "--amend" in resto:
                return True
            if "reset" in resto and "--hard" in resto:
                return True
        elif exe == "rm":
            cortas = _banderas_cortas(resto)
            if ("r" in cortas or "R" in cortas or "--recursive" in resto) \
                    and ("f" in cortas or "--force" in resto):
                return True
    return False


def _clasificar_comando(a: Accion, techos: dict) -> Veredicto:
    """Los comandos. `operacion` distingue dos formas de pedirlo:

      "allowlist"  por id del allowlist que ya existe (tools/commands.py).
                   Directo: ninguno escribe fuera del repo ni toca la red.
      "correr"     un argv libre. Pregunta, mostrando el argv exacto y el
                   cwd; y si es de los irreversibles, pregunta siempre.
    """
    if a.operacion == "allowlist":
        cid = a.forma.get("id")
        try:
            from calipso.tools.commands import ALLOWLIST
        except Exception:
            return Veredicto(NIVEL_PREGUNTA,
                             "no se pudo leer el allowlist", False)
        if cid in ALLOWLIST:
            return Veredicto(NIVEL_DIRECTO, f"allowlist: {cid}")
        return Veredicto(NIVEL_PREGUNTA, f"no esta en el allowlist: {cid}")
    argv = list(a.forma.get("argv") or [])
    if es_irreversible(argv):
        return Veredicto(NIVEL_PREGUNTA,
                         "operacion irreversible: no admite permiso "
                         "permanente (5.4)", True)
    return Veredicto(NIVEL_PREGUNTA, "comando fuera del allowlist")


def _clasificar_archivo(a: Accion, techos: dict) -> Veredicto:
    """Leer y escribir. Leer es directo -- no destruye nada y es la mitad
    del pedido de Pedro -- salvo las credenciales de 5.7. Escribir es
    directo dentro de las raices del catastro y de ~/.calipso, y pregunta
    afuera, mostrando la ruta absoluta resuelta."""
    ruta = a.forma.get("ruta")
    if not ruta:
        return Veredicto(NIVEL_PREGUNTA, "accion de archivo sin ruta")
    p = _resolver(ruta)
    if es_credencial_del_servidor(p):
        return Veredicto(NIVEL_NUNCA,
                         "es la credencial del propio servidor de Calipso "
                         "(5.7): no hay prompt, hay negativa")
    if es_credencial_de_pedro(p):
        return Veredicto(NIVEL_PREGUNTA,
                         f"credencial de Pedro: {p}", True)
    if a.operacion == "leer":
        return Veredicto(NIVEL_DIRECTO, "leer no destruye nada (5.3)")
    for raiz in raices_de_escritura():
        if _dentro_de(p, raiz):
            return Veredicto(NIVEL_DIRECTO, f"dentro de {raiz}")
    return Veredicto(NIVEL_PREGUNTA, f"escribir fuera de las raices: {p}")


def _clasificar_app(a: Accion, techos: dict) -> Veredicto:
    """Abrir del catalogo y cerrar lo que Calipso abrio son directos: en
    los dos casos hay handle y el conjunto es cerrado. Cerrar lo que no
    abrio, o matar por PID, es pregunta: no hay handle, la busqueda por
    nombre puede acertarle a otra cosa, y del otro lado puede haber una
    hora de trabajo sin guardar (5.5)."""
    if a.operacion in ("abrir", "cerrar_propia"):
        return Veredicto(NIVEL_DIRECTO, f"{a.operacion}: hay handle (5.5)")
    return Veredicto(NIVEL_PREGUNTA,
                     "cerrar algo que Calipso no abrio: no hay handle (5.5)")


_CLASIFICADORES: dict[str, Callable[[Accion, dict], Veredicto]] = {
    "plata": _clasificar_plata,
    "comando": _clasificar_comando,
    "archivo": _clasificar_archivo,
    "app": _clasificar_app,
}


def familias() -> tuple[str, ...]:
    return tuple(sorted(_CLASIFICADORES))


def registrar_clasificador(
        familia: str, fn: Callable[[Accion, dict], Veredicto]) -> None:
    _CLASIFICADORES[familia] = fn


def clasificar(a: Accion, techos: dict | None = None) -> Veredicto:
    """El nivel de una accion. Una familia desconocida NO es directo: es
    pregunta. Es el mismo criterio de todo el modulo -- lo que no se sabe
    clasificar se pregunta, nunca se deja pasar."""
    techos = {**TECHOS_DEFECTO, **(techos or {})}
    fn = _CLASIFICADORES.get(a.familia)
    if fn is None:
        return Veredicto(NIVEL_PREGUNTA,
                         f"familia desconocida: {a.familia!r}")
    return fn(a, techos)


# --------------------------------------------------------------------------
# Cobertura: cuando un permiso permanente ya concedido tapa una accion
# --------------------------------------------------------------------------

def _cubre_exacto(forma_permiso: dict, forma_accion: dict) -> bool:
    """El default, y el que aplica a los comandos: igualdad exacta del
    dict entero. El argv se compara elemento por elemento porque es una
    lista dentro del dict, y `["npm","test"]` != `["npm","test","--","x"]`.
    """
    return forma_permiso == forma_accion


def _cubre_archivo(forma_permiso: dict, forma_accion: dict) -> bool:
    """La unica familia con subsuncion, y es la que el spec nombra: se
    concede "escribir bajo ~/Downloads", no "escribir fuera de las
    raices". El permiso guarda una `raiz` y tapa las rutas de abajo. Un
    permiso con `ruta` exacta solo tapa ese archivo."""
    ruta = forma_accion.get("ruta")
    if not ruta:
        return False
    raiz = forma_permiso.get("raiz")
    if raiz:
        return _dentro_de(_resolver(ruta), _resolver(raiz))
    return _cubre_exacto(forma_permiso, forma_accion)


_COBERTURAS: dict[str, Callable[[dict, dict], bool]] = {
    "archivo": _cubre_archivo,
}


def registrar_cobertura(familia: str,
                        fn: Callable[[dict, dict], bool]) -> None:
    _COBERTURAS[familia] = fn


def cubre(permiso: dict, a: Accion) -> bool:
    """Un permiso permanente tapa una accion cuando coinciden familia,
    operacion y forma. Nunca por categoria: no existe conceder "npm", solo
    `["npm","test"]` en tal cwd."""
    if permiso.get("familia") != a.familia:
        return False
    if permiso.get("operacion") != a.operacion:
        return False
    fn = _COBERTURAS.get(a.familia, _cubre_exacto)
    return bool(fn(permiso.get("forma") or {}, a.forma))
