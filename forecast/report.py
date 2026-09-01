"""report — matplotlib PNGs + report.html (español rioplatense, non-expert)."""
from pathlib import Path
import json, base64
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

OUT = Path(__file__).resolve().parent
PLOTS = OUT / "plots"
plt.rcParams.update({"figure.dpi": 150, "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 9})

CONFIGS = ["price_only","plus_fx","plus_fx_ipim","plus_fx_competitor"]
LABELS = {"price_only":"Solo precio","plus_fx":"+ FX","plus_fx_ipim":"+ FX + IPIM","+FX+competitor":"+ FX + competidor","plus_fx_competitor":"+ FX + competidor"}

def save_b64(fig, path):
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path

def plot_hero_mae(df_res):
    agg=df_res.groupby("config")["mae"].mean().reindex(CONFIGS)
    fig, ax = plt.subplots(figsize=(7, 3.2))
    colors=["#6b7280","#2563eb","#059669","#ea580c"]
    bars=ax.bar([LABELS.get(c,c) for c in CONFIGS], [agg.get(c,0) for c in CONFIGS], color=colors, edgecolor="white")
    ax.set_ylabel("MAE promedio ($)")
    ax.set_title("¿Ayudan las covariables?  Error promedio por configuración")
    ax.bar_label(bars, fmt="%.0f", fontsize=8)
    ax.set_ylim(0, max(agg.values)*1.25 if len(agg.dropna()) else 1)
    fig.tight_layout()
    return fig

def plot_per_product_winner(df_res):
    # delta = mae(price_only) - mae(plus_fx); positivo = gana FX
    piv=df_res.pivot_table(index="series", columns="config", values="mae", aggfunc="mean")
    if "price_only" not in piv.columns or "plus_fx" not in piv.columns:
        fig, ax=plt.subplots(figsize=(7,2)); ax.text(0.5,0.5,"Sin datos suficientes",ha="center"); return fig
    piv["delta"] = piv["price_only"] - piv["plus_fx"]
    piv=piv.dropna(subset=["delta"])
    top=piv.sort_values("delta", ascending=False).head(10)
    bottom=piv.sort_values("delta").head(5)
    # combine for horizontal bar
    show=pd.concat([top, bottom]).sort_values("delta")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    colors=["#059669" if v>0 else "#dc2626" for v in show["delta"]]
    ax.barh(range(len(show)), show["delta"], color=colors)
    ax.set_yticks(range(len(show)))
    ax.set_yticklabels([s.replace("__"," — ") for s in show.index], fontsize=7)
    ax.set_xlabel("Mejora con FX  (MAE solo precio − MAE +FX)  → verde = gana FX")
    ax.set_title("Top productos: dónde ayuda (y dónde no) el dólar")
    ax.axvline(0,color="#999",linewidth=0.8)
    return fig

def plot_forecast_vs_actual(df, forecasts_for_plot):
    if not forecasts_for_plot:
        fig, ax=plt.subplots(figsize=(7,2.5)); ax.text(0.5,0.5,"Sin serie de ejemplo",ha="center"); return fig
    col=list(forecasts_for_plot.keys())[0]
    d=forecasts_for_plot[col]
    dates=pd.to_datetime(d["dates"])
    y_true=np.array(d["y_true"],float); y_pred=np.array(d["y_pred"],float)
    y_lo=np.array(d["y_lo"],float); y_hi=np.array(d["y_hi"],float)
    fig, ax = plt.subplots(figsize=(7, 3.3))
    ax.plot(dates, y_true, label="Real", color="#111827", linewidth=1.8, marker="o", markersize=3)
    ax.plot(dates, y_pred, label="Pronóstico +FX", color="#2563eb", linewidth=1.4, linestyle="--")
    ax.fill_between(dates, y_lo, y_hi, color="#93c5fd", alpha=0.35, label="Banda 10–90%")
    ax.set_ylabel("Precio por unidad ($)")
    ax.set_title(f"Pronóstico vs Real — {col.replace('__',' — ')}  (30 días, nowcast T+1)")
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", rotation=18)
    fig.tight_layout()
    return fig

def plot_volatility(df):
    # rolling 14d CV per category
    from etl.canasta import CANASTA_BY_ID
    fig, ax = plt.subplots(figsize=(7, 3.1))
    cats={}
    for col in df.columns:
        pid=col.split("__")[0]
        cat=CANASTA_BY_ID.get(pid,{}).get("category","Otro")
        cats.setdefault(cat, []).append(col)
    for cat, cols in sorted(cats.items()):
        # mean price per category per day (mean across chains/products)
        s=df[cols].mean(axis=1)
        cv=s.rolling(14, min_periods=7).std()/s.rolling(14, min_periods=7).mean()
        ax.plot(df.index, cv, label=cat, linewidth=1.2)
    ax.set_ylabel("CV 14 días")
    ax.set_title("Volatilidad por categoría  (CV móvil 14d — picos = fresco/verdulería)")
    ax.legend(fontsize=7, ncol=3)
    fig.tight_layout()
    return fig

def build_report(df, df_res, forecasts_for_plot, cov_df, meta, timesfm_ok, cov_note):
    PLOTS.mkdir(parents=True, exist_ok=True)
    # generate PNGs
    p1=PLOTS/"01_mae_por_config.png"
    p2=PLOTS/"02_productos_ganadores.png"
    p3=PLOTS/"03_forecast_vs_real.png"
    p4=PLOTS/"04_volatilidad.png"
    save_b64(plot_hero_mae(df_res), p1)
    save_b64(plot_per_product_winner(df_res), p2)
    save_b64(plot_forecast_vs_actual(df, forecasts_for_plot), p3)
    save_b64(plot_volatility(df), p4)
    # stats for badges
    agg=df_res.groupby("config")["mae"].mean().reindex(CONFIGS)
    # HTML
    chains=", ".join(c.get("label","") for c in meta.get("chains",[]))
    date_range=f"{df.index.min().date()} → {df.index.max().date()}" if len(df)>0 else "—"
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Canasta Rosario — TimesFM 3 Evaluación</title>
<style>
:root{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,sans-serif; color:#111827; background:#f8fafc}}
body{{max-width:880px;margin:0 auto;padding:18px}}
.card{{background:white;border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin:12px 0}}
.badge{{display:inline-block;background:#eff6ff;color:#1d4ed8;border-radius:999px;padding:4px 10px;font-size:12px;margin-right:6px}}
h1{{font-size:22px;margin:8px 0}} h2{{font-size:16px;margin:14px 0 6px}} p{{line-height:1.45;font-size:14px;color:#334155}}
img{{max-width:100%;border:1px solid #e5e7eb;border-radius:8px}} table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{border:1px solid #e5e7eb;padding:6px 8px;text-align:left}} th{{background:#f1f5f9}}
.caption{{background:#f8fafc;border-left:3px solid #2563eb;padding:8px 10px;margin:8px 0;font-size:13px}}
.footer{{font-size:12px;color:#64748b}}
</style></head><body>
<header class="card">
<h1>Canasta Rosario — TimesFM 3 Evaluación</h1>
<p>Rango: <b>{date_range}</b> · Archivos: <b>{meta.get('file_count','?')}</b> · Sucursales: <b>{meta.get('branches_count','?')}</b> · Cadenas: {chains or '—'}</p>
<p><span class="badge">Gran Rosario</span> <span class="badge">Walk-forward 30 días (h=1)</span> <span class="badge">{'TimesFM 3' if timesfm_ok else 'Baseline naive (TimesFM no instalado)'}</span> <span class="badge">{cov_note}</span></p>
<p style="font-size:12px;color:#64748b">Generado {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} — datos: <code>data/rosario-*.json</code> → <code>forecast/eval_results.json</code></p>
</header>
<section class="card">
<h2>1. ¿Ayudan las covariables?</h2>
<img src="plots/01_mae_por_config.png" alt="MAE por configuración">
<div class="caption"><b>Qué ves:</b> barra por configuración (solo precio, +FX, +FX+IPIM, +FX+competidor). Altura = error promedio MAE ($). <b>Qué significa:</b> si la barra baja al agregar FX, el dólar explica parte del movimiento de precios. Si no baja, el precio se mueve por otras razones (ofertas, stock, logística).</div>
<table><tr><th>Config</th><th>MAE ($)</th></tr>
{''.join(f"<tr><td>{LABELS.get(c,c)}</td><td>{agg.get(c, float('nan')):.1f}</td></tr>" for c in CONFIGS)}
</table>
</section>
<section class="card">
<h2>2. ¿En qué productos ayuda el dólar?</h2>
<img src="plots/02_productos_ganadores.png" alt="Productos ganadores">
<div class="caption"><b>Qué ves:</b> diferencia MAE (solo precio − con FX). Verde a la derecha = con FX acierta más; rojo a la izquierda = con FX empeora. <b>Qué significa:</b> no todos los productos miran al dólar — almacén/importados suelen ganar, frescos casi no.</div>
</section>
<section class="card">
<h2>3. Pronóstico vs Real (ejemplo)</h2>
<img src="plots/03_forecast_vs_real.png" alt="Forecast vs real">
<div class="caption"><b>Qué ves:</b> línea negra = precio real, celeste punteada = pronóstico +FX (h=1, nowcast), banda celeste = intervalo 10–90%. <b>Qué significa:</b> ves si el modelo sigue la tendencia y si el real cae dentro de la banda (cobertura).</div>
</section>
<section class="card">
<h2>4. Volatilidad por categoría</h2>
<img src="plots/04_volatilidad.png" alt="Volatilidad">
<div class="caption"><b>Qué ves:</b> coeficiente de variación móvil 14 días por categoría. <b>Qué significa:</b> picos altos = categoría inestable (verdulería, carnes) — ahí el pronóstico siempre va a errar más.</div>
</section>
<section class="card">
<h2>Tabla — MAE por serie (top 25)</h2>
{df_res.sort_values('mae').head(25).to_html(index=False, float_format=lambda x: f"{x:.1f}")}
</section>
<section class="card footer">
<b>Metodología:</b> Walk-forward nowcast h=1 sobre últimos 30 días; contexto 60 días. 4 configs: (1) solo precio, (2) +FX (blue/MEP, brecha, vol7), (3) +FX+IPIM mensual interpolado, (4) +FX+precio mínimo competidor. TimesFM 3 zero-shot con cuantiles 0.1/0.5/0.9; si no está instalado, baseline naive (último valor + drift). Métricas: MAE, MAPE, RMSE, cobertura 10–90%. Datos SEPA lunes/jueves/viernes/sáb/dom (martes/miércoles sin CKAN). Covariables: {cov_note}. Código: <code>forecast/test_harness.py</code> — re-ejecutar: <code>uv run python forecast/test_harness.py</code> (o --force con &lt;50 archivos).
</section>
</body></html>"""
    out_html=OUT/"report.html"
    out_html.write_text(html, encoding="utf-8")
    # also copy to web/forecast.html if web exists
    web_forecast = Path(OUT).parent / "web" / "forecast.html"
    if web_forecast.parent.exists():
        web_forecast.write_text(html, encoding="utf-8")
    print(f"[report] {out_html} + PNGs en {PLOTS}")

def build_placeholder(n, meta):
    PLOTS.mkdir(parents=True, exist_ok=True)
    # minimal placeholder report that explains queue
    date_range = f"{meta.get('latest_date','—')}" if meta else "—"
    chains=", ".join(c.get("label","") for c in (meta.get("chains") or []))
    html=f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Canasta Rosario — TimesFM 3 Evaluación (en cola)</title>
<style>body{{max-width:760px;margin:0 auto;padding:18px;font-family:system-ui,sans-serif;color:#111827}} .card{{background:white;border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin:12px 0}} .badge{{display:inline-block;background:#fef3c7;color:#92400e;border-radius:999px;padding:4px 10px;font-size:12px}}</style></head><body>
<div class="card"><h1>Canasta Rosario — TimesFM 3 Evaluación</h1>
<p><span class="badge">En cola — backfill {n}/64</span></p>
<p>El backfill de 90 días (2026-06-02 → 2026-08-31) está corriendo en paralelo. Este reporte se genera automáticamente cuando haya ≥50 archivos en <code>data/rosario-*.json</code>.</p>
<p>Último dato: <b>{date_range}</b> · Sucursales: <b>{meta.get('branches_count','?') if meta else '?'}</b> · Cadenas: {chains or '—'}</p>
<p>Estado actual: <b>{n} JSONs</b> — faltan ~{max(0,64-n)}. Logs: <code>data/backfill.log</code></p>
<pre style="background:#f8fafc;padding:10px;border-radius:8px;overflow:auto">when backfill done, run:
  uv run python forecast/test_harness.py
  # o forzar con datos actuales:
  uv run python forecast/test_harness.py --force
  # ver reporte:
  python -m http.server --directory forecast 8000
  # → http://localhost:8000/report.html</pre>
<p style="font-size:13px;color:#64748b">Scaffold listo: <code>forecast/test_harness.py</code>, <code>forecast/utils.py</code>, <code>forecast/covariates.py</code>, <code>forecast/report.py</code></p>
</div></body></html>"""
    (OUT/"report.html").write_text(html, encoding="utf-8")
    print(f"[report] placeholder en cola ({n}/64) → forecast/report.html")
