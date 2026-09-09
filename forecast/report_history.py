"""Render the saved, paired history experiments as a reviewable Markdown report."""
import json
from pathlib import Path

from etl.etl import ROOT
from forecast.evaluate_history import MODELS, paired_change


def main():
    folder = ROOT / "forecast/history-evaluation"
    stages = {}
    for stage in ("baseline", "july-august", "full"):
        path = folder / f"{stage}.json"
        if path.exists():
            stages[stage] = json.loads(path.read_text())
    baseline, recent = stages["baseline"], stages["july-august"]
    final = stages.get("full")
    names = {"persistence": "Tomorrow = today", "drift5": "Current drift (5 differences)",
             "weekly_persistence": "Same weekday last week", "ridge_returns": "Pooled ridge on price returns",
             "timesfm3": "TimesFM 3, prices only"}
    def number(value, digits=2):
        return f"{value:.{digits}f}" if value is not None else "—"
    lines = [
        "# Historical backfill and paired forecast evaluation", "",
        f"Test period: **{baseline['test_start']}–{baseline['test_end']}**, "
        f"**{len(baseline['predictions'])} identical category/chain targets** in every stage.", "",
        "## Result", "",
    ]
    old_mae = baseline["metrics"]["timesfm3"]["mae"]
    recent_mae = recent["metrics"]["timesfm3"]["mae"]
    lines += [f"Adding July and August reduced TimesFM's MAE from **{old_mae:.2f} to {recent_mae:.2f}** "
              f"(**{(1-recent_mae/old_mae)*100:.1f}% lower**) on the fixed September cohort.", ""]
    if final:
        full_mae = final["metrics"]["timesfm3"]["mae"]
        lines += [f"The full-history stage contains **{final['snapshot_days']} daily snapshots**, beginning "
                  f"**{final['history_start']}**. TimesFM's MAE is **{full_mae:.2f}**.", ""]
        context_equal = all(a["context_days"] == b["context_days"] for a, b in zip(recent["predictions"], final["predictions"]))
        if context_equal and abs(full_mae - recent_mae) < 1e-6:
            lines += ["The additional older periods did not change TimesFM's September forecasts: "
                      "the long March–June 2026 gap resets its context. Older periods can still train the pooled regression, "
                      "which is refitted on all eligible earlier observations at each forecast date.", ""]
        ridge_recent = recent["metrics"]["ridge_returns"]["mae"]
        ridge_full = final["metrics"]["ridge_returns"]["mae"]
        lines += [f"The older history reduced pooled regression MAE from **{ridge_recent:.2f} to {ridge_full:.2f}** "
                  f"(**{(1-ridge_full/ridge_recent)*100:.1f}% lower**), but it remains worse than persistence. "
                  "The current five-difference drift model did not improve on this fixed cohort; "
                  "its short recent input window was already available in the original history.", ""]
    else:
        lines += ["The remaining older archive import/evaluation is in progress.", ""]
    lines += ["## Mean absolute error — lower is better", "",
              "| Model | Original 14 days | July/August: 70 days | Full archive |",
              "|---|---:|---:|---:|"]
    for model in MODELS:
        values = [number(stages[s]["metrics"][model].get("mae")) if s in stages else "Pending" for s in ("baseline", "july-august", "full")]
        lines.append(f"| {names[model]} | {' | '.join(values)} |")
    lines += ["", "MAE averages errors in each category's normalized price unit (ARS/kg, ARS/L, or ARS/unit). "
              "The identical target cohort makes stage comparisons valid; percentage errors below also account for different price scales.", "",
              "Persistence means predicting tomorrow's price equals today's price. For example, a price of ARS 1,000/kg "
              "today produces a forecast of ARS 1,000/kg tomorrow. It learns no trend and uses no external variables.", "",
              "| Model | Original MAPE | July/August MAPE | Full MAPE |", "|---|---:|---:|---:|"]
    for model in MODELS:
        values = [number(stages[s]["metrics"][model].get("mape_pct")) + "%" if s in stages else "Pending" for s in ("baseline", "july-august", "full")]
        lines.append(f"| {names[model]} | {' | '.join(values)} |")
    last = final or recent
    lines += ["", "## Direction and movement detection", "",
              "Latest completed stage; a movement is at least 0.8% in either direction. An undefined precision means the model never predicted that class.", "",
              "| Model | Direction accuracy | Up precision | Up recall | Down precision | Down recall |",
              "|---|---:|---:|---:|---:|---:|"]
    for model in MODELS:
        metrics = last["metrics"][model]
        cls = metrics["classes"]
        values = [metrics["direction_accuracy_pct"], cls["up"]["precision_pct"], cls["up"]["recall_pct"],
                  cls["down"]["precision_pct"], cls["down"]["recall_pct"]]
        lines.append(f"| {names[model]} | " + " | ".join(number(v, 1) + ("%" if v is not None else "") for v in values) + " |")
    ass = last["assortment"]
    lines += ["", f"There are **{ass['movement_targets']} actual movement targets**; "
              f"**{ass['with_description_change']}** also changed the cheapest option's description/brand. "
              "This evaluates the cheapest qualifying category offer, not repricing of an unchanged SKU.", "",
              "## Strength of the evidence", ""]
    for stage in ("july-august", "full"):
        if stage not in stages:
            continue
        current = stages[stage]
        for other_name, field in (("original history", "paired_change_vs_baseline"), ("July/August", "paired_change_vs_july_august")):
            if field not in current:
                continue
            m = current[field]["timesfm3"]
            lo, hi = m["day_bootstrap_95pct"]
            lines.append(f"- TimesFM, {stage} versus {other_name}: MAE change **{m['mae_delta']:+.2f}**, "
                         f"day-cluster bootstrap 95% interval **[{lo:+.2f}, {hi:+.2f}]**.")
    persistence_rows = [{**r, "predictions": {**r["predictions"], "timesfm3": r["last"]}} for r in last["predictions"]]
    difference = paired_change(persistence_rows, last["predictions"], "timesfm3")
    lo, hi = difference["day_bootstrap_95pct"]
    lines += [f"- Latest TimesFM versus persistence: MAE change **{difference['mae_delta']:+.2f}**, "
              f"interval **[{lo:+.2f}, {hi:+.2f}]**.", "",
              "There are only eight test days, and these stages reuse the same test cohort. "
              "The intervals are exploratory, not independent replications or proof of future performance. "
              "TimesFM's narrow MAE advantage over persistence does not establish a reliable production improvement. "
              "Persistence still deserves to be the reference baseline. No model was tuned on these test results or promoted to production.", "",
              "## Protocol and provenance", "",
              "- Target snapshots are frozen by SHA-256 and remain the original local September observations.",
              "- All training examples precede the forecast date. Earlier test-day observations may enter later forecasts, as in daily operation.",
              "- Missing dates remain calendar gaps. Only context is forward-filled, for at most two days; targets and yesterday's reference must both be observed.",
              "- TimesFM uses at most 512 contiguous context days after that limited fill. No compaction across long gaps.",
              "- The regression uses lagged returns, recent volatility/range, days since a movement, weekday, category, and chain. "
              "Standardization is fitted only on training data; ridge alpha is fixed at 100 and training/predicted returns are clipped to ±30%.",
              "- The weekly persistence baseline uses today's price when seven prior context days are unavailable; fallback counts are in each result JSON.",
              "- This isolates price-history length: no FX/IPIM covariates were added or changed between stages.",
              "- These saved stages loaded the actual TimesFM checkpoint on CPU, with zero naive fallbacks: no failed model prediction was replaced by a simple baseline. "
              "CPU was an execution choice, not a model requirement. New runs accept --device auto/cpu/cuda; auto chooses CUDA on the host running the command.",
              "- TimesFM 3 remains an evaluation model: it does not produce the site's daily estimates. "
              "The [pretrained-weight license](https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE) "
              "restricts use to non-commercial, non-production purposes. Separately, these eight test days do not establish dependable forecasting skill.",
              "- This is an observation-date backtest. Archive capture/first-seen times are retained but are not enforced as historical intraday publication cutoffs.", "",
              "## Import validation", "",
              "The August 26 overlap had 107 identical prices out of 108 local cells, one different cheapest option, "
              "and two additional archive cells. Existing local snapshots were preserved. July/August added 56 dates without failures.", "",
              "The importer preserves full product, banner, and branch IDs; manufacturer barcode prefixes no longer classify food categories. "
              "Conflicting source identities are quarantined with all variants in the raw audit file and excluded from aggregates. "
              "Misdated revisions are rejected and other indexed revisions are tried. Historical imports never rewind latest.json.", "",
              "Each new aggregate records its source URL/revision, first-seen time, download SHA-256, compressed size, and importer version. "
              "Filtered raw candidates are stored locally as gzip JSON under data/raw/. The pinned archive index and batch manifests are in data/backfill/.", ""]
    completion = ROOT / "data/backfill/completion.json"
    if completion.exists():
        audit = json.loads(completion.read_text())
        lines += [f"Completion audit: **{audit['snapshots']} snapshots**, **{audit['new_snapshots']} new**, "
                  f"**{len(audit['unresolved_linked_dates'])} unresolved linked dates**. "
                  f"**{len(audit['unavailable_dates'])} calendar dates** have no indexed public download.", ""]
        if audit.get("rejected_source_dates"):
            lines += ["Rejected dates (all available revisions contain an earlier date): "
                      + ", ".join(sorted(audit["rejected_source_dates"])) + ".", ""]
    lines += ["## Reproduce", "", "```bash",
              "# ETL and evaluation dependencies; zstd must be available on PATH.",
              "uv sync --extra evaluation",
              "# TimesFM 3 is a separate research dependency used by these saved runs.",
              "uv pip install 'timesfm==3.0.0'",
              "uv run --no-sync python -m etl.backfill --start 2026-07-01 --end 2026-08-31 --index data/backfill/archive-index-2026-09-09.json",
              "uv run --no-sync python -m forecast.evaluate_history --stage baseline --data data/research/baseline --device cpu",
              "uv run --no-sync python -m forecast.evaluate_history --stage july-august --data data/research/july-august --device cpu",
              "uv run --no-sync python -m etl.backfill --start 2024-08-19 --end 2026-06-30 --index data/backfill/archive-index-2026-09-09.json",
              "uv run --no-sync python -m forecast.evaluate_history --stage full --device cpu",
              "uv run --no-sync python -m forecast.report_history", "```", "",
              "The two staged data directories are local checkpoints, ignored by Git. To recreate them from the completed collection, "
              "copy only snapshots dated 2026-08-26 onward into baseline/ and 2026-07-01 onward into july-august/. "
              "The per-target predictions and scores are JSON artifacts alongside this report.", "",
              "Source: [Preciazo public SEPA archive](https://github.com/catdevnull/sepa-precios-metadata/blob/main/index.md); "
              "original data: [SEPA](https://datos.produccion.gob.ar/dataset/sepa-precios), CC BY 4.0.", ""]
    (folder / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(folder / "report.md")


if __name__ == "__main__":
    main()
