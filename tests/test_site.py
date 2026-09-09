"""Prevent misleading comparisons in the shopping presentation."""
from web.generate import build_page, render_rows


def test_price_highlight_requires_comparable_units_and_handles_ties():
    rows = [{"id": "apple", "name": "Manzana", "category": "Verdulería", "prices": {
        "a": {"price_per_unit": 10, "price_lista": 10, "per_unit": "u", "desc": "Envase <especial>"},
        "b": {"price_per_unit": 100, "price_lista": 50, "per_unit": "kg"},
        "c": {"price_per_unit": 100, "price_lista": 100, "per_unit": "kg"},
    }}]
    html = render_rows(rows, ['a', 'b', 'c'], {'apple': {'unit': 'kg'}})
    assert html.count('class="best"') == 2
    assert 'data-comparable="false"' in html
    assert '<details class="offer"' not in html
    assert 'aria-haspopup="dialog"' in html
    assert 'Envase &lt;especial&gt;' in html
    assert 'class="best"' not in render_rows(rows, ['a', 'b'], {'apple': {'unit': 'kg'}})


def test_partial_baskets_are_not_ranked_and_absent_zone_is_not_selectable():
    data = {"date": "2026-09-05", "branches_count": 2,
            "chains": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "hero": [{"chain_id": "a", "total": 10, "items_found": 1},
                     {"chain_id": "b", "total": 30, "items_found": 2}],
            "table": [], "zones": {"gran": {"hero": []}}}
    html = build_page(data, {}, {}, {})
    assert 'los totales no son comparables' in html
    assert 'Más barato' not in html
    assert 'Ahorro máximo' not in html
    assert 'data-zone="gran"' not in html
    assert 'class="fc-badge' not in html
    assert '<details class="disclosure" id="metodologia"><summary>' in html


def test_superseded_forecast_scores_are_not_presented_as_current():
    from web.generate import render_forecast
    evaluation = {'timesfm_ok': True, 'fallback_naive': 2220}
    html = render_forecast({}, evaluation, 'package-price-v2')
    assert 'pendiente repetirla' in html
    assert '2.220 predicciones' not in html
    evaluation['price_normalization_version'] = 'package-price-v2'
    html = render_forecast({}, evaluation, 'package-price-v2')
    assert 'pendiente repetirla' not in html
    assert '2.220 predicciones' in html
    evaluation['status'] = 'superseded'
    assert 'pendiente repetirla' in render_forecast({}, evaluation, 'package-price-v2')


def test_forecast_arrows_only_use_current_matching_full_area_prices():
    from copy import deepcopy
    date = '2026-09-08'
    row = {'id': 'milk', 'name': 'Leche', 'category': 'Lácteos', 'prices': {
        'a': {'price_per_unit': 100, 'price_lista': 100, 'per_unit': 'L'}}}
    data = {'date': date, 'price_normalization_version': 'v2', 'table': [row],
            'chains': [{'id': 'a', 'label': 'A'}], 'hero': []}
    data['zones'] = {'rosario': {**data, 'hero': [{'chain_id': 'a', 'total': 100, 'items_found': 1}]}}
    forecast = {'as_of': date, 'mode': 'real', 'price_normalization_version': 'v2',
                'items': {'milk__a': {'as_of': date, 'last': 100, 'pred': 102, 'delta_pct': 2, 'dir': 'sube'}}}
    definitions = {'milk': {'unit': 'L'}}
    for direction, symbol in [('sube', '↑'), ('baja', '↓'), ('estable', '→')]:
        forecast['items']['milk__a']['dir'] = direction
        html = build_page(data, {}, {}, definitions, forecast)
        assert html.count('class="forecast-arrow ') == 1
        assert f'>{symbol}</span>' in html
        assert '$102/L' in html
    for field, value in [('as_of', '2026-09-07'), ('price_normalization_version', 'old'), ('mode', 'synthetic')]:
        invalid = {**forecast, field: value}
        assert 'class="forecast-arrow ' not in build_page(data, {}, {}, definitions, invalid)
    for field, value in [('as_of', '2026-09-07'), ('last', 90), ('pred', float('nan'))]:
        invalid = deepcopy(forecast)
        invalid['items']['milk__a'][field] = value
        assert 'class="forecast-arrow ' not in build_page(data, {}, {}, definitions, invalid)
    assert 'class="forecast-arrow ' not in build_page(data, {}, {}, definitions)


def test_history_reports_observed_days_and_explicit_gaps():
    from web.generate import render_history
    history = {'snapshots': 626, 'first_date': '2024-08-19', 'last_date': '2026-09-08',
               'unavailable_dates': ['2026-04-01'], 'rejected_source_dates': {'2024-12-27': {}}}
    html = render_history(history)
    assert '626 días con datos reales' in html
    assert '1 fechas sin descarga pública' in html
    assert '1 archivos descartados' in html
    assert 'history-evaluation/report.md' in html
    assert render_history({}) == ''
