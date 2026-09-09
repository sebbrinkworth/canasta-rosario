import io
import json
import subprocess
import tarfile
import zipfile

import pytest

from etl.backfill import choose_entry, extract_archive, import_day, selected_product_rows
from etl.etl import observation_from_row


HEADER = "id_comercio|id_bandera|id_sucursal|id_producto|productos_ean|productos_descripcion|productos_cantidad_presentacion|productos_unidad_medida_presentacion|productos_marca|productos_precio_lista\n"
ROW = "12|1|095|07790070431905|1|ARROZ LARGO FINO 1 KG|1|kg|Marca|1500\n"


def test_streaming_filter_preserves_identity_and_chunk_boundaries():
    content = ("\ufeff" + HEADER + ROW + ROW.replace("|095|", "|096|") + ROW.rstrip()).encode()
    rows = list(selected_product_rows(io.BytesIO(content), {("12", "1", "095")}, chunk_size=17))
    assert len(rows) == 2
    assert rows[0]["id_producto"] == "07790070431905"
    obs = observation_from_row(rows[0], {"sucursales_localidad": "Rosario"})
    assert obs["product_id"] == "07790070431905"
    assert obs["ean_flag"] == "1"
    assert obs["bandera_id"] == "1"
    assert obs["canonical_id"] == "arroz"
    assert obs["price_per_unit"] == 1500


def test_revision_choice_ignores_metadata_only_and_prefers_clean_early_capture():
    entries = [
        {"id": "missing"},
        {"id": "warning", "link": "a", "firstSeenAt": "2026-07-01", "warnings": "bad"},
        {"id": "later", "link": "b", "firstSeenAt": "2026-07-03"},
        {"id": "first", "link": "c", "firstSeenAt": "2026-07-02"},
    ]
    assert choose_entry(entries)["id"] == "first"
    assert choose_entry([entries[0]]) is None


def fixture_archive(tmp_path, extra_row="", nested_zip=False):
    path = tmp_path / "fixture.tar"
    contents = {
        # Products intentionally appear before branch metadata.
        "2026-07-01/shop/productos.csv": HEADER + ROW + extra_row,
        "2026-07-01/shop/sucursales.csv": "id_comercio|id_bandera|id_sucursal|sucursales_localidad|sucursales_provincia|sucursales_nombre\n12|1|095|Rosario|AR-S|Shop\n",
    }
    if nested_zip:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as inner:
            for name, text in contents.items():
                inner.writestr(name.rsplit("/", 1)[-1], text)
        contents = {"2026-07-01/shop.zip": buffer.getvalue()}
    with tarfile.open(path, "w") as archive:
        for name, text in contents.items():
            data = text.encode() if isinstance(text, str) else text
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    compressed = tmp_path / "fixture.tar.zst"
    subprocess.run(["zstd", "-q", str(path), "-o", str(compressed)], check=True)
    return compressed


def test_retailer_zip_inside_tar_is_supported(tmp_path):
    path = fixture_archive(tmp_path, nested_zip=True)
    _, branches, observations, counts = extract_archive(path, "2026-07-01")
    assert len(branches) == 1
    assert observations[0]["product_id"] == "07790070431905"
    assert observations[0]["price_per_unit"] == 1500
    assert counts["product_files"] == 1


def test_archive_validation_and_no_latest_rewind(tmp_path):
    path = fixture_archive(tmp_path)
    with pytest.raises(ValueError, match="date mismatch"):
        extract_archive(path, "2026-07-02")
    output = tmp_path / "out"
    output.mkdir()
    (output / "latest.json").write_text('{"date":"2026-09-08"}')
    entry = {"name": path.name, "id": "fixture", "link": "https://example.invalid/unused"}
    result = import_day("2026-07-01", entry, output, tmp_path, True)
    assert result["status"] == "imported"
    assert json.loads((output / "latest.json").read_text())["date"] == "2026-09-08"
    snapshot = json.loads((output / "rosario-2026-07-01.json").read_text())
    rice = next(x for x in snapshot["table"] if x["id"] == "arroz")
    assert rice["prices"]["12"]["price_per_unit"] == 1500
    assert import_day("2026-07-01", entry, output, tmp_path, True)["status"] == "existing"


def test_conflicting_product_duplicates_are_quarantined(tmp_path):
    path = fixture_archive(tmp_path, ROW.replace("1500", "2000"))
    _, _, observations, counts = extract_archive(path, "2026-07-01")
    assert counts["conflicting_identities_excluded"] == 1
    assert len(observations) == 1
    assert observations[0]["identity_conflict"]
    assert observations[0]["price_per_unit"] is None
    assert len(observations[0]["source_variants"]) == 2
    from etl.prices import normalize_observation
    assert normalize_observation(observations[0], "kg") is None
