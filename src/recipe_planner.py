"""Meal selection, labels, variants, grocery output, and online feedback."""

from itertools import combinations

from food_data import FOOD_MOODS, SUBSTITUTIONS, matches_mood, normalize, purchase_line
from recipe_api import load_online_feedback, save_online_feedback, violates_preferences

def food_labels(name: str, ingredient_names: list[str], category: str = "",
                area: str = "", extra: tuple[str, ...] = ()):
    meal = {
        "name": name, "category": category, "area": area,
        "ingredients": [{"name": ingredient} for ingredient in ingredient_names],
    }
    labels = []
    for label in (category, area, *extra):
        if label and label.lower() not in {"unknown", "uncategorized", "none"} and label not in labels:
            labels.append(label)
    for mood in FOOD_MOODS:
        if matches_mood(meal, mood):
            labels.append(mood.title())
    return list(dict.fromkeys(labels))


def related_variants(meal: dict, candidates: list[dict], limit: int = 2):
    source = {item["canonical"] for item in meal["ingredients"]}
    ranked = []
    for other in candidates:
        if other["id"] == meal["id"]:
            continue
        other_ingredients = {item["canonical"] for item in other["ingredients"]}
        union = source | other_ingredients
        overlap = len(source & other_ingredients) / max(len(union), 1)
        same_area = (normalize(meal["area"]) not in {"", "unknown"}
                     and normalize(meal["area"]) == normalize(other["area"]))
        same_category = (normalize(meal["category"]) not in {"", "uncategorized"}
                         and normalize(meal["category"]) == normalize(other["category"]))
        score = overlap + 0.25 * same_area + 0.25 * same_category
        if overlap >= 0.20 or (same_category and overlap >= 0.08):
            ranked.append((score, other))
    ranked.sort(key=lambda result: result[0], reverse=True)
    return [other for _score, other in ranked[:limit]]


def suggest_substitutions(shopping, pantry, diet: str, allergies: set[str]):
    pantry_names = {name for (name, _unit), amount in pantry.items() if amount > 0}
    suggestions = []
    for (ingredient, _unit), _amount in shopping:
        for alternative in SUBSTITUTIONS.get(ingredient, ()):
            if alternative not in pantry_names:
                continue
            fake_meal = {"ingredients": [{"name": alternative}]}
            if not violates_preferences(fake_meal, diet, allergies):
                suggestions.append((ingredient, alternative))
                break
    return suggestions


def make_online_plan(meals: list[dict], meal_count: int, pantry: dict, double_for_leftovers: bool):
    """Choose a set of meals, rewarding pantry use and ingredients shared across recipes."""
    multiplier = 2 if double_for_leftovers else 1
    best_plan, best_score = None, float("-inf")
    for selection in combinations(meals, meal_count):
        used = {}
        score = 0.0
        seen_ingredients = set()
        for meal in selection:
            names = {item["canonical"] for item in meal["ingredients"]}
            score += meal["score"] + 0.8 * len(names & seen_ingredients)
            seen_ingredients |= names
            for item in meal["ingredients"]:
                key = (item["canonical"], item["unit"])
                used[key] = used.get(key, 0.0) + item["amount"] * multiplier
        for key, quantity in used.items():
            score += 1.5 * min(quantity, pantry.get(key, 0.0)) / max(quantity, 1.0)
        if score > best_score:
            best_plan, best_score = list(selection), score
    return best_plan


def show_plan(plan, candidates, pantry, double_for_leftovers, moods, diet, allergies):
    multiplier = 2 if double_for_leftovers else 1
    print("\nONLINE MEAL PLAN")
    if moods:
        print("Food mood filters: " + ", ".join(moods))
    if double_for_leftovers:
        print("Each recipe is doubled to provide leftovers.")
    for day, meal in enumerate(plan, 1):
        print(f"\nMeal {day}: {meal['name']} — {meal['area']} / {meal['category']}")
        labels = food_labels(meal["name"], [item["name"] for item in meal["ingredients"]],
                             meal["category"], meal["area"])
        print("  Labels: " + ", ".join(labels))
        print("  Ingredients:")
        for item in meal["ingredients"]:
            amount = item["amount"] * multiplier
            label = f"{amount:g} {item['unit']}" if item["unit"] != "item" else item["measure"]
            print(f"    - {label} {item['name']}")
        print("  Instructions:")
        for number, step in enumerate(meal["steps"], 1):
            print(f"    {number}. {step}")
        print(f"  Source: {meal['url']}")

    totals = {}
    for meal in plan:
        for item in meal["ingredients"]:
            key = (item["canonical"], item["unit"])
            totals[key] = totals.get(key, 0.0) + item["amount"] * multiplier
    print("\nCOMBINED GROCERY LIST (after pantry stock)")
    shopping = [(key, max(0, amount - pantry.get(key, 0.0))) for key, amount in totals.items()]
    shopping = [(key, amount) for key, amount in shopping if amount > 0]
    if not shopping:
        print("  Nothing to buy from the listed quantities.")
    for (name, unit), amount in sorted(shopping):
        print("  - " + purchase_line(name, amount, unit))
    print("  Amounts are combined only when ingredient names and units match after normalization.")
    swaps = suggest_substitutions(shopping, pantry, diet, allergies)
    if swaps:
        print("\nOPTIONAL SUBSTITUTIONS USING ITEMS ALREADY IN YOUR PANTRY")
        for missing, available in swaps:
            print(f"  - Try {available} in place of {missing}; adjust the recipe to taste.")
    planned_ids = {meal["id"] for meal in plan}
    alternatives = [meal for meal in candidates if meal["id"] not in planned_ids]
    print("\nRELATED RECIPE VARIANTS")
    found_variants = False
    for meal in plan:
        variants = related_variants(meal, alternatives, limit=2)
        if variants:
            found_variants = True
            print(f"  Instead of {meal['name']}:")
            for variant in variants:
                variant_labels = food_labels(
                    variant["name"], [item["name"] for item in variant["ingredients"]],
                    variant["category"], variant["area"])
                print(f"    - {variant['name']} [{', '.join(variant_labels)}] — {variant['url']}")
    if not found_variants:
        print("  No close variants were found in the current search results.")
    record_online_feedback(plan)


def record_online_feedback(plan):
    liked, avoided = load_online_feedback()
    changed = False
    print("\nHelp PantryPal improve these online recommendations:")
    for meal in plan:
        answer = input(f"Did you like {meal['name']}? (y/n/skip): ").strip().lower()
        if answer in {"y", "yes"}:
            liked.add(meal["id"])
            avoided.discard(meal["id"])
            changed = True
        elif answer in {"n", "no"}:
            avoided.add(meal["id"])
            liked.discard(meal["id"])
            changed = True
    if changed:
        try:
            save_online_feedback(liked, avoided)
            print("Saved. Future online plans will favor liked recipes and rank disliked ones lower.")
        except OSError as exc:
            print(f"Could not save online feedback: {exc}")


