"""Load PantryPal's editable vocabulary and grocery rules from JSON."""

from __future__ import annotations

import json
from math import ceil
from pathlib import Path
import re
import unicodedata


DATA_DIR = Path(__file__).with_name("data")


def load_json(filename: str):
    path = DATA_DIR / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"PantryPal data file could not be loaded: {path}") from exc


ALIASES = load_json("ingredient_aliases.json")
FOOD_CATEGORIES = load_json("food_categories.json")
CUISINE_AREAS = FOOD_CATEGORIES["cuisine_areas"]
MOOD_ALIASES = FOOD_CATEGORIES["mood_aliases"]
FOOD_MOODS = tuple(FOOD_CATEGORIES["labels"])
MOOD_RULES = FOOD_CATEGORIES["mood_rules"]
MOOD_SEARCHES = FOOD_CATEGORIES["mood_searches"]
SUBSTITUTIONS = load_json("substitutions.json")
GROCERY_DATA = load_json("grocery_data.json")
UNIT_CONVERSIONS = GROCERY_DATA["unit_conversions"]
PACKAGE_SIZES = GROCERY_DATA["package_sizes"]
DIETARY_RULES = load_json("dietary_rules.json")
ALLERGEN_TERMS = DIETARY_RULES["allergens"]
DIET_EXCLUSIONS = DIETARY_RULES["diet_exclusions"]

def normalize(text: str):
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


NORMALIZED_ALIASES = {normalize(key): normalize(value) for key, value in ALIASES.items()}
NUMBER_PATTERN = r"(?:\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?)"


def canonical_ingredient(text: str):
    cleaned = normalize(text)
    if cleaned in NORMALIZED_ALIASES:
        return NORMALIZED_ALIASES[cleaned]
    if cleaned.endswith("ies") and len(cleaned) > 4:
        return cleaned[:-3] + "y"
    if cleaned.endswith("oes") and len(cleaned) > 4:
        return cleaned[:-2]
    if cleaned.endswith(("ches", "shes", "xes", "zes")) and len(cleaned) > 4:
        return cleaned[:-2]
    if cleaned.endswith("s") and not cleaned.endswith(("ss", "us")):
        return cleaned[:-1]
    return cleaned


def normalize_mood(text: str):
    mood = normalize(text)
    for suffix in (" cuisine", " food", " style", " dishes"):
        if mood.endswith(suffix):
            mood = mood[:-len(suffix)].strip()
    return MOOD_ALIASES.get(mood, mood)


def matches_mood(meal: dict, mood: str):
    if mood in CUISINE_AREAS:
        return normalize(meal.get("area", "")) == normalize(CUISINE_AREAS[mood])
    rule = MOOD_RULES.get(mood)
    if not rule:
        title = normalize(meal.get("name", ""))
        ingredients = normalize(" ".join(item.get("name", "") for item in meal.get("ingredients", [])))
        return mood in title or mood in ingredients

    category = normalize(meal.get("category", ""))
    title = normalize(meal.get("name", ""))
    ingredients = normalize(" ".join(item.get("name", "") for item in meal.get("ingredients", [])))
    full_text = f"{title} {ingredients} {category}"
    if category in rule.get("category_none", []):
        return False
    checks = []
    if rule.get("category_any"):
        checks.append(category in rule["category_any"])
    if rule.get("terms_any"):
        checks.append(any(term in full_text for term in rule["terms_any"]))
    if rule.get("title_any"):
        checks.append(any(term in title for term in rule["title_any"]))
    if rule.get("ingredient_any"):
        checks.append(any(term in ingredients for term in rule["ingredient_any"]))
    if rule.get("terms_none"):
        checks.append(not any(term in full_text for term in rule["terms_none"]))
    return any(checks) if checks else bool(rule.get("category_none"))


def parse_measure(measure: str):
    """Convert common recipe measures to comparable volume, weight, or item units."""
    text = (measure or "").strip().lower()
    match = re.search(NUMBER_PATTERN, text)
    amount = 1.0
    if match:
        token = re.sub(r"\s+", " ", match.group(0))
        if " " in token and "/" in token:
            whole, fraction = token.split()
            numerator, denominator = fraction.split("/")
            amount = float(whole) + float(numerator) / float(denominator)
        elif "/" in token:
            numerator, denominator = token.split("/")
            amount = float(numerator) / float(denominator)
        else:
            amount = float(token)
        text = text[match.end():].strip()
    unit_match = re.search(r"\b(teaspoons?|tsp|tablespoons?|tbsp|cups?|milliliters?|ml|liters?|l|kilograms?|kg|grams?|g|ounces?|oz|pounds?|lbs?)\b", text)
    if unit_match:
        unit = unit_match.group(1).strip()
        factor, canonical_unit = UNIT_CONVERSIONS[unit]
        return amount * factor, canonical_unit
    item_match = re.search(r"\b(cans?|tins?|cloves?|pieces?|pcs|slices?|bunches?|pinches?|sprigs?|heads?|fillets?|stalks?|leaves?)\b", text)
    if item_match:
        unit = item_match.group(1)
        if unit.endswith("s") and unit not in {"pcs"}:
            unit = unit[:-1]
        if unit == "pcs":
            unit = "piece"
        return amount, unit
    return amount, "item"


def standardize_quantity(amount: float, unit: str):
    """Convert common volume and weight units; preserve discrete and package units."""
    unit = (unit or "item").strip().lower()
    if unit in UNIT_CONVERSIONS:
        factor, canonical_unit = UNIT_CONVERSIONS[unit]
        return amount * factor, canonical_unit
    if unit.endswith("s") and unit not in {"glass"}:
        unit = unit[:-1]
    if unit == "pcs":
        unit = "piece"
    return amount, unit


def purchase_line(name: str, amount: float, unit: str):
    """Return a shopping suggestion using common approximate retail package sizes."""
    package_size = PACKAGE_SIZES.get(name, {}).get(unit)
    if package_size:
        packages = max(1, ceil(amount / package_size))
        return f"{name}: buy {packages} × {package_size:g} {unit} package(s) (need {amount:g} {unit})"
    if unit in {"can", "tin", "piece", "clove", "slice", "bunch", "head", "fillet", "stalk"}:
        return f"{name}: buy {max(1, ceil(amount))} {unit}(s) (need {amount:g} {unit})"
    return f"{name}: {amount:g} {unit}"
