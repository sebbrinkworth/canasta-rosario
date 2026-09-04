#!/usr/bin/env python3
"""Walk-forward backtest of the lightweight drift forecast on REAL SEPA data only.

For each real day T (needing >=4 prior obs), predicts T from history before T
with the same drift logic as build_next.py, then compares with the actual price.

Two eval layers:
- Daily direction (same as before): sube/baja/estable with precision per class.
- EVENT PRECISION layer: for each direction class, report precision/recall/F1
  at the 0.8% threshold SEPARATELY from the stable hit-rate. Plus a weekly
  horizon variant (h=7): does the price move >0.8% within the next 7 days,
  and in which direction? (hit = predicted move direction matches first real
  move in the window; a "sube" that happens on day 5 still counts).

Writes data/backtest.json: hit-rate on direction, MAE, per-category, event
precision/recall/F1 for sube/baja, and weekly-horizon aggregates.
"""
import json, pathlib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "backtest.json"
THRESH = 0.8  # same % threshold as build_next.py
WEEK_H = 7


def load_series(field="price_per_unit"):
    import pandas as pd
    rows = {}
    for fp in sorted(DATA.glob("rosario-*.json")):
        import re
        d = json.loads(fp.read_text())
        date = d.get("date") or re.search(r"(\d{4}-\d{2}-\d{2})", fp.name).group(1)
        for item in d.get("table", []):
            pid = item["id"]
            for cid, po in (item.get("prices") or {}).items():
                if po is None:
                    val = float("nan")
                else:
                    try:
                        val = float(po.get(field))
                    except Exception:
                        val = float("nan")
                rows.setdefault(date, {})[f"{pid}__{cid}"] = val
    import pandas as pd
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.to_datetime(df.index)
    return df.sort_index().ffill(limit=2)


def direction(delta_pct):
    if abs(delta_pct) < THRESH:
        return "estable"
    return "sube" if delta_pct > 0 else "baja"


def drift_pred(series_hist):
    """Same logic as build_next.py: last + mean of last up-to-5 diffs."""
    h = series_hist.dropna()
    if len(h) < 4:
        return None
    last = float(h.iloc[-1])
    diffs = h.iloc[-7:].diff().dropna()
    drift = float(diffs.tail(5).mean()) if len(diffs) >= 2 else 0.0
    return last + drift


def _class_stats(preds, actuals, cls):
    """preds/actuals: iterables of direction labels. Returns dict for one class
    with n, hits, precision (of predicted cls), recall (of actual cls), f1."""
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


def main():
    try:
        from etl.canasta import CANASTA_BY_ID
        cat_of = lambda pid: CANASTA_BY_ID.get(pid, {}).get("category", "Otro")
    except Exception:
        cat_of = lambda pid: "Otro"
    df = load_series()
    dates = list(df.index)
    total = hits = 0
    abs_err, abs_base = [], []
    per_cat = {}
    from collections import Counter
    pred_c, hits_c = Counter(), Counter()
    # event-level accumulators (daily)
    ev = {k: {"pred": [], "actual": []} for k in ("sube", "baja", "estable")}
    # weekly accumulators (h=7): only where 7 future days exist
    wk = {k: {"pred": [], "actual": []} for k in ("sube", "baja", "estable")}
    n_days = 0
    for ti in range(1, len(dates)):
        hist = df.iloc[:ti]
        actual = df.iloc[ti]
        # future window for weekly variant: ti+1 .. ti+WEEK_H
        future = df.iloc[ti + 1: ti + 1 + WEEK_H] if ti + 1 < len(dates) else None
        day_hits = day_total = 0
        for col in df.columns:
            h = hist[col].dropna()
            a = actual[col]
            if len(h) < 4 or np.isnan(a) or a == 0:
                continue
            last = float(h.iloc[-1])
            pred = drift_pred(hist[col])
            if pred is None:
                continue
            pred_dir = direction((pred - last) / abs(last) * 100)
            real_dir = direction((float(a) - last) / abs(last) * 100)
            ok = pred_dir == real_dir
            total += 1
            day_total += 1
            hits += int(ok)
            pred_c[pred_dir] += 1
            hits_c[pred_dir] += int(ok)
            day_hits += int(ok)
            abs_err.append(abs(pred - float(a)))
            abs_base.append(abs(float(a)))
            pid = col.split("__", 1)[0]
            c = cat_of(pid)
            s = per_cat.setdefault(c, {"n": 0, "hits": 0})
            s["n"] += 1
            s["hits"] += int(ok)
            # event layer: accumulate per-class pred/actual
            ev[pred_dir]["pred"].append(pred_dir)
            ev[pred_dir]["actual"].append(real_dir)
            # weekly variant: predict move within next 7 days from current drift
            if future is not None:
                fcol = future[col].dropna()
                if len(fcol) >= 1:
                    # first real move in window (vs last observed)
                    first_move = None
                    for v in fcol.values:
                        dlt = (float(v) - last) / abs(last) * 100
                        if abs(dlt) >= THRESH:
                            first_move = direction(dlt)
                            break
                    actual_wk = first_move if first_move is not None else "estable"
                    wk[pred_dir]["pred"].append(pred_dir)
                    wk[pred_dir]["actual"].append(actual_wk)
        if day_total:
            n_days += 1
    mae = float(np.mean(abs_err)) if abs_err else 0.0
    mape = float(np.mean([e / b * 100 for e, b in zip(abs_err, abs_base) if b])) if abs_err else 0.0
    event_prec = {k: _class_stats(v["pred"], v["actual"], k) for k, v in ev.items()}
    weekly_prec = {k: _class_stats(v["pred"], v["actual"], k) for k, v in wk.items()}
    OUT.write_text(json.dumps({
        "method": "drift-7d, umbral 0.8%, solo datos reales SEPA",
        "eval_days": n_days,
        "date_range": [str(dates[1].date()) if len(dates) > 1 else None, str(dates[-1].date()) if dates else None],
        "n": total,
        "hits": hits,
        "hit_rate": round(hits / total * 100, 1) if total else 0.0,
        "mae": round(mae, 1),
        "mape": round(mape, 2),
        "pred_dist": dict(pred_c),
        "moves_prec": {k: {"n": pred_c.get(k, 0), "hits": hits_c.get(k, 0), "precision": round(hits_c.get(k, 0) / pred_c[k] * 100, 1) if pred_c.get(k) else 0.0} for k in ("sube", "baja", "estable")},
        "event_precision": {
            "threshold_pct": THRESH,
            "note": "Precision/recall/F1 por clase de dirección (daily). precision = de las veces que predijo la clase, cuántas acertó; recall = de las veces que la clase ocurrió, cuántas anticipó.",
            "sube": event_prec["sube"],
            "baja": event_prec["baja"],
            "estable": event_prec["estable"],
        },
        "weekly": {
            "method": "drift-7d, umbral 0.8%, h<=7: predice si el precio se mueve >0.8% dentro de la semana y hacia dónde (primer movimiento real en la ventana)",
            "threshold_pct": THRESH,
            "horizon_days": WEEK_H,
            "classes": weekly_prec,
            "mov_prec_summary": {
                "sube_pred": weekly_prec["sube"]["n"],
                "sube_precision": weekly_prec["sube"]["precision"],
                "sube_recall": weekly_prec["sube"]["recall"],
                "baja_pred": weekly_prec["baja"]["n"],
                "baja_precision": weekly_prec["baja"]["precision"],
                "baja_recall": weekly_prec["baja"]["recall"],
            },
        },
        "by_category": {k: {"n": v["n"], "hit_rate": round(v["hits"] / v["n"] * 100, 1)} for k, v in sorted(per_cat.items())},
    }, ensure_ascii=False, indent=2))
    print(f"[backtest] {hits}/{total} = {hits/total*100:.1f}% dir. correcta en {n_days} dias, MAE {mae:.1f} -> {OUT}")
    for k in ("sube", "baja", "estable"):
        e = event_prec[k]
        print(f"  daily {k}: n_pred={e['n']} actual={e['actual']} prec={e['precision']}% recall={e['recall']}% f1={e['f1']}")
    for k in ("sube", "baja", "estable"):
        e = weekly_prec[k]
        print(f"  weekly {k}: n_pred={e['n']} actual={e['actual']} prec={e['precision']}% recall={e['recall']}% f1={e['f1']}")


if __name__ == "__main__":
    main()