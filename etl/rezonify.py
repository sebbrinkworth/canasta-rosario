#!/usr/bin/env python3
"""One-off + reusable: recompute per-zone aggregates from data/raw/*.json.

Writes zones {rosario, gran} into data/rosario-*.json + latest.json without
re-downloading SEPA zips. Safe to re-run. Used once for the 9 historical days;
going forward etl.py emits zones directly.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from etl.etl import aggregate_zone, build_table, zone_of
from etl.etl import CHAIN_LABELS, NON_RETAIL_COMERCIOS

for raw_fp in sorted((ROOT / "data" / "raw").glob("rosario-*.json")):
    date = raw_fp.stem.replace("rosario-", "")
    agg_fp = ROOT / "data" / f"rosario-{date}.json"
    if not agg_fp.exists():
        print(f"skip {date}: no agregado")
        continue
    raw = json.loads(raw_fp.read_text())
    observations = raw.get("observations", [])
    branches = raw.get("branches", [])
    zones = {}
    for zone in ("rosario", "gran"):
        agg_z = aggregate_zone(observations, branches, zone)
        br_z = [b for b in branches if zone_of(b.get("localidad") or b.get("sucursales_localidad")) == zone and str(b.get("id_comercio")) not in NON_RETAIL_COMERCIOS]
        zones[zone] = {
            "branches_count": len(br_z),
            "chains": [{"id": c, "label": CHAIN_LABELS.get(c, c)} for c in agg_z["chains"]],
            "hero": agg_z["hero"],
            "table": build_table(agg_z),
        }
        print(f"{date} {zone}: {len(br_z)} suc, hero={[(h['chain_label'], h['total']) for h in agg_z['hero'][:2]]}")
    agg = json.loads(agg_fp.read_text())
    agg["zones"] = zones
    agg_fp.write_text(json.dumps(agg, ensure_ascii=False, indent=2))
    print(f"updated {agg_fp.name}")
# refresh latest.json from newest file
latest_src = sorted((ROOT / "data").glob("rosario-*.json"))[-1]
(ROOT / "data" / "latest.json").write_text(latest_src.read_text())
print(f"latest -> {latest_src.name}")
