from pathlib import Path

from streamlit.testing.v1 import AppTest


SMOKE_APP = Path(__file__).with_name("commercial_smoke_app.py")


def _summary_app(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_SMOKE_PAGE", "Resumen Comercial")
    return AppTest.from_file(str(SMOKE_APP), default_timeout=45).run()


def test_sidebar_navigation_does_not_mutate_an_instantiated_widget(monkeypatch):
    app = _summary_app(monkeypatch)
    app.sidebar.button[8].click().run()

    assert not app.exception
    assert app.session_state["nav_page"] == "Carga Comercial"
    assert app.session_state["project_nav_selector"] == "Carga Comercial"


def test_top_navigation_uses_deferred_request(monkeypatch):
    app = _summary_app(monkeypatch)
    app.radio[0].set_value("Tiendas").run()

    assert not app.exception
    assert app.session_state["nav_page"] == "Tiendas Comerciales"
    assert app.session_state["project_nav_selector"] == "Tiendas Comerciales"
