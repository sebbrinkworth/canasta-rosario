#!/usr/bin/env python3
import json, pathlib
ROOT = pathlib.Path(__file__).parents[1]
DATA = ROOT / "data" / "latest.json"
OUT = pathlib.Path(__file__).parent / "index.html"

data = json.loads(DATA.read_text(encoding="utf-8"))
date = data["date"]
dt_fmt = f"{date[8:10]}/{date[5:7]}/{date[0:4]}"
branches = data["branches_count"]
chains = data["chains"]
hero = data["hero"]
table = data["table"]

# hero sorted cheapest first already
cheapest = hero[0]
most_exp = hero[-1]
ahorro = most_exp["total"] - cheapest["total"]
ahorro_pct = round(ahorro / most_exp["total"] * 100) if most_exp["total"] else 0

def fmt_money(v):
    return f"${v:,.0f}".replace(",",".").replace(".",".",1)  # simple
    # use arg format
def fmt(v):
    s = f"{v:,.2f}"
    # replace comma thousand with dot, dot decimal with comma? Keep simple
    return "$" + f"{v:,.0f}".replace(",",".")

# Build chains header order as in hero (cheapest first) or as stored
chain_order = [c["id"] for c in chains]
# But hero is cheapest first; keep that for columns? Use hero order for intuitive
hero_order = [h["chain_id"] for h in hero]

# For table, keep chain_order stable
html_chains = "".join(f'<th class="px-2 py-2 text-right text-xs font-semibold text-slate-700 whitespace-nowrap">{next((c["label"] for c in chains if c["id"]==cid), cid)}</th>' for cid in hero_order)

# Table rows grouped by category
from collections import defaultdict
cat_order = ["Lácteos","Panificados","Almacén","Infusiones","Conservas","Carnes","Frescos","Verdulería","Limpieza"]
cat_groups = defaultdict(list)
for row in table:
    cat_groups[row["category"]].append(row)

rows_html=""
for cat in cat_order:
    group = cat_groups.get(cat, [])
    if not group: continue
    rows_html += f'<tr><td colspan="{2+len(hero_order)}" class="bg-slate-100 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-slate-600">{cat}</td></tr>\n'
    for r in group:
        name = r["name"]
        unit = r["unit_display"]
        cheapest_cid = r.get("cheapest_chain")
        rows_html += f'<tr class="border-b border-slate-100 hover:bg-slate-50">'
        rows_html += f'<td class="px-3 py-2 text-sm font-medium text-slate-800 whitespace-nowrap">{name} <span class="text-xs text-slate-500">{unit}</span></td>'
        rows_html += f'<td class="px-2 py-2 text-right text-xs text-slate-500 hidden md:table-cell">{unit}</td>'
        for cid in hero_order:
            p = r["prices"].get(cid)
            if p is None:
                rows_html += f'<td class="px-2 py-2 text-right text-xs text-slate-400">—</td>'
            else:
                is_cheapest = (cid == cheapest_cid)
                cls = "bg-emerald-50 font-semibold text-emerald-700" if is_cheapest else "text-slate-700"
                # show price per unit + small package price
                per = p["price_per_unit"]
                lista = p["price_lista"]
                # format: $1.799 /L (small $1.799)
                # if per_unit differs from lista, show both
                if abs(per - lista) > 0.01 and p["per_unit"] in ("kg","L"):
                    cell = f'<div class="{cls} text-right text-sm px-1 rounded">${per:,.0f}<span class="text-xs font-normal">/{p["per_unit"]}</span></div><div class="text-xs text-slate-400 text-right">${lista:,.0f}</div>'.replace(",",".")
                else:
                    cell = f'<div class="{cls} text-right text-sm px-1 rounded">${lista:,.0f}</div>'.replace(",",".")
                rows_html += f'<td class="px-2 py-1.5 text-right">{cell}</td>'
        rows_html += '</tr>\n'

# Hero cards
hero_cards=""
for i, h in enumerate(hero):
    is_win = i==0
    border = "border-emerald-400 bg-emerald-50" if is_win else "border-slate-200 bg-white"
    hero_cards += f'''
    <div class="rounded-xl border-2 {border} p-4 flex flex-col gap-1 min-w-[160px] flex-1">
      <div class="text-sm font-bold text-slate-800">{h["chain_label"]}</div>
      <div class="text-2xl font-extrabold {"text-emerald-700" if is_win else "text-slate-800"}">${h["total"]:,.0f}</div>
      <div class="text-xs text-slate-500">{h["items_found"]}/25 ítems · $/pack + $/kg</div>
      {f'<span class="mt-1 inline-flex w-fit rounded-full bg-emerald-600 px-2 py-0.5 text-xs font-bold text-white">Más barato</span>' if is_win else ''}
    </div>'''.replace(",",".")

html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Canasta Rosario — 25 alimentos — {dt_fmt}</title>
<script src="https://cdn.tailwindcss.com"></script>
<meta name="description" content="Compará el costo de 25 alimentos en Rosario + Gran Rosario con datos SEPA.">
</head>
<body class="bg-slate-50 text-slate-800 antialiased">
<header class="mx-auto max-w-6xl px-4 pt-6 pb-4">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div>
      <h1 class="text-2xl md:text-3xl font-extrabold tracking-tight text-slate-900">Canasta Rosario <span class="font-normal text-slate-500">— 25 alimentos</span></h1>
      <p class="mt-1 text-sm text-slate-600">Datos SEPA del <strong>{dt_fmt}</strong> · <span class="inline-flex items-center rounded-full bg-slate-900 px-2.5 py-0.5 text-xs font-semibold text-white">Cubre Rosario + Gran Rosario · {branches} sucursales · {len(chains)} cadenas</span></p>
    </div>
    <div class="text-xs text-slate-500">Fuente SEPA CC BY 4.0 · <a class="underline" href="https://datos.produccion.gob.ar/dataset/sepa-precios">datos.produccion.gob.ar</a></div>
  </div>
  <div class="mt-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">Solo grandes cadenas — La Gallega / DAR / Micropack no informan a SEPA (adhesión voluntaria). Metodología y limitaciones al pie.</div>
</header>

<main class="mx-auto max-w-6xl px-4 pb-10">
  <!-- Qué es esto -->
  <section class="mt-4 rounded-xl border border-slate-200 bg-white p-5 md:p-6 shadow-sm">
    <h2 class="text-base md:text-lg font-extrabold text-slate-900">¿Qué es esto?</h2>
    <p class="mt-2 text-sm md:text-[15px] leading-relaxed text-slate-700">En Rosario el mismo paquete de yerba, aceite o leche puede salir muy distinto según dónde compres. <strong>Canasta Rosario</strong> compara <strong>todos los días una canasta fija de 25 alimentos y limpieza</strong> en 5 cadenas de Rosario y Gran Rosario, para que en 10 segundos sepas <strong>dónde conviene comprar hoy</strong> y cuánto te ahorrás. Sin login, sin app, sin vueltas: una sola página, precios por paquete y por kilo/litro.</p>
    <div class="mt-4 grid gap-3 md:grid-cols-3">
      <div class="rounded-lg bg-slate-50 border border-slate-200 p-3">
        <div class="text-xs font-bold uppercase tracking-wide text-slate-600">Cómo leerlo</div>
        <p class="mt-1 text-xs md:text-[13px] text-slate-700 leading-relaxed">Arriba ves el <strong>total de la canasta por cadena</strong>, del más barato al más caro. En verde el ganador. Abajo, la tabla: cada fila es un producto, cada celda su precio. <strong>Verde = más barato</strong> en $/kg-L. <strong>“—” = no informado</strong> ese día por esa cadena (no inventamos precios).</p>
      </div>
      <div class="rounded-lg bg-slate-50 border border-slate-200 p-3">
        <div class="text-xs font-bold uppercase tracking-wide text-slate-600">De dónde salen los datos</div>
        <p class="mt-1 text-xs md:text-[13px] text-slate-700 leading-relaxed">Fuente oficial <strong>SEPA (Precios Claros)</strong>, Secretaría de Comercio — lo que las grandes cadenas están obligadas a informar a diario. Licencia CC BY 4.0. Cobertura: <strong>{branches} sucursales</strong> en Rosario + Gran Rosario. No incluye La Gallega / DAR / Micropack porque no informan a SEPA (adhesión voluntaria). Sin promos bancarias en v1.</p>
      </div>
      <div class="rounded-lg bg-emerald-50 border border-emerald-200 p-3">
        <div class="text-xs font-bold uppercase tracking-wide text-emerald-800">Qué estamos probando</div>
        <p class="mt-1 text-xs md:text-[13px] text-slate-700 leading-relaxed">Además de mostrar hoy, probamos si se puede <strong>anticipar el precio de mañana</strong> con <a class="underline font-semibold" href="forecast_synthetic.html">TimesFM 3 de Google</a>. Usamos como pistas (<em>covariables</em>): <strong>dólar blue / MEP / oficial, brecha % y volatilidad 7 días</strong> (dolarapi.com), <strong>IPIM mayorista</strong> (INDEC, interpolado diario) y <strong>precio mínimo de la competencia</strong>. En sintético, sumarlas bajó el error de $150 a $142 (-5.5%, Almacén -12%). Cuando haya 30 días reales, el mismo test corre sin sintéticos.</p>
      </div>
    </div>
  </section>
  <!-- Hero -->
  <section>
    <h2 class="text-sm font-bold uppercase tracking-wide text-slate-600 mb-3">Costo total canasta HOY por cadena — más barato primero</h2>
    <div class="flex flex-wrap gap-3">
      {hero_cards}
    </div>
    <p class="mt-3 text-sm text-slate-600">Ahorro máximo: <strong class="text-emerald-700">${ahorro:,.0f} ({ahorro_pct}%)</strong> entre {cheapest["chain_label"]} y {most_exp["chain_label"]}. Precios por paquete y $/kg-L donde aplica.</p>
  </section>

  <!-- Controls (no-JS visible) -->
  <section class="mt-6 flex flex-wrap gap-2 items-center text-xs">
    <span class="text-slate-500">Vista:</span>
    <span class="rounded-full border border-slate-300 bg-white px-3 py-1 font-medium">Precio por paquete + $/kg-L</span>
    <span class="text-slate-400">· En móvil deslizá la tabla →</span>
  </section>

  <!-- Table -->
  <section class="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
    <table class="w-full min-w-[720px] text-sm">
      <thead class="bg-slate-50 border-b border-slate-200">
        <tr>
          <th class="px-3 py-2 text-left text-xs font-semibold text-slate-600">Producto</th>
          <th class="px-2 py-2 text-right text-xs font-semibold text-slate-600 hidden md:table-cell">Unidad</th>
          {html_chains}
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </section>
  <p class="mt-2 text-xs text-slate-500">Verde = más barato por $/kg-L (o paquete si unidad no normalizada). “—” = No informado ese día.</p>

  <!-- Footer metodología -->
  <footer class="mt-10 rounded-xl bg-white border border-slate-200 p-6 text-sm leading-relaxed text-slate-700">
    <h3 class="font-bold text-slate-900">Metodología</h3>
    <ul class="mt-2 list-disc pl-5 space-y-1 text-xs md:text-sm">
      <li><strong>Fuente:</strong> SEPA — Sistema Electrónico de Publicidad de Precios Argentinos, <a class="underline" href="https://datos.produccion.gob.ar/dataset/sepa-precios">datos.produccion.gob.ar</a>, licencia CC BY 4.0. Datos del {dt_fmt}.</li>
      <li><strong>Cobertura:</strong> {branches} sucursales en bbox Rosario + Gran Rosario (lat -33.1 / -32.7, lon -61.0 / -60.4). Cadenas: {", ".join(c["label"] for c in chains)}. <strong>No incluye</strong> La Gallega, DAR, Micropack — no reportan a SEPA (ver validación).</li>
      <li><strong>Canasta:</strong> 25 ítems (alimentos + limpieza) basada en CBA INDEC. Matching por keywords con filtro negativo + precio de referencia SEPA ($/kg-L). “No informado” si no hay match.</li>
      <li><strong>Limitaciones:</strong> matching difuso beta — puede haber falsos positivos en granel/marca blanca. Precio por unidad usa <code>productos_precio_referencia</code> cuando existe. Sin promos bancarias.</li>
      <li><strong>Repro:</strong> <code>uv run python -m etl.etl --date YYYY-MM-DD --gran-rosario</code>. Datos en <code>/data/rosario-YYYY-MM-DD.json</code>.</li>
    </ul>
    <p class="mt-3 text-xs">Roadmap: scraping La Gallega v1.1 · <a class="underline" href="https://github.com/sebbrinkworth/canasta-rosario">GitHub — sebbrinkworth/canasta-rosario</a> · MIT</p>
  </footer>
</main>
</body>
</html>
"""
OUT.write_text(html.replace(",","."), encoding="utf-8")
print(f"Wrote {OUT} ({len(html)} bytes)")
