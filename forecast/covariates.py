"""covariates — FX diario real (bluelytics) + IPIM real (series-tiempo) + competidor, joined daily.

Fuentes:
- FX: https://api.bluelytics.com.ar/v2/evolution.json — histórico diario blue+oficial
  (sin key; ~4.600 días por serie). dolarapi.com es spot-only (sin histórico) y NO se
  usa como fuente histórica.
- IPIM: https://apis.datos.gob.ar/series/api — serie mensual vigente
  448.1_NIVEL_GENERAL_0_0_13_46 (Índice de Precios Internos al por Mayor, nivel general,
  base Dic-2015=100, INDEC vía SSPM), interpolada a diario. Si no hay datos: estado
  explícito "IPIM: no data" (nunca se sintetiza en silencio).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:
    requests = None

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "covariates"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FX_CACHE = CACHE_DIR / "fx_bluelytics.csv"
IPIM_CACHE = CACHE_DIR / "ipim_series_tiempo.csv"
FX_CACHE_TTL_S = 12 * 3600
IPIM_CACHE_TTL_S = 24 * 3600

BLUELYTICS_URL = "https://api.bluelytics.com.ar/v2/evolution.json"
SERIES_TIEMPO_URL = "https://apis.datos.gob.ar/series/api/series"
IPIM_SERIE_ID = "448.1_NIVEL_GENERAL_0_0_13_46"

# Última publicación mensual conocida del IPIM (verificada 2026-09-04: serie
# actualizada hasta 2026-07). Si el fetch trae datos pero el último valor es más
# viejo que esta ventana, se marca IPIM como "no data (stale)" en la nota.
IPIM_MAX_STALE_DAYS = 75
# Lag de publicación: el IPIM de un mes se publica ~30-45 días después del fin
# de mes. Para no filtrar futuro en el backtest, cada fecha diaria solo ve los
# valores mensuales publicados hasta esa fecha (60 días de margen seguro).
IPIM_PUB_LAG_DAYS = 60


def _http_get_json(url: str, timeout: int = 10, retries: int = 3, backoff: float = 2.0):
    """GET con retries simples. Devuelve dict/list o None."""
    if requests is None:
        return None
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "canasta-rosario/forecast"})
            if r.ok:
                return r.json()
            print(f"[covariates] HTTP {r.status_code} en {url} (intento {attempt+1}/{retries})")
        except Exception as e:
            print(f"[covariates] fetch fail ({attempt+1}/{retries}): {url}: {e}")
        if attempt < retries - 1:
            time.sleep(backoff * (attempt + 1))
    return None


def _cache_fresh(path: Path, ttl_s: float) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < ttl_s


# ---------------------------------------------------------------- FX real ----
def fetch_fx_daily(force: bool = False) -> tuple[pd.Series | None, pd.Series | None, str]:
    """Historial diario real blue/oficial desde bluelytics (cache CSV en data/covariates/).

    Devuelve (blue, oficial, source). blue/oficial: pd.Series daily con value_sell;
    None si no se pudo obtener nada.
    """
    if not force and _cache_fresh(FX_CACHE, FX_CACHE_TTL_S):
        try:
            df = pd.read_csv(FX_CACHE, index_col=0, parse_dates=True)
            if {"fx_blue", "fx_oficial"}.issubset(df.columns) and len(df) > 0:
                return df["fx_blue"], df["fx_oficial"], "bluelytics.com.ar (cache data/covariates/fx_bluelytics.csv)"
        except Exception as e:
            print(f"[covariates] cache FX ilegible: {e}")
    payload = _http_get_json(BLUELYTICS_URL, timeout=15)
    if payload and isinstance(payload, list) and len(payload) > 0:
        df = pd.DataFrame(payload)
        # items: {date, source ('Blue'|'Oficial'), value_sell, value_buy}
        src = df["source"].astype(str).str.strip().str.lower()
        blue = pd.to_numeric(df.loc[src == "blue", "value_sell"], errors="coerce")
        oficial = pd.to_numeric(df.loc[src == "oficial", "value_sell"], errors="coerce")
        idx = pd.to_datetime(df["date"], errors="coerce")
        blue.index = idx[src == "blue"]
        oficial.index = idx[src == "oficial"]
        blue = blue.sort_index().groupby(level=0).last()
        oficial = oficial.sort_index().groupby(level=0).last()
        if len(blue) > 0 and len(oficial) > 0:
            out = pd.DataFrame({"fx_blue": blue, "fx_oficial": oficial}).dropna(how="all")
            out.to_csv(FX_CACHE)
            return out["fx_blue"], out["fx_oficial"], "bluelytics.com.ar"
        print("[covariates] bluelytics: respuesta sin filas blue/oficial utilizables")
    # fallback: cache viejo mejor que nada (queda marcado en source)
    try:
        df = pd.read_csv(FX_CACHE, index_col=0, parse_dates=True)
        if {"fx_blue", "fx_oficial"}.issubset(df.columns) and len(df) > 0:
            return df["fx_blue"], df["fx_oficial"], "bluelytics.com.ar (cache vencida data/covariates/fx_bluelytics.csv)"
    except Exception:
        pass
    return None, None, "sin datos"


def _forward_fill_daily(s: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Expande a calendario diario y ffill huecos (hasta 10 días); NaN inicial/cols finales quedan NaN."""
    if s is None or len(s) == 0:
        return pd.Series(dtype=float)
    s = s.sort_index()
    daily = s.reindex(pd.date_range(start, end, freq="D"))
    return daily.ffill(limit=10)


# --------------------------------------------------------------- IPIM real ----
def fetch_ipim_monthly(force: bool = False) -> tuple[pd.Series | None, str]:
    """IPIM nivel general mensual desde series-tiempo (apis.datos.gob.ar), con retries.

    Devuelve (serie_mensual, source). None si no hay datos reales (nunca sintetiza).
    """
    if not force and _cache_fresh(IPIM_CACHE, IPIM_CACHE_TTL_S):
        try:
            df = pd.read_csv(IPIM_CACHE, index_col=0, parse_dates=True)
            if len(df) > 0:
                return df.iloc[:, 0], f"series-tiempo {IPIM_SERIE_ID} (cache data/covariates/ipim_series_tiempo.csv)"
        except Exception as e:
            print(f"[covariates] cache IPIM ilegible: {e}")
    url = f"{SERIES_TIEMPO_URL}?ids={IPIM_SERIE_ID}&format=json&metadata=none&limit=500"
    payload = _http_get_json(url, timeout=20)
    if payload and isinstance(payload.get("data"), list) and len(payload["data"]) > 0:
        rows = [(pd.Timestamp(r[0]), r[1]) for r in payload["data"] if r and len(r) >= 2 and r[1] is not None]
        if rows:
            s = pd.Series({d: float(v) for d, v in rows}).sort_index()
            pd.DataFrame({"ipim_monthly": s}).to_csv(IPIM_CACHE)
            return s, f"series-tiempo {IPIM_SERIE_ID} (INDEC)"
        print("[covariates] series-tiempo: data vacía para IPIM")
    try:
        df = pd.read_csv(IPIM_CACHE, index_col=0, parse_dates=True)
        if len(df) > 0:
            return df.iloc[:, 0], f"series-tiempo {IPIM_SERIE_ID} (cache vencida data/covariates/ipim_series_tiempo.csv)"
    except Exception:
        pass
    return None, "sin datos"


def build_daily_covariates(index: pd.DatetimeIndex) -> tuple[pd.DataFrame, str]:
    """Construye DataFrame diario alineado a index (dates).

    Columnas: fx_blue, fx_mep, fx_oficial, brecha, fx_vol7, ipim_idx
    - fx_blue / fx_oficial: histórico diario real (bluelytics), ffill de huecos.
    - fx_mep: sin fuente histórica confiable disponible → NaN (no sintético).
    - brecha / fx_vol7: derivados del FX real.
    - ipim_idx: serie mensual real interpolada a diario; columna vacía + nota
      "IPIM: no data" si el fetch falla (nunca se sintetiza en silencio).
    Solo si no hay FX real disponible se usa stub determinístico, con source marcado.
    """
    idx = pd.DatetimeIndex(index).sort_values()
    if len(idx) == 0:
        return (pd.DataFrame(columns=["fx_blue", "fx_mep", "fx_oficial", "brecha", "fx_vol7", "ipim_idx"]),
                "sin fechas")
    start, end = idx[0], idx[-1]

    blue_raw, oficial_raw, fx_source = fetch_fx_daily()
    ipim_monthly, ipim_source = fetch_ipim_monthly()

    if blue_raw is not None and oficial_raw is not None:
        blue = _forward_fill_daily(blue_raw, start, end).reindex(idx)
        oficial = _forward_fill_daily(oficial_raw, start, end).reindex(idx)
        brecha = (blue - oficial) / oficial
        logret = np.log(blue.astype(float)).diff()
        vol7 = logret.rolling(7, min_periods=3).std()
        mep = pd.Series(np.nan, index=idx)  # sin fuente histórica MEP: explícitamente NaN
        df = pd.DataFrame({
            "fx_blue": blue,
            "fx_mep": mep,
            "fx_oficial": oficial,
            "brecha": brecha,
            "fx_vol7": vol7,
        }, index=idx)
        fx_note = f"FX real: bluelytics.com.ar diario (blue/oficial)"
    else:
        # Fallback explícito: stub determinístico (nunca se presenta como real).
        print("[covariates] WARNING: FX real no disponible → stub sintético marcado")
        rng = np.random.default_rng(42)
        blue = pd.Series(1450.0 + np.cumsum(rng.normal(0, 3, len(idx))) + np.linspace(0, 20, len(idx)), index=idx)
        oficial = pd.Series(1050.0 + np.linspace(0, 8, len(idx)) + rng.normal(0, 1.5, len(idx)), index=idx)
        brecha = (blue - oficial) / oficial
        logret = np.log(blue).diff()
        vol7 = logret.rolling(7, min_periods=3).std().fillna(0.015)
        mep = pd.Series(np.nan, index=idx)
        df = pd.DataFrame({
            "fx_blue": blue,
            "fx_mep": mep,
            "fx_oficial": oficial,
            "brecha": brecha,
            "fx_vol7": vol7,
        }, index=idx)
        fx_note = "FX: STUB sintético (bluelytics no disponible)"

    # IPIM real (mensual → diario SOLO con valores publicados a la fecha).
    # Sin look-ahead: para cada fecha se usa el último valor mensual cuya
    # publicación ya ocurrió (fin de mes + IPIM_PUB_LAG_DAYS). Nunca se interpola
    # con valores futuros: entre publicaciones se mantiene el último conocido
    # (step-forward, no time-interpolate). Sin datos → "no data".
    ipim = pd.Series(np.nan, index=idx, dtype=float)
    ipim_note = "IPIM: no data"
    if ipim_monthly is not None:
        ms = ipim_monthly.sort_index()
        if ms.index.tz is None:
            ms.index = ms.index.tz_localize(None)
        monthly_idx = ms.index + pd.offsets.MonthEnd(0)
        ms.index = monthly_idx
        if pd.notna(ms.iloc[-1]) and (end - ms.index[-1]).days > IPIM_MAX_STALE_DAYS:
            ipim_note = f"IPIM: no data (stale: último {ms.index[-1].date()}, {ipim_source})"
            print(f"[covariates] WARNING: {ipim_note}")
        else:
            # Fecha de publicación estimada = fin de mes + lag. Solo valores
            # publicados a cada fecha (asof join) — causal, sin futuro.
            pub_dates = ms.index + pd.to_timedelta(IPIM_PUB_LAG_DAYS, unit="D")
            vals = ms.values
            # asof: para cada fecha, último valor con pub_date <= fecha
            import bisect
            pub_list = list(pub_dates)
            filled = []
            for d in idx:
                d_ts = pd.Timestamp(d).tz_localize(None) if getattr(d, 'tz', None) else pd.Timestamp(d)
                j = bisect.bisect_right(pub_list, d_ts) - 1
                filled.append(float(vals[j]) if j >= 0 and pd.notna(vals[j]) else np.nan)
            ipim = pd.Series(filled, index=idx, dtype=float)
            n_known = int(np.sum(~np.isnan(filled)))
            ipim_note = f"IPIM real: INDEC {IPIM_SERIE_ID} mensual, último publicado a cada fecha (lag {IPIM_PUB_LAG_DAYS}d, step-forward sin interpolar futuro; {n_known}/{len(idx)} días con valor; {ipim_source})"

    df["ipim_idx"] = ipim

    note = f"{fx_note}; {ipim_note}"
    return df, note


def competitor_min_price(df_prices: pd.DataFrame, pid: str, chain: str, date_idx) -> pd.Series:
    """Para cada fecha, mínimo price_per_unit entre cadenas != chain para ese pid."""
    cols = [c for c in df_prices.columns if c.startswith(pid + "__") and not c.endswith("__" + chain)]
    if not cols: return pd.Series(np.nan, index=date_idx)
    return df_prices[cols].min(axis=1).reindex(date_idx)
