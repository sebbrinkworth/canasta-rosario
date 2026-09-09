# Historical backfill and paired forecast evaluation

Test period: **2026-09-01–2026-09-08**, **860 identical category/chain targets** in every stage.

## Result

Adding July and August reduced TimesFM's MAE from **60.25 to 47.73** (**20.8% lower**) on the fixed September cohort.

The full-history stage contains **626 daily snapshots**, beginning **2024-08-19**. TimesFM's MAE is **47.73**.

The additional older periods did not change TimesFM's September forecasts: the long March–June 2026 gap resets its context. Older periods can still train the pooled regression, which is refitted on all eligible earlier observations at each forecast date.

The older history reduced pooled regression MAE from **85.33 to 81.82** (**4.1% lower**), but it remains worse than persistence. The current five-difference drift model did not improve on this fixed cohort; its short recent input window was already available in the original history.

## Mean absolute error — lower is better

| Model | Original 14 days | July/August: 70 days | Full archive |
|---|---:|---:|---:|
| Tomorrow = today | 50.36 | 50.36 | 50.36 |
| Current drift (5 differences) | 75.77 | 75.77 | 75.77 |
| Same weekday last week | 154.95 | 166.41 | 166.41 |
| Pooled ridge on price returns | 113.96 | 85.33 | 81.82 |
| TimesFM 3, prices only | 60.25 | 47.73 | 47.73 |

MAE averages errors in each category's normalized price unit (ARS/kg, ARS/L, or ARS/unit). The identical target cohort makes stage comparisons valid; percentage errors below also account for different price scales.

Persistence means predicting tomorrow's price equals today's price. For example, a price of ARS 1,000/kg today produces a forecast of ARS 1,000/kg tomorrow. It learns no trend and uses no external variables.

| Model | Original MAPE | July/August MAPE | Full MAPE |
|---|---:|---:|---:|
| Tomorrow = today | 1.28% | 1.28% | 1.28% |
| Current drift (5 differences) | 1.85% | 1.85% | 1.85% |
| Same weekday last week | 3.45% | 3.62% | 3.62% |
| Pooled ridge on price returns | 2.50% | 1.95% | 1.89% |
| TimesFM 3, prices only | 1.50% | 1.19% | 1.19% |

## Direction and movement detection

Latest completed stage; a movement is at least 0.8% in either direction. An undefined precision means the model never predicted that class.

| Model | Direction accuracy | Up precision | Up recall | Down precision | Down recall |
|---|---:|---:|---:|---:|---:|
| Tomorrow = today | 92.7% | — | 0.0% | — | 0.0% |
| Current drift (5 differences) | 80.2% | 1.5% | 2.7% | 0.0% | 0.0% |
| Same weekday last week | 78.4% | 20.5% | 48.6% | 7.9% | 26.9% |
| Pooled ridge on price returns | 70.9% | 13.6% | 56.8% | 9.8% | 38.5% |
| TimesFM 3, prices only | 90.5% | 46.4% | 35.1% | 20.6% | 26.9% |

There are **63 actual movement targets**; **43** also changed the cheapest option's description/brand. This evaluates the cheapest qualifying category offer, not repricing of an unchanged SKU.

## Strength of the evidence

- TimesFM, july-august versus original history: MAE change **-12.52**, day-cluster bootstrap 95% interval **[-22.56, -2.67]**.
- TimesFM, full versus original history: MAE change **-12.52**, day-cluster bootstrap 95% interval **[-22.56, -2.67]**.
- TimesFM, full versus July/August: MAE change **+0.00**, day-cluster bootstrap 95% interval **[+0.00, +0.00]**.
- Latest TimesFM versus persistence: MAE change **-2.63**, interval **[-14.73, +6.36]**.

There are only eight test days, and these stages reuse the same test cohort. The intervals are exploratory, not independent replications or proof of future performance. TimesFM's narrow MAE advantage over persistence does not establish a reliable production improvement. Persistence still deserves to be the reference baseline. No model was tuned on these test results or promoted to production.

## Protocol and provenance

- Target snapshots are frozen by SHA-256 and remain the original local September observations.
- All training examples precede the forecast date. Earlier test-day observations may enter later forecasts, as in daily operation.
- Missing dates remain calendar gaps. Only context is forward-filled, for at most two days; targets and yesterday's reference must both be observed.
- TimesFM uses at most 512 contiguous context days after that limited fill. No compaction across long gaps.
- The regression uses lagged returns, recent volatility/range, days since a movement, weekday, category, and chain. Standardization is fitted only on training data; ridge alpha is fixed at 100 and training/predicted returns are clipped to ±30%.
- The weekly persistence baseline uses today's price when seven prior context days are unavailable; fallback counts are in each result JSON.
- This isolates price-history length: no FX/IPIM covariates were added or changed between stages.
- These saved stages loaded the actual TimesFM checkpoint on CPU, with zero naive fallbacks: no failed model prediction was replaced by a simple baseline. CPU was an execution choice, not a model requirement. New runs accept --device auto/cpu/cuda; auto chooses CUDA on the host running the command.
- TimesFM 3 remains an evaluation model: it does not produce the site's daily estimates. The [pretrained-weight license](https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE) restricts use to non-commercial, non-production purposes. Separately, these eight test days do not establish dependable forecasting skill.
- This is an observation-date backtest. Archive capture/first-seen times are retained but are not enforced as historical intraday publication cutoffs.

## Import validation

The August 26 overlap had 107 identical prices out of 108 local cells, one different cheapest option, and two additional archive cells. Existing local snapshots were preserved. July/August added 56 dates without failures.

The importer preserves full product, banner, and branch IDs; manufacturer barcode prefixes no longer classify food categories. Conflicting source identities are quarantined with all variants in the raw audit file and excluded from aggregates. Misdated revisions are rejected and other indexed revisions are tried. Historical imports never rewind latest.json.

Each new aggregate records its source URL/revision, first-seen time, download SHA-256, compressed size, and importer version. Filtered raw candidates are stored locally as gzip JSON under data/raw/. The pinned archive index and batch manifests are in data/backfill/.

Completion audit: **626 snapshots**, **612 new**, **0 unresolved linked dates**. **122 calendar dates** have no indexed public download.

Rejected dates (all available revisions contain an earlier date): 2024-12-27, 2024-12-28, 2024-12-29.

## Reproduce

```bash
# ETL and evaluation dependencies; zstd must be available on PATH.
uv sync --extra evaluation
# TimesFM 3 is a separate research dependency used by these saved runs.
uv pip install 'timesfm==3.0.0'
uv run --no-sync python -m etl.backfill --start 2026-07-01 --end 2026-08-31 --index data/backfill/archive-index-2026-09-09.json
uv run --no-sync python -m forecast.evaluate_history --stage baseline --data data/research/baseline --device cpu
uv run --no-sync python -m forecast.evaluate_history --stage july-august --data data/research/july-august --device cpu
uv run --no-sync python -m etl.backfill --start 2024-08-19 --end 2026-06-30 --index data/backfill/archive-index-2026-09-09.json
uv run --no-sync python -m forecast.evaluate_history --stage full --device cpu
uv run --no-sync python -m forecast.report_history
```

The two staged data directories are local checkpoints, ignored by Git. To recreate them from the completed collection, copy only snapshots dated 2026-08-26 onward into baseline/ and 2026-07-01 onward into july-august/. The per-target predictions and scores are JSON artifacts alongside this report.

Source: [Preciazo public SEPA archive](https://github.com/catdevnull/sepa-precios-metadata/blob/main/index.md); original data: [SEPA](https://datos.produccion.gob.ar/dataset/sepa-precios), CC BY 4.0.
