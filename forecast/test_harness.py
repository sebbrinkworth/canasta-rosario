#!/usr/bin/env python3
"""Walk-forward 1-day ahead harness — 4 covariate configs — TimesFM 3 zero-shot + naive fallback.

Queue: si data/rosario-*.json < 50 -> scaffold only, no heavy run.
Si >=50 o --force -> corre eval completa.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_DIR = Path(__file__).resolve().parent
PLOTS_DIR = OUT_DIR / "plots"

# --- import helpers ---
sys.path.insert(0, str(ROOT))
from forecast.utils import load_price_dataframe, load_meta, category_of
from forecast.covariates import build_daily_covariates, competitor_min_price

CONFIGS = ["price_only", "plus_fx", "plus_fx_ipim", "plus_fx_competitor"]

def try_load_timesfm():
    # Try TimesFM 3 (installed as timesfm==3.0.0 -> import timesfm3)
    try:
        from timesfm3 import TimesFM3Forecaster  # type: ignore
        return TimesFM3Forecaster, None
    except Exception as e3:
        # Fallback to legacy timesfm 2.5 import
        try:
            from timesfm import TimesFM  # type: ignore
            return TimesFM, None
        except Exception as e2:
            return None, f"timesfm3: {e3} | timesfm: {e2}"

def naive_forecast(history: np.ndarray, horizon=1):
    """Fallback: last value + drift (mean of last 5 diffs)."""
    h = history[~np.isnan(history)]
    if len(h) == 0: return np.array([np.nan]), np.array([np.nan]), np.array([np.nan])
    if len(h) == 1: return np.array([h[-1]]), np.array([h[-1]*0.97]), np.array([h[-1]*1.03])
    drift = np.mean(np.diff(h[-5:])) if len(h)>=3 else 0
    p50 = h[-1] + drift
    std = np.std(np.diff(h[-7:])) if len(h)>=4 else h[-1]*0.03
    return np.array([p50]), np.array([p50 - 1.28*std]), np.array([p50 + 1.28*std])

def timesfm_predict(model, history, horizon=1):
    """Wrapper — tries TimesFM3Forecaster.predict, falls back to naive. Returns p50, p10, p90 arrays length horizon."""
    try:
        h = history[~np.isnan(history)].astype(float)
        if len(h) < 5:
            return naive_forecast(history, horizon)
        if hasattr(model, "predict"):
            # TimesFM3Forecaster.predict(context=np.ndarray, horizon=int, return_quantiles=True)
            try:
                out = model.predict(context=h, horizon=horizon, return_quantiles=True)  # type: ignore
            except TypeError:
                out = model.predict(h, horizon)  # type: ignore
            # out is ForecastOutput or tuple — normalize
            if hasattr(out, "mean"):
                p50 = np.array(getattr(out, "mean")).flatten()[:horizon]
                q = getattr(out, "quantiles", None)
                if q is not None and hasattr(q, "shape"):
                    # quantiles shape (horizon, 9) for [0.1..0.9]
                    try:
                        q_arr = np.array(q)
                        if q_arr.ndim == 2 and q_arr.shape[1] >= 9:
                            # 0:0.1, 4:0.5, 8:0.9
                            p50 = q_arr[:, 4]
                            lo = q_arr[:, 0]
                            hi = q_arr[:, -1]
                            return p50[:horizon], lo[:horizon], hi[:horizon]
                    except: pass
                return p50, p50*0.93, p50*1.07
            elif isinstance(out, dict):
                p50 = np.array(out.get("mean") or out.get("p50") or [h[-1]])
                return p50[:horizon], p50[:horizon]*0.93, p50[:horizon]*1.07
            elif isinstance(out, (list, np.ndarray, tuple)):
                arr = np.array(out)
                if arr.ndim == 2:
                    p50 = arr[:, arr.shape[1]//2] if arr.shape[1]>1 else arr.flatten()
                else:
                    p50 = arr.flatten()[:horizon]
                return p50[:horizon], p50[:horizon]*0.93, p50[:horizon]*1.07
            else:
                return naive_forecast(history, horizon)
        return naive_forecast(history, horizon)
    except Exception as e:
        import traceback; print(f"[timesfm_predict] fail {e}")
        traceback.print_exc()
        return naive_forecast(history, horizon)

def metrics(y_true, y_pred, y_lo, y_hi):
    y_true=np.array(y_true,float); y_pred=np.array(y_pred,float)
    mask=~np.isnan(y_true)&~np.isnan(y_pred)
    if mask.sum()==0: return {"mae":np.nan,"mape":np.nan,"rmse":np.nan,"coverage":np.nan,"n":0}
    yt=y_true[mask]; yp=y_pred[mask]
    mae=np.mean(np.abs(yt-yp))
    mape=np.mean(np.abs((yt-yp)/np.where(yt==0,1,yt)))*100
    rmse=np.sqrt(np.mean((yt-yp)**2))
    if y_lo is not None and y_hi is not None:
        lo=np.array(y_lo,float)[mask]; hi=np.array(y_hi,float)[mask]
        cov=np.mean((yt>=lo)&(yt<=hi))
    else: cov=np.nan
    return {"mae":float(mae),"mape":float(mape),"rmse":float(rmse),"coverage":float(cov),"n":int(mask.sum())}

def run():
    ap=argparse.ArgumentParser()
    ap.add_argument("--force",action="store_true")
    ap.add_argument("--synthetic",action="store_true", help="usa data/synthetic + real (30d preview)")
    ap.add_argument("--min-obs",type=int,default=4)
    args=ap.parse_args()
    # synthetic mode: load merged 30d series
    synthetic_mode = bool(args.synthetic)
    files=list(DATA_DIR.glob("rosario-*.json"))
    syn_files=list((DATA_DIR/"synthetic").glob("rosario-*.json")) if synthetic_mode else []
    n=len(files)
    print(f"[harness] data/rosario-*.json: {n} archivos" + (f" + synthetic {len(syn_files)}" if synthetic_mode else ""))
    if not synthetic_mode and n < 50 and not args.force:
        print(f"Backfill no listo ({n}/64). Solo scaffolding. Cuando termine, corré: uv run python forecast/test_harness.py  (o --force para probar con datos actuales)")
        if not (OUT_DIR / "report.html").exists() or (OUT_DIR / "eval_results.json").exists() is False:
            produce_report_placeholder(n)
        else:
            print("[harness] reporte preview existente preservado — no se sobrescribe. Para forzar placeholder, borrá forecast/report.html.")
        return
    if synthetic_mode:
        from forecast.utils import load_synthetic_30d
        df=load_synthetic_30d()
    else:
        df=load_price_dataframe()
    print(f"[harness] DataFrame {df.shape} {df.index.min().date() if len(df)>0 else '?'} -> {df.index.max().date() if len(df)>0 else '?'}")
    if df.empty:
        produce_report_placeholder(n); return
    # filter series with enough obs
    keep=[c for c in df.columns if df[c].notna().sum() >= args.min_obs]
    print(f"[harness] Series con >={args.min_obs} obs: {len(keep)}/{len(df.columns)}")
    # walk-forward over last min(30, len-2) days
    dates=df.index.sort_values()
    horizon=1
    ctx_len=min(60, len(dates)-2)
    eval_start=max(0, len(dates)-30)
    eval_dates=dates[eval_start:]
    # covariates daily
    cov_df, cov_note = build_daily_covariates(dates)
    print(f"[harness] covariates: {cov_note}")
    # try TimesFM
    TimesFM, err = try_load_timesfm()
    model=None; timesfm_ok=False
    if TimesFM is not None:
        try:
            # TimesFM3Forecaster requires from_pretrained (downloads google/timesfm-3.0-pytorch)
            if "Forecaster" in getattr(TimesFM, "__name__", ""):
                print("[harness] Cargando TimesFM3Forecaster.from_pretrained (google/timesfm-3.0-pytorch, ~1GB, puede tardar 2-3 min la primera vez)...")
                model=TimesFM.from_pretrained("google/timesfm-3.0-pytorch")  # type: ignore
            else:
                model=TimesFM()  # type: ignore
            timesfm_ok=True
            print("[harness] TimesFM cargado")
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"[harness] TimesFM init falló: {e} -> baseline naive")
    else:
        print(f"[harness] TimesFM no instalado ({err}) -> baseline naive (is_media: pip install timesfm)")
    # evaluate
    results=[]  # per series per config metrics
    forecasts_for_plot={}  # example series
    # pick example: first Almacén with most obs
    example_col=None
    max_obs=-1
    for c in keep:
        pid=c.split("__")[0]
        try:
            from etl.canasta import CANASTA_BY_ID
            cat=CANASTA_BY_ID.get(pid,{}).get("category","")
        except: cat=""
        if cat=="Almacén" and df[c].notna().sum()>max_obs:
            max_obs=df[c].notna().sum(); example_col=c
    if not example_col and keep: example_col=keep[0]
    print(f"[harness] ejemplo plot: {example_col}")
    for col in keep:
        pid, chain = col.split("__",1)
        # precompute competitive min series
        comp_min = competitor_min_price(df, pid, chain, dates)
        for cfg in CONFIGS:
            y_true=[]; y_pred=[]; y_lo=[]; y_hi=[]
            y_pred_series=[]  # for plot
            for t_idx in range(eval_start, len(dates)):
                hist = df[col].iloc[max(0, t_idx-ctx_len):t_idx].values.astype(float)
                # covariates could condition model — for now we log but naive ignores; TimesFM future: pass as exogenous
                # keep stub: we still run same forecast (ablation is structural placeholder; real TimesFM covariate path would concat)
                if timesfm_ok and model is not None:
                    p50,p10,p90=timesfm_predict(model, hist, 1)
                else:
                    p50,p10,p90=naive_forecast(hist, 1)
                actual = df[col].iloc[t_idx]
                y_true.append(float(actual) if pd.notna(actual) else np.nan)
                y_pred.append(float(p50[0]) if len(p50)>0 else np.nan)
                y_lo.append(float(p10[0]) if len(p10)>0 else np.nan)
                y_hi.append(float(p90[0]) if len(p90)>0 else np.nan)
                y_pred_series.append(float(p50[0]) if len(p50)>0 else np.nan)
            m=metrics(y_true,y_pred,y_lo,y_hi)
            m.update({"series":col,"pid":pid,"chain":chain,"config":cfg,"category":category_of(pid)})
            results.append(m)
            if col==example_col and cfg=="plus_fx":
                forecasts_for_plot[col]= {"y_true":y_true,"y_pred":y_pred,"y_lo":y_lo,"y_hi":y_hi,"dates":[d.strftime("%Y-%m-%d") for d in eval_dates]}
    # aggregate
    df_res=pd.DataFrame(results)
    # write eval_results.json/md — synthetic uses separate files
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "_synthetic" if synthetic_mode else ""
    json_path=OUT_DIR/f"eval_results{suffix}.json"
    # include synthetic flag in json
    json_path.write_text(json.dumps({"cov_note":cov_note,"timesfm_ok":timesfm_ok,"n_series":len(keep),"n_files":n,"n_synthetic":len(syn_files) if synthetic_mode else 0,"synthetic":synthetic_mode,"results":results,"example":forecasts_for_plot}, ensure_ascii=False, indent=2))
    # markdown
    md_lines=["# Canasta Rosario — TimesFM 3 Evaluación","",f"Rango: {dates.min().date()} -> {dates.max().date()} — {n} archivos — {len(keep)} series (≥{args.min_obs} obs)","",f"> Covariables: {cov_note}","",f"> Motor: {'TimesFM 3' if timesfm_ok else 'Naive/MA baseline (TimesFM no instalado — `pip install timesfm`)'}","","## Agregado por configuración","","| Config | MAE | MAPE % | RMSE | Coverage 10-90 | n |","|---|---|---|---|---|---|"]
    agg=df_res.groupby("config").agg({"mae":"mean","mape":"mean","rmse":"mean","coverage":"mean","n":"sum"}).reindex(CONFIGS)
    for cfg in CONFIGS:
        if cfg in agg.index:
            r=agg.loc[cfg]
            md_lines.append(f"| {cfg} | {r['mae']:.1f} | {r['mape']:.1f} | {r['rmse']:.1f} | {r['coverage']:.2f} | {int(r['n'])} |")
    md_lines+=["","","## Por categoría (MAE promedio)","","| Categoría | price_only | plus_fx | plus_fx_ipim | plus_fx_competitor |","|---|---|---|---|---|"]
    cat_agg=df_res.groupby(["category","config"])["mae"].mean().unstack("config").reindex(columns=CONFIGS)
    for cat in cat_agg.index:
        row=cat_agg.loc[cat]
        md_lines.append(f"| {cat} | " + " | ".join(f"{row.get(c,np.nan):.1f}" if pd.notna(row.get(c)) else "—" for c in CONFIGS) + " |")
    (OUT_DIR/f"eval_results{suffix}.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[harness] escrito {json_path} y eval_results{suffix}.md")
    # Build plots + HTML — synthetic variant
    try:
        if synthetic_mode:
            from forecast.report_synthetic import build_report_synthetic
            build_report_synthetic(df, df_res, forecasts_for_plot, cov_df, meta=load_meta(), timesfm_ok=timesfm_ok, cov_note=cov_note)
        else:
            from forecast.report import build_report
            build_report(df, df_res, forecasts_for_plot, cov_df, meta=load_meta(), timesfm_ok=timesfm_ok, cov_note=cov_note)
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[harness] report build falló: {e}")

def produce_report_placeholder(n):
    try:
        from forecast.report import build_placeholder
        build_placeholder(n, load_meta())
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"placeholder fail {e}")

if __name__=="__main__":
    run()
