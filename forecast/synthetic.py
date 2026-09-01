#!/usr/bin/env python3
"""synthetic.py — genera 23 días sintéticos (2026-08-01..24) a partir de 7 reales (26..31 + 09-01).
Turns 7 real days into 30-day series for TimesFM plumbing preview.
"""
import json, random
from pathlib import Path
from datetime import date, timedelta
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SYN_DIR = DATA_DIR / "synthetic"

def load_real_stats():
    from forecast.utils import load_price_dataframe
    df = load_price_dataframe()
    # also need raw missing pattern
    # compute per col median/std and missing rate
    stats = {}
    for col in df.columns:
        s = df[col].dropna()
        if len(s)==0: continue
        stats[col] = {"median": float(s.median()), "std": float(s.std() if len(s)>1 else s.iloc[0]*0.04), "n": int(len(s)), "miss_rate": float(df[col].isna().mean())}
    # category
    return df, stats

def generate_synthetic(start="2026-08-01", n_days=23, seed=42):
    rng = np.random.default_rng(seed)
    random.seed(seed)
    df_real, stats = load_real_stats()
    # get template: use first real file as skeleton
    template_path = sorted(DATA_DIR.glob("rosario-2026-*.json"))[0]
    template = json.loads(template_path.read_text())
    SYN_DIR.mkdir(parents=True, exist_ok=True)
    start_d = date.fromisoformat(start)
    # also load all real dates to avoid overwrite
    real_dates = {d.strftime("%Y-%m-%d") for d in pd.to_datetime(df_real.index)}
    # For covariate synthesis we also write daily covariates stub csv
    fx_vals = []
    fx_base = 1350.0
    # random walk anchored
    walk = 0.0
    for i in range(n_days):
        d = start_d + timedelta(days=i)
        dstr = d.isoformat()
        if dstr in real_dates:
            continue
        # trend inflation +0.2%/day since start
        trend_factor = 1 + 0.002 * i
        # FX for this day (for later covariate csv)
        walk += rng.normal(0, 13)
        fx_blue = fx_base + walk + i*1.2
        fx_vals.append((dstr, fx_blue))
        # Build synthetic day JSON by perturbing medians per col back to table structure
        # Need to reconstruct table from stats + template product/chain layout
        # Use template table items and for each chain generate price_per_unit
        syn_table = []
        for item in template["table"]:
            pid = item["id"]
            # copy meta
            new_item = {"id": pid, "name": item["name"], "unit_display": item.get("unit_display",""), "category": item.get("category",""), "prices": {}}
            for chain_id in [c["id"] for c in template["chains"]]:
                col = f"{pid}__{chain_id}"
                st = stats.get(col)
                if st is None:
                    # no real obs — replicate missing pattern 80% miss
                    if rng.random() < 0.8:
                        new_item["prices"][chain_id] = None
                    else:
                        # fallback tiny price
                        base = 1000
                        val = base * trend_factor + rng.normal(0, base*0.04)
                        new_item["prices"][chain_id] = {"price_lista": round(val,2), "price_per_unit": round(val,2), "per_unit": item.get("prices",{}).get(chain_id,{}).get("per_unit","kg") if isinstance(item.get("prices",{}).get(chain_id), dict) else "kg", "desc": "SINTETICO", "marca": "SINT"}
                    continue
                # missing?
                if rng.random() < max(0, min(0.6, st["miss_rate"]*0.9)):
                    # replicate missing — sometimes real had — ; synthetic also —
                    # but keep at least 20% available
                    # use miss_rate bounded
                    # already drawn; if miss -> None
                    new_item["prices"][chain_id] = None
                    continue
                base = st["median"] * trend_factor
                jitter = rng.normal(0, st["std"]*0.35)
                # promo dip 5% chance
                if rng.random() < 0.05:
                    dip = rng.uniform(0.08, 0.15)
                    jitter -= base * dip
                # fx pass-through small: when fx_blue high vs base, ~10% pass
                fx_effect = (fx_blue - fx_base)/fx_base * 0.10 * base
                if rng.random() < 0.3:
                    jitter += fx_effect * rng.uniform(0.5, 1.0)
                val = base + jitter
                # clamp to outlier filter bounds
                lo = st["median"] * 0.35
                hi = st["median"] * 2.4
                val = float(np.clip(val, lo, hi))
                # round
                val = round(val, 2)
                # pick per_unit from template if available
                orig = item.get("prices",{}).get(chain_id)
                per_unit = orig.get("per_unit","kg") if isinstance(orig, dict) else "kg"
                new_item["prices"][chain_id] = {"price_lista": val, "price_per_unit": val, "per_unit": per_unit, "desc": "SINTETICO", "marca": "SINT"}
            syn_table.append(new_item)
        syn_doc = {
            "date": dstr,
            "gran_rosario": True,
            "synthetic": True,
            "branches_count": template.get("branches_count", 20),
            "chains": template["chains"],
            "hero": [],  # computed quickly
            "table": syn_table
        }
        # hero totals
        # sum per chain found
        for ch in template["chains"]:
            cid = ch["id"]
            tot = 0; cnt=0
            for it in syn_table:
                p = it["prices"].get(cid)
                if p and p.get("price_per_unit"):
                    tot += p["price_per_unit"]; cnt+=1
            syn_doc["hero"].append({"chain_id": cid, "chain_label": ch["label"], "total": round(tot,2), "items_found": cnt})
        out = SYN_DIR / f"rosario-{dstr}.json"
        out.write_text(json.dumps(syn_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[synthetic] wrote {n_days} days to {SYN_DIR} (13k-ish each)")
    # also write covariate synthetic csv for reference
    # FX + IPIM stub
    fx_df = pd.DataFrame(fx_vals, columns=["date","fx_blue"])
    fx_df["fx_blue"] = fx_df["fx_blue"]
    # add more cols synthetic around 1350, brecha 12-18%
    fx_df["fx_oficial"] = fx_df["fx_blue"] / (1 + np.random.default_rng(seed+1).uniform(0.12,0.18, len(fx_df)))
    fx_df["fx_mep"] = fx_df["fx_blue"] * np.random.default_rng(seed+2).uniform(0.97,1.01, len(fx_df))
    fx_df["brecha"] = (fx_df["fx_blue"] - fx_df["fx_oficial"])/fx_df["fx_oficial"]
    fx_df["ipim_idx"] = 100 + np.linspace(0, 1.2, len(fx_df))  # slight trend
    fx_df.to_csv(SYN_DIR / "covariates_synthetic.csv", index=False)
    print(f"[synthetic] covariates → {SYN_DIR / 'covariates_synthetic.csv'}")
    # also create merged long csv data/forecast_synthetic_30d.csv via utils helper? we do via load helper
    print(f"[synthetic] done. Real {len(df_real)} days + synthetic {n_days} = ~30 days total.")
    # print shape check
    from forecast.utils import load_synthetic_30d
    try:
        df2 = load_synthetic_30d()
        print(f"[synthetic] merged shape {df2.shape} {df2.index.min().date()} → {df2.index.max().date()}")
    except Exception as e:
        print(f"[synthetic] load_synthetic_30d not yet available: {e}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-08-01")
    ap.add_argument("--n", type=int, default=23)
    args = ap.parse_args()
    generate_synthetic(start=args.start, n_days=args.n)
