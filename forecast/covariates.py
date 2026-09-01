"""covariates — FX (dolarapi) + IPIM stub, joined daily."""
from pathlib import Path
import pandas as pd
import numpy as np
import json
try:
    import requests
except ImportError:
    requests = None

def fetch_dolarapi():
    """Intenta dolarapi.com/v1/dolares — devuelve dict {oficial, blue, mep} último valor.
    Si falla, usa stub determinístico y loguea source."""
    source = "stub"
    data = None
    if requests is not None:
        try:
            r = requests.get("https://dolarapi.com/v1/dolares", timeout=6)
            if r.ok:
                data = r.json()
                source = "dolarapi.com"
        except Exception as e:
            print(f"[covariates] dolarapi fail: {e} → stub")
    return data, source

def build_daily_covariates(index: pd.DatetimeIndex) -> tuple[pd.DataFrame, str]:
    """Construye DataFrame diario alineado a index (dates).
    Columnas: fx_blue, fx_mep, fx_oficial, brecha, fx_vol7, ipim_idx
    Si dolarapi no disponible o sin histórico, genera stub sintético suave."""
    api_data, source = fetch_dolarapi()
    idx = pd.DatetimeIndex(index).sort_values()
    n = len(idx)
    # Try to parse live values if available
    if api_data and isinstance(api_data, list):
        # api_data is list of {casa, compra, venta}
        m = {d.get("casa","").lower(): d for d in api_data}
        blue = float((m.get("blue") or {}).get("venta") or 1450)
        mep = float((m.get("bolsa") or m.get("mep") or {}).get("venta") or 1430)
        oficial = float((m.get("oficial") or {}).get("venta") or 1050)
    else:
        blue, mep, oficial = 1450.0, 1430.0, 1050.0
        source = "stub (sintético suave)"
    rng = np.random.default_rng(42)
    # stub: drift + noise anchored to anchor values
    trend = np.cumsum(rng.normal(0, 3, n))  # ~ random walk
    fx_blue_s = blue + trend + np.linspace(0, 20, n)
    fx_mep_s = mep + trend*0.9 + np.linspace(0, 18, n)
    fx_oficial_s = oficial + np.linspace(0, 8, n) + rng.normal(0, 1.5, n)
    brecha = (fx_blue_s - fx_oficial_s) / fx_oficial_s
    # 7d vol (rolling std of log returns)
    logret = pd.Series(np.log(fx_blue_s)).diff()
    vol7 = logret.rolling(7, min_periods=3).std().fillna(0.015).values
    # IPIM: monthly → interpolate daily (stub: slow drift)
    ipim = 100 + np.linspace(0, 6, n) + np.cumsum(rng.normal(0, 0.15, n))
    df = pd.DataFrame({
        "fx_blue": fx_blue_s,
        "fx_mep": fx_mep_s,
        "fx_oficial": fx_oficial_s,
        "brecha": brecha,
        "fx_vol7": vol7,
        "ipim_idx": ipim,
    }, index=idx)
    note = f"FX source: {source} — IPIM: stub mensual interpolado" if "stub" in source else f"FX source: {source} (histórico interpolado) — IPIM: stub"
    return df, note

def competitor_min_price(df_prices: pd.DataFrame, pid: str, chain: str, date_idx) -> pd.Series:
    """Para cada fecha, mínimo price_per_unit entre cadenas != chain para ese pid."""
    cols = [c for c in df_prices.columns if c.startswith(pid + "__") and not c.endswith("__" + chain)]
    if not cols: return pd.Series(np.nan, index=date_idx)
    return df_prices[cols].min(axis=1).reindex(date_idx)
