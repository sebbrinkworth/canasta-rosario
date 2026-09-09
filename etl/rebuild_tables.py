#!/usr/bin/env python3
"""Rebuild data/rosario-*.json tables from data/raw/*.json using the FIXED
matcher (etl.etl.match_product) + normalized units.

- Re-matches every raw observation; drops matches that no longer qualify
  (pet food, incense, beverages, bakery, ...).
- Re-runs filter_outliers + aggregate + build_table (+ zones).
- Preserves date/branches/chains metadata shape; refreshes latest.json.
- Prints before/after diagnostics per file.
"""
import gzip, json, pathlib, sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from etl.etl import (match_product, filter_outliers, aggregate, build_table,
                     aggregate_zone, CHAIN_LABELS,
                     NON_RETAIL_COMERCIOS)
from etl.etl import zone_of
from etl.canasta import CANASTA_BY_ID
from etl.prices import normalize_observation, NORMALIZATION_VERSION
from datetime import datetime

RAW = ROOT / "data" / "raw"
AGG = ROOT / "data"

def rebuild_one(raw_fp: pathlib.Path):
    if raw_fp.name.endswith(".gz"):
        with gzip.open(raw_fp, "rt", encoding="utf-8") as stream:
            d = json.load(stream)
    else:
        d = json.loads(raw_fp.read_text())
    date_str = d.get("date") or raw_fp.stem.replace("rosario-", "")
    branches = d.get("branches", [])
    branches = [b for b in branches if str(b.get("id_comercio")) not in NON_RETAIL_COMERCIOS]
    kept, dropped, changed = [], Counter(), Counter()
    unverified_units = Counter()
    for o in d.get("observations", []):
        new = match_product(o.get("descripcion", ""), o.get("ean", ""))
        old = o.get("canonical_id")
        if new is None:
            dropped[old or "?"] += 1
            continue
        if new != old:
            changed[f"{old}->{new}"] += 1
            o["canonical_id"] = new
        normalized = normalize_observation(o, CANASTA_BY_ID[new]["unit"])
        if normalized is None:
            unverified_units[new] += 1
            continue
        kept.append(normalized)
    kept2, rejected, medians = filter_outliers(kept)
    agg = aggregate(kept2, branches)
    table = build_table(agg)
    zones = {}
    for zone in ("rosario", "gran"):
        try:
            agg_z = aggregate_zone(kept2, branches, zone)
            br_z = [b for b in branches
                    if zone_of(b.get("localidad") or b.get("sucursales_localidad")) == zone
                    and str(b.get("id_comercio")) not in NON_RETAIL_COMERCIOS]
            zones[zone] = {
                "branches_count": len(br_z),
                "chains": [{"id": cid, "label": CHAIN_LABELS.get(cid, cid)} for cid in agg_z["chains"]],
                "hero": agg_z["hero"],
                "table": build_table(agg_z),
            }
        except Exception as e:
            print(f"  zone {zone} failed: {e}")
            zones[zone] = {"branches_count": 0, "chains": [], "hero": [], "table": []}
    out = {
        "date": date_str, "gran_rosario": d.get("gran_rosario", True),
        "branches_count": len(branches),
        "chains": [{"id": cid, "label": CHAIN_LABELS.get(cid, cid)} for cid in agg["chains"]],
        "hero": agg["hero"],
        "table": table,
        "zones": zones,
        "generated_at": datetime.now().isoformat(),
        "rebuilt_with": "package-price-v2: list price / verified package quantity",
        "price_normalization_version": NORMALIZATION_VERSION,
        "normalization": {"excluded_unverified": sum(unverified_units.values()),
                          "excluded_by_product": dict(unverified_units)},
    }
    if d.get("source"):
        out["source"] = d["source"]
    (AGG / f"rosario-{date_str}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # Preserve the input archive: repeated rebuilds must not erase candidates.

    return {"date": date_str, "kept": len(kept2), "dropped": dict(dropped),
            "changed": dict(changed), "rejected": len(rejected),
            "unverified_units": sum(unverified_units.values()),
            "hero": [(h["chain_label"], h["total"]) for h in agg["hero"]]}

if __name__ == "__main__":
    files = sorted([*RAW.glob("rosario-*.json"), *RAW.glob("rosario-*.json.gz")])
    print(f"rebuilding {len(files)} days")
    latest = None
    for fp in files:
        r = rebuild_one(fp)
        latest = r
        nd = sum(r["dropped"].values())
        nc = sum(r["changed"].values())
        print(f"{r['date']}: kept={r['kept']} dropped_match={nd} changed={nc} outliers_rej={r['rejected']} unverified_units={r['unverified_units']}")
        if nd or nc:
            print(f"   dropped: {r['dropped']}")
            if nc:
                print(f"   changed: {r['changed']}")
    # refresh latest.json from newest date
    if not files:
        raise SystemExit("No raw snapshots found; existing outputs preserved")
    newest = max(files, key=lambda p: p.name)
    date_str = newest.name.removeprefix("rosario-").removesuffix(".gz").removesuffix(".json")
    (AGG / "latest.json").write_text(
        (AGG / f"rosario-{date_str}.json").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"latest.json -> {date_str}")
