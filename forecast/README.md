# Forecast — Canasta Rosario × TimesFM 3

**Datos reales únicamente.** El preview sintético (30 días) se eliminó el 2026-09-04
por transparencia: nada sintético alimenta el sitio ni la evaluación. La historia
SEPA real se acumula día a día (ventana rodante de 7 días en CKAN, sin backfill —
lo que no se baja el día que sale, se pierde), así que la precisión mejora sola
con el tiempo a medida que el recolector diario suma días.

## Daily collector

`scripts/daily_collect.sh` (cron local vía automation `canasta-daily-collect`,
17:05 ART): sincroniza repo → ETL del día (ZIP SEPA del weekday, ~330MB) →
`forecast/build_next.py` → `backtest.py` → `web/generate.py` → commit `canasta-bot`
→ push. GitHub Actions está bloqueado por SEPA (403 a IPs de runners), por eso corre local.

## Evaluación (walk-forward, solo reales)

```bash
PYTHONPATH=. uv run python forecast/test_harness.py --force   # TimesFM si hay GPU; naive fallback
PYTHONPATH=. uv run python forecast/test_harness.py --skip-timesfm --force  # baseline naive (CPU/CI)
# salida: forecast/eval_results.{json,md} + forecast/report.html + forecast/plots/*.png
# reporte: web/forecast.html
```

Dos capas de evaluación (2026-09-05: bugs corregidos tras revisión externa):
- **Dirección diaria** (h=1): sube/baja/estable con precision/recall/F1 por clase (umbral 0.8%), calculados sobre listas GLOBALES pred/actual (agrupar por clase predicha inflaba recall a 100% — corregido).
- **Ventana semanal** (h=7, ventana [T,T+6] completa y observada): incluye el día objetivo y exige los 7 días observados; ventanas incompletas no se puntúan.
- **Solo observaciones reales**: celdas rellenadas por ffill se excluyen del scoring.
- **Línea base persistencia** (mañana = hoy) en `data/backtest.json`: todo modelo debe superarla (MAE ~116 vs drift ~153 pre-limpieza; con series 90%+ planas, la persistencia gana por defecto).
- **Assortment tracking**: % de cambios de precio donde el cheapest también cambió de descripción/marca (el movimiento puede ser surtido, no remarcación).
- **Fallback accounting** en el harness: cada predicción naive dentro de una corrida TimesFM se cuenta (`fallback_naive`, `fallback_cov_dropped`); una corrida etiquetada TimesFM nunca contiene baseline en silencio.

Con <30 días reales y ~92% de pares día-a-día planos, la precisión de eventos ↑↓
es baja por diseño del problema; el scoreboard del sitio la publica igual (honestidad
> marketing) y las flechas ↑↓ del sitio quedan gated hasta que la precisión supere 25%.

## Covariables

`forecast/covariates.py` → `build_daily_covariates(index)`: `fx_blue/oficial, brecha, fx_vol7, ipim_idx` (fx_mep queda NaN: sin fuente histórica). FX = histórico diario real de `bluelytics.com.ar` (evolution.json, blue+oficial), cacheado en `data/covariates/`. IPIM = serie mensual real `448.1_NIVEL_GENERAL_0_0_13_46` de series-tiempo (apis.datos.gob.ar, INDEC); **causal**: cada fecha diaria solo ve valores mensuales ya publicados (fin de mes + 60 días de lag, step-forward — nunca se interpola con futuro); si el fetch falla o está desactualizada, estado explícito `IPIM: no data` (nunca sintético en silencio). Stub determinístico solo como fallback marcado si no hay FX real. `dolarapi.com` es spot-only: no sirve como fuente histórica.

## TimesFM 3

`forecast/test_harness.py` intenta `import timesfm3`; si no está, baseline naive (last + drift, banda ±1.28σ). Con el checkpoint (`google/timesfm-3.0-pytorch`) corre zero-shot. Covariables vía `past_only_covariates`. **Nota de licencia**: Google restringe los pesos preentrenados de TimesFM 3 a uso no-comercial/no-producción — el sitio en producción usa el drift liviano; TimesFM vive solo en evaluación. Las 4 configs pasan: `price_only` (nada), `plus_fx` (brecha + vol7 — NO niveles ni retornos del FX), `plus_fx_ipim` (+ IPIM lagged), `plus_fx_competitor` (+ mínimo competidor /1000). La tabla de eventos del reporte agrega POOL por configuración (no la primera serie).

## Archivos

- `utils.py:load_price_dataframe()` carga solo reales (`data/rosario-*.json`).
- `backtest.py`: backtest walk-forward del drift + baseline persistencia (solo reales, solo observados) → `data/backtest.json`.
- `build_next.py`: pronóstico T+1 del sitio — drift liviano SIN covariables (producción; TimesFM es no-comercial) → `data/forecast-next.json`.
- `test_harness.py`: evaluación TimesFM vs naive con capa de eventos + fallback accounting.
- `etl/rebuild_tables.py`: re-match de `data/raw/*.json` con el matcher vigente + reagregación (usado 2026-09-05 para limpiar pet food / no-comestibles).
- `report.py`: reporte HTML/PNG → `web/forecast.html`.
