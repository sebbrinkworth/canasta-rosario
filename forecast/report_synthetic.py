"""report_synthetic — HTML + 4 matplotlib PNGs for synthetic 30d preview."""
from pathlib import Path
import pandas as pd, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
PLOTS_SYN = OUT / "plots_synthetic"
plt.rcParams.update({"figure.dpi":150, "font.size":10, "axes.titlesize":11, "axes.labelsize":9})
CONFIGS = ["price_only","plus_fx","plus_fx_ipim","plus_fx_competitor"]
LABELS = {"price_only":"Solo precio","plus_fx":"+ FX","plus_fx_ipim":"+ FX + IPIM","plus_fx_competitor":"+ FX + competidor"}

def save(fig, path):
    fig.tight_layout(); fig.savefig(path, bbox_inches="tight"); plt.close(fig); return path

def plot_mae(df_res):
    agg=df_res.groupby("config")["mae"].mean().reindex(CONFIGS)
    fig,ax=plt.subplots(figsize=(7,3.2))
    colors=["#6b7280","#2563eb","#059669","#ea580c"]
    vals=[agg.get(c,0) for c in CONFIGS]
    bars=ax.bar([LABELS[c] for c in CONFIGS], vals, color=colors, edgecolor="white")
    ax.set_ylabel("MAE promedio ($)"); ax.set_title("¿Ayudan las covariables?  MAE por configuración (30d sintético)")
    try: ax.bar_label(bars, fmt="%.0f", fontsize=8)
    except: pass
    mx=max([v for v in vals if pd.notna(v)], default=1)
    ax.set_ylim(0, mx*1.25)
    return fig

def plot_winner(df_res):
    piv=df_res.pivot_table(index="series", columns="config", values="mae", aggfunc="mean")
    if "price_only" not in piv.columns or "plus_fx" not in piv.columns:
        fig,ax=plt.subplots(figsize=(7,2)); ax.text(0.5,0.5,"Sin datos",ha="center"); return fig
    piv["delta"]=piv["price_only"]-piv["plus_fx"]
    piv=piv.dropna(subset=["delta"])
    top=piv.sort_values("delta", ascending=False).head(10)
    fig,ax=plt.subplots(figsize=(7,4.2))
    colors=["#059669" if v>0 else "#dc2626" for v in top["delta"]]
    ax.barh(range(len(top)), top["delta"], color=colors)
    ax.set_yticks(range(len(top))); ax.set_yticklabels([s.replace("__"," — ") for s in top.index], fontsize=7)
    ax.set_xlabel("Mejora con FX  (MAE solo precio − MAE +FX) → verde = gana FX")
    ax.set_title("Top 10 productos donde +FX gana (sintético)")
    ax.axvline(0,color="#999",linewidth=0.8)
    return fig

def plot_example(df, forecasts):
    if not forecasts:
        fig,ax=plt.subplots(figsize=(7,2.5)); ax.text(0.5,0.5,"Sin serie ejemplo",ha="center"); return fig
    col=list(forecasts.keys())[0]
    d=forecasts[col]
    dates=pd.to_datetime(d["dates"])
    yt=np.array(d["y_true"],float); yp=np.array(d["y_pred"],float)
    lo=np.array(d["y_lo"],float); hi=np.array(d["y_hi"],float)
    fig,ax=plt.subplots(figsize=(7,3.3))
    ax.plot(dates, yt, label="Real", color="#111827", linewidth=1.8, marker="o", markersize=3)
    ax.plot(dates, yp, label="Pronóstico +FX", color="#2563eb", linewidth=1.4, linestyle="--")
    ax.fill_between(dates, lo, hi, color="#93c5fd", alpha=0.35, label="Banda 10–90%")
    ax.set_ylabel("Precio por unidad ($)"); ax.set_title(f"Aceite girasol-like — {col.replace('__',' — ')}  (30d, nowcast h=1)")
    ax.legend(fontsize=8); ax.tick_params(axis="x", rotation=18)
    return fig

def plot_vol(df):
    from etl.canasta import CANASTA_BY_ID
    fig,ax=plt.subplots(figsize=(7,3.1))
    cats={}
    for c in df.columns:
        cat=CANASTA_BY_ID.get(c.split("__")[0],{}).get("category","Otro")
        cats.setdefault(cat,[]).append(c)
    for cat, cols in sorted(cats.items()):
        s=df[cols].mean(axis=1)
        cv=s.rolling(14,min_periods=7).std()/s.rolling(14,min_periods=7).mean()
        ax.plot(df.index, cv, label=cat, linewidth=1.2)
    ax.set_ylabel("CV 14 días"); ax.set_title("Volatilidad por categoría  (CV móvil 14d — sintético + real)")
    ax.legend(fontsize=7,ncol=3)
    return fig

def build_report_synthetic(df, df_res, forecasts, cov_df, meta, timesfm_ok, cov_note):
    PLOTS_SYN.mkdir(parents=True, exist_ok=True)
    p1=PLOTS_SYN/"01_mae_por_config.png"; p2=PLOTS_SYN/"02_productos_ganadores.png"; p3=PLOTS_SYN/"03_forecast_vs_real.png"; p4=PLOTS_SYN/"04_volatilidad.png"
    save(plot_mae(df_res), p1); save(plot_winner(df_res), p2); save(plot_example(df, forecasts), p3); save(plot_vol(df), p4)
    agg=df_res.groupby("config")["mae"].mean().reindex(CONFIGS)
    chains=", ".join(c.get("label","") for c in meta.get("chains",[]))
    dr=f"{df.index.min().date()} → {df.index.max().date()}" if len(df)>0 else "—"
    banner="Synthetic preview 23 sintéticos + 7 reales (jitter + promo + FX pass-through) — para validar plumbing, no para publicar MAE"
    html=f"""<!doctype html><html lang="es\"><head><meta charset="utf-8\"><meta name="viewport\" content=\"width=device-width,initial-scale=1\"><title>Canasta Rosario — Preview Sintético 30d (TimesFM)</title>
<style>:root{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#111827;background:#f8fafc}}body{{max-width:880px;margin:0 auto;padding:18px}}.card{{background:white;border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin:12px 0}}.badge{{display:inline-block;background:#eff6ff;color:#1d4ed8;border-radius:999px;padding:4px 10px;font-size:12px;margin-right:6px}}h1{{font-size:22px;margin:8px 0}}h2{{font-size:16px;margin:14px 0 6px}}p{{line-height:1.45;font-size:14px;color:#334155}}img{{max-width:100%;border:1px solid #e5e7eb;border-radius:8px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #e5e7eb;padding:6px 8px;text-align:left}}th{{background:#f1f5f9}}.caption{{background:#f8fafc;border-left:3px solid #2563eb;padding:8px 10px;margin:8px 0;font-size:13px}}.banner{{background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:10px;font-size:13px;margin-bottom:12px}}.footer{{font-size:12px;color:#64748b}}</style></head><body>
<div class="banner">⚠️ {banner}<br><b>{dr}</b> · 30 días (sintéticos 2026-08-01..24 + reales 2026-08-25..09-01) · Walk-forward últimos 10 días, contexto 20d, h=1 · El Action diario reemplazará sintéticos por reales (~30 reales hacia fines de sep).</div>
<header class="card"><h1>Canasta Rosario — Preview Sintético 30 días · TimesFM 3</h1>
<p>Rango: <b>{dr}</b> · Reales: 7 · Sintéticos: 23 · Sintéticos en <code>data/synthetic/rosario-*.json</code> (no en <code>data/*.json</code>)</p>
<p><span class="badge">Gran Rosario</span> <span class="badge">Walk-forward h=1</span> <span class="badge">{'TimesFM 3' if timesfm_ok else 'Baseline naive (TimesFM no instalado)'}</span> <span class="badge">{cov_note}</span></p>
<p style="font-size:12px;color:#64748b">Generado {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} — <code>forecast/eval_results_synthetic.json</code> · Cadenas: {chains or '—'}</p>
</header>
<section class="card"><h2>1. ¿Ayudan las covariables? (MAE por config)</h2>
<img src="plots_synthetic/01_mae_por_config.png" alt="MAE por config">
<div class="caption"><b>Qué ves:</b> altura = error promedio MAE ($). Si +FX baja, el dólar ayuda a predecir. <b>Qué significa:</b> en sintético el FX tiene señal leve (30% de series con pass-through). Con reales veremos si confirma.</div>
<table><tr><th>Config</th><th>MAE ($)</th></tr>
{''.join(f"<tr><td>{LABELS.get(c,c)}</td><td>{agg.get(c,float('nan')):.1f}</td></tr>" for c in CONFIGS)}
</table></section>
<section class="card"><h2>2. Top 10 donde +FX gana</h2>
<img src="plots_synthetic/02_productos_ganadores.png" alt="ganadores">
<div class="caption"><b>Qué ves:</b> barra horizontal = MAE solo precio − MAE +FX. Verde = con FX acierta más. <b>Qué significa:</b> almacén/importados suelen ganar con dólar; frescos no. En sintético esto está sembrado (30% correlación FX).</div></section>
<section class="card"><h2>3. Pronóstico vs Real (ejemplo 30d)</h2>
<img src="plots_synthetic/03_forecast_vs_real.png" alt="forecast">
<div class="caption"><b>Qué ves:</b> negro = real, celeste punteada = pronóstico +FX (h=1), banda = 10–90%. <b>Qué significa:</b> ves si el modelo sigue la tendencia y si el real cae dentro de la banda.</div></section>
<section class="card"><h2>4. Volatilidad por categoría (14d)</h2>
<img src="plots_synthetic/04_volatilidad.png" alt="vol">
<div class="caption"><b>Qué ves:</b> CV móvil 14 días por categoría. <b>Qué significa:</b> picos = categorías inestables (verdulería/carnes) donde el pronóstico erra más.</div></section>
<section class="card"><h2>Tabla — MAE por serie (top 25, sintético)</h2>
{df_res.sort_values('mae').head(25).to_html(index=False, float_format=lambda x: f"{x:.1f}")}
</section>
<section class="card footer"><b>Metodología preview:</b> 23 días sintéticos (median + N(0,std*0.35) + 5% promo −8..−15% + trend +0.2%/día + FX pass-through) + 7 reales. Walk-forward nowcast h=1 últimos 10 días, contexto 20d. TimesFM 3 si instalado, si no baseline naive (drift). Covariables: {cov_note}. Re-ejecutar: <code>uv run python forecast/test_harness.py --synthetic --force</code>. Cuando haya ~30 reales, correr sin --synthetic.<br>Repro: <code>PYTHONPATH=. uv run python forecast/synthetic.py</code> regenera sintéticos.</section>
</body></html>"""
    (OUT/"report_synthetic.html").write_text(html, encoding="utf-8")
    # copy to web/
    web = Path(OUT).parent / "web" / "forecast_synthetic.html"
    if web.parent.exists():
        web.write_text(html, encoding="utf-8")
    print(f"[report_synthetic] {OUT/'report_synthetic.html'} + PNGs en {PLOTS_SYN} ; web/forecast_synthetic.html actualizado")
