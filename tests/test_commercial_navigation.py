from pathlib import Path

from streamlit.testing.v1 import AppTest

from commercial.ui import _latest_week


SMOKE_APP = Path(__file__).with_name("commercial_smoke_app.py")


def _summary_app(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_SMOKE_PAGE", "Radiografía Comercial")
    return AppTest.from_file(str(SMOKE_APP), default_timeout=45).run()


def test_sidebar_navigation_does_not_mutate_an_instantiated_widget(monkeypatch):
    app = _summary_app(monkeypatch)
    upload_button = next(button for button in app.sidebar.button if button.label == "Carga PDF")
    upload_button.click().run()

    assert not app.exception
    assert app.session_state["nav_page"] == "Carga Comercial"
    assert app.session_state["project_nav_selector"] == "Carga Comercial"


def test_sidebar_navigation_uses_deferred_request(monkeypatch):
    app = _summary_app(monkeypatch)
    catalog_button = next(button for button in app.sidebar.button if button.label == "Catálogo")
    catalog_button.click().run()

    assert not app.exception
    assert app.session_state["nav_page"] == "Catálogo Comercial"
    assert app.session_state["project_nav_selector"] == "Catálogo Comercial"


def test_latest_week_ignores_sin_semana_when_iso_weeks_exist():
    assert _latest_week(["2024-W14", "Sin semana", "2026-W34"]) == "2026-W34"


def test_summary_has_week_filter_and_visual_blocks(monkeypatch):
    app = _summary_app(monkeypatch)

    assert not app.exception
    assert [item.label for item in app.selectbox][1:3] == ["Periodo", "Tienda"]
    assert len(app.get("plotly_chart")) == 1
    assert len(app.dataframe) == 1


def test_macro_to_micro_navigation_reaches_model_detail(monkeypatch):
    app = _summary_app(monkeypatch)
    next(item for item in app.selectbox if item.label == "Tienda").set_value("Iztapalapa").run()
    next(item for item in app.selectbox if item.label == "Categoría").set_value("Dama").run()
    next(item for item in app.selectbox if item.label == "Línea").set_value("BLUSA").run()
    model = next(item for item in app.selectbox if item.label == "Modelo / SKU")
    model.set_value(model.options[1]).run()

    assert not app.exception
    assert len(app.get("plotly_chart")) == 1
    assert len(app.dataframe) == 1
