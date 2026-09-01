# Canasta Rosario — TimesFM 3 Evaluación

Rango: 2026-08-01 → 2026-09-01 — 7 archivos — 125 series (≥4 obs)

> Covariables: FX source: dolarapi.com (histórico interpolado) — IPIM: stub

> Motor: Naive/MA baseline (TimesFM no instalado — `pip install timesfm`)

## Agregado por configuración

| Config | MAE | MAPE % | RMSE | Coverage 10-90 | n |
|---|---|---|---|---|---|
| price_only | 150.3 | 3.1 | 263.3 | 0.70 | 3381 |
| plus_fx | 150.3 | 3.1 | 263.3 | 0.70 | 3381 |
| plus_fx_ipim | 150.3 | 3.1 | 263.3 | 0.70 | 3381 |
| plus_fx_competitor | 150.3 | 3.1 | 263.3 | 0.70 | 3381 |


## Por categoría (MAE promedio)

| Categoría | price_only | plus_fx | plus_fx_ipim | plus_fx_competitor |
|---|---|---|---|---|
| Almacén | 36.4 | 36.4 | 36.4 | 36.4 |
| Carnes | 196.4 | 196.4 | 196.4 | 196.4 |
| Conservas | 34.9 | 34.9 | 34.9 | 34.9 |
| Frescos | 11.2 | 11.2 | 11.2 | 11.2 |
| Infusiones | 230.7 | 230.7 | 230.7 | 230.7 |
| Limpieza | 108.4 | 108.4 | 108.4 | 108.4 |
| Lácteos | 261.7 | 261.7 | 261.7 | 261.7 |
| Panificados | 73.0 | 73.0 | 73.0 | 73.0 |
| Verdulería | 280.3 | 280.3 | 280.3 | 280.3 |