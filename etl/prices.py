"""Comparable prices from the package's list price and physical contents.

SEPA reference fields are not consistent across retailers: a reference price
may describe 100 g while cantidad_referencia describes the entire 900 g pack.
Never reuse those prices as $/kg or try to repair them with a guessed factor.
Preserve the original reference fields for auditing; calculate from presentation
quantity, or an unambiguous package size printed in the description instead.
"""
import math
import re
import unicodedata

NORMALIZATION_VERSION = "package-price-v2"

# Scale converts the source quantity into kg, litres, or individual items.
UNIT_SCALES = {}
for aliases, base, scale in (
    ("KG KGM KGR K KILO KILOS KILOGRAMO KILOGRAMOS", "kg", 1),
    ("G GR GRM GRS GRAMO GRAMOS", "kg", .001),
    ("L LT LTR LTS LITRO LITROS", "L", 1),
    ("ML MLT CM3 CC MILILITRO MILILITROS", "L", .001),
    ("U UN UNI UD UDS UNIDAD UNIDADES CU C/U", "u", 1),
    ("DOC DOCENA DOCENAS", "u", 12),
):
    for alias in aliases.split():
        UNIT_SCALES[alias] = (base, scale)


def positive_number(value):
    try:
        result = float(str(value).strip().replace(",", "."))
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def unit_key(unit):
    return str(unit or "").strip().upper().rstrip(".")


def normalize_unit(unit):
    """Unit *dimension* only. Use base_quantity to convert its numeric amount."""
    return UNIT_SCALES.get(unit_key(unit), ("?", 0))[0]


def base_quantity(quantity, unit):
    amount = positive_number(quantity)
    base, scale = UNIT_SCALES.get(unit_key(unit), ("?", 0))
    converted = amount * scale if amount and scale else None
    return (converted, base) if converted and math.isfinite(converted) else (None, "?")


def price_per_unit(price, quantity, unit):
    amount, base = base_quantity(quantity, unit)
    price = positive_number(price)
    if price is None or amount is None:
        return None, "?"
    return price / amount, base


NUMBER = r"\d+(?:[.,]\d+)?"
UNITS = "|".join(re.escape(u) for u in sorted(UNIT_SCALES, key=len, reverse=True))
SIZE = re.compile(rf"(?<![\d.,])(?P<amount>{NUMBER})\s*(?P<unit>{UNITS})(?![A-Z0-9])")
PACK_BEFORE = re.compile(r"(?<![\d.,])(?P<count>\d+)\s*[X×]\s*$")
PACK_AFTER = re.compile(r"^\s*[X×]\s*(?P<count>\d+)\s*(?:UNI|UNIDADES|UN|UDS|UD|U)\b")


def description_quantity(description, expected_unit):
    """Read explicit sizes (including 3 x 125 g and 75 g x 3 units).

    Different candidate sizes, bonuses, and ambiguous packs are rejected.
    Repeated equivalent sizes, e.g. '500 g ... PAQ-500-gr.', are accepted.
    """
    desc = unicodedata.normalize("NFKD", str(description or "").upper())
    desc = "".join(c for c in desc if not unicodedata.combining(c))
    # SEPA descriptions sometimes use package trailers like PAQ-500-gr.
    desc = re.sub(r"(?<=\d)-(?=[A-Z])", " ", desc)
    candidates = []
    for match in SIZE.finditer(desc):
        amount, unit = base_quantity(match['amount'], match['unit'])
        if unit != expected_unit or amount is None:
            continue
        before = PACK_BEFORE.search(desc[:match.start()])
        after = PACK_AFTER.match(desc[match.end():])
        if before and after:
            return None
        pack = before or after
        if pack and expected_unit != "u":
            count = int(pack['count'])
            if count <= 0:
                return None
            amount *= count
        candidates.append(amount)
    # Egg cartons can state 'X 30 C T' without an explicit unit token.
    if expected_unit == 'u' and not candidates:
        carton = re.search(r"\bHUEVO.*\bX\s*(\d+)\s*C\s*T\s*$", desc)
        if carton:
            candidates.append(float(carton[1]))
    if not candidates:
        return None
    first = candidates[0]
    if all(math.isclose(n, first, rel_tol=1e-6) for n in candidates):
        return first
    return None


def normalize_observation(observation, expected_unit):
    """Return a copy with a verified comparable value, or None to exclude it.

    A generic '1 UNI' is one package, not necessarily one egg or one kg.
    Legacy derived price_per_unit is intentionally ignored on every rebuild.
    """
    if observation.get("identity_conflict"):
        return None
    price = positive_number(observation.get("price_lista"))
    if price is None:
        return None
    amount, unit = base_quantity(observation.get("cantidad_presentacion"),
                                 observation.get("unidad_presentacion"))
    basis = "presentation"
    if amount is None or unit != expected_unit or (unit == "u" and amount == 1):
        amount = description_quantity(observation.get("descripcion"), expected_unit)
        basis = "description"
    if amount is None or amount <= 0:
        return None
    converted_price = price / amount
    if not math.isfinite(converted_price) or round(converted_price, 2) <= 0:
        return None
    result = dict(observation)
    result.update(price_per_unit=round(converted_price, 2),
                  per_unit_name=expected_unit, normalized_quantity=amount,
                  price_basis=basis, price_normalization_version=NORMALIZATION_VERSION)
    return result
