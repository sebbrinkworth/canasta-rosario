"""Audit completed backfills and reconcile successful recovery passes."""
import gzip
import json
import math
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from etl.backfill import atomic_json
from etl.etl import ROOT


def main():
    data = ROOT / "data"
    index = json.loads((data / "backfill/archive-index-2026-09-09.json").read_text())
    linked = {d for d, entries in index.items() if any(x.get("link") for x in entries)}
    files = sorted(data.glob("rosario-*.json"))
    present, cells, versions = {}, {}, Counter()
    bytes_downloaded = raw_observations = conflicts = new = 0
    for path in files:
        obj = json.loads(path.read_text())
        day = obj["date"]
        assert path.name == f"rosario-{day}.json", path
        assert obj["price_normalization_version"] == "package-price-v2", path
        count = 0
        for row in obj["table"]:
            for cell in row["prices"].values():
                if cell is None:
                    continue
                value = cell["price_per_unit"]
                assert math.isfinite(value) and value > 0, (path, row["id"])
                qty = cell.get("normalized_quantity")
                if qty:
                    assert math.isclose(value, cell["price_lista"] / qty, abs_tol=.011), (path, row["id"])
                count += 1
        cells[day] = count
        source = obj.get("source")
        present[day] = {"status": "imported" if source else "original", "cells": count}
        if not source:
            continue
        new += 1
        assert any(entry.get("link") == source["url"] and entry["id"] == source["revision"] for entry in index[day]), path
        raw = data / "raw" / (path.name + ".gz")
        with gzip.open(raw, "rt", encoding="utf-8") as stream:
            raw_obj = json.load(stream)
        assert raw_obj["date"] == day and raw_obj["source"]["sha256"] == source["sha256"], raw
        assert raw_obj["price_normalization_version"] == "package-price-v2", raw
        rows = raw_obj["observations"]
        raw_observations += len(rows)
        flagged = sum(bool(row.get("identity_conflict")) for row in rows)
        conflicts += flagged
        present[day].update(source=source, raw_observations=len(rows), conflicting_identities_excluded=flagged)
        bytes_downloaded += source["compressed_bytes"]
        versions[source["import_version"]] += 1
    missing = sorted(linked - present.keys())
    attempts = {}
    # Recovery manifests are evidence for rejected dates; earlier failed passes
    # remain intact even when a later pass successfully imports that date.
    for path in sorted((data / "backfill").glob("*.json")):
        if path.name == "archive-index-2026-09-09.json":
            continue
        obj = json.loads(path.read_text())
        for day, result in obj.get("days", {}).items():
            if day in missing and result.get("rejected_revisions"):
                attempts[day] = result["rejected_revisions"]
    rejected = {}
    for day in missing:
        entries = [e for e in index[day] if e.get("link")]
        tried = attempts.get(day, [])
        if ({e["id"] for e in entries} <= {e["revision"] for e in tried}
                and all("Archive date mismatch" in e["error"] for e in tried)):
            rejected[day] = {"reason": "Every indexed revision contains a different date", "attempts": tried}
    calendar = []
    day, last = date.fromisoformat(min(present)), date.fromisoformat(max(present))
    while day <= last:
        calendar.append(str(day))
        day += timedelta(days=1)
    unavailable = sorted(set(calendar) - linked - present.keys())
    result = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": len(files), "new_snapshots": new, "original_snapshots": len(files) - new,
        "first_date": min(present), "last_date": max(present), "calendar_days": len(calendar),
        "indexed_linked_dates": len(linked), "unavailable_dates": unavailable,
        "unresolved_linked_dates": sorted(set(missing) - rejected.keys()),
        "rejected_source_dates": rejected,
        "raw_observations_imported": raw_observations,
        "conflicting_identities_excluded": conflicts,
        "validated_archive_bytes": bytes_downloaded,
        "importer_versions": dict(versions),
        "cell_count_min": min(cells.values()), "cell_count_max": max(cells.values()),
        "days": present,
    }
    atomic_json(data / "backfill/completion.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("days", "unavailable_dates", "rejected_source_dates")}, indent=2))
    print("Rejected source dates:", sorted(rejected))
    if result["unresolved_linked_dates"]:
        raise SystemExit("Some linked dates still require recovery")


if __name__ == "__main__":
    main()
