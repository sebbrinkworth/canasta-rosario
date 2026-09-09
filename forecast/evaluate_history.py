"""Paired chronological evaluation of staged history backfills.

The baseline run fixes a September test cohort. Subsequent stages predict the
same targets with more past data. No test-set tuning; all learned parameters
use dates strictly before the forecast date. TimesFM is research-only here.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from etl.backfill import atomic_json
from etl.etl import ROOT

MODELS = ("persistence", "drift5", "weekly_persistence", "ridge_returns", "timesfm3")
THRESHOLD = 0.008
MIN_HISTORY = 4
MAX_CONTEXT = 512
RIDGE_ALPHA = 100.0


def load_panel(directory):
    records, identities, versions, hashes = {}, {}, set(), {}
    for path in sorted(Path(directory).glob("rosario-*.json")):
        blob = path.read_bytes()
        obj = json.loads(blob)
        day = obj["date"]
        versions.add(obj.get("price_normalization_version"))
        hashes[day] = hashlib.sha256(blob).hexdigest()
        records[day], identities[day] = {}, {}
        for row in obj["table"]:
            for chain, cell in row["prices"].items():
                key = f"{row['id']}__{chain}"
                if cell and cell.get("price_per_unit") and np.isfinite(cell["price_per_unit"]):
                    records[day][key] = float(cell["price_per_unit"])
                    identities[day][key] = f"{cell.get('desc', '')}|{cell.get('marca', '')}"
    if versions != {"package-price-v2"}:
        raise ValueError(f"Mixed or unsupported price normalizations: {versions}")
    if not records:
        raise ValueError("No daily snapshots")
    panel = pd.DataFrame.from_dict(records, orient="index").sort_index()
    panel.index = pd.to_datetime(panel.index)
    panel = panel.reindex(pd.date_range(panel.index.min(), panel.index.max(), freq="D"))
    desc = pd.DataFrame.from_dict(identities, orient="index")
    desc.index = pd.to_datetime(desc.index)
    desc = desc.reindex(index=panel.index, columns=panel.columns).fillna("")
    return panel, desc, hashes


def trailing_history(values, t, limit=MAX_CONTEXT):
    """A long missing interval resets context; never compact across a gap."""
    h = values[max(0, t - limit):t]
    missing = np.flatnonzero(~np.isfinite(h))
    if len(missing):
        h = h[missing[-1] + 1:]
    return h


def numeric_features(h, day_of_week):
    last = h[-1]
    r = np.diff(h) / h[:-1]
    recent = h[-28:]
    moves = np.flatnonzero(np.abs(r) >= THRESHOLD)
    age = min(len(r) - 1 - moves[-1], 28) if len(moves) else min(len(r), 28)
    return [
        float(np.clip(r[-1], -.5, .5)),
        *[float(np.clip(np.mean(r[-n:]), -.5, .5)) for n in (3, 7, 28)],
        float(min(np.std(r[-7:]), .5)),
        float(np.clip(np.min(recent) / last - 1, -.5, .5)),
        float(np.clip(np.max(recent) / last - 1, -.5, .5)),
        age / 28.0,
        *[float(day_of_week == d) for d in range(7)],
    ]


def build_examples(panel, descriptions):
    observed = panel.notna().to_numpy()
    values = panel.ffill(limit=2).to_numpy()
    raw = panel.to_numpy()
    pids = sorted({c.split("__")[0] for c in panel.columns})
    chains = sorted({c.split("__")[1] for c in panel.columns})
    examples, features, outcomes = [], [], []
    for ci, column in enumerate(panel.columns):
        pid, chain = column.split("__")
        cat = [float(pid == x) for x in pids] + [float(chain == x) for x in chains]
        for t in range(1, len(panel)):
            # Real observations today and yesterday define a one-calendar-day
            # target; forward-filled targets or stale reference prices do not.
            if not (observed[t, ci] and observed[t - 1, ci]):
                continue
            h = trailing_history(values[:, ci], t)
            if len(h) < MIN_HISTORY:
                continue
            day = panel.index[t]
            actual, last = raw[t, ci], raw[t - 1, ci]
            examples.append({"date": str(day.date()), "series": column, "t": t, "ci": ci,
                             "last": last, "actual": actual,
                             "description_changed": bool(descriptions.iloc[t, ci] != descriptions.iloc[t - 1, ci])})
            features.append(numeric_features(h, day.dayofweek) + cat)
            outcomes.append(actual / last - 1)
    return examples, np.asarray(features, dtype=float), np.asarray(outcomes, dtype=float), values


def direction(change):
    return "stable" if abs(change) < THRESHOLD else ("up" if change > 0 else "down")


def score(rows, model):
    usable = [r for r in rows if r["predictions"].get(model) is not None]
    if not usable:
        return {"n": 0}
    errors = np.array([abs(r["predictions"][model] - r["actual"]) for r in usable])
    real = [direction(r["actual"] / r["last"] - 1) for r in usable]
    pred = [direction(r["predictions"][model] / r["last"] - 1) for r in usable]
    classes = {}
    for cls in ("up", "down", "stable"):
        tp = sum(p == a == cls for p, a in zip(pred, real))
        npred, nactual = pred.count(cls), real.count(cls)
        precision = tp / npred if npred else None
        recall = tp / nactual if nactual else None
        f1 = 2 * tp / (npred + nactual) if npred + nactual else None
        classes[cls] = {"predicted": npred, "actual": nactual, "true_positive": tp,
                        "precision_pct": precision * 100 if precision is not None else None,
                        "recall_pct": recall * 100 if recall is not None else None,
                        "f1": f1}
    persistence_errors = np.array([abs(r["last"] - r["actual"]) for r in usable])
    return {"n": len(usable), "mae": float(errors.mean()),
            "mape_pct": float(np.mean(errors / np.array([r["actual"] for r in usable])) * 100),
            "direction_accuracy_pct": sum(p == a for p, a in zip(pred, real)) / len(real) * 100,
            "mae_skill_vs_persistence_pct": float((1 - errors.mean() / persistence_errors.mean()) * 100) if persistence_errors.mean() else None,
            "classes": classes}


def paired_change(before, after, model):
    old = {(r["date"], r["series"]): r for r in before}
    day_totals = {}
    for row in after:
        prev = old.get((row["date"], row["series"]))
        if prev is None or prev["predictions"].get(model) is None or row["predictions"].get(model) is None:
            continue
        if prev["actual"] != row["actual"] or prev["last"] != row["last"]:
            raise ValueError("Paired comparison has changed target/reference values")
        delta = abs(row["predictions"][model] - row["actual"]) - abs(prev["predictions"][model] - prev["actual"])
        totals = day_totals.setdefault(row["date"], [0.0, 0])
        totals[0] += delta
        totals[1] += 1
    if not day_totals:
        return {"n": 0}
    totals = np.array(list(day_totals.values()))
    rng = np.random.default_rng(20260909)
    # Cluster by test day: product forecasts from one day are not independent.
    samples = rng.integers(0, len(totals), size=(2000, len(totals)))
    draw = totals[samples].sum(axis=1)
    deltas = draw[:, 0] / draw[:, 1]
    return {"n": int(totals[:, 1].sum()), "mae_delta": float(totals[:, 0].sum() / totals[:, 1].sum()),
            "day_bootstrap_95pct": [float(x) for x in np.quantile(deltas, [.025, .975])],
            "test_days": len(totals), "interpretation": "Negative MAE delta is improvement; only eight test days, exploratory interval."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--stage", choices=("baseline", "july-august", "full"), required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "forecast/history-evaluation")
    parser.add_argument("--test-start", default="2026-09-01")
    parser.add_argument("--test-end", default="2026-09-08")
    parser.add_argument("--skip-timesfm", action="store_true")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto",
                        help="TimesFM device on this host; auto uses CUDA when available")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    panel, desc, hashes = load_panel(args.data)
    examples, x, y, values = build_examples(panel, desc)
    baseline_path = args.output / "baseline.json"
    baseline = json.loads(baseline_path.read_text()) if args.stage != "baseline" else None
    wanted = {(r["date"], r["series"]) for r in baseline["predictions"]} if baseline else None
    selected = [i for i, row in enumerate(examples)
                if args.test_start <= row["date"] <= args.test_end
                and (wanted is None or (row["date"], row["series"]) in wanted)]
    if wanted is not None and len(selected) != len(wanted):
        raise ValueError("Expanded panel cannot predict every baseline test target")
    if baseline:
        for day in sorted({examples[i]["date"] for i in selected}):
            if hashes[day] != baseline["target_snapshot_sha256"][day]:
                raise ValueError(f"Test snapshot changed: {day}")
    model, model_error, selected_device = None, None, None
    if not args.skip_timesfm:
        try:
            import torch
            from timesfm3 import TimesFM3Forecaster
            torch.set_num_threads(2)
            selected_device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
            if selected_device == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("CUDA requested but unavailable on this host; run on the GPU machine or use --device cpu")
            model = TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch", device=selected_device)
        except Exception as exc:
            model_error = str(exc)
    engines = {"ridge_alpha": RIDGE_ALPHA, "timesfm_checkpoint": "google/timesfm-3.0-pytorch",
               "timesfm_device": selected_device, "timesfm_requested_device": args.device,
               "timesfm_loaded": model is not None, "timesfm_error": model_error,
               "timesfm_fallbacks": 0, "timesfm_failures": 0, "weekly_fallbacks": 0}
    engines["package_versions"] = {}
    for package in ("numpy", "pandas", "scikit-learn", "timesfm", "torch"):
        try:
            engines["package_versions"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            engines["package_versions"][package] = None
    @lru_cache(maxsize=2000)
    def timesfm_predict(context):
        result = model.predict(context=np.array(context), horizon=1, return_quantiles=False)
        p = float(np.asarray(result.forecast).ravel()[0])
        if not np.isfinite(p) or p <= 0:
            raise ValueError("TimesFM produced an invalid price")
        return p
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    example_dates = np.array([row["date"] for row in examples])
    predictions = []
    started = time.monotonic()
    for day in sorted({examples[i]["date"] for i in selected}):
        train = example_dates < day
        # All hyperparameters are fixed before the first stage. Training on
        # returns permits pooling older price levels without nominal-price drift.
        reg = make_pipeline(StandardScaler(), Ridge(alpha=RIDGE_ALPHA))
        reg.fit(x[train], np.clip(y[train], -.3, .3))
        today = [i for i in selected if examples[i]["date"] == day]
        ridge_predictions = np.clip(reg.predict(x[today]), -.3, .3)
        for i, ret in zip(today, ridge_predictions):
            row = dict(examples[i])
            h = trailing_history(values[:, row["ci"]], row["t"])
            weekly = h[-7] if len(h) >= 7 else row["last"]
            engines["weekly_fallbacks"] += int(len(h) < 7)
            pred = {"persistence": row["last"], "drift5": float(h[-1] + np.diff(h[-7:])[-5:].mean()),
                    "weekly_persistence": float(weekly), "ridge_returns": float(row["last"] * (1 + ret)), "timesfm3": None}
            if model is not None:
                try:
                    pred["timesfm3"] = timesfm_predict(tuple(h))
                except Exception as exc:
                    engines["timesfm_failures"] += 1
                    row["timesfm_error"] = str(exc)
            row["predictions"] = pred
            row["context_days"] = len(h)
            row["training_examples"] = int(train.sum())
            del row["t"], row["ci"]
            predictions.append(row)
        print(f"{args.stage} {day}: {len(today)} targets, {train.sum()} training examples, {time.monotonic()-started:.1f}s", flush=True)
    predictions.sort(key=lambda r: (r["date"], r["series"]))
    movement = [r for r in predictions if direction(r["actual"] / r["last"] - 1) != "stable"]
    result = {
        "stage": args.stage, "created_at": datetime.now(timezone.utc).isoformat(),
        "history_start": str(panel.index.min().date()), "history_end": str(panel.index.max().date()),
        "snapshot_days": len(hashes), "calendar_days": len(panel),
        "test_start": args.test_start, "test_end": args.test_end,
        "price_normalization_version": "package-price-v2",
        "protocol": {"threshold_pct": THRESHOLD * 100, "min_context_days": MIN_HISTORY,
                     "max_context_days": MAX_CONTEXT, "max_ffill_days": 2,
                     "target_policy": "Observed today and yesterday, >=4 contiguous context days after max 2-day ffill; long gaps reset context",
                     "training_policy": "Expanding walk-forward, dates strictly earlier than target; hyperparameters fixed; no test-set tuning",
                     "availability_limit": "Observation-date backtest: historical first-seen/capture times are retained but not enforced as intraday publication cutoffs",
                     "scope": "Next-day category/chain cheapest price; no claim of same-SKU accuracy or weekly-horizon improvement",
                     "timesfm_usage": "Research evaluation only; no production model change"},
        "target_snapshot_sha256": {day: hashes[day] for day in sorted({r["date"] for r in predictions})},
        "engines": engines, "metrics": {m: score(predictions, m) for m in MODELS},
        "assortment": {"movement_targets": len(movement), "with_description_change": sum(r["description_changed"] for r in movement)},
        "predictions": predictions,
    }
    if baseline:
        result["paired_change_vs_baseline"] = {m: paired_change(baseline["predictions"], predictions, m) for m in MODELS}
    if args.stage == "full":
        previous = json.loads((args.output / "july-august.json").read_text())
        result["paired_change_vs_july_august"] = {m: paired_change(previous["predictions"], predictions, m) for m in MODELS}
    atomic_json(args.output / f"{args.stage}.json", result)
    print(json.dumps(result["metrics"], indent=2), flush=True)
    if not args.skip_timesfm and (model is None or engines["timesfm_failures"]):
        raise SystemExit("TimesFM evaluation incomplete; failures are explicit in output")


if __name__ == "__main__":
    main()
