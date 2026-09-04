"""utils — carga data/rosario-*.json → DataFrame index=date, cols=product_chain."""
from pathlib import Path
import json
import re
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

def list_jsons():
    return sorted(DATA_DIR.glob("rosario-*.json"))

def list_synthetic_jsons():
    # synthetic preview removed 2026-09-04: real SEPA history only
    return []

def load_synthetic_30d(price_field: str = "price_per_unit", fill_limit: int = 2) -> pd.DataFrame:
    """DEPRECATED 2026-09-04: synthetic preview removed — returns real-only data.
    Kept for backwards compatibility with old callers; the synthetic directory no longer exists."""
    return load_price_dataframe(price_field=price_field, fill_limit=fill_limit)

def load_price_dataframe(price_field: str = "price_per_unit", fill_limit: int = 2) -> pd.DataFrame:
    """Values = price_field (price_per_unit | price_lista). '—'/null → NaN, ffill limit 2."""
    files = list_jsons()
    rows = {}
    for fp in files:
        try:
            d = json.loads(fp.read_text())
        except Exception:
            continue
        date = d.get("date") or re.search(r"(\d{4}-\d{2}-\d{2})", fp.name).group(1)
        for item in d.get("table", []):
            pid = item["id"]
            for cid, price_obj in (item.get("prices") or {}).items():
                col = f"{pid}__{cid}"
                if price_obj is None:
                    val = np.nan
                else:
                    raw = price_obj.get(price_field)
                    if raw is None or raw == "—" or raw == "":
                        val = np.nan
                    else:
                        try:
                            val = float(raw)
                        except:
                            val = np.nan
                rows.setdefault(date, {})[col] = val
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    # forward-fill at most fill_limit days
    df = df.ffill(limit=fill_limit)
    return df

def load_meta():
    files = list_jsons()
    if not files:
        return {}
    latest = max(files, key=lambda p: p.name)
    try:
        d = json.loads(latest.read_text())
        return {"latest_date": d.get("date"), "branches_count": d.get("branches_count"), "chains": d.get("chains", []), "file_count": len(files)}
    except:
        return {"file_count": len(files)}

def category_of(pid: str) -> str:
    try:
        from etl.canasta import CANASTA_BY_ID
        return CANASTA_BY_ID.get(pid, {}).get("category", "Otro")
    except:
        return "Otro"
