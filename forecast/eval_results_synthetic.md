# Canasta Rosario — TimesFM 3 Evaluación

Rango: 2026-08-01 -> 2026-09-01 — 7 archivos — 125 series (≥4 obs)

> Covariables: FX source: dolarapi.com (past_only brecha+vol7) + IPIM stub + competidor — TimesFM 3 con covariables (b3sti4 4060, divergencia real)

> Motor: TimesFM 3 (b3sti4 4060, covariates wired)

## Agregado por configuración

| Config | MAE | MAPE % | RMSE | Coverage 10-90 | n |
|---|---|---|---|---|---|
| price_only | 150.3 | 3.1 | 263.3 | 0.70 | 3381 |
| plus_fx | 146.6 | 3.0 | 256.7 | 0.72 | 3381 |
| plus_fx_ipim | 145.1 | 3.0 | 254.1 | 0.72 | 3381 |
| plus_fx_competitor | 142.0 | 2.9 | 248.7 | 0.72 | 3381 |


## Por categoría (MAE promedio)

| Categoría | price_only | plus_fx | plus_fx_ipim | plus_fx_competitor |
|---|---|---|---|---|
| Almacén | 36.4 | 33.5 | 32.8 | 32.0 |
| Carnes | 196.4 | 192.5 | 189.7 | 187.2 |
| Conservas | 34.9 | 34.3 | 34.0 | 33.7 |
| Frescos | 11.2 | 11.0 | 11.0 | 10.9 |
| Infusiones | 230.7 | 228.6 | 226.5 | 222.8 |
| Limpieza | 108.4 | 106.9 | 105.3 | 104.2 |
| Lácteos | 261.7 | 252.2 | 250.0 | 241.9 |
| Panificados | 73.0 | 71.7 | 71.2 | 70.8 |
| Verdulería | 280.3 | 275.8 | 273.5 | 267.4 |