#!/usr/bin/env python3
"""Walk-forward backtest of the lightweight drift forecast on REAL SEPA data only.

For each real day T (needing >=4 prior obs), predicts T from history before T
with the same drift logic as build_next.py, then compares with the actual price.
Writes data/backtest.json: hit-rate on direction (sube/baja/estable), MAE, per-category.
"""
import json, pathlib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "backtest.json"
THRESH = 0.8  # same % threshold as build_next.py


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
    n_days = 0
    for ti in range(1, len(dates)):
        hist = df.iloc[:ti]
        actual = df.iloc[ti]
        day_hits = day_total = 0
        for col in df.columns:
            h = hist[col].dropna()
            a = actual[col]
            if len(h) < 4 or np.isnan(a) or a == 0:
                continue
            last = float(h.iloc[-1])
            diffs = h.iloc[-7:].diff().dropna()
            drift = float(diffs.tail(5).mean()) if len(diffs) >= 2 else 0.0
            pred = last + drift
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
        if day_total:
            n_days += 1
    mae = float(np.mean(abs_err)) if abs_err else 0.0
    mape = float(np.mean([e / b * 100 for e, b in zip(abs_err, abs_base) if b])) if abs_err else 0.0
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
        "by_category": {k: {"n": v["n"], "hit_rate": round(v["hits"] / v["n"] * 100, 1)} for k, v in sorted(per_cat.items())},
    }, ensure_ascii=False, indent=2))
    print(f"[backtest] {hits}/{total} = {hits/total*100:.1f}% dir. correcta en {n_days} dias, MAE {mae:.1f} -> {OUT}")


if __name__ == "__main__":
    main()
