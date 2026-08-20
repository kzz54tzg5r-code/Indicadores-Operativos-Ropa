from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from commercial import pdf_pages
from commercial.pdf_pages import _dimension_summary, _pending_pdf_entries, _process_pdf_entries, _scenario_models
from commercial.ui import _latest_week


SMOKE_APP = Path(__file__).with_name("commercial_smoke_app.py")


def _summary_app(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_SMOKE_PAGE", "Mi Tienda Comercial")
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
    catalog_button = next(button for button in app.sidebar.button if button.label == "Qué vendo")
    catalog_button.click().run()

    assert not app.exception
    assert app.session_state["nav_page"] == "Ventas Comerciales"
    assert app.session_state["project_nav_selector"] == "Ventas Comerciales"


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


def test_pending_pdf_entries_only_returns_retryable_files_for_week(monkeypatch, tmp_path):
    source = tmp_path / "AC_IZT.pdf"
    source.write_bytes(b"pdf")
    monkeypatch.setattr(pdf_pages, "resolve_entry_path", lambda _entry: source)
    manifest = {
        "pdfs": [
            {"id": "done", "week": "2026-W34", "status": "Procesado"},
            {"id": "review", "week": "2026-W34", "status": "Revisar"},
            {"id": "working", "week": "2026-W34", "status": "Procesando"},
            {"id": "error", "week": "2026-W34", "status": "Error"},
            {"id": "waiting", "week": "2026-W34", "status": "Pendiente de validación"},
            {"id": "other-week", "week": "2026-W33", "status": "Error"},
        ]
    }

    assert [entry["id"] for entry in _pending_pdf_entries(manifest, "2026-W34")] == [
        "working", "error", "waiting",
    ]


def test_pdf_processing_persists_each_success_and_continues_after_error(monkeypatch, tmp_path):
    good = tmp_path / "AC_IZT.pdf"
    bad = tmp_path / "AC_BAD.pdf"
    good.write_bytes(b"good")
    bad.write_bytes(b"bad")
    updates = []
    snapshots = []

    def extract(path):
        if path == bad:
            raise ValueError("PDF ilegible")
        return {
            "status": "Procesado", "store": "Iztapalapa", "week": "2026-W34",
            "report_date": "2026-08-19", "pages": 23, "models": 100,
            "parser_version": pdf_pages.PDF_PARSER_VERSION,
        }

    class Progress:
        def __init__(self):
            self.calls = []

        def progress(self, value, text=""):
            self.calls.append((value, text))

    class Placeholder:
        def __init__(self):
            self.frames = []

        def dataframe(self, frame, **_kwargs):
            self.frames.append(frame.copy())

    monkeypatch.setattr(pdf_pages, "load_snapshots", lambda: {})
    monkeypatch.setattr(pdf_pages, "extract_pdf_snapshot", extract)
    monkeypatch.setattr(pdf_pages, "save_snapshot", lambda entry_id, snapshot: snapshots.append((entry_id, snapshot)))
    monkeypatch.setattr(pdf_pages, "update_entry", lambda category, entry_id, **changes: updates.append((category, entry_id, changes)))
    progress = Progress()
    placeholder = Placeholder()

    outcome = _process_pdf_entries(
        [
            ({"id": "good", "name": good.name, "store": ""}, good),
            ({"id": "bad", "name": bad.name, "store": ""}, bad),
        ],
        "2026-W34",
        progress,
        placeholder,
    )

    assert outcome["completed"] == 2
    assert len(outcome["errors"]) == 1
    assert snapshots[0][0] == "good"
    assert any(entry_id == "good" and changes.get("status") == "Procesado" for _, entry_id, changes in updates)
    assert any(entry_id == "bad" and changes.get("status") == "Error" for _, entry_id, changes in updates)
    assert outcome["results"][-1]["Estado"] == "Error"
    assert len(progress.calls) == 4
    assert placeholder.frames


def test_dimension_summary_keeps_pieces_sales_and_utility_as_separate_participations():
    frame = pd.DataFrame([
        {"Tienda": "A", "Tipo": "section", "Etiqueta": "DAMA", "Sección": "", "VPD": 70, "Existencia": 700, "Piso": 600, "Bodega": 100, "Posiciones": 10, "Inversión": 0, "% Piezas": 70, "% Venta": 75, "% Utilidad": 80},
        {"Tienda": "A", "Tipo": "section", "Etiqueta": "NIÑA", "Sección": "", "VPD": 30, "Existencia": 300, "Piso": 250, "Bodega": 50, "Posiciones": 5, "Inversión": 0, "% Piezas": 30, "% Venta": 25, "% Utilidad": 20},
    ])

    result = _dimension_summary(frame, "Sección").set_index("Elemento")

    assert result.loc["Dama", "% Part. piezas"] == 70
    assert result.loc["Dama", "% Part. venta $"] == 75
    assert result.loc["Dama", "% Part. utilidad"] == 80
    assert result.loc["Infantil", "VPD"] == 30


def test_scenario_models_filters_ranking_and_assigns_plain_language_action():
    frame = pd.DataFrame([
        {"Tienda": "A", "Escenario": "Sugerido / VPD", "Ranking": 1, "Sección": "Dama", "ID_ART": "100", "Modelo": "M1", "Rubro": "BLUSA", "Piso": 8, "Bodega": 2, "Existencia": 10, "VPD": 1, "DDI": 10, "Inversión": 0, "% Utilidad": 2, "% Venta": 3},
        {"Tienda": "A", "Escenario": "Utilidad", "Ranking": 1, "Sección": "Dama", "ID_ART": "100", "Modelo": "M1", "Rubro": "BLUSA", "Piso": 8, "Bodega": 2, "Existencia": 10, "VPD": 1, "DDI": 10, "Inversión": 0, "% Utilidad": 5, "% Venta": 3},
    ])

    result = _scenario_models(frame, "Sugerido / VPD")

    assert len(result) == 1
    assert result.iloc[0]["Prioridad"] == "1 · Urgente"
    assert result.iloc[0]["Acción"] == "Resurtir"
    assert result.iloc[0]["Línea"] == "Blusa"
