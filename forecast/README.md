# Forecast — Canasta Rosario × TimesFM 3

## Modo sintético (preview 30d — ahora)
7 reales (2026-08-25..09-01) + 23 sintéticos (2026-08-01..24) = 30 días para validar plumbing sin esperar 23 días.

```bash
PYTHONPATH=. uv run python forecast/synthetic.py        # regenera data/synthetic/rosario-*.json + covariates_synthetic.csv
PYTHONPATH=. uv run python forecast/test_harness.py --synthetic --force   # walk-forward h=1, últimos 10d, ctx 20d, 4 configs
# salida: forecast/eval_results_synthetic.{json,md} + forecast/report_synthetic.html + forecast/plots_synthetic/*.png
# mirror web: web/forecast_synthetic.html (Pages)
```

Sintético: base = mediana real, jitter N(0,std*0.35), 5% promo −8..−15%, trend +0.2%/día, FX pass-through 10% con 30% prob. Bounds median*0.35..2.4. No se toca `data/*.json`.

## Modo real (cuando haya ~30 reales — fines sep)
El Action `daily.yml` ya junta 1/día a las 17:00 ART → `data/rosario-*.json` + `web/index.html`. SEPA es ventana 7 días rolling, no hay backfill.

```bash
uv run python forecast/test_harness.py --force          # o sin --force cuando haya ≥50 archivos
# salida: forecast/eval_results.{json,md} + forecast/report.html + forecast/plots/*.png → web/forecast.html
uv run python -m http.server --directory forecast 8000  # http://localhost:8000/report.html
```

## Covariables
`forecast/covariates.py` → `build_daily_covariates(index)`: `fx_blue/oficial, brecha, fx_vol7, ipim_idx` (fx_mep queda NaN: sin fuente histórica). FX = histórico diario real de `bluelytics.com.ar` (evolution.json, blue+oficial), cacheado en `data/covariates/`. IPIM = serie mensual real `448.1_NIVEL_GENERAL_0_0_13_46` de series-tiempo (apis.datos.gob.ar, INDEC), interpolada a diario; si el fetch falla o está desactualizada, estado explícito `IPIM: no data` (nunca sintético en silencio). Stub determinístico solo como fallback marcado si no hay FX real. `dolarapi.com` es spot-only: no sirve como fuente histórica.

## TimesFM 3
`forecast/test_harness.py` intenta `import timesfm`; si no está, baseline naive (last + drift, banda ±1.28σ). Con `pip install timesfm` y checkpoint, TimesFM 3 zero-shot reemplaza naive (API `model.forecast`).

## Archivos
- `utils.py:load_synthetic_30d()` merge synthetic+real; `load_price_dataframe()` solo real.
- `synthetic.py` generador.
- `report.py` vs `report_synthetic.py` (banner synthetic + captions "Qué ves / Qué significa").
