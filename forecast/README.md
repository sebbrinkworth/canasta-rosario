# Forecast — Canasta Rosario × TimesFM 3

**Datos reales únicamente.** El preview sintético (30 días) se eliminó el 2026-09-04
por transparencia: nada sintético alimenta el sitio ni la evaluación. CKAN conserva
una ventana rodante de 7 días, pero existe un archivo público de SEPA mantenido
por Preciazo que permite recuperar fechas anteriores. `etl/backfill.py` importa
ese archivo, conserva la procedencia y deja explícitos los huecos y las revisiones
inválidas. Más historia no garantiza mayor precisión.

## Backfill y evaluación por etapas

Ver [comparación de historia](history-evaluation/report.md) y sus resultados JSON:
14 días originales, incorporación de julio/agosto, y resto del archivo disponible.
Las tres etapas usan los mismos 860 objetivos de septiembre, con entrenamiento
anterior a cada objetivo, persistencia, drift, persistencia semanal, regresión
sobre retornos y TimesFM 3 real (solo investigación). No se ajustan parámetros
con los resultados del período de prueba.

```bash
uv sync --extra evaluation
# zstd debe estar instalado; TimesFM se instala aparte para investigación.
uv run --no-sync python -m etl.backfill --start 2026-07-01 --end 2026-08-31
uv run --no-sync python -m forecast.evaluate_history --stage full
uv run --no-sync python -m forecast.report_history
```

La evaluación `full` requiere los resultados anteriores `baseline.json` y
`july-august.json`. El reporte documenta cómo recrear las etapas.
Las importaciones son reanudables y no modifican `latest.json` ni reemplazan
observaciones locales existentes. Los crudos nuevos están en
`data/raw/rosario-*.json.gz`; `etl/rebuild_tables.py` acepta JSON y JSON gzip.
Se conservan `product_id`, `bandera_id`, `branch_id` y el indicador EAN por
separado. Los prefijos de fabricante no clasifican alimentos. Las identidades
con filas contradictorias se conservan para auditoría y se excluyen del agregado.
Los huecos largos reinician el contexto; no se compactan fechas discontinuas.

Próximos pasos: [experimentos propuestos](next-experiments.md), con validación
en varios períodos, seguimiento del mismo producto, promociones y competidores.
El evaluador acepta `--device auto|cpu|cuda`; `auto` usa CUDA si está disponible
en la máquina donde se ejecuta. Las tres evaluaciones guardadas usaron CPU.

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

La evaluación inicial tenía <30 días reales y ~92% de pares día-a-día planos.
La sección de evaluación del sitio informa los aciertos de movimiento y mantiene los resultados experimentales en una sección desplegable,
separados de la tabla de precios observados. Las flechas de pronóstico del método liviano aparecen junto a los precios en «Toda la zona»; el valor estimado y su variación se muestran al tocar el precio.

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


## Datos corregidos — 2026-09-06

La historia utiliza `package-price-v2`: precio de lista dividido por contenido
verificado del envase. Se reconstruyeron los 11 días y se recalcularon el drift
y su backtest. Ver [validación de cantidades](../docs/validation.md).

La corrida TimesFM guardada en `eval_results.*` y sus gráficos es **histórica**
(`status: superseded`): usa los precios anteriores y no debe compararse con el
backtest actual. El sitio la identifica como pendiente de reevaluación. Al
repetir el harness, el resultado nuevo registra `price_normalization_version`
y reemplaza el aviso histórico.
