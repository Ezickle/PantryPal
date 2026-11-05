"""Command-line flow for PantryPal's live recipe search."""

from food_data import (ALIASES, CUISINE_AREAS, FOOD_MOODS, MOOD_ALIASES,
                       PACKAGE_SIZES, SUBSTITUTIONS, UNIT_CONVERSIONS,
                       canonical_ingredient, matches_mood, normalize, normalize_mood,
                       parse_measure, purchase_line, standardize_quantity)
from recipe_api import (RecipeSearchError, api_get, closest_ingredient, fetch_details,
                        ingredient_vocabulary, load_online_feedback, parse_meal,
                        parse_pantry, rank_meal, save_online_feedback, search_many,
                        search_meals, violates_preferences, ONLINE_FEEDBACK_FILE)
from recipe_planner import (food_labels, make_online_plan, record_online_feedback,
                            related_variants, show_plan, suggest_substitutions)


def online_search_flow():
    print("\nLive search uses TheMealDB. Enter up to 3 dish names or main ingredients.")
    print("Moods include sweet, spicy, savory, comfort, hearty, fresh, citrusy, creamy, smoky, crispy,")
    print("tropical, herby, nutty, garlicky, mild, breakfast, seafood, and many cuisine styles.")
    print("Examples: Japanese, Italian, Mexican, Thai, Indian, French, Spanish, and Vietnamese.")
    print("Diet and allergy checks use ingredient names returned by the service; verify the linked recipe details.")
    mood_text = input("What kind of food are you feeling? (comma separated, optional): ")
    moods = [part.strip() for part in mood_text.split(",") if part.strip()]
    queries = [part.strip() for part in input("Search terms (comma separated, optional): ").split(",") if part.strip()][:3]
    if not queries and not moods:
        print("Search cancelled.")
        return
    pantry_text = input("Pantry quantities (example: tomato=3 pieces, rice=2 cups) [none]: ").strip()
    pantry = parse_pantry(pantry_text)
    diet = input("Diet (none/vegan/vegetarian/pescatarian/dairy-free/gluten-free) [none]: ").strip().lower() or "none"
    valid_diets = {"none", "vegan", "vegetarian", "pescatarian", "dairy-free", "gluten-free"}
    if diet not in valid_diets:
        print("Unknown diet; using none.")
        diet = "none"
    allergies = {item.strip().lower() for item in input("Allergies to screen out (comma separated) [none]: ").split(",") if item.strip()}
    try:
        meals = search_many(queries, pantry, diet, allergies, moods)
    except RecipeSearchError as exc:
        print(f"\n{exc}")
        print("Check your internet connection and try again. The built-in planner is still available.")
        return
    if not meals:
        print("\nNo online recipes matched that query and those filters.")
        return
    count = int_prompt("How many different meals should I plan?", 3, 1, 7)
    leftovers = input("Double each recipe batch for leftovers? (y/n) [n]: ").strip().lower() in {"y", "yes"}
    if len(meals) < count:
        print(f"Only {len(meals)} distinct recipes were found; planning {len(meals)} meal(s) instead.")
        count = len(meals)
    plan = make_online_plan(meals, count, pantry, leftovers)
    show_plan(plan, meals, pantry, leftovers, moods, diet, allergies)


def int_prompt(prompt: str, default: int, minimum: int, maximum: int):
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return default
        try:
            value = int(raw)
            if minimum <= value <= maximum:
                return value
        except ValueError:
            pass
        print(f"Enter a whole number from {minimum} to {maximum}.")
