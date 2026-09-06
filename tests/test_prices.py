"""Quantity conversions and regressions from actual SEPA packaging records."""
import json

import pytest

from etl.prices import base_quantity, description_quantity, normalize_observation, price_per_unit


@pytest.mark.parametrize('quantity,unit,expected', [
    (500, 'GRM', (.5, 'kg')), (100, 'gr.', (.1, 'kg')),
    (1, 'kgr', (1, 'kg')), (750, 'MLT', (.75, 'L')),
    (1000, 'cm3', (1, 'L')), ('1,5', 'lt.', (1.5, 'L')),
    (12, 'UD', (12, 'u')), (6, 'un.', (6, 'u')),
])
def test_base_quantities(quantity, unit, expected):
    assert base_quantity(quantity, unit) == expected


def observation(price, quantity, unit, desc='', **extra):
    return dict(price_lista=price, cantidad_presentacion=quantity,
                unidad_presentacion=unit, descripcion=desc, **extra)


@pytest.mark.parametrize('description,price,expected', [
    ('YERBA MATE SELECCION CARREFOUR EXTRA CAJA X 500 GR', 3890, 7780),
    ('YOGUR BEBIB FRUTILLA LA SERENISIMA SACHET X 900 GR', 4409, 4898.89),
    ('JABON DE TOCADOR MARINA BULNEZ 75 GRAMOS', 749, 9986.67),
])
def test_generic_package_with_explicit_grams(description, price, expected):
    raw = observation(price, 1, 'UNI', description,
                      price_per_unit=1, per_unit_name='kg')
    result = normalize_observation(raw, 'kg')
    assert result['price_per_unit'] == expected
    assert result['price_basis'] == 'description'
    assert raw['price_per_unit'] == 1  # normalization never mutates the source
    assert normalize_observation(result, 'kg') == result  # no double conversion


def test_inconsistent_retailer_reference_cannot_override_package_size():
    raw = observation(4409, 1, 'UNI', 'YOGUR X 900 GR',
                      precio_referencia='489.89', cantidad_referencia='900', unidad_referencia='GRS')
    result = normalize_observation(raw, 'kg')
    assert result['price_per_unit'] == 4898.89
    # Dividing this retailer's reference quote by reference quantity is also wrong.
    assert round(price_per_unit(489.89, 900, 'GRS')[0], 2) != result['price_per_unit']
    assert result['precio_referencia'] == '489.89'


def test_milk_is_litres_even_when_reference_says_grams():
    raw = observation(1710, 1, 'UNI', 'LECHE ENTERA CREMIGAL X 1 LT',
                      precio_referencia='1710', cantidad_referencia='1000', unidad_referencia='GRM')
    result = normalize_observation(raw, 'L')
    assert (result['price_per_unit'], result['per_unit_name']) == (1710, 'L')


@pytest.mark.parametrize('description,unit,expected', [
    ('JABON 3 X 125GRS', 'kg', .375),
    ('JABON 75 GRS X 3 UNI', 'kg', .225),
    ('Yerba 500g PAQ-500-gr.', 'kg', .5),
    ('HUEVO BLANCO BENECH X 30 C T', 'u', 30),
    ('HUEVO CARTON X 6 UNI', 'u', 6),
    ('ACEITE X 1,5 L', 'L', 1.5),
    ('PAQUETE 500 G + 100 G GRATIS', 'kg', None),
    ('PACK 500 G O 1 KG', 'kg', None),
    ('POLLO ENTERO FRESCO UNI', 'kg', None),
])
def test_description_sizes(description, unit, expected):
    result = description_quantity(description, unit)
    assert result == pytest.approx(expected) if expected is not None else result is None


def test_egg_carton_is_not_one_egg():
    result = normalize_observation(observation(4999, 1, 'UNI', 'HUEVO X 30 C T'), 'u')
    assert result['price_per_unit'] == 166.63
    assert normalize_observation(observation(1000, 1, 'UNI', 'HUEVO CARTON'), 'u') is None


@pytest.mark.parametrize('raw', [observation(1000, 0, 'kg'),
                                 observation(-10, 1, 'kg'),
                                 observation(float('inf'), 1, 'kg'),
                                 observation(1000, 1, 'UNI', 'POLLO ENTERO'),
                                 observation(1000, 1, 'L', 'PRODUCTO SIN PESO')])
def test_unverified_prices_are_excluded(raw):
    assert normalize_observation(raw, 'kg') is None


def test_aggregation_excludes_incompatible_units_from_minimum_and_total():
    from etl.etl import aggregate
    rows = [dict(canonical_id='pollo', chain_id='12', price_per_unit=1000, per_unit_name='u'),
            dict(canonical_id='pollo', chain_id='12', price_per_unit=4000, per_unit_name='kg')]
    agg = aggregate(rows, [])
    assert agg['cheapest']['12']['pollo']['price_per_unit'] == 4000
    assert agg['hero'][0]['total'] == 4000
    assert agg['hero'][0]['items_found'] == 1


def test_rebuild_preserves_raw_and_is_numerically_repeatable(tmp_path, monkeypatch):
    import etl.rebuild_tables as rebuild
    raw = tmp_path / 'raw.json'
    source = {'date': '2026-09-05', 'branches': [], 'observations': [
        dict(observation(3890, 1, 'UNI', 'YERBA MATE X 500 GR', price_per_unit=778, per_unit_name='kg'),
             canonical_id='yerba', chain_id='10', chain_label='Carrefour', ean='1', marca='Test', branch_localidad='Rosario')]}
    raw.write_text(json.dumps(source))
    before = raw.read_bytes()
    monkeypatch.setattr(rebuild, 'AGG', tmp_path)
    first = rebuild.rebuild_one(raw)
    second = rebuild.rebuild_one(raw)
    assert raw.read_bytes() == before
    assert first == second
    data = json.loads((tmp_path / 'rosario-2026-09-05.json').read_text())
    row = next(r for r in data['table'] if r['id'] == 'yerba')
    assert row['prices']['10']['price_per_unit'] == 7780


def test_csv_extraction_uses_same_normalization_and_preserves_reference_fields(tmp_path, monkeypatch):
    import csv
    import io
    import zipfile
    from etl import etl
    monkeypatch.setattr(etl, 'is_rosario_branch', lambda row, gran_rosario=False: True)
    headers = ['id_comercio', 'id_bandera', 'id_sucursal', 'id_producto', 'productos_ean',
               'productos_descripcion', 'productos_precio_lista', 'productos_cantidad_presentacion',
               'productos_unidad_medida_presentacion', 'productos_precio_referencia',
               'productos_cantidad_referencia', 'productos_unidad_medida_referencia']
    csv_text = io.StringIO()
    writer = csv.writer(csv_text, delimiter='|')
    writer.writerow(headers)
    writer.writerow(['10', '1', '1', '123', '1', 'YOGUR X 900 GR', '4409', '1', 'UNI', '489.89', '900', 'GRS'])
    writer.writerow(['10', '1', '1', '124', '0', 'POLLO ENTERO UNI', '1000', '1', 'UNI', '1000', '1', 'UNI'])
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, 'w') as archive:
        archive.writestr('sucursales.csv', 'id_comercio|id_bandera|id_sucursal\n10|1|1\n')
        archive.writestr('productos.csv', csv_text.getvalue())
    archive_path = tmp_path / 'sepa.zip'
    with zipfile.ZipFile(archive_path, 'w') as archive:
        archive.writestr('chain.zip', inner.getvalue())
    _, _, rows = etl.extract_observations(archive_path)
    assert rows[0]['price_per_unit'] == 4898.89
    assert rows[0]['cantidad_referencia'] == '900'
    assert rows[0]['precio_referencia'] == '489.89'
    assert rows[1]['price_per_unit'] is None
    kept, rejected, _ = etl.filter_outliers(rows)
    assert len(kept) == len(rejected) == 1
