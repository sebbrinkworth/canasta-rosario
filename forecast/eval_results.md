# Canasta Rosario — TimesFM 3 Evaluación

Rango: 2026-08-26 -> 2026-09-05 — 11 archivos — 110 series (≥4 obs)

> Covariables: FX real: bluelytics.com.ar diario (blue/oficial); IPIM real: INDEC 448.1_NIVEL_GENERAL_0_0_13_46 mensual, último publicado a cada fecha (lag 60d, step-forward sin interpolar futuro; 11/11 días con valor; series-tiempo 448.1_NIVEL_GENERAL_0_0_13_46 (cache vencida data/covariates/ipim_series_tiempo.csv))

> Motor: TimesFM 3

## Agregado por configuración

| Config | MAE | MAPE % | RMSE | Coverage 10-90 | n |
|---|---|---|---|---|---|
| price_only | 65.9 | 1.6 | 117.1 | 0.86 | 1085 |
| plus_fx | 65.7 | 1.6 | 117.3 | 0.86 | 1085 |
| plus_fx_ipim | 65.0 | 1.6 | 116.8 | 0.86 | 1085 |
| plus_fx_competitor | 65.5 | 1.6 | 117.4 | 0.85 | 1085 |


> Precisión de eventos (umbral 0.8%) — POOL global por configuración (todas las series). De las veces que el modelo dijo ↑/↓, cuántas acertó; recall = de los movimientos reales, cuántos anticipó. Solo observaciones reales.

| Config | ↑ prec (d) | ↑ recall (d) | ↓ prec (d) | ↓ recall (d) | ↑ prec (w7) | ↓ prec (w7) |
|---|---|---|---|---|---|---|
| price_only | 19.6% (n=46) | 23.1% | 10.5% (n=38) | 11.1% | 11.8% | 44.4% |
| plus_fx | 19.5% (n=41) | 20.5% | 9.8% (n=41) | 11.1% | 11.8% | 44.4% |
| plus_fx_ipim | 19.6% (n=46) | 23.1% | 8.7% (n=46) | 11.1% | 11.8% | 44.4% |
| plus_fx_competitor | 20.5% (n=44) | 23.1% | 9.5% (n=42) | 11.1% | 11.8% | 44.4% |

> Fallbacks naive durante la corrida: **2220** predicciones; covariables descartadas por TypeError: **0**. Las celdas rellenadas excluidas del scoring: **180**.


## Por categoría (MAE promedio)

| Categoría | price_only | plus_fx | plus_fx_ipim | plus_fx_competitor |
|---|---|---|---|---|
| Almacén | 7.5 | 7.5 | 7.3 | 7.4 |
| Carnes | 178.8 | 181.8 | 175.4 | 180.2 |
| Conservas | 13.3 | 13.9 | 15.0 | 13.7 |
| Frescos | 11.5 | 12.6 | 12.0 | 12.6 |
| Infusiones | 24.1 | 24.3 | 24.3 | 24.2 |
| Limpieza | 59.8 | 60.0 | 61.8 | 60.7 |
| Lácteos | 100.8 | 99.2 | 99.5 | 96.4 |
| Panificados | 163.7 | 150.3 | 153.4 | 148.3 |
| Verdulería | 94.9 | 96.6 | 92.9 | 99.4 |