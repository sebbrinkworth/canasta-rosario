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
from forecast.utils import load_price_dataframe, load_meta, load_price_observed, category_of
from forecast.covariates import build_daily_covariates, competitor_min_price

CONFIGS = ["price_only", "plus_fx", "plus_fx_ipim", "plus_fx_competitor"]
THRESH = 0.8   # same direction threshold as build_next.py/backtest.py
WEEK_H = 7     # weekly-horizon variant: proper 7-day window [T, T+6], full windows only

# Fallback accounting: every naive_forecast use inside timesfm_predict is
# counted here. run() snapshots deltas per (series, config) so a run labelled
# TimesFM reports exactly how many of its predictions are really baseline.
_FB = {"naive": 0, "cov_dropped": 0}
def _fb_bump(key):
    try:
        _FB[key] += 1
    except Exception:
        pass

def _class_stats(preds, actuals, cls):
    """Precision/recall/F1 for one direction class. preds/actuals: lists of
    direction labels ('sube'|'baja'|'estable')."""
    preds = list(preds)
    actuals = list(actuals)
    tp = sum(1 for p, a in zip(preds, actuals) if p == cls and a == cls)
    fp = sum(1 for p, a in zip(preds, actuals) if p == cls and a != cls)
    fn = sum(1 for p, a in zip(preds, actuals) if p != cls and a == cls)
    n_pred = tp + fp
    n_act = tp + fn
    prec = tp / n_pred * 100 if n_pred else 0.0
    rec = tp / n_act * 100 if n_act else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"n": n_pred, "actual": n_act, "hits": tp, "precision": round(prec, 1),
            "recall": round(rec, 1), "f1": round(f1, 2)}


def direction(delta_pct, thresh=THRESH):
    if abs(delta_pct) < thresh:
        return "estable"
    return "sube" if delta_pct > 0 else "baja"


def event_stats(daily_pred, daily_actual, week_pred, week_actual):
    """Aggregate event layer for one series: dict with per-class daily stats,
    weekly stats, and a required "move_precision" summary key.

    FIX: stats are computed on GLOBAL pred/actual lists (pairs with a None on
    either side are dropped). Grouping by predicted class first hides missed
    events and inflates recall to 100% — never do that."""
    dp = [(p, a) for p, a in zip(daily_pred, daily_actual) if p is not None and a is not None]
    wp = [(p, a) for p, a in zip(week_pred, week_actual) if p is not None and a is not None]
    dp_pred, dp_act = zip(*dp) if dp else ([], [])
    wp_pred, wp_act = zip(*wp) if wp else ([], [])
    daily = {k: _class_stats(list(dp_pred), list(dp_act), k) for k in ("sube", "baja", "estable")}
    weekly = {k: _class_stats(list(wp_pred), list(wp_act), k) for k in ("sube", "baja", "estable")}
    return {
        "threshold_pct": THRESH,
        "daily": daily,
        "weekly": weekly,
        "move_precision": {
            "daily": {"sube": daily["sube"]["precision"], "baja": daily["baja"]["precision"],
                       "n_sube": daily["sube"]["n"], "n_baja": daily["baja"]["n"]},
            "weekly": {"sube": weekly["sube"]["precision"], "baja": weekly["baja"]["precision"],
                        "n_sube": weekly["sube"]["n"], "n_baja": weekly["baja"]["n"]},
        },
    }


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

def _prep_cov_block(arr: np.ndarray) -> np.ndarray | None:
    """Sanitize covariate block: arr shape (n_cov, L). Forward-fill NaNs, clip extreme, return float32."""
    if arr is None or arr.size == 0:
        return None
    a = np.array(arr, dtype=float)
    if a.ndim == 1:
        a = a[None, :]
    # forward-fill per row then fill remaining with row mean / 0
    for r in range(a.shape[0]):
        s = pd.Series(a[r]).ffill().bfill()
        # clip absurd
        s = s.replace([np.inf, -np.inf], np.nan).fillna(0)
        a[r] = s.values
        # clip to ±5 sigma-ish (keep in range)
        a[r] = np.clip(a[r], -1e6, 1e6)
    # if still any NaN, zero
    a = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    return a

def timesfm_predict(model, history, horizon=1, past_only_covariates=None):
    """Wrapper — tries TimesFM3Forecaster.predict, falls back to naive.
    Returns (p50, p10, p90, info) with info in:
      model | model_no_cov (TypeError path dropped covariates) |
      naive_short (history < 5) | naive_fail (exception).
    Callers MUST aggregate info to report fallback counts — a run labelled
    TimesFM must never silently contain baseline predictions."""
    try:
        h_full = np.array(history, dtype=float)
        h = h_full[~np.isnan(h_full)].astype(float)
        if len(h) < 5:
            _fb_bump("naive")
            return naive_forecast(history, horizon)
        if hasattr(model, "predict"):
            po = _prep_cov_block(past_only_covariates) if past_only_covariates is not None else None
            # When covariates present, pass full history (with NaNs) so context length matches covariate length
            # TimesFM interpolates NaNs internally via linear_interpolation. Without covariates, use compacted h for speed.
            ctx = h_full if po is not None else h
            # Compact po to match non-NaN positions if ctx is compacted — but we pass full, so keep po as-is.
            # If h has leading NaNs, model trims them and trims covariates correspondingly.
            try:
                if po is not None:
                    out = model.predict(context=ctx, horizon=horizon, past_only_covariates=po, return_quantiles=True)  # type: ignore
                else:
                    out = model.predict(context=h, horizon=horizon, return_quantiles=True)  # type: ignore
            except TypeError:
                # Model API rejected covariates: count it — the prediction
                # below runs WITHOUT covariates and must be labelled as such.
                _fb_bump("cov_dropped")
                out = model.predict(h, horizon)  # type: ignore
            # out is ForecastOutput or tuple — normalize
            # TimesFM3 ForecastOutput has .forecast and .quantiles
            if hasattr(out, "forecast"):
                # TimesFM3
                p50 = np.array(getattr(out, "forecast")).flatten()[:horizon] if getattr(out, "forecast") is not None else np.array([h[-1]])
                q = getattr(out, "quantiles", None)
                if q is not None and hasattr(q, "shape") and np.array(q).size > 0:
                    try:
                        q_arr = np.array(q)
                        if q_arr.ndim == 2 and q_arr.shape[1] >= 9:
                            p50 = q_arr[:, 4]
                            lo = q_arr[:, 0]
                            hi = q_arr[:, -1]
                            return p50[:horizon], lo[:horizon], hi[:horizon]
                        elif q_arr.ndim == 1:
                            return p50, p50*0.93, p50*1.07
                    except: pass
                return p50, p50*0.93, p50*1.07
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
                _fb_bump("naive")
                return naive_forecast(history, horizon)
        _fb_bump("naive")
        return naive_forecast(history, horizon)
    except Exception as e:
        import traceback; print(f"[timesfm_predict] fail {e}")
        traceback.print_exc()
        _fb_bump("naive")
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
    ap.add_argument("--skip-timesfm",action="store_true", help="fuerza baseline naive (no carga el modelo; útil en CPU/CI)")
    ap.add_argument("--min-obs",type=int,default=4)
    args=ap.parse_args()
    # datos reales únicamente (preview sintético eliminado 2026-09-04)
    files=list(DATA_DIR.glob("rosario-*.json"))
    n=len(files)
    print(f"[harness] data/rosario-*.json: {n} archivos")
    if n < 50 and not args.force:
        print(f"Backfill no listo ({n}/64). Solo scaffolding. Cuando termine, corré: uv run python forecast/test_harness.py  (o --force para probar con datos actuales)")
        if not (OUT_DIR / "report.html").exists() or (OUT_DIR / "eval_results.json").exists() is False:
            produce_report_placeholder(n)
        else:
            print("[harness] reporte preview existente preservado — no se sobrescribe. Para forzar placeholder, borrá forecast/report.html.")
        return
    df=load_price_dataframe()
    print(f"[harness] DataFrame {df.shape} {df.index.min().date() if len(df)>0 else '?'} -> {df.index.max().date() if len(df)>0 else '?'}")
    if df.empty:
        produce_report_placeholder(n); return
    observed = load_price_observed().reindex_like(df).fillna(False).astype(bool)
    n_filled_cells = int((~observed).sum().sum())
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
    if args.skip_timesfm:
        print("[harness] --skip-timesfm: usando baseline naive")
    elif TimesFM is not None:
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
        comp_min = competitor_min_price(df, pid, chain, dates)
        # pre-slice covariate windows aligned to dates for speed (series already aligned)
        # cov_df indexed by dates — ensure length matches
        brecha_s = cov_df["brecha"].reindex(dates).ffill().bfill().fillna(0).values
        vol7_s   = cov_df["fx_vol7"].reindex(dates).ffill().bfill().fillna(0.015).values
        ipim_s   = cov_df["ipim_idx"].reindex(dates).ffill().bfill().fillna(100).values
        # normalize ipim to small scale (z-like) to avoid dominating; use /100
        ipim_s = (ipim_s - 100.0) / 10.0
        comp_s = pd.Series(comp_min).reindex(dates).ffill().bfill().values.astype(float) if comp_min is not None else np.full(len(dates), np.nan)
        # competitor as relative spread vs own price median — keep raw but nan->0
        comp_s = np.nan_to_num(comp_s, nan=0.0, posinf=0.0, neginf=0.0)
        for cfg in CONFIGS:
            fb0_n, fb0_c = _FB["naive"], _FB["cov_dropped"]
            y_true=[]; y_pred=[]; y_lo=[]; y_hi=[]
            y_pred_series=[]  # for plot
            daily_pred=[]; daily_actual=[]; week_pred=[]; week_actual=[]
            hist_all = df[col].values.astype(float)
            obs_col = observed[col] if col in observed.columns else None
            for t_idx in range(eval_start, len(dates)):
                start = max(0, t_idx-ctx_len)
                hist = df[col].iloc[start:t_idx].values.astype(float)
                # build past_only covariates for this cfg, aligned to context window [start:t_idx)
                po = None
                if cfg == "plus_fx":
                    po = np.vstack([brecha_s[start:t_idx], vol7_s[start:t_idx]])
                elif cfg == "plus_fx_ipim":
                    po = np.vstack([brecha_s[start:t_idx], vol7_s[start:t_idx], ipim_s[start:t_idx]])
                elif cfg == "plus_fx_competitor":
                    # if competitor all zeros -> fall back to fx only
                    win_comp = comp_s[start:t_idx]
                    if np.all(win_comp == 0):
                        po = np.vstack([brecha_s[start:t_idx], vol7_s[start:t_idx]])
                    else:
                        # scale competitor to comparable magnitude (divide by 1000)
                        win_comp = win_comp / 1000.0
                        po = np.vstack([brecha_s[start:t_idx], vol7_s[start:t_idx], win_comp])
                # else price_only: po=None
                if timesfm_ok and model is not None:
                    p50,p10,p90=timesfm_predict(model, hist, 1, past_only_covariates=po)
                else:
                    p50,p10,p90=naive_forecast(hist, 1)
                actual = df[col].iloc[t_idx]
                # filled cells are not scored: ffill stability is not a forecast hit
                t_is_obs = bool(obs_col.iloc[t_idx]) if obs_col is not None else True
                if not t_is_obs:
                    y_true.append(np.nan); y_pred.append(np.nan); y_lo.append(np.nan); y_hi.append(np.nan)
                    y_pred_series.append(np.nan)
                    daily_actual.append(None); daily_pred.append(None)
                    week_actual.append(None); week_pred.append(None)
                    # still advance model state? no — skip prediction entirely
                    # (remove the unused predict above is complex; the y_* NaNs
                    # exclude this step from metrics via mask)
                    continue
                y_true.append(float(actual) if pd.notna(actual) else np.nan)
                y_pred.append(float(p50[0]) if len(p50)>0 else np.nan)
                y_lo.append(float(p10[0]) if len(p10)>0 else np.nan)
                y_hi.append(float(p90[0]) if len(p90)>0 else np.nan)
                y_pred_series.append(float(p50[0]) if len(p50)>0 else np.nan)
                # event layer: daily direction (pred vs actual, threshold 0.8%)
                # both endpoints must be observed (no ffill artefacts)
                d_prev = df[col].iloc[t_idx-1]
                prev_is_obs = bool(obs_col.iloc[t_idx-1]) if obs_col is not None else True
                if pd.notna(actual) and pd.notna(d_prev) and d_prev != 0 and prev_is_obs:
                    act_dlt = (float(actual) - float(d_prev)) / abs(float(d_prev)) * 100
                    daily_actual.append(direction(act_dlt))
                    if len(p50) > 0 and pd.notna(p50[0]):
                        pred_dlt = (float(p50[0]) - float(d_prev)) / abs(float(d_prev)) * 100
                        daily_pred.append(direction(pred_dlt))
                    else:
                        daily_pred.append(None)
                else:
                    daily_actual.append(None); daily_pred.append(None)
                # weekly variant: proper 7-day window [t_idx, t_idx+6] — includes
                # the immediate target day, requires the FULL window observed.
                # Incomplete windows (edge of history) are not scored.
                if t_idx + WEEK_H <= len(dates):
                    fut = df[col].iloc[t_idx:t_idx+WEEK_H]
                    fobs = obs_col.iloc[t_idx:t_idx+WEEK_H] if obs_col is not None else None
                    if len(fut.dropna()) == WEEK_H and (fobs is None or bool(fobs.all())) and pd.notna(d_prev) and d_prev != 0:
                        fw = None
                        for v in fut.values:
                            fd = (float(v) - float(d_prev)) / abs(float(d_prev)) * 100
                            if abs(fd) >= THRESH:
                                fw = direction(fd)
                                break
                        week_actual.append(fw if fw is not None else "estable")
                        if len(p50) > 0 and pd.notna(p50[0]):
                            pdlt = (float(p50[0]) - float(d_prev)) / abs(float(d_prev)) * 100
                            week_pred.append(direction(pdlt))
                        else:
                            week_pred.append(None)
                    else:
                        week_actual.append(None); week_pred.append(None)
                else:
                    week_actual.append(None); week_pred.append(None)
            m=metrics(y_true,y_pred,y_lo,y_hi)
            m.update({"series":col,"pid":pid,"chain":chain,"config":cfg,"category":category_of(pid)})
            # event layer: precision/recall/F1 per class + weekly variant
            ev = event_stats(daily_pred, daily_actual, week_pred, week_actual)
            for k in ("daily", "weekly"):
                for cls in ("sube", "baja", "estable"):
                    for kk in ("n", "actual", "hits", "precision", "recall", "f1"):
                        m[f"event_{k}_{cls}_{kk}"] = ev[k][cls][kk]
            m["event_move_precision_daily"] = ev["move_precision"]["daily"]
            m["event_move_precision_weekly"] = ev["move_precision"]["weekly"]
            m["fallback_naive"] = _FB["naive"] - fb0_n
            m["fallback_cov_dropped"] = _FB["cov_dropped"] - fb0_c
            # stash raw event pairs for pooled config-level aggregation
            m["_daily_pairs"] = [(p, a) for p, a in zip(daily_pred, daily_actual) if p is not None and a is not None]
            m["_weekly_pairs"] = [(p, a) for p, a in zip(week_pred, week_actual) if p is not None and a is not None]
            results.append(m)
            if col==example_col and cfg=="plus_fx":
                forecasts_for_plot[col]= {"y_true":y_true,"y_pred":y_pred,"y_lo":y_lo,"y_hi":y_hi,"dates":[d.strftime("%Y-%m-%d") for d in eval_dates]}
    # aggregate
    df_res=pd.DataFrame(results)
    # write eval_results.json/md
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path=OUT_DIR/f"eval_results.json"
    # include metadata in json (drop private pair lists from serialized rows)
    pub_results = [{k: v for k, v in m.items() if not k.startswith("_")} for m in results]
    total_fb_naive = int(sum(m.get("fallback_naive", 0) for m in results))
    total_fb_cov = int(sum(m.get("fallback_cov_dropped", 0) for m in results))
    json_path.write_text(json.dumps({"cov_note": cov_note, "timesfm_ok": timesfm_ok,
        "n_series": len(keep), "n_files": n,
        "fallback_naive": total_fb_naive, "fallback_cov_dropped": total_fb_cov,
        "filled_cells_skipped": int(n_filled_cells),
        "scoring_note": "Solo observaciones reales: celdas rellenadas por ffill excluidas del scoring. Ventana semanal [T,T+6] completa y observada.",
        "results": pub_results, "example": forecasts_for_plot}, ensure_ascii=False, indent=2))
    # markdown
    md_lines=["# Canasta Rosario — TimesFM 3 Evaluación","",f"Rango: {dates.min().date()} -> {dates.max().date()} — {n} archivos — {len(keep)} series (≥{args.min_obs} obs)","",f"> Covariables: {cov_note}","",f"> Motor: {'TimesFM 3' if timesfm_ok else 'Naive/MA baseline (TimesFM no instalado — `pip install timesfm`)'}","","## Agregado por configuración","","| Config | MAE | MAPE % | RMSE | Coverage 10-90 | n |","|---|---|---|---|---|---|"]
    agg=df_res.groupby("config").agg({"mae":"mean","mape":"mean","rmse":"mean","coverage":"mean","n":"sum"}).reindex(CONFIGS)
    for cfg in CONFIGS:
        if cfg in agg.index:
            r=agg.loc[cfg]
            md_lines.append(f"| {cfg} | {r['mae']:.1f} | {r['mape']:.1f} | {r['rmse']:.1f} | {r['coverage']:.2f} | {int(r['n'])} |")
    md_lines+=["","","> Precisión de eventos (umbral 0.8%) — POOL global por configuración (todas las series). De las veces que el modelo dijo ↑/↓, cuántas acertó; recall = de los movimientos reales, cuántos anticipó. Solo observaciones reales.","","| Config | ↑ prec (d) | ↑ recall (d) | ↓ prec (d) | ↓ recall (d) | ↑ prec (w7) | ↓ prec (w7) |","|---|---|---|---|---|---|---|"]
    for cfg in CONFIGS:
        sub = df_res[df_res["config"]==cfg]
        if sub.empty: continue
        # pool event pairs across all series of this config (honest aggregate)
        dpool = [pr for m in results if m["config"]==cfg for pr in m.get("_daily_pairs", [])]
        wpool = [pr for m in results if m["config"]==cfg for pr in m.get("_weekly_pairs", [])]
        dp, da = zip(*dpool) if dpool else ([], [])
        wp, wa = zip(*wpool) if wpool else ([], [])
        ds = _class_stats(list(dp), list(da), "sube"); db = _class_stats(list(dp), list(da), "baja")
        ws = _class_stats(list(wp), list(wa), "sube"); wb = _class_stats(list(wp), list(wa), "baja")
        md_lines.append(
            f"| {cfg} | {ds['precision']:.1f}% (n={ds['n']}) | {ds['recall']:.1f}% | "
            f"{db['precision']:.1f}% (n={db['n']}) | {db['recall']:.1f}% | "
            f"{ws['precision']:.1f}% | {wb['precision']:.1f}% |")
    if total_fb_naive or total_fb_cov:
        md_lines += ["", f"> Fallbacks naive durante la corrida: **{total_fb_naive}** predicciones; covariables descartadas por TypeError: **{total_fb_cov}**. Las celdas rellenadas excluidas del scoring: **{n_filled_cells}**."]
    md_lines+=["","","## Por categoría (MAE promedio)","","| Categoría | price_only | plus_fx | plus_fx_ipim | plus_fx_competitor |","|---|---|---|---|---|"]
    cat_agg=df_res.groupby(["category","config"])["mae"].mean().unstack("config").reindex(columns=CONFIGS)
    for cat in cat_agg.index:
        row=cat_agg.loc[cat]
        md_lines.append(f"| {cat} | " + " | ".join(f"{row.get(c,np.nan):.1f}" if pd.notna(row.get(c)) else "—" for c in CONFIGS) + " |")
    (OUT_DIR/"eval_results.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[harness] escrito {json_path}")
    # Build plots + HTML
    try:
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
