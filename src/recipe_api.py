"""TheMealDB search, parsing, and preference filtering."""

from __future__ import annotations

import json
import re
from difflib import get_close_matches, SequenceMatcher
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from food_data import (ALIASES, ALLERGEN_TERMS, CUISINE_AREAS, DIET_EXCLUSIONS,
                       MOOD_SEARCHES, matches_mood, normalize, normalize_mood,
                       canonical_ingredient, parse_measure)

BASE_URL = "https://www.themealdb.com/api/json/v1/1/"
USER_AGENT = "PantryPal-Student-Project/1.0"
ONLINE_FEEDBACK_FILE = Path(__file__).with_name("pantry_pal_online_feedback.json")
INGREDIENT_VOCABULARY = None


class RecipeSearchError(Exception):
    """Raised when TheMealDB cannot be reached or returns invalid data."""


def api_get(endpoint: str, params: dict):
    url = BASE_URL + endpoint + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise RecipeSearchError(f"The online recipe service could not be reached: {exc}") from exc


def load_online_feedback():
    try:
        data = json.loads(ONLINE_FEEDBACK_FILE.read_text(encoding="utf-8"))
        return set(data.get("liked", [])), set(data.get("avoided", []))
    except (OSError, ValueError, TypeError):
        return set(), set()


def save_online_feedback(liked: set[str], avoided: set[str]):
    data = {"liked": sorted(liked), "avoided": sorted(avoided)}
    ONLINE_FEEDBACK_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def parse_meal(raw: dict):
    ingredients = []
    for index in range(1, 21):
        name = (raw.get(f"strIngredient{index}") or "").strip()
        measure = (raw.get(f"strMeasure{index}") or "").strip()
        if name:
            amount, unit = parse_measure(measure)
            ingredients.append({"name": name, "canonical": canonical_ingredient(name),
                                "measure": measure, "amount": amount, "unit": unit})
    instructions = re.sub(r"\r\n?", "\n", raw.get("strInstructions") or "").strip()
    steps = [re.sub(r"^\s*(?:\d+[.)]|[-*])\s*", "", line).strip()
             for line in re.split(r"\n+", instructions) if line.strip()]
    if len(steps) <= 1:
        steps = [part.strip() for part in re.split(r"(?<=[.!?])\s+", instructions) if part.strip()]
    return {"id": raw.get("idMeal", ""), "name": raw.get("strMeal", "Untitled recipe"),
            "category": raw.get("strCategory") or "Uncategorized", "area": raw.get("strArea") or "Unknown",
            "ingredients": ingredients, "steps": steps, "thumbnail": raw.get("strMealThumb") or "",
            "source": raw.get("strSource") or "",
            "url": raw.get("strSource") or f"https://www.themealdb.com/meal/{raw.get('idMeal', '')}"}


def estimate_nutrition(meal: dict):
    """Return a deliberately rough whole-recipe estimate from listed measures."""
    profiles = (
        (("oil", "butter", "ghee", "lard", "margarine"), 8.8, 0),
        (("cheese", "parmesan", "mozzarella", "cream", "coconut milk"), 3.2, 0.12),
        (("chicken", "beef", "pork", "lamb", "turkey", "duck", "fish", "salmon", "tuna", "prawn", "shrimp"), 1.9, 0.22),
        (("lentil", "chickpea", "bean", "tofu", "tempeh", "pea"), 1.35, 0.09),
        (("rice", "pasta", "noodle", "flour", "bread", "oat", "quinoa", "potato"), 1.5, 0.045),
        (("sugar", "honey", "syrup", "jam"), 3.8, 0),
        (("tomato", "onion", "garlic", "pepper", "carrot", "spinach", "broccoli", "cabbage", "mushroom", "zucchini", "eggplant", "lemon", "lime", "herb"), 0.35, 0.018),
    )
    calories = protein = 0.0
    for item in meal.get("ingredients", []):
        name = normalize(item.get("name", ""))
        kcal, protein_per_100g = 0.8, 0.04
        for terms, profile_kcal, profile_protein in profiles:
            if any(term in name for term in terms):
                kcal, protein_per_100g = profile_kcal, profile_protein
                break
        amount, unit = item.get("amount", 1), item.get("unit", "item")
        try:
            amount = max(0.0, float(amount))
        except (TypeError, ValueError):
            amount = 1.0
        grams = amount * {"g": 1, "kg": 1000, "ml": 1, "l": 1000,
                          "oz": 28, "lb": 454, "clove": 3, "piece": 100,
                          "slice": 25, "can": 400, "fillet": 150,
                          "bunch": 50, "item": 80}.get(unit, 80)
        calories += grams * kcal
        protein += grams * protein_per_100g
    return {"calories": round(calories / 10) * 10, "protein": round(protein)}


def ingredient_vocabulary():
    global INGREDIENT_VOCABULARY
    if INGREDIENT_VOCABULARY is None:
        vocabulary = set(ALIASES) | set(ALIASES.values())
        try:
            response = api_get("list.php", {"i": "list"})
            vocabulary.update(normalize(item.get("strIngredient") or "")
                              for item in (response.get("meals") or []))
        except RecipeSearchError:
            pass
        INGREDIENT_VOCABULARY = {item for item in vocabulary if item}
    return INGREDIENT_VOCABULARY


def closest_ingredient(text: str):
    cleaned = normalize(text)
    vocabulary = {normalize(item) for item in ingredient_vocabulary()}
    if cleaned in vocabulary or not cleaned:
        return cleaned
    matches = get_close_matches(cleaned, sorted(vocabulary), n=5, cutoff=0.70)
    ranked = [(candidate, SequenceMatcher(None, cleaned, candidate).ratio()) for candidate in matches]
    ranked = [(candidate, score) for candidate, score in ranked if score >= 0.78]
    if not ranked:
        return cleaned
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] <= 0.06:
        options = list(dict.fromkeys(candidate for candidate, _ in ranked[:3]))
        print(f"\nI found a few close ingredient matches for '{text.strip()}':")
        for index, option in enumerate(options, 1):
            print(f"  {index}. {option}")
        print("  0. Keep the original spelling")
        choice = input("Choose a match [0]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        return cleaned
    return ranked[0][0]


def parse_pantry(raw: str):
    inventory = {}
    for entry in raw.split(","):
        if "=" not in entry:
            continue
        name, quantity = entry.split("=", 1)
        amount, unit = parse_measure(quantity)
        corrected = closest_ingredient(name)
        if corrected != normalize(name):
            print(f"  Recognized pantry item '{name.strip()}' as '{corrected}'.")
        key = canonical_ingredient(corrected)
        inventory[(key, unit)] = inventory.get((key, unit), 0.0) + amount
    return inventory


def rank_meal(meal: dict, pantry: dict, query: str):
    names = {item["canonical"] for item in meal["ingredients"]}
    available = {name for (name, _unit), amount in pantry.items() if amount > 0}
    matched = names & available
    coverage = len(matched) / max(len(names), 1)
    score = 10 * coverage + (2 if normalize(query) in normalize(meal["name"]) else 0)
    meal["pantry_matches"], meal["pantry_coverage"] = sorted(matched), coverage
    return score


def violates_preferences(meal: dict, diet: str, allergies: set[str]):
    text = f" {normalize(' '.join(item['name'] for item in meal['ingredients']))} "
    for allergy in allergies:
        terms = ALLERGEN_TERMS.get(allergy, [allergy])
        if any(f" {normalize(term)} " in text for term in terms):
            return True
    for term in DIET_EXCLUSIONS.get(diet, []):
        if f" {normalize(term)} " in text:
            return True
    return False


def fetch_details(summaries, pantry, diet, allergies, query):
    results, skipped = [], 0
    for summary in summaries:
        try:
            payload = api_get("lookup.php", {"i": summary["idMeal"]})
        except RecipeSearchError:
            skipped += 1
            continue
        details = payload.get("meals") or []
        if not details:
            continue
        meal = parse_meal(details[0])
        if not violates_preferences(meal, diet, allergies):
            meal["score"] = rank_meal(meal, pantry, query)
            results.append(meal)
    if skipped:
        print(f"  {skipped} recipe detail(s) could not be retrieved; those results were skipped.")
    return results


def search_meals(query, pantry, diet, allergies, limit=8):
    query = query.strip()
    meals = (api_get("search.php", {"s": query}).get("meals") or [])
    if not meals:
        corrected = closest_ingredient(query)
        if normalize(corrected) != normalize(query):
            print(f"  Interpreting '{query}' as '{corrected}'.")
        meals = api_get("filter.php", {"i": corrected.replace(" ", "_")}).get("meals") or []
    return sorted(fetch_details(meals[:limit], pantry, diet, allergies, query),
                  key=lambda meal: meal["score"], reverse=True)


def search_many(queries, pantry, diet, allergies, moods=None):
    moods = [normalize_mood(mood) for mood in (moods or []) if mood.strip()]
    by_id = {}
    def add(meals):
        by_id.update((meal["id"], meal) for meal in meals)
    for query in queries:
        add(search_meals(query, pantry, diet, allergies, limit=8))
    for mood in moods:
        if mood in CUISINE_AREAS:
            payload = api_get("filter.php", {"a": CUISINE_AREAS[mood]})
            add(fetch_details((payload.get("meals") or [])[:12], pantry, diet, allergies, mood))
            continue
        config = MOOD_SEARCHES.get(mood)
        if not config:
            add(search_meals(mood, pantry, diet, allergies, limit=8))
            continue
        for category in config.get("categories", []):
            payload = api_get("filter.php", {"c": category})
            add(fetch_details((payload.get("meals") or [])[:12], pantry, diet, allergies, mood))
        for ingredient in config.get("ingredients", []):
            payload = api_get("filter.php", {"i": ingredient})
            add(fetch_details((payload.get("meals") or [])[:6], pantry, diet, allergies, mood))
        for term in config.get("terms", []):
            add(search_meals(term, pantry, diet, allergies, limit=4))
    filtered = [meal for meal in by_id.values()
                if all(matches_mood(meal, mood) for mood in moods)]
    liked, avoided = load_online_feedback()
    for meal in filtered:
        meal["score"] += 2.0 * (meal["id"] in liked) - 3.0 * (meal["id"] in avoided)
    return sorted(filtered, key=lambda meal: meal["score"], reverse=True)
