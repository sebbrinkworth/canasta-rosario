#!/usr/bin/env python3
"""ETL SEPA -> Canasta Rosario.
Usage: uv run python -m etl.etl --date 2026-08-31 --gran-rosario
       uv run python -m etl.etl --date 2026-08-31 --zip /tmp/sepa_lunes.zip
"""
import argparse, csv, io, json, re, zipfile, unicodedata
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from etl.canasta import CANASTA

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_AGG = ROOT / "data"

CKAN_IDS = {
    "lunes": "0a9069a9-06e8-4f98-874d-da5578693290",
    "martes": "9dc06241-cc83-44f4-8e25-c9b1636b8bc8",
    "miercoles": "1e92cd42-4f94-4071-a165-62c4cb2ce23c",
    "jueves": "d076720f-a7f0-4af8-b1d6-1b99d5a90c14",
    "viernes": "91bc072a-4726-44a1-85ec-4a8467aad27e",
    "sabado": "b3c3da5d-213d-41e7-8d74-f23fda0a3c30",
    "domingo": "f8e75128-515a-436e-bf8d-5c63a62f2005",
}
CKAN_BASE = "https://datos.produccion.gob.ar/dataset/6f47ec76-d1ce-4e34-a7e1-621fe9b1d0b5/resource/{}/download/sepa_{}.zip"
WEEKDAY_ES = ["lunes","martes","miercoles","jueves","viernes","sabado","domingo"]

CHAIN_LABELS = {
    "10": "Carrefour",
    "12": "Coto",
    "9": "Jumbo/Vea/Disco",
    "2": "La Anónima",
    "16": "Libertad",
    "11": "ChangoMás",
    "15": "DIA",
    "13": "Cooperativa Obrera",
}
ALLOWED_CHAINS = {"2","9","10","11","12","13","15","16"}
EXCLUDE_CHAINS = None

def normalize_text(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s

def parse_csv_text(txt: str) -> str:
    txt = txt.lstrip("\ufeff")
    lines=[]
    for l in txt.splitlines():
        if l.startswith("Ultima") or l.startswith("Última") or l.startswith("Ã"): 
            continue
        if not l.strip(): continue
        lines.append(l)
    return "\n".join(lines)

def price_per_unit(price_lista: float, qty_present: float, unit_present: str, qty_ref: float = None, unit_ref: str = None) -> tuple[float, str]:
    up = (unit_present or "").strip().upper()
    if up in ("GRM","GR","G","GRS"):
        if qty_present and qty_present>0:
            return price_lista / qty_present * 1000, "kg"
    elif up in ("KGM","KG","KILO"):
        if qty_present and qty_present>0:
            return price_lista / qty_present, "kg"
    elif up in ("MLT","ML","CM3","CC"):
        if qty_present and qty_present>0:
            return price_lista / qty_present * 1000, "L"
    elif up in ("LTR","LT","L"):
        if qty_present and qty_present>0:
            return price_lista / qty_present, "L"
    elif up in ("UNI","UN","U","UNIDAD"):
        if qty_present and qty_present>0:
            return price_lista / qty_present, "u"
    if qty_ref and unit_ref:
        ur = unit_ref.strip().upper()
        if ur in ("KGM","KG"): return price_lista / (qty_present or 1) * (1000 if up in ("GRM",) else 1), "kg"
    return price_lista, "?"

def price_per_unit_calc(price_lista, cantidad_presentacion, unidad_presentacion):
    try:
        p = float(str(price_lista).replace(",","."))
        q = float(str(cantidad_presentacion).replace(",","."))
        u = str(unidad_presentacion or "")
        val, unit = price_per_unit(p, q, u)
        return round(val,2), unit
    except: return None, "?"

NEGATIVE = {
    "leche_entera": ["chocolate","chocolatin","alfajor","dulce de leche","polvo","condensada","bon o bon","georgalos","tableta","nugaton","nugat","crema","leche en polvo","pan de leche","pan d leche","pref","100 uds","100uds","galletita","galletitas","leche en polvo","crema de leche","alimento","gato","perro","kingfood","king food","humedo"],
    "pan_lactal": ["rallado","hamburguesa","pancho","fugazza","panchos"],
    "arroz": ["condimento","galleta","harina de arroz","barrita","snack","barrita de arroz"],
    "fideos": ["arroz","barrita"],
    "aceite_girasol": ["oliva","maiz","mezcla","soja"],
    "harina_000": ["integral","leudante","0000","sin gluten"],
    "azucar": ["impalpable","gaseosa","edulcorante","azucarado","sin azucar","sin azúcar","barra","cereal","muecas","chocolate"],
    "yerba": ["saquito","saquitos","filtro","mate cocido","capsula","cafe"],
    "cafe": ["filtro","taza","capsula","cuchara","cubierto","licor","golosina","saquito","saquitos","mate cocido"],
    "tomate_triturado": ["salsa","ketchup","extracto"],
    "arvejas": ["sopa"],
    "pollo": ["alimento","king food","humedo","perro","gato","capelleti","capelletis","raviol","sorrent","tapa","patita","nugget","hamburguesa","caldo","sabor pollo","picada","galletita","pet","cat chow","ciriola","zepellin"],
    "carne_picada": ["pollo","rucula","cerdo","alimento","hamburguesa","rucula picada"],
    "huevo": ["maple"],
    "papa": ["pure de papas","papas fritas","sopapa","baston","noisette","copos","fritas","simplot","mc cain","mccain"],
    "cebolla": ["mani","snack","verdeo","deshidratada","polvo","alicate","alicante","escamas","papas","lays","chetos","doritos","sabor","pringles","papa frita","queso y cebolla"],
    "manzana": ["jugo","gaseosa","agua","aperitivo","terma","crush","te ","torta","gaseosa","amargo","shampoo","acondicionador","jab","crema","desodorante","alimento","head","rallador","isotonica","bebida","vinagre","avena","coloracion","nutrisse","acondicionad","acrilico","isotonico","powerade","decoralba","vinagre"],
    "banana": ["jugo","yogur","gaseosa","bocadito","barra","integra","cereal","bananita","cremigal","lays","platano sabor","snack"],
    "queso_cremoso": ["rallado","canelon","panzotti","procesado","neufchatel","neufchâtel","queso crema","cheddar","fundido","snack","maiz","nacho","crema"],
    "yogur": ["barra","cereal","tortaza","torta","helado","postre","flan"],
    "manteca": ["lechuga","medialuna","papel","popcorn","manteca de cacao","poroto","galletita","pepas","mini","sin manteca","budin","mani","mani king","figacita","figacitas"],
    "galletitas_agua": ["pepas","pepitos","sandwich","media tarde","avena","chips","dulce","rellena","vainilla","chocolate","limon","cereal"],
    "jabon_tocador": ["polvo","liquido","líquido","ropa","lavar ropa","suavizante","detergente","lavavajillas","tocador liquido","zorro","ala","skip","ecovita"],
    "detergente": ["suavizante","jabon liquido","jabon líquido","enjuague","lavandina","tableta","tablet"],
    "lavandina": ["gel"],
}

def ean_matches(ean: str, prefixes: list) -> bool:
    if not ean or not prefixes:
        return False
    ean_digits = re.sub(r'\D', '', str(ean))
    if not ean_digits:
        return False
    for pref in prefixes:
        pref_digits = re.sub(r'\D', '', str(pref))
        if len(pref_digits) >= 6 and ean_digits.startswith(pref_digits):
            return True
        if ean_digits == pref_digits:
            return True
    return False

# Stricter per-product keyword requirements for fallback
# If set, description must contain ALL terms in list to qualify (besides negatives)
STRICT_REQUIRE = {
    "leche_entera": [["leche"]],  # must contain leche, but negatives handle pan etc. Also require sachet/carton/uat/la serenisima/coto/dia/manfrey if possible — keep loose
    "pan_lactal": [["pan","lactal"]],
    "tomate_triturado": [["pure","tomate"],["tomate","triturado"]],
    "detergente": [["detergente"]],
    "jabon_tocador": [["jabon","tocador"]],
    "queso_cremoso": [["queso","cremoso"],["cremoso"]],
}

def _strict_ok(pid: str, desc_n: str) -> bool:
    reqs = STRICT_REQUIRE.get(pid)
    if not reqs:
        return True
    # any alternative group must be fully present
    for group in reqs:
        if all(normalize_text(t) in desc_n for t in group):
            return True
    return False

def match_product(descripcion: str, ean: str = ""):
    desc_n = normalize_text(descripcion)
    # Priority 1: EAN when available — direct high-confidence match
    if ean:
        for item in CANASTA:
            prefixes = item.get("ean_prefixes") or []
            if prefixes and ean_matches(ean, prefixes):
                # still respect negatives? EAN is trusted, skip negative check
                return item["id"]
    # Priority 2: keyword fallback — require all primary keywords implicitly via kw match + negatives + strict
    best = None
    best_len = 0
    for item in CANASTA:
        negs = NEGATIVE.get(item["id"], [])
        if any(normalize_text(n) in desc_n for n in negs):
            continue
        if not _strict_ok(item["id"], desc_n):
            continue
        for kw in item["keywords"]:
            kw_n = normalize_text(kw)
            if kw_n in desc_n:
                if len(kw_n.strip()) <= 5:
                    if not re.search(r'\b' + re.escape(kw_n.strip()) + r'\b', desc_n):
                        continue
                if len(kw_n) > best_len:
                    best = item["id"]
                    best_len = len(kw_n)
    return best

def is_price_sane(price_per_unit: float) -> bool:
    if price_per_unit is None or price_per_unit == 0:
        return False
    if price_per_unit != price_per_unit:  # NaN
        return False
    return True

def filter_outliers(observations):
    """Reject observations whose price_per_unit is far from median for that product.
    Median is computed from cheapest-per-chain values (1 per chain per product) to avoid skew from bulk matches.
    Returns (kept, rejected, medians)."""
    from statistics import median
    # compute cheapest per chain per product to get robust median
    cheapest_by_pid_chain = defaultdict(dict)
    for o in observations:
        pid=o["canonical_id"]
        cid=o["chain_id"]
        cur=cheapest_by_pid_chain[pid].get(cid)
        if cur is None or o["price_per_unit"] < cur["price_per_unit"]:
            cheapest_by_pid_chain[pid][cid]=o
    medians={}
    for pid, by_chain in cheapest_by_pid_chain.items():
        vals=sorted([v["price_per_unit"] for v in by_chain.values() if v["price_per_unit"] and v["price_per_unit"]>0])
        if vals:
            medians[pid]=median(vals)
    kept=[]
    rejected=[]
    low_factor = 0.15
    high_factor = 6.5
    for o in observations:
        m = medians.get(o["canonical_id"])
        p = o["price_per_unit"]
        if not is_price_sane(p):
            rejected.append((o, "price 0/NaN"))
            continue
        if m and m>0:
            if p < m * low_factor or p > m * high_factor:
                rejected.append((o, f"outlier vs median {m:.0f} (p={p:.0f})"))
                continue
        kept.append(o)
    return kept, rejected, medians

def is_rosario_branch(row, gran_rosario=False):
    prov = (row.get("sucursales_provincia") or "").strip()
    if prov != "AR-S":
        return False
    loc = (row.get("sucursales_localidad") or "").strip()
    loc_up = loc.upper()
    if loc_up == "ROSARIO" or loc == "Rosario":
        return True
    if gran_rosario:
        if loc_up in ("FUNES","FISHERTON","FISHERTON ROSARIO"):
            return True
        try:
            lat = float((row.get("sucursales_latitud") or "").strip().replace(",","."))
            lon = float((row.get("sucursales_longitud") or "").strip().replace(",","."))
            if -33.1 <= lat <= -32.7 and -61.0 <= lon <= -60.4:
                return True
        except: pass
    return False

def extract_observations(zip_path: Path, gran_rosario=False):
    comercios = {}
    branches = []
    all_branches = []
    observations = []
    with zipfile.ZipFile(zip_path) as outer:
        for name in outer.namelist():
            if not name.endswith(".zip"): continue
            try:
                data = outer.read(name)
            except: continue
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    if "comercio.csv" in z.namelist():
                        txt = parse_csv_text(z.read("comercio.csv").decode("utf-8", errors="ignore"))
                        reader = csv.DictReader(io.StringIO(txt), delimiter="|")
                        for row in reader:
                            cid=(row.get("id_comercio") or "").strip()
                            bid=(row.get("id_bandera") or "").strip()
                            if not cid or not bid: continue
                            if cid.startswith("Ultima") or cid.startswith("Últ"): continue
                            key=f"{cid}-{bid}"
                            comercios[key] = {
                                "id_comercio": cid, "id_bandera": bid,
                                "razon": row.get("comercio_razon_social",""), "bandera": row.get("comercio_bandera_nombre","")
                            }
                    if "sucursales.csv" not in z.namelist(): continue
                    txt = parse_csv_text(z.read("sucursales.csv").decode("utf-8", errors="ignore"))
                    reader = csv.DictReader(io.StringIO(txt), delimiter="|")
                    file_branches=[]
                    for row in reader:
                        all_branches.append(row)
                        if is_rosario_branch(row, gran_rosario=gran_rosario):
                            file_branches.append(row)
                            branches.append(row)
                    if not file_branches:
                        continue
                    if "productos.csv" not in z.namelist(): continue
                    branch_keys = {(r.get("id_comercio"), r.get("id_bandera"), r.get("id_sucursal")) for r in file_branches}
                    # productos.csv is huge (GB) - stream to avoid RAM spike (fix: avoid z.read().splitlines() OOM)
                    try:
                        pf = z.open("productos.csv")
                    except KeyError:
                        continue
                    with pf:
                        text = io.TextIOWrapper(pf, encoding="utf-8", errors="ignore")
                        header = None
                        for raw in text:
                            if not raw.strip():
                                continue
                            raw = raw.lstrip("\ufeff")
                            if raw.startswith("Ultima") or raw.startswith("Última") or raw.startswith("Ã"):
                                continue
                            header = [h.strip() for h in raw.strip().split("|")]
                            break
                        if not header:
                            continue
                        def _prod_lines():
                            for raw in text:
                                if not raw.strip():
                                    continue
                                if raw.startswith("Ultima") or raw.startswith("Última") or raw.startswith("Ã"):
                                    continue
                                yield raw
                        reader2 = csv.DictReader(_prod_lines(), fieldnames=header, delimiter="|")
                        for prow in reader2:
                            key = (prow.get("id_comercio"), prow.get("id_bandera"), prow.get("id_sucursal"))
                            if key not in branch_keys:
                                continue
                            try:
                                price_lista = float((prow.get("productos_precio_lista") or "").replace(",","."))
                            except: continue
                            if price_lista <=0: continue
                            desc = prow.get("productos_descripcion") or ""
                            ean = prow.get("productos_ean") or prow.get("id_producto") or ""
                            canonical = match_product(desc, ean)
                            if not canonical:
                                continue
                            try:
                                qty_present = float((prow.get("productos_cantidad_presentacion") or "0").replace(",","."))
                            except: qty_present = 0
                            unit_present = prow.get("productos_unidad_medida_presentacion") or ""
                            precio_ref = (prow.get("productos_precio_referencia") or "").strip()
                            cantidad_ref = (prow.get("productos_cantidad_referencia") or "").strip()
                            unidad_ref = (prow.get("productos_unidad_medida_referencia") or "").strip()
                            if precio_ref:
                                try:
                                    per_unit = float(precio_ref.replace(",","."))
                                    ur = unidad_ref.upper()
                                    if ur in ("KGM","KG","KG."): per_unit_name="kg"
                                    elif ur in ("LTR","LT","L","LITRO"): per_unit_name="L"
                                    elif ur in ("GRM","GR","GRS","G","GR."): per_unit_name="kg"
                                    elif ur in ("MLT","ML","CM3"): 
                                        per_unit_name="L"
                                    elif ur in ("UNI","UN","U"): per_unit_name="u"
                                    else: per_unit_name=unidad_ref.lower() or "?"
                                    pass
                                except:
                                    per_unit, per_unit_name = price_per_unit(price_lista, qty_present, unit_present)
                            else:
                                try:
                                    per_unit, per_unit_name = price_per_unit(price_lista, qty_present, unit_present)
                                except:
                                    per_unit, per_unit_name = price_lista, "?"
                            bmatch = next((b for b in file_branches if b.get("id_sucursal")==prow.get("id_sucursal") and b.get("id_comercio")==prow.get("id_comercio")), None)
                            observations.append({
                                "canonical_id": canonical,
                                "chain_id": prow.get("id_comercio"),
                                "chain_label": CHAIN_LABELS.get(prow.get("id_comercio"), prow.get("id_comercio")),
                                "branch_id": prow.get("id_sucursal"),
                                "branch_name": bmatch.get("sucursales_nombre") if bmatch else "",
                                "branch_localidad": bmatch.get("sucursales_localidad") if bmatch else "",
                                "ean": ean,
                                "descripcion": desc,
                                "marca": prow.get("productos_marca") or "",
                                "price_lista": price_lista,
                                "cantidad_presentacion": qty_present,
                                "unidad_presentacion": unit_present,
                                "price_per_unit": round(per_unit,2) if per_unit else None,
                                "per_unit_name": per_unit_name,
                            })
            except zipfile.BadZipFile:
                continue
    return comercios, branches, observations

def aggregate(observations, branches):
    cheapest = defaultdict(dict)
    for obs in observations:
        cid = obs["chain_id"]
        pid = obs["canonical_id"]
        cur = cheapest[cid].get(pid)
        if cur is None or obs["price_per_unit"] < cur["price_per_unit"]:
            cheapest[cid][pid] = obs
    for bad in list(cheapest.keys()):
        if bad not in ALLOWED_CHAINS:
            del cheapest[bad]
    chains = sorted(cheapest.keys())
    hero=[]
    for cid in chains:
        total=0
        count=0
        for pid, obs in cheapest[cid].items():
            item = next((c for c in CANASTA if c["id"]==pid), None)
            if not item: continue
            unit = item["unit"]
            need = item["need_qty"]
            if obs["per_unit_name"] == unit or (unit=="kg" and obs["per_unit_name"]=="kg") or (unit=="L" and obs["per_unit_name"]=="L") or (unit=="u" and obs["per_unit_name"]=="u"):
                total += obs["price_per_unit"] * need
                count+=1
            else:
                total += obs["price_lista"] * (need / (obs["cantidad_presentacion"] or 1)) if obs["cantidad_presentacion"] else obs["price_lista"]
                count+=1
        hero.append({"chain_id": cid, "chain_label": CHAIN_LABELS.get(cid,cid), "total": round(total,2), "items_found": count})
    hero.sort(key=lambda x: x["total"])
    branch_summary=[]
    for b in branches:
        if (b.get("id_comercio") or "") in CHAIN_LABELS or True:
            branch_summary.append({
                "id_comercio": b.get("id_comercio"), "id_bandera": b.get("id_bandera"),
                "id_sucursal": b.get("id_sucursal"), "nombre": b.get("sucursales_nombre"),
                "localidad": b.get("sucursales_localidad"), "lat": b.get("sucursales_latitud"), "lon": b.get("sucursales_longitud")
            })
    return {
        "chains": chains,
        "cheapest": {k: v for k,v in cheapest.items()},
        "hero": hero,
        "branches": branch_summary,
    }

def run(date_str: str, gran_rosario=False, zip_path: Path = None):
    if zip_path is None:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = WEEKDAY_ES[dt.weekday()]
        alt = weekday
        candidates = [Path(f"/tmp/canasta-etl/sepa_{weekday}.zip"), ROOT / f"sepa_{weekday}.zip"]
        for c in candidates:
            if c.exists():
                zip_path = c
                break
        if zip_path is None:
            rid = CKAN_IDS.get(weekday)
            if not rid:
                raise SystemExit(f"No CKAN id for {weekday}, pass --zip")
            url = CKAN_BASE.format(rid, weekday)
            print(f"Downloading {url} ...")
            zip_path = Path(f"/tmp/sepa_{weekday}.zip")
            import subprocess, shlex
            # Use curl (handles egress proxy auth reliably; urllib 407s after 2 downloads)
            res = subprocess.run(["curl","-L","--fail","--connect-timeout","30","--max-time","300","-o",str(zip_path), url], capture_output=True, text=True)
            if res.returncode != 0:
                raise SystemExit(f"curl failed for {url}: {res.stderr[:800]}")
            print(f"Saved to {zip_path} ({zip_path.stat().st_size} bytes)")
    print(f"Parsing {zip_path} gran_rosario={gran_rosario} ...")
    comercios, branches, observations_raw = extract_observations(zip_path, gran_rosario=gran_rosario)
    print(f"Branches matched: {len(branches)} ; observations matched to canasta (raw): {len(observations_raw)}")
    kept, rejected, medians = filter_outliers(observations_raw)
    if rejected:
        print(f"Outlier/sanity rejected: {len(rejected)} (kept {len(kept)})")
        for obs, reason in rejected[:15]:
            print(f"  REJECT {obs['canonical_id']} {obs['chain_label']} p={obs['price_per_unit']} {obs['descripcion'][:55]} -> {reason}")
        if len(rejected) > 15:
            print(f"  ... and {len(rejected)-15} more")
    observations = kept
    agg = aggregate(observations, branches)
    print(f"Chains with data: {list(agg['cheapest'].keys())}")
    for h in agg["hero"]:
        print(f"  {h['chain_label']}: ${h['total']} ({h['items_found']} items)")
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    DATA_AGG.mkdir(parents=True, exist_ok=True)
    raw_out = DATA_RAW / f"rosario-{date_str}.json"
    raw_out.write_text(json.dumps({
        "date": date_str, "gran_rosario": gran_rosario,
        "branches": agg["branches"],
        "observations": observations,
        "comercios": comercios,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {raw_out}")
    table=[]
    for item in CANASTA:
        row={"id": item["id"], "name": item["name"], "unit_display": item["unit_display"], "category": item["category"], "prices": {}}
        for cid in agg["chains"]:
            obs = agg["cheapest"][cid].get(item["id"])
            if obs:
                row["prices"][cid] = {"price_lista": obs["price_lista"], "price_per_unit": obs["price_per_unit"], "per_unit": obs["per_unit_name"], "desc": obs["descripcion"], "marca": obs["marca"]}
            else:
                row["prices"][cid] = None
        vals=[(cid, v["price_per_unit"]) for cid,v in row["prices"].items() if v]
        if vals:
            cheapest_cid = min(vals, key=lambda x: x[1])[0]
            row["cheapest_chain"] = cheapest_cid
        else:
            row["cheapest_chain"]=None
        table.append(row)
    agg_out = DATA_AGG / f"rosario-{date_str}.json"
    agg_out.write_text(json.dumps({
        "date": date_str, "gran_rosario": gran_rosario,
        "branches_count": len(branches),
        "chains": [{"id": cid, "label": CHAIN_LABELS.get(cid,cid)} for cid in agg["chains"]],
        "hero": agg["hero"],
        "table": table,
        "generated_at": datetime.now().isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {agg_out}")
    (DATA_AGG / "latest.json").write_text((DATA_AGG / f"rosario-{date_str}.json").read_text(encoding="utf-8"), encoding="utf-8")
    return agg_out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--gran-rosario", action="store_true")
    ap.add_argument("--zip", dest="zip_path", default=None)
    args=ap.parse_args()
    zp = Path(args.zip_path) if args.zip_path else None
    run(args.date, gran_rosario=args.gran_rosario, zip_path=zp)

if __name__=="__main__":
    main()
