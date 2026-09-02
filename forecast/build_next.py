#!/usr/bin/env python3
"""Build data/forecast-next.json with AUTO-REPLACE: real-only when enough real days.

- Counts data/rosario-*.json (real, agregados).
- If real_days >= 30: uses only real (mode=real).
- Else: merges data/synthetic + real to reach ~30 (mode=synthetic+real), clearly labeled.
- Forecast method (lightweight, no GPU): drift of last 5 diffs on price_per_unit.
  Full TimesFM3 eval lives in forecast/test_harness.py (b3sti4 4060).
"""
import json, pathlib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "forecast-next.json"
THRESHOLD = 30

def load_df(files, field="price_per_unit"):
    import pandas as pd
    rows = {}
    for fp in files:
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        import re
        date = d.get("date") or re.search(r"(\d{4}-\d{2}-\d{2})", fp.name).group(1)
        for item in d.get("table", []):
            pid = item["id"]
            for cid, po in (item.get("prices") or {}).items():
                col = f"{pid}__{cid}"
                if po is None:
                    val = float("nan")
                else:
                    try:
                        val = float(po.get(field))
                    except Exception:
                        val = float("nan")
                rows.setdefault(date, {})[col] = val
    if not rows:
        import pandas as _pd
        return _pd.DataFrame()
    import pandas as pd
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.to_datetime(df.index)
    return df.sort_index().ffill(limit=2)

def main():
    real_files = sorted(DATA.glob("rosario-*.json"))
    synt_files = sorted((DATA / "synthetic").glob("rosario-*.json"))
    real_days = len(real_files)
    if real_days >= THRESHOLD:
        df = load_df(real_files)
        mode = "real"
        used_real, used_synt = real_days, 0
    else:
        # merge synthetic + real, sorted, keep last 30
        df = load_df(synt_files + real_files)
        # keep last 30 dates to bound size
        if len(df) > 30:
            df = df.iloc[-30:]
        mode = "synthetic+real"
        used_real, used_synt = real_days, max(0, len(df) - real_days)
    items = {}
    for col in df.columns:
        s = df[col].dropna()
        if len(s) < 4:
            continue
        last = float(s.iloc[-1])
        diffs = s.iloc[-7:].diff().dropna()
        drift = float(diffs.tail(5).mean()) if len(diffs) >= 2 else 0.0
        vol = float(diffs.std()) if len(diffs) >= 2 else abs(last) * 0.02
        pred = last + drift
        if last == 0 or np.isnan(last) or np.isnan(pred):
            continue
        delta = (pred - last) / abs(last) * 100
        if abs(delta) < 0.8:
            d = "estable"
        elif delta > 0:
            d = "sube"
        else:
            d = "baja"
        conf = "alta" if abs(drift) > (vol * 0.5) else "media"
        if vol > abs(last) * 0.08:
            conf = "baja"
        pid, cid = col.split("__", 1)
        items[col] = {"dir": d, "delta_pct": round(float(delta), 2),
                      "pred": round(float(pred), 2), "last": round(float(last), 2), "conf": conf}
    OUT.write_text(json.dumps({
        "mode": mode,
        "real_days": used_real,
        "synthetic_days": used_synt,
        "threshold": THRESHOLD,
        "generated_from": "real-only" if mode == "real" else "synthetic_30d_merged",
        "note": ("Solo datos reales SEPA. " if mode == "real"
                 else f"Sintético se reemplaza solo: {used_real}/{THRESHOLD} días reales, resto sintético. "),
        "items": items,
    }, ensure_ascii=False, indent=2))
    print(f"[build_next] mode={mode} real={used_real} synt={used_synt} forecasts={len(items)} -> {OUT}")

if __name__ == "__main__":
    main()
