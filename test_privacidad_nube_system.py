"""El system del turno en /nube: cuando el turno va tapado a la nube, el
system tiene que ser minimo (sin recuerdos, sin contexto personal). Ver
`_sistema_del_turno` en calipso/server.py -- lo usan las 4 llamadas del
camino de envio (principal, orquestacion, y los dos fallbacks del except).
"""
import calipso.server as srv


def test_a_la_nube_tapado_usa_el_system_minimo_y_no_toca_build_context(monkeypatch):
    """Si el turno va tapado a la nube, no se arma el contexto completo: se
    devuelve `_sistema_nube()`: el minimo mas el contrato del abismo sin
    nombres, sin filtrar recuerdos ni llamar a `_build_context` (que traeria
    contexto sin tapar)."""
    llamado = []
    monkeypatch.setattr(srv, "_build_context",
                         lambda *a, **k: llamado.append((a, k)) or "CONTEXTO CRUDO")

    resultado = srv._sistema_del_turno("mi dato", "rt", {}, a_la_nube_tapado=True)

    # desde el abismo el system de nube es el minimo MAS el contrato sin
    # nombres y la linea de marcadores (spec seccion 8.1): sigue sin tocar
    # _build_context. Desde los canarios viaja como UNA seccion cruda
    # (titulo vacio) que `render_context` rinde tal cual
    assert resultado == [("", srv._sistema_nube())]
    assert srv.prompt_compiler.render_context(resultado) == srv._sistema_nube()
    assert srv._sistema_nube().startswith(srv._SISTEMA_NUBE_MINIMO)
    assert llamado == [], "no debe llamar a _build_context en /nube tapado"


def test_sin_nube_tapado_usa_el_contexto_completo(monkeypatch):
    """Sin /nube (o /nube que quedo en local), el system es el de siempre:
    el resultado de `_build_context`, llamado con los mismos argumentos."""
    marcado = object()
    llamado = []

    def _falso_build_context(chat_msg, runtime, features):
        llamado.append((chat_msg, runtime, features))
        return marcado

    monkeypatch.setattr(srv, "_build_context", _falso_build_context)

    resultado = srv._sistema_del_turno("mi dato", "rt", {}, a_la_nube_tapado=False)

    assert resultado is marcado
    assert llamado == [("mi dato", "rt", {})]
