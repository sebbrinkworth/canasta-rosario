# Next forecast experiments after the historical backfill

The collection now has 626 daily snapshots, but not 626 consecutive dates.
The September comparison uses only eight test days. It measures the cheapest
qualifying category offer in each chain, which can change because a different
product becomes cheapest. Of its 63 price movements, 43 also change the recorded
description or brand. Better prediction requires handling this target explicitly.

## Execution and deployment

The three saved history experiments ran on CPU because the evaluation script
explicitly selected CPU. This was an execution choice, not a TimesFM limitation.
The evaluator now accepts `--device auto`, `--device cpu`, and `--device cuda`.
Auto selects CUDA when it is available on the machine running the command;
it does not dispatch work to another machine by itself.

On 2026-09-09, the existing remote RTX 4060 / 8 GB environment was checked over
SSH. CUDA and TimesFM 3 were available. One actual saved September target was
recomputed on the GPU and matched its saved CPU forecast exactly. This smoke
check is not a GPU rerun of the full benchmark. Future GPU benchmark runs should
use a separate output directory and record dependency versions, device, and
target hashes; small numerical differences across devices are possible.

TimesFM 3 is evaluated offline and does not generate the website's daily
estimates. Its [weight license](https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE)
restricts use to non-commercial, non-production purposes, including derivatives.
An experiment label does not make a live prediction service exempt. Separately,
forecast quality still needs broader validation. Google's
[repository](https://github.com/google-research/timesfm#license-notice-for-pretrained-weights)
states that weights through TimesFM 2.5 remain Apache-2.0, making 2.5 a candidate
to evaluate for eventual deployment alongside conventional models.

## Proposed sequence

1. **Broaden chronological validation.** Use several untouched test blocks across
   2024, 2025, and 2026, always fitting on earlier data. Choose settings on earlier
   validation blocks and keep a final block untouched. Report 1-, 7-, and 14-day
   errors, movement precision/recall, and uncertainty coverage. Compare every
   model with persistence on identical observed targets; do not bridge long gaps.
2. **Separate product prices from assortment changes.** Build stable
   product/banner/branch series using the retained raw IDs. Evaluate same-product
   repricing separately from the cheapest category offer. Exclude conflicting
   identities and flag missing offers. Absence in SEPA does not prove stockout.
3. **Fit a pooled movement model.** Test a classifier for whether a price changes,
   followed by a regression for the size/direction of a change. Gradient-boosted
   trees are a candidate alongside the current ridge regression. Pooling across
   products can learn from older segments even when a long gap resets one
   series' immediate forecast context. Evaluate the final combined price forecast
   as well as the classifier; do not report only accuracy on mostly stable days.
4. **Add feature groups one at a time.** Keep the targets, folds, and evaluation
   procedure fixed, so each comparison measures the added information.

| Priority | Candidate inputs | Timing and interpretation |
|---|---|---|
| First | Days since last price change, lagged returns, volatility, weekday, month-end and holidays | Extend the existing lag/weekday features. Future calendar values are known; future prices are not. |
| First | Own price relative to yesterday's competitors, competitor recent changes, cross-chain price dispersion | Compute only from observations available at the forecast cutoff. |
| First | Promotion indicator and discount depth, cheapest-product switch, number of reported qualifying offers | Raw candidates retain promotion fields and IDs. Promotion conditions may differ from an unconditional price; validate field coverage first. |
| Next | Official and blue FX changes over 7/14/30 days, exchange-rate gap and volatility | Test lagged changes rather than only nominal levels. Use actual historical observations, never simulated fallback values. |
| Next | Food/wholesale price indices and inflation releases | Use the last release actually published by the cutoff, with vintage/revision tracking where available. A fixed publication lag is only an approximation. |

The older `forecast/covariates.py` already has FX, IPIM, and competitor plumbing.
It needs an audit before reuse: it can synthesize FX after a fetch failure, and
the old harness can drop covariates or substitute a naive forecast. The new
experiments should fail or explicitly exclude unavailable feature groups,
without mixing substitute forecasts into a named-model result.

TimesFM 3 supports multivariate targets and past-only or past-and-future
covariates according to its [official examples](https://github.com/google-research/timesfm#2-multivariate-forecasting-with-covariates).
That makes joint chain forecasts plus competitor/calendar inputs a useful
research comparison. Known calendar variables may extend into the forecast
horizon; observed FX and competitor prices must stop at the cutoff.

These are proposed experiments, not measured improvements. More history does
not itself fine-tune TimesFM: our saved runs use its unchanged pretrained weights
and supply a longer input context. The pooled regression actually refits on
the older training examples.
