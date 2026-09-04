#!/usr/bin/env python3
import json, pathlib
ROOT = pathlib.Path(__file__).parents[1]
DATA = ROOT / "data" / "latest.json"
OUT = pathlib.Path(__file__).parent / "index.html"

data = json.loads(DATA.read_text(encoding="utf-8"))
# Pronóstico experimental T+1 (tendencia 7d, generado por forecast/; si falta, sin flechas)
FORECAST_PATH = ROOT / "data" / "forecast-next.json"
try:
    _fc = json.loads(FORECAST_PATH.read_text(encoding="utf-8"))
    FORECAST = _fc.get("items", {})
    FORECAST_NOTE = _fc.get("note", "")
except Exception:
    FORECAST = {}
    FORECAST_NOTE = ""
# Backtest real (cuántas pegamos) — si falta, se omite la sección
BT_PATH = ROOT / "data" / "backtest.json"
try:
    BT = json.loads(BT_PATH.read_text(encoding="utf-8"))
except Exception:
    BT = {}
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

def fmt_ar(v):
    """$69.601 formato argentino, solo para números (nunca sobre HTML/JS)."""
    return f"${v:,.0f}".replace(",", ".")

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

MOVE_PREC_GATE = 25.0  # % precision de la clase sube/baja bajo el cual no mostramos flechas ↑↓ (solo →)


def _move_precision():
    """Measured move precision from data/backtest.json. Returns (daily_sube, daily_baja, weekly_sube, weekly_baja).
    Daily if present, else weekly if present, else (None...) — gating uses whatever the method actually measured."""
    try:
        ev = (BT or {}).get("event_precision") or {}
        wk = (BT or {}).get("weekly") or {}
        ds = (ev.get("daily") or {}).get("sube") or {}
        db = (ev.get("daily") or {}).get("baja") or {}
        ws = (wk.get("classes") or {}).get("sube") or {}
        wb = (wk.get("classes") or {}).get("baja") or {}
        return ds.get("precision"), db.get("precision"), ws.get("precision"), wb.get("precision")
    except Exception:
        return None, None, None, None


def forecast_badge(pid, cid):
    """Flechita ↑↓→ tocable: badge con cursor pointer + tooltip en hover (desktop) y tap (móvil).
    Gate: las flechas ↑↓ solo se muestran si la precisión medida de la clase (backtest real)
    supera MOVE_PREC_GATE; si no, renderizamos la flecha gris → con leyenda honesta en el tooltip."""
    f = FORECAST.get(f"{pid}__{cid}")
    if not f:
        return ""
    d = f.get("dir", "estable")
    delta = f.get("delta_pct", 0)
    conf = f.get("conf", "media")
    ds, db, ws, wb = _move_precision()
    if d == "sube":
        prec = ds if ds is not None else ws
        show_arrow = prec is not None and prec >= MOVE_PREC_GATE
        if show_arrow:
            arrow, cls2, label = "↑", "fc-up", f"Se espera que suba {delta:+.1f}% · confianza {conf}"
        else:
            arrow, cls2, label = "→", "fc-flat", f"Sin flecha ↑: esta clase hoy acierta {prec}% (umbral {MOVE_PREC_GATE:.0f}%) — no podemos anticipar subas todavía, mostramos →"
    elif d == "baja":
        prec = db if db is not None else wb
        show_arrow = prec is not None and prec >= MOVE_PREC_GATE
        if show_arrow:
            arrow, cls2, label = "↓", "fc-down", f"Se espera que baje {delta:+.1f}% · confianza {conf}"
        else:
            arrow, cls2, label = "→", "fc-flat", f"Sin flecha ↓: esta clase hoy acierta {prec}% (umbral {MOVE_PREC_GATE:.0f}%) — no podemos anticipar bajas todavía, mostramos →"
    else:
        arrow, cls2, label = "→", "fc-flat", f"Estable ({delta:+.1f}%) · confianza {conf}"
    tip = f"{label}. Pronóstico experimental 24-48h, no es recomendación de compra. Tocá de nuevo para cerrar."
    return f'<button type="button" class="fc-badge {cls2}" data-tip="{tip}" aria-label="{label}">{arrow}</button>'

def render_rows(table_data, chain_ids):
    cat_groups = defaultdict(list)
    for row in table_data:
        cat_groups[row["category"]].append(row)
    out = ""
    for cat in cat_order:
        group = cat_groups.get(cat, [])
        if not group: continue
        out += f'<tr><td colspan="{2+len(chain_ids)}" class="bg-slate-100 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-slate-600">{cat}</td></tr>\n'
        for r in group:
            name = r["name"]
            unit = r["unit_display"]
            cheapest_cid = r.get("cheapest_chain")
            out += f'<tr class="border-b border-slate-100 hover:bg-slate-50">'
            out += f'<td class="px-3 py-2 text-sm font-medium text-slate-800 whitespace-nowrap">{name} <span class="text-xs text-slate-500">{unit}</span></td>'
            out += f'<td class="px-2 py-2 text-right text-xs text-slate-500 hidden md:table-cell">{unit}</td>'
            for cid in chain_ids:
                p = r["prices"].get(cid)
                if p is None:
                    out += f'<td class="px-2 py-2 text-right text-xs text-slate-400">—</td>'
                else:
                    is_cheapest = (cid == cheapest_cid)
                    cls = "bg-emerald-50 font-semibold text-emerald-700" if is_cheapest else "text-slate-700"
                    per = p["price_per_unit"]
                    lista = p["price_lista"]
                    badge = forecast_badge(r["id"], cid)
                    if abs(per - lista) > 0.01 and p["per_unit"] in ("kg","L"):
                        cell = f'<div class="{cls} text-right text-sm px-1 rounded">{fmt_ar(per)}<span class="text-xs font-normal">/{p["per_unit"]}</span>{badge}</div><div class="text-xs text-slate-400 text-right">{fmt_ar(lista)}</div>'
                    else:
                        cell = f'<div class="{cls} text-right text-sm px-1 rounded">{fmt_ar(lista)}{badge}</div>'
                    out += f'<td class="px-2 py-1.5 text-right">{cell}</td>'
            out += '</tr>\n'
    return out

def render_hero(hero_list):
    cards = ""
    for i, h in enumerate(hero_list):
        is_win = i==0
        border = "border-emerald-400 bg-emerald-50" if is_win else "border-slate-200 bg-white"
        cards += f'''
        <div class="rounded-xl border-2 {border} p-4 flex flex-col gap-1 min-w-[160px] flex-1">
          <div class="text-sm font-bold text-slate-800">{h["chain_label"]}</div>
          <div class="text-2xl font-extrabold {"text-emerald-700" if is_win else "text-slate-800"}">{fmt_ar(h["total"])}</div>
          <div class="text-xs text-slate-500">{h["items_found"]}/25 ítems · $/pack + $/kg</div>
          {f'<span class="mt-1 inline-flex w-fit rounded-full bg-emerald-600 px-2 py-0.5 text-xs font-bold text-white">Más barato</span>' if is_win else ''}
        </div>'''
    return cards

# Zonas: todo (combinado) + rosario + gran. Fallback a combinado si falta.
zones_data = data.get("zones") or {}
ZDESC = {
    "todo": ("Todo: Rosario + alrededores", f"{branches} sucursales"),
    "rosario": ("Solo Rosario", f"{(zones_data.get('rosario') or {}).get('branches_count', '?')} sucursales"),
    "gran": ("Alrededores (Funes, Fisherton…)", f"{(zones_data.get('gran') or {}).get('branches_count', '?')} sucursales"),
}
zone_blocks = {}
for zkey in ("todo", "rosario", "gran"):
    if zkey == "todo":
        z_hero, z_table = hero, table
        z_chains, z_order = chains, hero_order
    else:
        zd = zones_data.get(zkey) or {}
        if not zd.get("hero"):
            continue
        z_hero, z_table = zd["hero"], zd["table"]
        z_chains = zd.get("chains", chains)
        z_order = [h["chain_id"] for h in z_hero]
    z_cheapest = z_hero[0] if z_hero else None
    z_exp = z_hero[-1] if z_hero else None
    if z_cheapest and z_exp and z_exp["total"]:
        z_ah = z_exp["total"] - z_cheapest["total"]
        z_ahp = round(z_ah / z_exp["total"] * 100)
    else:
        z_ah, z_ahp = 0, 0
    z_heads = "".join(f'<th class="px-2 py-2 text-right text-xs font-semibold text-slate-700 whitespace-nowrap">{next((c["label"] for c in z_chains if c["id"]==cid), cid)}</th>' for cid in z_order)
    zone_blocks[zkey] = {
        "title": ZDESC[zkey][0], "sub": ZDESC[zkey][1],
        "hero": render_hero(z_hero),
        "heads": z_heads,
        "rows": render_rows(z_table, z_order),
        "foot": f'Ahorro máximo: <strong class="text-emerald-700">{fmt_ar(z_ah)} ({z_ahp}%)</strong> entre {z_cheapest["chain_label"]} y {z_exp["chain_label"]}.' if z_cheapest and z_exp else "",
    }
zone_blocks["todo"]["title"] = f"Todo: Rosario + alrededores"
zone_sections = ""
for zkey in ("todo", "rosario", "gran"):
    zb = zone_blocks.get(zkey)
    if not zb:
        continue
    hidden = "" if zkey == "todo" else ' hidden'
    zone_sections += f"""
  <div data-zoneblock="{zkey}"{hidden}>
  <section class="mt-4">
    <h2 class="text-sm font-bold uppercase tracking-wide text-slate-600 mb-1">Costo total canasta HOY por cadena — {zb['title']}</h2>
    <p class="text-xs text-slate-500 mb-3">{zb['sub']}</p>
    <div class="flex flex-wrap gap-3">
      {zb['hero']}
    </div>
    <p class="mt-3 text-sm text-slate-600">{zb['foot']} Precios por paquete y $/kg-L donde aplica.</p>
  </section>
  <section class="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
    <table class="w-full min-w-[720px] text-sm">
      <thead class="bg-slate-50 border-b border-slate-200">
        <tr>
          <th class="px-3 py-2 text-left text-xs font-semibold text-slate-600">Producto</th>
          <th class="px-2 py-2 text-right text-xs font-semibold text-slate-600 hidden md:table-cell">Unidad</th>
          {zb['heads']}
        </tr>
      </thead>
      <tbody>
        {zb['rows']}
      </tbody>
    </table>
  </section>
  </div>"""

# Precisión del pronóstico (backtest real) — honesto: separa estables de movimientos
if BT and BT.get("n"):
    mp = BT.get("moves_prec", {})
    sube = mp.get("sube", {"n":0,"hits":0,"precision":0})
    baja = mp.get("baja", {"n":0,"hits":0,"precision":0})
    est = mp.get("estable", {"n":0,"hits":0,"precision":0})
    mov_n = sube["n"] + baja["n"]
    mov_h = sube["hits"] + baja["hits"]
    mov_p = round(mov_h / mov_n * 100, 1) if mov_n else 0
    # event layer: precision/recall por clase (daily + weekly)
    ev = BT.get("event_precision") or {}
    wk = BT.get("weekly") or {}
    def _s(d, k): return (d.get(k) or {}) if isinstance(d, dict) else {}
    ev_d = _s(ev, "daily"); ev_w = _s(wk, "classes")
    ev_sube = _s(ev_d, "sube"); ev_baja = _s(ev_d, "baja"); ev_est = _s(ev_d, "estable")
    wk_sube = _s(ev_w, "sube"); wk_baja = _s(ev_w, "baja")
    ev_sube_p = ev_sube.get("precision", 0); ev_sube_r = ev_sube.get("recall", 0)
    ev_baja_p = ev_baja.get("precision", 0); ev_baja_r = ev_baja.get("recall", 0)
    wk_sube_p = wk_sube.get("precision", 0); wk_baja_p = wk_baja.get("precision", 0)
    cat_rows = "".join(
        f'<tr class="border-b border-slate-100"><td class="px-2 py-1">{k}</td>'
        f'<td class="px-2 py-1 text-right">{v["hit_rate"]}%</td>'
        f'<td class="px-2 py-1 text-right text-slate-400">{v["n"]}</td></tr>'
        for k, v in (BT.get("by_category") or {}).items()
    )
    precision_html = f"""
  <section class="mt-6 rounded-xl border-2 border-slate-800 bg-white p-5 md:p-6 shadow-sm">
    <h3 class="text-base md:text-lg font-extrabold text-slate-900">¿Cuántas pegamos? <span class="text-sm font-normal text-slate-500">— medido con datos reales, no con sintéticos</span></h3>
    <p class="mt-2 text-sm md:text-[15px] leading-relaxed text-slate-700">La flecha <strong>↑/↓</strong> (mover el precio) es la parte difícil: hoy acierta <strong class="text-amber-700">{mov_p}%</strong> ({mov_h}/{mov_n}). Cuando dice <strong>→</strong> (“no cambia”) acierta <strong>{est['precision']}%</strong> ({est['hits']}/{est['n']}). Por eso, hasta que la precisión de movimiento pase el umbral (<strong>{MOVE_PREC_GATE:.0f}%</strong>), el sitio muestra solo la flecha gris → aunque el modelo interno crea que va a subir o bajar.</p>
    <p class="mt-2 rounded-lg bg-slate-50 border border-slate-200 px-3 py-2 text-xs md:text-[13px] text-slate-600">🚫 <strong>Cero datos sintéticos:</strong> todo lo que ves (precios, pronósticos y este marcador) se calcula <strong>solo con precios reales de SEPA</strong>. Empezamos a recolectar el 26/08/2026, así que la historia es corta: con pocos días la precisión es limitada, y <strong>mejora automáticamente cada día</strong> que el recolector agrega datos reales.</p>
    <div class="mt-3 grid gap-3 md:grid-cols-2 text-xs md:text-[13px] leading-relaxed">
      <div class="rounded-lg bg-emerald-50 border border-emerald-200 p-3"><strong>Lo fácil: decir “mañana no cambia” →</strong> acierta el <strong>{est['precision']}%</strong> ({est['hits']}/{est['n']}). La mayoría de los días los precios no se mueven, y ahí somos buenos.</div>
      <div class="rounded-lg bg-amber-50 border border-amber-200 p-3"><strong>Lo difícil: anticipar subas y bajas.</strong> Hoy <strong>↑</strong> acierta <strong>{ev_sube_p}%</strong> (recall {ev_sube_r}%), <strong>↓</strong> acierta <strong>{ev_baja_p}%</strong> (recall {ev_baja_r}%). En ventana semanal (7 días): <strong>↑ {wk_sube_p}% · ↓ {wk_baja_p}%</strong>. Tómalas como señal débil — por eso seguimos con el experimento TimesFM + dólar.</div>
    </div>
    <details class="mt-3 text-xs md:text-[13px]"><summary class="cursor-pointer underline text-slate-600\">Ver por categoría</summary>
      <table class="mt-2 w-full max-w-md text-xs"><thead><tr class="text-left text-slate-500\"><th class="px-2 py-1\">Categoría</th><th class="px-2 py-1 text-right\">Acierto</th><th class="px-2 py-1 text-right\">Casos</th></tr></thead><tbody>{cat_rows}</tbody></table>
    </details>
  </section>"""
else:
    precision_html = ""

html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Canasta Rosario — 25 alimentos — {dt_fmt}</title>
<script src="https://cdn.tailwindcss.com"></script>
<meta name="description" content="Compará el costo de 25 alimentos en Rosario + Gran Rosario con datos SEPA.">
<style>
.fc-badge{{cursor:pointer;border:1px dashed #94a3b8;border-radius:9999px;padding:0 6px;margin-left:4px;font-size:11px;font-weight:700;line-height:1.6;position:relative;background:#fff}}
.fc-up{{color:#dc2626;border-color:#fca5a5;background:#fef2f2}}
.fc-down{{color:#047857;border-color:#6ee7b7;background:#ecfdf5}}
.fc-flat{{color:#64748b}}
.fc-badge::after{{content:attr(data-tip);display:none;position:absolute;right:0;top:130%;z-index:30;width:210px;white-space:normal;background:#0f172a;color:#fff;font-size:11px;font-weight:400;border-radius:8px;padding:8px 10px;text-align:left;line-height:1.4;box-shadow:0 4px 14px rgba(0,0,0,.25)}}
.fc-badge:hover::after,.fc-badge.show::after{{display:block}}
.zone-chip{{cursor:pointer}}
.zone-chip[aria-pressed="true"]{{background:#0f172a;color:#fff;border-color:#0f172a}}
</style>
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
        <p class="mt-1 text-xs md:text-[13px] text-slate-700 leading-relaxed">Además de mostrar hoy, probamos si se puede <strong>anticipar el precio de mañana</strong> con <strong>TimesFM 3 de Google</strong>. Las flechas <strong>↑ ↓ →</strong> en cada precio son ese pronóstico, integrado acá mismo (<a class="underline font-semibold" href="#pronostico">ver cómo funciona</a>). Usamos como pistas (<em>covariables</em>): <strong>dólar blue / oficial, brecha % y volatilidad 7 días</strong> (histórico diario real de bluelytics.com.ar), <strong>IPIM mayorista</strong> (INDEC, serie mensual de series-tiempo interpolada a diario) y <strong>precio mínimo de la competencia</strong>. <strong>Solo datos reales</strong> — nada sintético ni simulado. La precisión de los pronósticos <strong>mejora sola con el tiempo</strong> a medida que acumulamos más días de historia real.</p>
      </div>
    </div>
  </section>
  <!-- Filtro de zona -->
  <section class="mt-4 flex flex-wrap gap-2 items-center text-xs" role="group" aria-label="Filtrar por zona">
    <span class="text-slate-500 font-semibold">Zona:</span>
    <button type="button" class="zone-chip rounded-full border border-slate-300 bg-white px-3 py-1 font-medium" data-zone="todo" aria-pressed="true">Todo ({branches})</button>
    <button type="button" class="zone-chip rounded-full border border-slate-300 bg-white px-3 py-1 font-medium" data-zone="rosario" aria-pressed="false">Rosario</button>
    <button type="button" class="zone-chip rounded-full border border-slate-300 bg-white px-3 py-1 font-medium" data-zone="gran" aria-pressed="false">Alrededores</button>
    <span class="text-slate-400">· En móvil deslizá la tabla →</span>
  </section>
  {zone_sections}
  <p class="mt-2 text-xs text-slate-500">Verde = más barato por $/kg-L (o paquete si unidad no normalizada). “—” = No informado ese día. Las flechas son botones: <button type="button" class="fc-badge fc-up" style="cursor:pointer" onclick="return false">↑</button> <button type="button" class="fc-badge fc-down" onclick="return false">↓</button> <button type="button" class="fc-badge fc-flat" onclick="return false">→</button> — <strong>tocá cualquier flecha de la tabla</strong> para ver % esperado y confianza. Pronóstico experimental 24-48h, no es recomendación de compra. <a class="underline" href="#pronostico">Cómo funciona</a>.</p>

  <!-- Precisión: cuántas pegamos -->
  {precision_html}
  <!-- Pronóstico en esta misma vista -->
  <section id="pronostico" class="mt-6 rounded-xl border border-emerald-200 bg-emerald-50/50 p-5 md:p-6">
    <h3 class="text-base font-extrabold text-slate-900">Pronóstico en esta misma vista — qué significan las flechas</h3>
    <p class="mt-2 text-sm leading-relaxed text-slate-700">Cada precio lleva una flecha con lo que el modelo espera para las próximas 24-48h. Hoy es <strong>tendencia de 7 días + covariables</strong> (la versión liviana que anda sin GPU). En paralelo corremos el experimento completo con <strong>TimesFM 3</strong> en la RTX 4060 para validar si sumar dólar e IPIM mejora de verdad. <strong>Todo se entrena y evalúa solo con precios reales de SEPA</strong> — no usamos datos sintéticos ni simulados.</p>
    <div class="mt-3 grid gap-3 md:grid-cols-3 text-xs md:text-[13px] leading-relaxed">
      <div class="rounded-lg bg-white border border-slate-200 p-3"><strong>Dólar y brecha</strong><br>blue / oficial (histórico diario real de bluelytics.com.ar), brecha % = (blue-oficial)/oficial y volatilidad 7 días. Es la pista n°1 para aceite, harina, yerba.</div>
      <div class="rounded-lg bg-white border border-slate-200 p-3"><strong>Mayorista y competencia</strong><br>IPIM nivel general (INDEC, serie mensual de series-tiempo interpolada a diario) + precio mínimo de las otras 4 cadenas para el mismo producto. Capta remarcación y undercutting.</div>
      <div class="rounded-lg bg-white border border-slate-200 p-3"><strong>Cómo leer la confianza</strong><br>Pasá el cursor sobre la flecha: muestra % esperado y confianza (alta/media/baja según volatilidad reciente). Con solo 9 días de historia real, la precisión de eventos (↑↓) todavía es baja — <strong>mejora automáticamente a medida que el recolector diario suma datos</strong>. Detalle técnico en <code>forecast/</code> del repo.</div>
    </div>
  </section>

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
<script>
// Filtro de zona: muestra solo el bloque elegido
document.querySelectorAll('.zone-chip').forEach(function(btn){{btn.addEventListener('click',function(){{
  document.querySelectorAll('.zone-chip').forEach(function(b){{b.setAttribute('aria-pressed','false')}});
  btn.setAttribute('aria-pressed','true');
  var z=btn.getAttribute('data-zone');
  document.querySelectorAll('[data-zoneblock]').forEach(function(div){{div.hidden=(div.getAttribute('data-zoneblock')!==z)}});
}})}});
// Flechas tocables: tap muestra el dato, otro tap lo cierra
document.addEventListener('click',function(e){{
  var b=e.target.closest?e.target.closest('.fc-badge[data-tip]'):null;
  document.querySelectorAll('.fc-badge.show').forEach(function(x){{if(x!==b)x.classList.remove('show')}});
  if(b){{b.classList.toggle('show');e.preventDefault()}}
}});
</script>
</body>
</html>
"""
OUT.write_text(html, encoding="utf-8")
print(f"Wrote {OUT} ({len(html)} bytes)")
