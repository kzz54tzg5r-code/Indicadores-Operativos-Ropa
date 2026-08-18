from pathlib import Path

from commercial.analytics import (
    inventory_buckets,
    location_summary,
    opportunities,
    rank_models,
    snapshots_to_frames,
    store_summary,
)
from commercial.parsers import extract_pdf_snapshot, read_capacity_file, store_from_filename


ROOT = Path(__file__).resolve().parents[1]
CAPACITY = ROOT / "data" / "commercial" / "capacidades" / "capacidades_24.04.26.xls"
PDF = ROOT / "data" / "commercial" / "pdfs" / "2024-W14" / "AC_IZT.pdf"


def test_capacity_sample_is_normalized():
    models = read_capacity_file(CAPACITY)

    assert len(models) == 6761
    assert set(models["Tienda"]) == {"Olivar"}
    assert {"Dama", "Caballero", "Infantil"}.issubset(set(models["Sección"]))
    assert {"Doblado", "Colgado", "Jeans", "Lencería"} == set(models["Ubicación"])
    assert models["Existencia"].sum() == 161906


def test_pdf_sample_builds_weekly_snapshot():
    snapshot = extract_pdf_snapshot(PDF)

    assert snapshot["status"] == "Procesado"
    assert snapshot["store"] == "Iztapalapa"
    assert snapshot["report_date"] == "2024-04-01"
    assert snapshot["week"] == "2024-W14"
    assert snapshot["pages"] == 23
    assert snapshot["models"] == 7615
    assert snapshot["existence"] == 291307
    assert snapshot["vpd"] == 3326
    assert snapshot["ddi"] == 88
    assert len(snapshot["sections"]) == 7
    assert {row["Ubicación"] for row in snapshot["locations"]} == {"Doblado", "Colgado"}


def test_model_rankings_and_inventory_views_are_available():
    models = read_capacity_file(CAPACITY)
    snapshot = extract_pdf_snapshot(PDF)
    _, _, locations = snapshots_to_frames([snapshot])

    ranked_vpd = rank_models(models, "Sugerido / VPD")
    ranked_utility = rank_models(models, "Utilidad")
    coverage = inventory_buckets(models)
    location = location_summary(models, locations)
    actions = opportunities(models)

    assert not ranked_vpd.empty and not ranked_utility.empty
    assert {"Campeón", "Lento", "En riesgo"}.issubset(set(ranked_vpd["Estado modelo"]))
    assert len(coverage) == 4
    assert {"Doblado", "Colgado", "Jeans", "Lencería"} == set(location["Ubicación"])
    assert not actions.empty


def test_store_codes_used_by_weekly_pdf_names_are_recognized():
    expected = {
        "AC_AGS_17.08.26.pdf": "Aguascalientes",
        "AC_ARCO_17.08.26.pdf": "Arco Norte",
        "AC_ATE_17.08.26.pdf": "Atemajac",
        "AC_ECA_17.08.26.pdf": "Ecatepec",
        "AC_MIR_17.08.26.pdf": "Miravalle",
        "AC_QRO_17.08.26.pdf": "Querétaro",
        "AC_TOL_17.08.26.pdf": "Toluca",
        "AC_VALL_17.08.26.pdf": "Vallejo",
        "AC_VER_17.08.26.pdf": "Veracruz",
        "AC_PUE_SUR_17.08.26.pdf": "Puebla Sur",
    }

    assert {name: store_from_filename(name) for name in expected} == expected


def test_pdf_snapshot_overlays_current_inventory_without_losing_sales():
    models = read_capacity_file(CAPACITY)
    snapshot = extract_pdf_snapshot(PDF)
    stores, sections, locations = snapshots_to_frames([snapshot])

    summary = store_summary(models, None, stores)
    by_store = summary.set_index("Tienda")
    section = location_summary(models, locations).set_index("Ubicación")

    assert by_store.loc["Iztapalapa", "Existencia"] == snapshot["existence"]
    assert by_store.loc["Olivar", "Venta $"] == models["Venta $"].sum()
    assert section.loc["Doblado", "Existencia"] == 130854
