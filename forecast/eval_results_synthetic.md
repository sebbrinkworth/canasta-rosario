# Canasta Rosario — TimesFM 3 Evaluación

Rango: 2026-08-01 -> 2026-09-03 — 9 archivos — 125 series (≥4 obs)

> Covariables: FX real: bluelytics.com.ar diario (blue/oficial); IPIM real: INDEC 448.1_NIVEL_GENERAL_0_0_13_46 mensual interpolado diario (series-tiempo 448.1_NIVEL_GENERAL_0_0_13_46 (cache data/covariates/ipim_series_tiempo.csv))

> Motor: Naive/MA baseline (TimesFM no instalado — `pip install timesfm`)

## Agregado por configuración

| Config | MAE | MAPE % | RMSE | Coverage 10-90 | n |
|---|---|---|---|---|---|
| price_only | 152.6 | 3.1 | 271.8 | 0.72 | 3491 |
| plus_fx | 152.6 | 3.1 | 271.8 | 0.72 | 3491 |
| plus_fx_ipim | 152.6 | 3.1 | 271.8 | 0.72 | 3491 |
| plus_fx_competitor | 152.6 | 3.1 | 271.8 | 0.72 | 3491 |


## Por categoría (MAE promedio)

| Categoría | price_only | plus_fx | plus_fx_ipim | plus_fx_competitor |
|---|---|---|---|---|
| Almacén | 34.7 | 34.7 | 34.7 | 34.7 |
| Carnes | 192.9 | 192.9 | 192.9 | 192.9 |
| Conservas | 34.6 | 34.6 | 34.6 | 34.6 |
| Frescos | 11.0 | 11.0 | 11.0 | 11.0 |
| Infusiones | 222.1 | 222.1 | 222.1 | 222.1 |
| Limpieza | 102.2 | 102.2 | 102.2 | 102.2 |
| Lácteos | 259.3 | 259.3 | 259.3 | 259.3 |
| Panificados | 90.9 | 90.9 | 90.9 | 90.9 |
| Verdulería | 301.5 | 301.5 | 301.5 | 301.5 |