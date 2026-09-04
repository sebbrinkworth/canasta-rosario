# Canasta Rosario — TimesFM 3 Evaluación

Rango: 2026-08-01 -> 2026-09-03 — 9 archivos — 125 series (≥4 obs)

> Covariables: FX real: bluelytics.com.ar diario (blue/oficial); IPIM real: INDEC 448.1_NIVEL_GENERAL_0_0_13_46 mensual interpolado diario (series-tiempo 448.1_NIVEL_GENERAL_0_0_13_46 (cache data/covariates/ipim_series_tiempo.csv))

> Motor: TimesFM 3

## Agregado por configuración

| Config | MAE | MAPE % | RMSE | Coverage 10-90 | n |
|---|---|---|---|---|---|
| price_only | 118.1 | 2.7 | 214.5 | 0.72 | 3491 |
| plus_fx | 117.7 | 2.6 | 214.1 | 0.72 | 3491 |
| plus_fx_ipim | 117.6 | 2.7 | 215.7 | 0.71 | 3491 |
| plus_fx_competitor | 116.6 | 2.6 | 212.5 | 0.73 | 3491 |


## Por categoría (MAE promedio)

| Categoría | price_only | plus_fx | plus_fx_ipim | plus_fx_competitor |
|---|---|---|---|---|
| Almacén | 29.3 | 28.1 | 28.5 | 27.7 |
| Carnes | 157.2 | 150.4 | 155.1 | 149.9 |
| Conservas | 28.6 | 29.2 | 30.2 | 29.0 |
| Frescos | 8.3 | 8.1 | 8.3 | 8.1 |
| Infusiones | 158.9 | 158.2 | 157.5 | 157.3 |
| Limpieza | 81.4 | 81.3 | 82.3 | 82.3 |
| Lácteos | 200.2 | 192.7 | 193.2 | 190.3 |
| Panificados | 80.8 | 90.4 | 88.8 | 89.1 |
| Verdulería | 225.1 | 230.6 | 226.5 | 227.4 |