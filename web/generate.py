#!/usr/bin/env python3
"""Generate the self-contained shopping page for all three static entry points."""
import json
import math
import sys
from collections import defaultdict
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/sebbrinkworth/canasta-rosario"
CATEGORIES = ["Lácteos", "Panificados", "Almacén", "Infusiones", "Conservas",
              "Carnes", "Frescos", "Verdulería", "Limpieza"]


def read_optional(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def text(value):
    return escape(str(value).strip(), quote=True)


def number(value, decimals=0):
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return "—"
    return f"{value:,.{decimals}f}".translate(str.maketrans({",": ".", ".": ","}))


def money(value):
    return f"${number(value)}"


def unit_name(unit):
    return {"kg": "kg", "L": "L", "u": "unidad"}.get(unit, unit)


def comparable(price, expected_unit):
    value = (price or {}).get("price_per_unit")
    return (bool(price) and price.get("per_unit") == expected_unit
            and isinstance(value, (int, float)) and math.isfinite(value) and value > 0)


def render_rows(rows, chain_ids, definitions):
    groups = defaultdict(list)
    for row in rows:
        groups[row["category"]].append(row)
    result = []
    for category in dict.fromkeys([*CATEGORIES, *groups]):
        if not groups[category]:
            continue
        result.append(f'<tr class="category"><th scope="rowgroup" colspan="{len(chain_ids)+1}">{text(category)}</th></tr>')
        for row in groups[category]:
            unit = definitions.get(row["id"], {}).get("unit")
            prices = row.get("prices") or {}
            valid = [prices[c]["price_per_unit"] for c in chain_ids
                     if comparable(prices.get(c), unit)]
            # A lone observation is not a comparison. Include ties when comparable.
            best = min(valid) if len(valid) > 1 else None
            result.append(f'<tr><th scope="row">{text(row["name"])}<small>por {text(unit_name(unit or "unidad"))}</small></th>')
            for cid in chain_ids:
                price = prices.get(cid)
                if not price:
                    result.append('<td><span class="missing" aria-label="Sin dato comparable">—</span></td>')
                    continue
                is_valid = comparable(price, unit)
                is_best = is_valid and best is not None and price["price_per_unit"] == best
                value = money(price["price_per_unit"] if is_valid else price.get("price_lista"))
                suffix = f'/{text(unit_name(unit))}' if is_valid else ' por envase'
                best_label = '<span class="sr-only">Menor precio informado. </span>' if is_best else ''
                result.append(f'''<td class="{'best' if is_best else ''}">
                  <button type="button" class="price-button" aria-haspopup="dialog" aria-expanded="false" aria-controls="price-detail"
                    data-product="{text(price.get('desc') or 'Descripción no disponible')}"
                    data-package="{text(money(price.get('price_lista')))}"
                    data-reference="{text(value + suffix)}"
                    data-comparable="{str(is_valid).lower()}"
                    data-label="{text(row['name'])}">
                    {best_label}{value}<span class="price-unit">{suffix}</span>
                  </button></td>''')
            result.append('</tr>')
    return "\n".join(result)


def render_zone(key, data, definitions, total_items):
    chains = data.get("chains") or []
    # Stable chain order; partial totals must not imply a basket ranking.
    chain_ids = [c["id"] for c in chains]
    labels = {c["id"]: c["label"] for c in chains}
    totals = {h["chain_id"]: h for h in data.get("hero", [])}
    cards = []
    for cid in chain_ids:
        h = totals.get(cid)
        if not h:
            continue
        cards.append(f'''<article class="chain-card"><h3>{text(labels[cid])}</h3>
          <p class="total">{money(h['total'])}</p>
          <p class="coverage">{h['items_found']} de {total_items} productos</p></article>''')
    heads = ''.join(f'<th scope="col">{text(labels[cid])}</th>' for cid in chain_ids)
    return f'''<section data-zoneblock="{key}" {'hidden' if key != 'todo' else ''} aria-label="Precios de {text(key)}">
      <div class="section-heading"><h2>Subtotales por cadena</h2><span>{data.get('branches_count', 0)} sucursales en esta zona</span></div>
      <p class="caption">Cada subtotal incluye los productos informados. Con distinta cobertura, los totales no son comparables.</p>
      <div class="chain-cards">{''.join(cards)}</div>
      <div class="section-heading products-heading"><h2>Compará por producto</h2><span>Valores en pesos argentinos</span></div>
      <p class="caption" id="legend-{key}"><span class="legend-dot" aria-hidden="true"></span>Verde: menor precio por la misma unidad · —: sin dato comparable. Tocá un precio para ver el producto.</p>
      <div class="table-scroll" tabindex="0" role="region" aria-label="Tabla de precios; desplazamiento horizontal" aria-describedby="legend-{key}">
        <table><caption class="sr-only">Precios informados por producto y cadena</caption>
          <thead><tr><th scope="col">Producto</th>{heads}</tr></thead>
          <tbody>{render_rows(data.get('table', []), chain_ids, definitions)}</tbody>
        </table>
      </div><p class="scroll-hint">Deslizá la tabla para ver todas las cadenas →</p>
    </section>'''


def render_forecast(backtest, evaluation, normalization_version=None):
    baseline = backtest.get("baseline_persistence") or {}
    results = ''
    if backtest.get("n") and baseline:
        movements = backtest.get("moves_prec") or {}
        predicted = sum((movements.get(c) or {}).get("n", 0) for c in ("sube", "baja"))
        hits = sum((movements.get(c) or {}).get("hits", 0) for c in ("sube", "baja"))
        results = f'''<p>En {backtest['n']} casos evaluados, el método de tendencia acertó {hits} de {predicted} avisos de suba o baja.</p>
          <table class="metrics"><caption>Error de precio en los mismos casos (menor es mejor)</caption>
          <thead><tr><th scope="col">Método</th><th scope="col">Error medio absoluto</th></tr></thead>
          <tbody><tr><th scope="row">Repetir el último precio</th><td>{number(baseline.get('mae'), 1)}</td></tr>
          <tr><th scope="row">Tendencia reciente</th><td>{number(backtest.get('mae'), 1)}</td></tr></tbody></table>
          <p class="caption">Error en pesos por unidad de referencia, agregado entre productos. Evaluamos solo precios observados.</p>'''
    experiment = ''
    if evaluation.get("timesfm_ok") and (evaluation.get("status") == "superseded" or
            evaluation.get("price_normalization_version") != normalization_version):
        experiment = '<p>La evaluación anterior de TimesFM usaba precios previos a la corrección de unidades. Está pendiente repetirla con los datos corregidos.</p>'
    elif evaluation.get("timesfm_ok"):
        experiment = f'''<p>También evaluamos TimesFM 3 de Google con información del dólar, precios mayoristas y competencia.
          Esa evaluación incluye {number(evaluation.get('fallback_naive', 0))} predicciones de respaldo del método simple;
          usa una muestra distinta de la tabla anterior y no permite una comparación directa.</p>'''
    return f'''<details class="disclosure" id="pronostico"><summary>¿Podemos anticipar los precios? <span>En evaluación</span></summary>
      <div class="disclosure-body"><p>Estamos probando pronósticos para el día siguiente. La tabla muestra únicamente precios informados; las predicciones quedan fuera de la comparación.</p>
      {results}{experiment}<p>La historia todavía es corta. Más datos permiten evaluar mejor, pero no garantizan mejores predicciones.</p>
      <a href="{REPO_URL}/blob/main/forecast/README.md">Método y evaluación técnica ↗</a></div></details>'''


CSS = """
:root{color-scheme:light;--ink:#172b27;--muted:#596b66;--line:#dce4df;--green:#146342;--paper:#f7f9f6}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--green);text-underline-offset:3px}button,summary{cursor:pointer}button{font:inherit}button:focus-visible,summary:focus-visible,a:focus-visible,[tabindex]:focus-visible{outline:3px solid #438b6c;outline-offset:3px}
.wrap{max-width:1160px;margin:auto;padding:0 28px}header{padding:38px 0 24px;border-bottom:1px solid var(--line)}.eyebrow{color:var(--green);font-size:11px;font-weight:750;letter-spacing:.12em;text-transform:uppercase}
.header-top{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}h1{font-size:32px;letter-spacing:-1px;line-height:1.15;margin:9px 0 12px}header p{margin:0;color:var(--muted)}.date{font-size:13px;text-align:right;padding-top:6px;white-space:nowrap}.date strong{display:block;color:var(--ink);font-weight:600}.intro{max-width:660px}.source-note{font-size:12px;margin-top:14px}
.zone-filter{display:flex;align-items:center;gap:8px;margin:24px 0 28px;flex-wrap:wrap}.zone-filter>span{font-size:13px;margin-right:4px;color:var(--muted)}.zone-chip{border:1px solid var(--line);background:white;border-radius:24px;padding:8px 16px;font-size:13px}.zone-chip[aria-pressed=true]{background:var(--ink);border-color:var(--ink);color:white}.zone-chip:hover{border-color:var(--green)}
.section-heading{display:flex;align-items:baseline;justify-content:space-between;gap:12px}.section-heading h2{font-size:17px;letter-spacing:-.25px;margin:0}.section-heading>span{font-size:12px;color:var(--muted)}.caption{font-size:12px;color:var(--muted);margin:7px 0 16px}.chain-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px}.chain-card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px}.chain-card h3{font-size:13px;font-weight:600;margin:0;min-height:20px}.total{font-size:25px;font-weight:650;letter-spacing:-.7px;font-variant-numeric:tabular-nums;margin:12px 0 2px}.coverage{font-size:12px;color:var(--muted);margin:0}.products-heading{margin-top:30px}.legend-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:5px}
.table-scroll{position:relative;overflow:auto;border:1px solid var(--line);border-radius:10px;background:white;max-height:72vh}table{border-collapse:separate;border-spacing:0;width:100%;font-variant-numeric:tabular-nums}th,td{padding:13px 14px;text-align:right;border-bottom:1px solid #edf0ed;vertical-align:top}thead th{font-size:12px;background:#edf2ee;position:sticky;top:0;z-index:3;white-space:nowrap}thead th:first-child{z-index:4}tbody th[scope=row],thead th:first-child{position:sticky;left:0;text-align:left;min-width:166px;background:#fff}thead th:first-child{background:#edf2ee}tbody th[scope=row]{z-index:1;font-size:13px;font-weight:600}th small{display:block;font-size:11px;color:var(--muted);font-weight:400;margin-top:2px}td{min-width:143px;font-size:14px}.category th{background:#f5f7f4;font-size:10px;font-weight:750;letter-spacing:.09em;text-align:left;text-transform:uppercase;padding:8px 14px}.best{background:#eef7ef;color:#155b3e}.best .price-button{font-weight:700}.price-unit{display:block;color:var(--muted);font-size:10px;font-weight:400}.missing{color:#89958f}.price-button{display:block;width:100%;border:0;background:none;color:inherit;font:inherit;text-align:right;padding:0;min-height:38px;white-space:nowrap;border-radius:4px}.price-button:hover,.price-button[aria-expanded=true]{color:var(--green)}.price-button[aria-expanded=true]{box-shadow:0 0 0 5px #dceee1}.price-button:hover{text-decoration:underline;text-underline-offset:3px}
.price-popover{position:fixed;inset:auto;margin:0;padding:20px;width:310px;max-width:calc(100vw - 32px);max-height:calc(100dvh - 32px);overflow:auto;border:1px solid var(--line);border-radius:14px;background:#fff;color:var(--ink);box-shadow:0 12px 40px #172b2726;z-index:20;font-size:13px}.popover-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.popover-heading h2{font-size:14px;margin:0}.close-popover{border:0;background:#eff3ef;color:var(--muted);border-radius:50%;width:32px;height:32px;font-size:22px;line-height:1}.product-description{margin:14px 0 18px;color:var(--muted);font-size:12px;line-height:1.6;overflow-wrap:anywhere}.price-popover dl{margin:0;border-top:1px solid var(--line);padding-top:14px;display:grid;grid-template-columns:1fr auto;gap:8px}.price-popover dt{color:var(--muted)}.price-popover dd{margin:0;font-weight:650;font-variant-numeric:tabular-nums}.price-popover .caption{margin:12px 0 0}
.scroll-hint{display:none;color:var(--muted);font-size:11px}
.about{margin:34px 0 20px}.disclosure{border-top:1px solid var(--line)}.disclosure:last-child{border-bottom:1px solid var(--line)}.disclosure>summary{padding:18px 0;font-size:14px;font-weight:600}.disclosure>summary>span{font-weight:400;color:var(--muted);font-size:12px;margin-left:10px}.disclosure-body{padding:0 0 22px;max-width:760px;color:var(--muted);font-size:13px}.disclosure-body p{margin:0 0 13px}.disclosure-body strong{color:var(--ink)}.metrics{max-width:560px;font-size:12px;margin:16px 0}.metrics caption{text-align:left;font-weight:600;color:var(--ink);margin-bottom:8px}.metrics th,.metrics td{padding:10px;text-align:left}.metrics thead th,.metrics tbody th{position:static;min-width:0}.metrics td{text-align:right;min-width:0}footer{display:flex;justify-content:space-between;gap:14px;padding:0 0 30px;font-size:11px;color:var(--muted)}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}[hidden]{display:none!important}
@media(max-width:650px){.wrap{padding:0 16px}header{padding-top:25px}.header-top{display:block}h1{font-size:28px}.date{text-align:left;margin-top:14px}.date strong{display:inline;margin-left:5px}.section-heading{display:block}.section-heading>span{display:block;margin-top:3px}.chain-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.chain-card{padding:13px}.total{font-size:24px}.zone-chip{padding:9px 13px}.zone-filter{gap:6px}.zone-filter>span{width:100%}.table-scroll{max-height:65vh}tbody th[scope=row],thead th:first-child{min-width:125px;max-width:125px}th,td{padding:11px 10px}td{min-width:120px}.scroll-hint{display:block}.disclosure>summary>span{display:block;margin:4px 0 0 17px}footer{flex-wrap:wrap}}
"""


def build_page(data, backtest, evaluation, definitions):
    date = data["date"]
    formatted = f"{date[8:10]}/{date[5:7]}/{date[:4]}"
    count = len(data.get("table", []))
    zones = {"todo": data, **{k: v for k, v in (data.get("zones") or {}).items() if v.get("hero")}}
    zone_labels = {"todo": "Toda la zona", "rosario": "Rosario", "gran": "Alrededores"}
    buttons = ''.join(f'<button type="button" class="zone-chip" data-zone="{k}" aria-pressed="{str(k == "todo").lower()}">{text(zone_labels.get(k, k))}</button>' for k in zones)
    sections = ''.join(render_zone(k, v, definitions, count) for k, v in zones.items())
    return f'''<!doctype html><html lang="es-AR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Canasta Rosario — precios del {formatted}</title>
<meta name="description" content="Compará precios informados de alimentos y limpieza en Rosario y alrededores. Datos SEPA, por producto y cadena.">
<style>{CSS}</style></head><body><div class="wrap">
<header><div class="header-top"><div><span class="eyebrow">Precios para tu compra</span><h1>Canasta Rosario</h1>
<p class="intro">Compará {count} productos de alimentos y limpieza en Rosario y alrededores.</p></div>
<p class="date">Últimos datos disponibles<strong><time datetime="{date}">{formatted}</time></strong></p></div>
<p class="source-note">Fuente: SEPA · {len(data.get('chains', []))} cadenas · {data.get('branches_count', 0)} sucursales · <a href="#metodologia">Cómo seleccionamos los precios</a></p></header>
<main><nav class="zone-filter" aria-label="Filtrar por zona"><span>Buscar en</span>{buttons}</nav>
{sections}
<section class="about" aria-label="Acerca de los datos">
<details class="disclosure" id="metodologia"><summary>Cómo seleccionamos los precios</summary><div class="disclosure-body">
<p><strong>Fuente y cobertura.</strong> Usamos los precios que las cadenas informan a <a href="https://datos.produccion.gob.ar/dataset/sepa-precios">SEPA</a>. Esta comparación no incluye La Gallega, DAR ni Micropack.</p>
<p><strong>Qué representa cada precio.</strong> Seleccionamos el menor precio por unidad entre los productos que coinciden con cada categoría, dentro de las sucursales de la zona. Pueden variar la marca, el envase y la sucursal; no es necesariamente el mismo producto ni una compra en un único local. Tocá el precio para ver su descripción.</p>
<p><strong>Cómo leer los subtotales.</strong> Aplicamos las cantidades de nuestra canasta a los productos disponibles. Si falta un producto o no podemos verificar su unidad, no se suma. Por eso una cadena con menos productos puede tener un subtotal menor sin ser más barata.</p>
<p><strong>Límites.</strong> Calculamos el precio por kg, litro o unidad con el precio del envase y su contenido. Excluimos tamaños ambiguos; la selección automática del producto aún puede contener errores. Los precios son los informados en la fecha indicada; no garantizan stock ni el precio en caja. No incluimos descuentos bancarios.</p>
<a href="{REPO_URL}/blob/main/docs/validation.md">Ver fuentes y validación técnica ↗</a></div></details>
{render_forecast(backtest, evaluation, data.get("price_normalization_version"))}</section></main>
<footer><span>Datos SEPA · CC BY 4.0</span><a href="{REPO_URL}">Código y datos abiertos ↗</a></footer></div>
<dialog id="price-detail" class="price-popover" aria-labelledby="detail-title" aria-describedby="detail-description">
  <div class="popover-heading"><h2 id="detail-title">Detalle del precio</h2><button type="button" class="close-popover" aria-label="Cerrar detalle">×</button></div>
  <p id="detail-description" class="product-description"></p>
  <dl><dt>Precio del envase</dt><dd id="detail-package"></dd><dt>Por unidad</dt><dd id="detail-reference"></dd></dl>
  <p class="caption" id="detail-unit-note" hidden>No comparable por unidad.</p>
</dialog>
<script>
const priceDetail = document.getElementById('price-detail');
let activePrice = null;
function closePriceDetail(restoreFocus = false) {{
  if (!activePrice) return;
  const previous = activePrice;
  previous.setAttribute('aria-expanded', 'false');
  priceDetail.close();
  activePrice = null;
  if (restoreFocus) previous.focus({{preventScroll:true}});
}}
document.querySelectorAll('.price-button').forEach(function(button) {{
  button.addEventListener('click', function() {{
    if (activePrice === button) {{ closePriceDetail(true); return; }}
    closePriceDetail();
    activePrice = button;
    button.setAttribute('aria-expanded', 'true');
    document.getElementById('detail-title').textContent = button.dataset.label;
    document.getElementById('detail-description').textContent = button.dataset.product;
    document.getElementById('detail-package').textContent = button.dataset.package;
    document.getElementById('detail-reference').textContent = button.dataset.comparable === 'true' ? button.dataset.reference : '—';
    document.getElementById('detail-unit-note').hidden = button.dataset.comparable === 'true';
    priceDetail.show();
    const anchor = button.getBoundingClientRect();
    const size = priceDetail.getBoundingClientRect();
    const margin = 16;
    const mobile = window.innerWidth <= 650;
    const left = mobile ? (window.innerWidth - size.width) / 2 : Math.max(margin, Math.min(anchor.right - size.width, window.innerWidth - size.width - margin));
    let top = mobile ? window.innerHeight - size.height - margin : anchor.bottom + 10;
    if (!mobile && top + size.height > window.innerHeight - margin) top = anchor.top - size.height - 10;
    priceDetail.style.left = left + 'px';
    priceDetail.style.top = Math.max(margin, top) + 'px';
    priceDetail.querySelector('button').focus({{preventScroll:true}});
  }});
}});
priceDetail.querySelector('button').addEventListener('click', function() {{ closePriceDetail(true); }});
document.addEventListener('keydown', function(event) {{
  if (event.key === 'Escape' && activePrice) {{ event.preventDefault(); closePriceDetail(true); }}
}});
document.addEventListener('pointerdown', function(event) {{
  if (activePrice && !priceDetail.contains(event.target) && !event.target.closest('.price-button')) closePriceDetail();
}});
window.addEventListener('resize', function() {{ closePriceDetail(); }});
document.addEventListener('scroll', function(event) {{
  if (activePrice && !priceDetail.contains(event.target)) closePriceDetail();
}}, true);
document.querySelectorAll('.zone-chip').forEach(function(button) {{
  button.addEventListener('click', function() {{
    closePriceDetail();
    document.querySelectorAll('.zone-chip').forEach(function(other) {{ other.setAttribute('aria-pressed', String(other === button)); }});
    document.querySelectorAll('[data-zoneblock]').forEach(function(section) {{ section.hidden = section.dataset.zoneblock !== button.dataset.zone; }});
  }});
}});
// Open the methodology when reached through its in-page link.
document.querySelectorAll('a[href="#metodologia"]').forEach(function(link) {{
  link.addEventListener('click', function() {{ document.getElementById('metodologia').open = true; }});
}});
if (location.hash === '#metodologia' || location.hash === '#pronostico') {{ document.querySelector(location.hash).open = true; }}
</script></body></html>'''


def main():
    sys.path.insert(0, str(ROOT))
    from etl.canasta import CANASTA
    data = json.loads((ROOT / 'data/latest.json').read_text(encoding='utf-8'))
    page = build_page(data, read_optional(ROOT / 'data/backtest.json'),
                      read_optional(ROOT / 'forecast/eval_results.json'),
                      {item['id']: item for item in CANASTA})
    for path in (ROOT / 'web/index.html', ROOT / 'index.html', ROOT / 'docs/index.html'):
        path.write_text(page, encoding='utf-8')
        print(f'Wrote {path} ({len(page)} characters)')


if __name__ == '__main__':
    main()
