# Canasta Rosario — TimesFM 3 Evaluación

Rango: 2026-06-04 → 2026-08-31 — 5 archivos — 112 series (≥4 obs)

> Covariables: FX source: dolarapi.com (histórico interpolado) — IPIM: stub

> Motor: Naive/MA baseline (TimesFM no instalado — `pip install timesfm`)

## Agregado por configuración

| Config | MAE | MAPE % | RMSE | Coverage 10-90 | n |
|---|---|---|---|---|---|
| price_only | 87.2 | 2.4 | 129.7 | 0.93 | 446 |
| plus_fx | 87.2 | 2.4 | 129.7 | 0.93 | 446 |
| plus_fx_ipim | 87.2 | 2.4 | 129.7 | 0.93 | 446 |
| plus_fx_competitor | 87.2 | 2.4 | 129.7 | 0.93 | 446 |


## Por categoría (MAE promedio)

| Categoría | price_only | plus_fx | plus_fx_ipim | plus_fx_competitor |
|---|---|---|---|---|
| Almacén | 3.1 | 3.1 | 3.1 | 3.1 |
| Carnes | 90.3 | 90.3 | 90.3 | 90.3 |
| Conservas | 3.4 | 3.4 | 3.4 | 3.4 |
| Frescos | 16.9 | 16.9 | 16.9 | 16.9 |
| Infusiones | 36.4 | 36.4 | 36.4 | 36.4 |
| Limpieza | 111.9 | 111.9 | 111.9 | 111.9 |
| Lácteos | 87.6 | 87.6 | 87.6 | 87.6 |
| Panificados | 0.0 | 0.0 | 0.0 | 0.0 |
| Verdulería | 280.5 | 280.5 | 280.5 | 280.5 |