"""Resumable import of the public Preciazo SEPA TAR/Zstandard archive.

python -m etl.backfill --start 2026-07-01 --end 2026-08-31 --workers 2

Historical imports never update latest.json. Raw candidates are retained in
gzip JSON, with source provenance and a manifest for both successes and gaps.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
import csv
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile

from etl.etl import (
    ROOT, ALLOWED_CHAINS, CHAIN_LABELS, NON_RETAIL_COMERCIOS,
    aggregate, aggregate_zone, build_table, filter_outliers,
    is_rosario_branch, observation_from_row, parse_csv_text, zone_of,
)
from etl.prices import NORMALIZATION_VERSION

INDEX_URL = "https://raw.githubusercontent.com/catdevnull/sepa-precios-metadata/main/index.json"
IMPORT_VERSION = "preciazo-tar-v3"


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def choose_entry(entries):
    """Prefer a warning-free earliest archived revision; never invent a URL."""
    linked = [x for x in entries if x.get("link")]
    return min(linked, key=lambda x: (bool(x.get("warnings")), x.get("firstSeenAt", ""), x["id"])) if linked else None


@contextmanager
def open_tar(path):
    proc = subprocess.Popen(["zstd", "-dc", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
            yield archive
        # A TAR terminator can precede the last compressed frame. Drain it so
        # decompressor integrity checks run and a corrupt tail is not accepted.
        while proc.stdout.read(1024 * 1024):
            pass
        error = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise ValueError(f"Zstandard decompression failed: {error[:500]}")
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
        proc.stdout.close()
        proc.stderr.close()


def csv_rows(content):
    text = parse_csv_text(content.decode("utf-8-sig", errors="replace"))
    return csv.DictReader(io.StringIO(text), delimiter="|")


@contextmanager
def open_inner_zip(stream):
    # Some historical TARs retain the original retailer ZIPs. ZIP needs seek;
    # spill larger members to disk instead of keeping national files in RAM.
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as tmp:
        shutil.copyfileobj(stream, tmp, length=1024 * 1024)
        tmp.seek(0)
        with zipfile.ZipFile(tmp) as archive:
            yield archive


def zip_csv_names(archive):
    result = {}
    for name in archive.namelist():
        base = name.replace("\\", "/").rsplit("/", 1)[-1]
        if base in ("comercio.csv", "sucursales.csv", "productos.csv"):
            if base in result:
                raise ValueError(f"Ambiguous CSV members in retailer ZIP: {base}")
            result[base] = name
    return result


def selected_product_rows(stream, branch_keys, chunk_size=4 * 1024 * 1024):
    """Split bounded binary chunks, decode only the requested branches.

    SEPA uses line-oriented pipe records. Buffer partial records across chunks;
    use DictReader on selected records to preserve quoting and field mapping.
    """
    header = None
    while True:
        line = stream.readline()
        if not line:
            return
        line = line.decode("utf-8-sig", errors="replace").strip()
        if not line or line.startswith(("Ultima", "Última", "Ã")):
            continue
        header = next(csv.reader([line], delimiter="|"))
        header = [h.strip() for h in header]
        break
    if header[:3] != ["id_comercio", "id_bandera", "id_sucursal"]:
        raise ValueError(f"Unexpected product identity columns: {header[:3]}")
    if "id_producto" not in header or "productos_precio_lista" not in header:
        raise ValueError("Required product columns are missing")
    prefixes = tuple(("|".join(k) + "|").encode() for k in sorted(branch_keys))
    if not prefixes:
        return
    pending = b""
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            complete = pending
        else:
            pending += chunk
            boundary = pending.rfind(b"\n")
            if boundary < 0:
                if len(pending) > 16 * 1024 * 1024:
                    raise ValueError("Product record exceeds 16 MiB")
                continue
            complete, pending = pending[:boundary + 1], pending[boundary + 1:]
        lines = (line.decode("utf-8", errors="replace") for line in complete.splitlines()
                 if line.startswith(prefixes))
        yield from csv.DictReader(lines, fieldnames=header, delimiter="|")
        if not chunk:
            break


def extract_archive(path, expected_date):
    branch_groups, comercios, branches = {}, {}, []
    archive_dates = set()
    def add_branches(group, content):
        rows = list(csv_rows(content))
        selected = [r for r in rows if is_rosario_branch(r, gran_rosario=True)
                    and r.get("id_comercio") in ALLOWED_CHAINS
                    and r.get("id_comercio") not in NON_RETAIL_COMERCIOS]
        branch_groups[group] = {
            (r["id_comercio"], r["id_bandera"], r["id_sucursal"]): r for r in selected
        }
        branches.extend(selected)
    def add_comercios(content):
        for r in csv_rows(content):
            cid, bid = r.get("id_comercio"), r.get("id_bandera")
            if cid and bid:
                comercios[f"{cid}-{bid}"] = {
                    "id_comercio": cid, "id_bandera": bid,
                    "razon": r.get("comercio_razon_social", ""),
                    "bandera": r.get("comercio_bandera_nombre", ""),
                }
    with open_tar(path) as archive:
        for member in archive:
            if not member.isfile():
                continue
            archive_dates.update(re.findall(r"\d{4}-\d{2}-\d{2}", member.name))
            if member.name.endswith("/sucursales.csv"):
                add_branches(str(Path(member.name).parent), archive.extractfile(member).read())
            elif member.name.endswith("/comercio.csv"):
                add_comercios(archive.extractfile(member).read())
            elif member.name.lower().endswith(".zip"):
                with open_inner_zip(archive.extractfile(member)) as retailer:
                    names = zip_csv_names(retailer)
                    if "sucursales.csv" in names:
                        add_branches(member.name, retailer.read(names["sucursales.csv"]))
                    if "comercio.csv" in names:
                        add_comercios(retailer.read(names["comercio.csv"]))
    if archive_dates != {expected_date}:
        raise ValueError(f"Archive date mismatch: expected {expected_date}, found {sorted(archive_dates)}")
    observations = []
    matched_files, selected_rows = 0, 0
    def add_products(stream, lookup):
        nonlocal selected_rows
        for row in selected_product_rows(stream, lookup):
            key = (row["id_comercio"], row["id_bandera"], row["id_sucursal"])
            selected_rows += 1
            obs = observation_from_row(row, lookup[key])
            if obs is not None:
                observations.append(obs)
    with open_tar(path) as archive:
        for member in archive:
            if not member.isfile():
                continue
            if member.name.endswith("/productos.csv"):
                lookup = branch_groups.get(str(Path(member.name).parent), {})
                if lookup:
                    matched_files += 1
                    add_products(archive.extractfile(member), lookup)
            elif member.name.lower().endswith(".zip"):
                lookup = branch_groups.get(member.name, {})
                if lookup:
                    with open_inner_zip(archive.extractfile(member)) as retailer:
                        names = zip_csv_names(retailer)
                        if "productos.csv" in names:
                            matched_files += 1
                            with retailer.open(names["productos.csv"]) as stream:
                                add_products(stream, lookup)
    if not observations:
        raise ValueError("No basket observations found; snapshot not published")
    # Full keys are strings. Do not collapse different banners or branches.
    unique, conflicts = {}, {}
    for obs in observations:
        key = (obs["chain_id"], obs["bandera_id"], obs["branch_id"], obs["product_id"])
        previous = unique.get(key)
        if previous is not None and previous != obs:
            variants = conflicts.setdefault(key, [previous])
            if obs not in variants:
                variants.append(obs)
        else:
            unique[key] = obs
    for key, variants in conflicts.items():
        # Keep all alternatives in the raw audit file, but do not choose an
        # arbitrary price for a contradictory source identity.
        unique[key] = {**unique[key], "identity_conflict": True,
                       "source_variants": variants, "price_per_unit": None,
                       "per_unit_name": "?", "price_basis": "conflicting-source-rows"}
    return comercios, branches, list(unique.values()), {
        "product_files": matched_files, "selected_branch_rows": selected_rows,
        "duplicate_rows": len(observations) - len(unique),
        "conflicting_identities_excluded": len(conflicts),
    }


def make_snapshot(day, branches, observations, provenance):
    kept, rejected, _ = filter_outliers(observations)
    if not kept:
        raise ValueError("No validated basket observations; snapshot not published")
    agg = aggregate(kept, branches)
    zones = {}
    for zone in ("rosario", "gran"):
        az = aggregate_zone(kept, branches, zone)
        zones[zone] = {
            "branches_count": sum(zone_of(b.get("sucursales_localidad")) == zone for b in branches),
            "chains": [{"id": c, "label": CHAIN_LABELS.get(c, c)} for c in az["chains"]],
            "hero": az["hero"], "table": build_table(az),
        }
    snapshot = {
        "date": day, "gran_rosario": True,
        "price_normalization_version": NORMALIZATION_VERSION,
        "branches_count": len(branches),
        "chains": [{"id": c, "label": CHAIN_LABELS.get(c, c)} for c in agg["chains"]],
        "hero": agg["hero"], "table": build_table(agg), "zones": zones,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": provenance,
        "normalization": {"candidate_observations": len(observations), "kept": len(kept), "rejected": len(rejected)},
    }
    return snapshot, agg["branches"]


def download(entry, path):
    if path.exists():
        return hashlib.file_digest(path.open("rb"), "sha256").hexdigest(), path.stat().st_size
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    for attempt in range(3):
        try:
            req = urllib.request.Request(entry["link"], headers={"User-Agent": "canasta-rosario historical backfill"})
            digest, size = hashlib.sha256(), 0
            with urllib.request.urlopen(req, timeout=60) as response, tmp.open("wb") as output:
                if response.status != 200:
                    raise ValueError(f"Expected full object, got HTTP {response.status}")
                expected = int(response.headers.get("Content-Length", 0))
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if expected and size != expected:
                raise ValueError(f"Incomplete object: {size}/{expected}")
            tmp.replace(path)
            return digest.hexdigest(), size
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def import_day(day, entry, output_dir, cache_dir, keep_archive=False):
    output_dir, cache_dir = Path(output_dir), Path(cache_dir)
    destination = output_dir / f"rosario-{day}.json"
    if destination.exists():
        existing = json.loads(destination.read_text())
        return {"date": day, "status": "existing", "source": existing.get("source")}
    if Path(entry["name"]).name != entry["name"] or entry["name"] in (".", ".."):
        raise ValueError("Unsafe archive filename in source index")
    path = cache_dir / entry["name"]
    started = time.monotonic()
    sha, size = download(entry, path)
    comercios, branches, observations, counts = extract_archive(path, day)
    provenance = {
        "provider": "SEPA via Preciazo public archive", "index_url": INDEX_URL,
        "url": entry["link"], "revision": entry["id"],
        "first_seen_at": entry.get("firstSeenAt"), "warnings": entry.get("warnings", ""),
        "sha256": sha, "compressed_bytes": size, "import_version": IMPORT_VERSION,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    snapshot, summary = make_snapshot(day, branches, observations, provenance)
    raw_path = output_dir / "raw" / f"rosario-{day}.json.gz"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = raw_path.with_suffix(raw_path.suffix + ".partial")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as stream:
        json.dump({"date": day, "gran_rosario": True, "price_normalization_version": NORMALIZATION_VERSION,
                   "source": provenance, "branches": summary, "observations": observations,
                   "comercios": comercios}, stream, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(raw_path)
    atomic_json(destination, snapshot)
    if not keep_archive:
        path.unlink()  # Only this downloaded, successfully processed cache object.
    return {"date": day, "status": "imported", "branches": len(branches),
            "observations": len(observations), "cells": sum(v is not None for row in snapshot["table"] for v in row["prices"].values()),
            **counts, "source": provenance, "seconds": round(time.monotonic() - started, 2)}


def import_revisions(day, entries, output_dir, cache_dir, keep_archive=False):
    """Try another archived revision if the preferred one is unusable."""
    entries = sorted((x for x in entries if x.get("link")),
                     key=lambda x: (bool(x.get("warnings")), x.get("firstSeenAt", ""), x["id"]))
    attempts = []
    for entry in entries:
        try:
            result = import_day(day, entry, output_dir, cache_dir, keep_archive)
            if attempts:
                result["rejected_revisions"] = attempts
            return result
        except Exception as exc:
            attempt = {"revision": entry["id"], "url": entry["link"],
                       "error": f"{type(exc).__name__}: {exc}"}
            path = Path(cache_dir) / Path(entry["name"]).name
            if path.exists():
                with path.open("rb") as stream:
                    attempt["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
            attempts.append(attempt)
    return {"date": day, "status": "failed", "error": "No usable archived revision", "rejected_revisions": attempts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--index", type=Path, help="Pinned local index (preferred for reproducible staged imports)")
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/archive-cache")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--keep-archives", action="store_true")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if end < start or args.workers < 1:
        parser.error("Invalid date interval or worker count")
    if args.index:
        index_bytes = args.index.read_bytes()
    else:
        with urllib.request.urlopen(INDEX_URL, timeout=30) as response:
            index_bytes = response.read()
    index = json.loads(index_bytes)
    manifest_path = args.output / "backfill" / f"{start}_{end}.json"
    manifest = {"start": str(start), "end": str(end), "index_url": INDEX_URL,
                "index_sha256": hashlib.sha256(index_bytes).hexdigest(), "import_version": IMPORT_VERSION,
                "started_at": datetime.now(timezone.utc).isoformat(), "days": {}}
    jobs = []
    day = start
    while day <= end:
        ds = str(day)
        entry = choose_entry(index.get(ds, []))
        if (args.output / f"rosario-{ds}.json").exists():
            manifest["days"][ds] = {"status": "existing"}
        elif entry is None:
            manifest["days"][ds] = {"status": "unavailable", "reason": "No indexed public download"}
        else:
            jobs.append((ds, index[ds]))
        day += timedelta(days=1)
    atomic_json(manifest_path, manifest)
    print(f"Backfill {start}..{end}: {len(jobs)} downloads, workers={args.workers}", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(import_revisions, ds, entries, args.output, args.cache, args.keep_archives): ds for ds, entries in jobs}
        for n, future in enumerate(as_completed(futures), 1):
            ds = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"date": ds, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            manifest["days"][ds] = result
            atomic_json(manifest_path, manifest)
            print(f"{n}/{len(jobs)} {ds}: {result['status']} cells={result.get('cells', '-')} seconds={result.get('seconds', '-')} {result.get('error', '')}", flush=True)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(manifest_path, manifest)
    failures = sum(x["status"] == "failed" for x in manifest["days"].values())
    print(f"Finished; failures={failures}; manifest={manifest_path}", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
