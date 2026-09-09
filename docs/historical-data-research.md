# Historical price data: access and forecast integration

Researched 2026-09-09. Research and sample verification only; no historical observations have been added to production.

## Finding

Recent SEPA history can be recovered from the public **Preciazo archive**. The official rolling feed is not the only surviving copy. Start with July–August 2026, validate overlap against our current collection, then evaluate whether older observations help.

Sources:

- [Machine-readable archive index](https://raw.githubusercontent.com/catdevnull/sepa-precios-metadata/main/index.json)
- [Browsable archive index](https://github.com/catdevnull/sepa-precios-metadata/blob/main/index.md)
- [Archive maintainer's documentation](https://github.com/catdevnull/preciazo/blob/master/sepa/README.md)
- [Official CKAN metadata API](https://datos.produccion.gob.ar/api/3/action/package_show?id=sepa-precios)

The index maps dates to resource revisions, download links, warnings, and first-seen timestamps. Downloads are public Backblaze B2 objects compressed as `.tar.zst`; the maintainer describes them as recompressed SEPA datasets. No login or API key was needed for the tested downloads.

## Verified availability

Counts below describe **index entries with at least one download link**, not a claim that every object was downloaded or every retailer reported on every day.

| Period | Dates with links | Implication |
|---|---:|---|
| 2024-08-19 through 2026-09-08 | 629 | Substantial older history, with gaps |
| 2025 | 349 | Candidate longer training/evaluation period |
| 2026-07-01 through 2026-09-08 | 70 / 70 | Best first backfill window |
| Our local collection, 2026-08-26 through 2026-09-08 | 14 / 14 | 56 additional recent dates are indexed |

The 2026 index has no linked downloads for January 1 or March 18–June 30. Preserve these gaps. Metadata entries without links are not recoverable observations.

### Download and content checks

- HTTP range requests for 2024-08-19, 2026-08-01, and 2026-08-26 returned **206**, advertised object sizes, and the expected Zstandard magic bytes.
- Fully downloaded **2026-08-01**: HTTP **200**, **57,885,026 bytes** compressed, **1,107,253,856 bytes** of archived file contents, 50 files. Streaming decompression completed successfully.
- Applied our existing Gran Rosario geography filter and allowed-chain set to its branch files: **14 branches**, comprising Coto 5, Carrefour 5, Jumbo/Vea/Disco 2, La Anónima 1, Libertad 1. This does not establish complete basket coverage at each branch. DIA was absent from this sample's qualifying branches.
- Inspected a Coto Rosario product row at branch 95: product ID `7790070431905`, description `OBLEA DE ARROZ CHOCOBAR GALLO SNACKS PAQ 20 GRM`, package list price 1700. This is a schema example, not a claim that the item belongs in our basket.
- Sample SHA-256: `53cea4d3647288c3547e9febc1d633afcb30e77e203728787f595c70f2dc8b80`.

Sample and inspection evidence are in `/tmp/canasta-history-research/`. Temporary files are not durable storage.

## Access procedure

1. Read `index.json`, select the desired date, and select an entry containing `link`. Record its revision, warnings, and `firstSeenAt`; some dates have multiple revisions.
2. Download that exact link. Record retrieval time, byte count, and SHA-256. Validate archive contents and dates before accepting observations.
3. Stream the TAR through `zstd -dc`. The archive contains dated retailer directories with `comercio.csv`, `sucursales.csv`, and `productos.csv`, rather than our existing ZIP-inside-ZIP layout.
4. Read branch metadata first, then stream matching product rows. Some product files precede their branch metadata in the TAR, so use two passes or stage selected files. Avoid expanding the entire national dataset in memory.
5. Filter to Gran Rosario and our product categories, apply the current matcher and `package-price-v2` normalization, and store a compact local panel. Our current `--zip` option cannot consume this archive unchanged.

At the sampled August sizes, 56 additional days would be roughly **3.2–3.8 GB compressed**; that is an extrapolation from two object sizes, not a measured total. Process one archive at a time and retain filtered data plus provenance.

## Changes needed for useful predictions

These are recommendations from inspecting this repository and the downloaded sample.

**Repair product identity before backfilling.** `etl/etl.py` currently prefers `productos_ean` over `id_producto`. In the inspected row these contain `1` and `7790070431905`, respectively. Preserve `id_producto` as a string and retain the EAN field separately; validate its meaning before barcode matching. Keep `(id_comercio, id_bandera, id_sucursal, id_producto)` as the observation identity. Current raw observations also omit `id_bandera`, which should be retained. Existing raw `ean` values alone cannot reliably reconstruct lost product IDs.

**Measure two separate outcomes:** price changes for the same product at the same branch, and changes in the cheapest qualifying option. The saved current backtest reports 52 of 76 price changes (68.4%) alongside a description/brand change. Those are not necessarily repricing events. Package quantity, availability, branch coverage, promotions, and selected-product identity need explicit fields.

**Validate an overlap day before merging.** Compare an archived date already in our collection, preferably August 26, using the current matcher and normalizer on both inputs. Check branch coverage, package prices, units, duplicate revisions, and daily aggregates. Archive and local captures may reflect different updates within a day. Never overwrite `latest.json` while importing an older date.

**Use the extra history deliberately.** The production drift uses only its last five price differences, so adding older rows alone will not materially improve its next prediction. Build a separate experiment using stable product histories, day of week, days since last change, lagged competitor prices, and recorded promotions. Treat FX/IPIM as optional additional features after the price panel is sound.

**Evaluate chronologically.** Use earlier weeks for development and later unseen weeks for evaluation, with no random row split. Exclude imputed targets and incomplete weekly windows. Keep missing-day boundaries intact. For realistic historical availability, consider first-seen timestamps and avoid silently training on later revisions. Compare persistence, weekly seasonal persistence, the existing drift, and candidate models on identical observations; report MAE and movement precision/recall separately.

The saved current backtest has MAE **73.3 for drift versus 48.3 for persistence**. Improvement remains unproven until a candidate beats the baseline on held-out data. The old TimesFM evaluation is marked superseded and must be regenerated on corrected prices.

## Other sources investigated

- **Official CKAN:** the live API returned seven weekday ZIP resources and two metadata resources. The catalog search exposed retail and wholesale rolling datasets; it did not expose the semester archives below. Useful for ongoing collection, but no verified long-history access route there today.
- **Semester SEPA archives:** [this project's technical documentation](https://github.com/santiagoriverti/precios_minoristas_supermercados/blob/main/docs/SEPA_TECNICO.md) describes daily price columns in semester bundles. Its [README](https://github.com/santiagoriverti/precios_minoristas_supermercados/blob/main/README.md) reports analysis from January 2024, but says the large price files are not included. I did not find a working public download URL for those bundles. Treat them as a follow-up lead, not immediately accessible data. Different units and missing product/branch metadata require validation if obtained.
- **Zenodo:** [Precios Claros, May 2016–March 2018](https://zenodo.org/records/6568295) has a working records API listing dated price and branch gzip files. This is a real older archive, but a lower-priority experiment because of its age and the product/geography mapping required.

Recommended first implementation: an isolated TAR/Zstandard importer with provenance, a validated overlap comparison, and a July 1–August 25 backfill; then a chronological baseline comparison using the resulting recent panel.
