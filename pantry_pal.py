"""PantryPal: a multi-step, preference-aware meal-planning agent.

Run with: python pantry_pal.py
Only the Python standard library is used. Quantities are per recipe serving.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Tuple
import json
from online_recipes import (
    canonical_ingredient as canonical_item,
    food_labels,
    online_search_flow,
    parse_measure,
    purchase_line,
    standardize_quantity,
    suggest_substitutions,
)


MEMORY_FILE = Path(__file__).with_name("pantry_pal_memory.json")

@dataclass(frozen=True)
class Recipe:
    id: str
    name: str
    ingredients: Dict[str, Tuple[float, str]]  # item -> (amount per serving, unit)
    minutes: int
    cost: float
    calories: int
    protein: int
    tags: FrozenSet[str]
    allergens: FrozenSet[str]
    instructions: Tuple[str, ...]


def recipe(id_, name, ingredients, minutes, cost, calories, protein, tags, allergens, *steps):
    return Recipe(id_, name, ingredients, minutes, cost, calories, protein,
                  frozenset(tags), frozenset(allergens), tuple(steps))


# Approximate nutrition and cost values are for a classroom demo, not dietary advice.
RECIPES = [
    recipe("chickpea_curry", "Chickpea tomato curry", {"chickpeas": (0.5, "can"), "tomatoes": (0.5, "can"), "onion": (0.25, "piece"), "rice": (0.5, "cup"), "curry powder": (1, "tsp"), "oil": (1, "tsp")}, 30, 2.70, 520, 18, {"vegan", "vegetarian", "dairy-free", "gluten-free"}, {"none"}, "Cook rice according to its package directions.", "Chop and cook onion in oil until soft; stir in curry powder.", "Add tomatoes and chickpeas; simmer for 15 minutes and serve over rice."),
    recipe("peanut_noodles", "Peanut vegetable noodles", {"noodles": (2, "oz"), "peanut butter": (1.5, "tbsp"), "soy sauce": (1, "tbsp"), "carrot": (0.5, "piece"), "lime": (0.25, "piece")}, 20, 2.40, 610, 21, {"vegetarian", "dairy-free"}, {"peanuts", "soy", "gluten"}, "Boil noodles until tender and drain.", "Whisk peanut butter, soy sauce, lime juice, and warm water.", "Slice carrot thinly, then toss everything together."),
    recipe("black_bean_tacos", "Black bean tacos", {"tortillas": (2, "piece"), "black beans": (0.5, "can"), "tomatoes": (0.5, "piece"), "lettuce": (0.5, "cup"), "cheese": (0.5, "oz")}, 20, 3.10, 490, 20, {"vegetarian"}, {"dairy", "gluten"}, "Warm and lightly mash the black beans.", "Warm tortillas in a pan.", "Fill tortillas with beans, chopped tomatoes, lettuce, and cheese."),
    recipe("tomato_pasta", "Garlic tomato pasta", {"pasta": (3, "oz"), "tomatoes": (1, "piece"), "garlic": (1, "clove"), "oil": (1, "tsp"), "parmesan": (0.5, "oz")}, 25, 2.80, 560, 19, {"vegetarian"}, {"wheat", "dairy"}, "Boil pasta until tender; save a little pasta water.", "Cook garlic in oil, add chopped tomatoes, and simmer for 10 minutes.", "Toss pasta with sauce and a splash of pasta water; top with parmesan."),
    recipe("lentil_soup", "Lentil vegetable soup", {"lentils": (0.5, "cup"), "carrot": (0.5, "piece"), "onion": (0.25, "piece"), "broth": (1.5, "cup"), "tomatoes": (0.5, "cup")}, 40, 2.20, 390, 23, {"vegan", "vegetarian", "dairy-free", "gluten-free"}, {"none"}, "Chop the onion and carrot.", "Add vegetables, lentils, broth, and tomatoes to a pot.", "Simmer until lentils are tender, about 30 minutes."),
    recipe("fried_rice", "Egg and vegetable fried rice", {"rice": (0.75, "cup"), "eggs": (1, "piece"), "peas": (0.5, "cup"), "carrot": (0.5, "piece"), "soy sauce": (1, "tbsp"), "oil": (1, "tsp")}, 20, 2.30, 450, 17, {"vegetarian", "dairy-free"}, {"eggs", "soy"}, "Use chilled cooked rice if available; otherwise cook rice and let it cool.", "Scramble the egg, then set it aside.", "Stir-fry carrot and peas, add rice and soy sauce, then fold in the egg."),
    recipe("baked_potato", "Loaded baked potato", {"potato": (1, "piece"), "beans": (0.25, "cup"), "cheese": (0.5, "oz"), "yogurt": (1, "tbsp"), "green onion": (1, "piece")}, 50, 2.60, 430, 19, {"vegetarian", "gluten-free"}, {"dairy"}, "Pierce potato with a fork and bake at 400°F (205°C) until tender, about 45 minutes.", "Warm the beans.", "Split potato and top with beans, cheese, yogurt, and sliced green onion."),
    recipe("shakshuka", "Tomato and egg skillet", {"eggs": (2, "piece"), "tomatoes": (1, "cup"), "bell pepper": (0.5, "piece"), "onion": (0.25, "piece"), "bread": (1, "slice")}, 30, 3.00, 410, 22, {"vegetarian"}, {"eggs", "wheat"}, "Cook chopped onion and bell pepper in a skillet until softened.", "Add tomatoes and simmer for 10 minutes.", "Make wells, crack in eggs, cover, and cook until set. Serve with bread."),
    recipe("tofu_stir_fry", "Tofu and broccoli stir-fry", {"tofu": (4, "oz"), "broccoli": (1, "cup"), "rice": (0.5, "cup"), "soy sauce": (1, "tbsp"), "oil": (1, "tsp")}, 25, 3.50, 480, 27, {"vegan", "vegetarian", "dairy-free"}, {"soy"}, "Cook rice according to package directions.", "Cube tofu and brown in a pan with oil.", "Add broccoli and a splash of water; cover until tender, then add soy sauce."),
    recipe("greek_chickpea_bowl", "Greek chickpea bowl", {"chickpeas": (0.5, "can"), "cucumber": (0.5, "piece"), "tomatoes": (0.5, "piece"), "feta": (0.5, "oz"), "lemon": (0.25, "piece")}, 15, 3.20, 420, 18, {"vegetarian", "gluten-free"}, {"dairy"}, "Rinse and drain chickpeas.", "Chop cucumber and tomatoes; crumble feta.", "Toss with lemon juice, a little oil, salt, and pepper."),
    recipe("bean_burrito", "Bean and corn burrito", {"tortillas": (1, "piece"), "black beans": (0.5, "can"), "corn": (0.5, "cup"), "rice": (0.5, "cup"), "salsa": (2, "tbsp")}, 25, 2.60, 540, 19, {"vegan", "vegetarian", "dairy-free"}, {"wheat"}, "Cook rice and warm beans and corn.", "Layer rice, beans, corn, and salsa on the tortilla.", "Fold in the sides, roll tightly, and toast seam-side down."),
    recipe("tuna_pasta", "Tuna lemon pasta", {"pasta": (3, "oz"), "tuna": (0.5, "can"), "lemon": (0.25, "piece"), "peas": (0.5, "cup"), "yogurt": (1, "tbsp")}, 20, 3.40, 500, 31, {"pescatarian"}, {"fish", "wheat", "dairy"}, "Boil pasta; add peas for the last 2 minutes, then drain.", "Drain tuna and mix with yogurt and lemon juice.", "Toss sauce with pasta and peas; season to taste."),
    recipe("chicken_couscous", "Chicken and vegetable couscous", {"chicken": (4, "oz"), "couscous": (0.5, "cup"), "zucchini": (0.5, "piece"), "lemon": (0.25, "piece"), "oil": (1, "tsp")}, 30, 4.20, 520, 38, {"dairy-free"}, {"none"}, "Prepare couscous according to package directions.", "Cook chicken thoroughly in a pan with oil; remove and rest.", "Cook sliced zucchini, then serve with sliced chicken, couscous, and lemon."),
    recipe("spinach_quesadilla", "Spinach and cheese quesadilla", {"tortillas": (2, "piece"), "cheese": (1, "oz"), "spinach": (1, "cup"), "beans": (0.25, "cup")}, 15, 2.90, 470, 23, {"vegetarian"}, {"dairy", "wheat"}, "Put cheese, spinach, and beans on half of each tortilla.", "Fold and cook in a dry skillet until golden on both sides.", "Cut into wedges and serve."),
    recipe("overnight_oats", "Savory tomato chickpea bowl", {"quinoa": (0.5, "cup"), "chickpeas": (0.25, "can"), "cucumber": (0.5, "piece"), "tomatoes": (0.5, "piece"), "lemon": (0.25, "piece")}, 25, 3.30, 460, 19, {"vegan", "vegetarian", "dairy-free", "gluten-free"}, {"none"}, "Rinse quinoa and simmer in water until fluffy.", "Rinse chickpeas and chop cucumber and tomatoes.", "Serve over quinoa with lemon juice, salt, and pepper."),
    recipe("mushroom_omelet", "Mushroom spinach omelet", {"eggs": (2, "piece"), "mushrooms": (0.5, "cup"), "spinach": (0.5, "cup"), "cheese": (0.5, "oz")}, 15, 2.80, 370, 27, {"vegetarian", "gluten-free"}, {"eggs", "dairy"}, "Slice mushrooms and cook until browned; wilt spinach in the pan.", "Beat eggs, pour into the pan, and cook gently until nearly set.", "Add cheese and vegetables, fold, and cook until eggs are done."),
    recipe("hummus_wrap", "Hummus crunch wrap", {"tortillas": (1, "piece"), "hummus": (2, "tbsp"), "carrot": (0.5, "piece"), "cucumber": (0.5, "piece"), "spinach": (0.5, "cup")}, 10, 2.50, 360, 12, {"vegan", "vegetarian", "dairy-free"}, {"sesame", "wheat"}, "Spread hummus over the tortilla.", "Add grated carrot, cucumber sticks, and spinach.", "Fold tightly and cut in half."),
]


@dataclass
class UserProfile:
    diet: str = "none"
    allergies: FrozenSet[str] = frozenset()
    dislikes: FrozenSet[str] = frozenset()
    liked: List[str] = field(default_factory=list)
    avoided: List[str] = field(default_factory=list)


@dataclass
class Request:
    meals: int
    servings: int
    max_minutes: int
    budget: float
    min_protein: int
    pantry: Dict[Tuple[str, str], float]
    double_for_leftovers: bool = False


class PantryPalAgent:
    """Goal-based agent: perceive preferences, search plans, act, then update memory."""

    def __init__(self):
        self.profile = self.load_memory()

    @staticmethod
    def load_memory() -> UserProfile:
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            return UserProfile(data.get("diet", "none"), frozenset(data.get("allergies", [])),
                               frozenset(data.get("dislikes", [])), data.get("liked", []), data.get("avoided", []))
        except (OSError, ValueError, TypeError):
            return UserProfile()

    def save_memory(self):
        data = {"diet": self.profile.diet, "allergies": sorted(self.profile.allergies),
                "dislikes": sorted(self.profile.dislikes), "liked": self.profile.liked[-20:],
                "avoided": self.profile.avoided[-20:]}
        MEMORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def perceive(self):
        print("\nLet's set your goal and constraints.")
        saved = self.profile
        print(f"Saved preferences: diet={saved.diet}, allergies={', '.join(sorted(saved.allergies)) or 'none'}, dislikes={', '.join(sorted(saved.dislikes)) or 'none'}")
        diet = ask_choice("Diet", ["none", "vegan", "vegetarian", "pescatarian", "dairy-free", "gluten-free"], saved.diet)
        allergies = ask_list("Allergies to exclude (comma separated; blank keeps saved)", saved.allergies)
        dislikes = ask_list("Ingredients you dislike (comma separated; blank keeps saved)", saved.dislikes)
        meals = int(ask_number("How many meals should I plan?", 3, 1, 7))
        servings = int(ask_number("Servings per meal", 2, 1, 12))
        max_minutes = int(ask_number("Maximum cooking time per meal (minutes)", 40, 5, 180))
        budget = ask_number("Weekly estimated grocery budget for this plan ($)", 30, 1, 1000)
        min_protein = int(ask_number("Minimum protein per serving in grams (0 to skip)", 0, 0, 100))
        pantry = ask_pantry()
        leftovers = input("Double each meal batch for leftovers? (y/n) [n]: ").strip().lower() in {"y", "yes"}
        self.profile = UserProfile(diet, frozenset(allergies), frozenset(dislikes), saved.liked, saved.avoided)
        return Request(meals, servings, max_minutes, budget, min_protein, pantry, leftovers)

    def plan(self, request: Request):
        candidates = [r for r in RECIPES if self.is_feasible(r, request)]
        if len(candidates) < request.meals:
            return [], candidates
        # Beam search explores alternative meal combinations under the weekly budget.
        # Each state holds (objective score, chosen recipes, running cost, used pantry).
        beam = [(0.0, tuple(), 0.0, dict(request.pantry))]
        beam_width = 300
        for _ in range(request.meals):
            expanded = []
            for score, chosen, cost, remaining in beam:
                already = {r.id for r in chosen}
                for r in candidates:
                    if r.id in already:
                        continue
                    multiplier = 2 if request.double_for_leftovers else 1
                    batch_servings = request.servings * multiplier
                    pantry_used = pantry_coverage(r, remaining, batch_servings)
                    pantry_ratio = pantry_fraction(r, pantry_used, batch_servings)
                    meal_cost = r.cost * batch_servings * (1 - pantry_ratio)
                    if cost + meal_cost > request.budget:
                        continue
                    new_remaining = dict(remaining)
                    for key, amount in pantry_used.items():
                        new_remaining[key] = max(0, new_remaining.get(key, 0) - amount)
                    new_score = score + self.score(r, request, pantry_used)
                    previous_ingredients = {canonical_item(item) for old in chosen for item in old.ingredients}
                    new_score += 0.4 * len(previous_ingredients &
                                           {canonical_item(item) for item in r.ingredients})
                    expanded.append((new_score, chosen + (r,), cost + meal_cost, new_remaining))
            if not expanded:
                return [], candidates
            expanded.sort(key=lambda state: state[0], reverse=True)
            beam = expanded[:beam_width]
        best = max(beam, key=lambda state: state[0])
        return list(best[1]), candidates

    def is_feasible(self, r: Recipe, req: Request) -> bool:
        if r.minutes > req.max_minutes or r.protein < req.min_protein:
            return False
        if self.profile.diet != "none" and self.profile.diet not in r.tags:
            return False
        if self.profile.allergies & r.allergens:
            return False
        if any(canonical_item(dislike) in canonical_item(ingredient)
               for dislike in self.profile.dislikes for ingredient in r.ingredients):
            return False
        return True

    def score(self, r: Recipe, req: Request, pantry_used: Dict[str, float]) -> float:
        batch_servings = req.servings * (2 if req.double_for_leftovers else 1)
        pantry_ratio = pantry_fraction(r, pantry_used, batch_servings)
        score = 12 * pantry_ratio + min(r.protein, 40) * 0.12
        score -= r.minutes * 0.025 + r.cost * req.servings * 0.06
        if r.id in self.profile.liked:
            score += 2.0
        if r.id in self.profile.avoided:
            score -= 3.0
        return score

    def act(self, plan, request, candidates=None):
        print("\n" + "=" * 64)
        print("YOUR MEAL PLAN")
        print("=" * 64)
        multiplier = 2 if request.double_for_leftovers else 1
        remaining = dict(request.pantry)
        total_cost = 0.0
        for r in plan:
            batch_servings = request.servings * multiplier
            used = pantry_coverage(r, remaining, batch_servings)
            coverage = pantry_fraction(r, used, batch_servings)
            total_cost += r.cost * batch_servings * (1 - coverage)
            for key, amount in used.items():
                remaining[key] = max(0.0, remaining.get(key, 0.0) - amount)
        if request.double_for_leftovers:
            print("Each recipe is doubled to provide leftovers.")
        for day, r in enumerate(plan, 1):
            print(f"\nMeal {day}: {r.name}")
            labels = food_labels(r.name, list(r.ingredients), extra=tuple(sorted(r.tags)))
            print("  Labels: " + ", ".join(labels))
            print(f"  Batch estimate: {r.cost * request.servings * multiplier:.2f} USD before pantry stock.")
            print(f"  Time: {r.minutes} min | Est. cost: ${r.cost * request.servings:.2f} | {r.calories} kcal | {r.protein}g protein per serving")
            print("  Steps:")
            for i, step in enumerate(r.instructions, 1):
                print(f"    {i}. {step}")
        print(f"\nEstimated recipe total: ${total_cost:.2f} of ${request.budget:.2f} budget")
        shopping = grocery_list(plan, request)
        print("\nCOMBINED GROCERY LIST (after using your pantry)")
        if not shopping:
            print("  Nothing to buy from this recipe list.")
        else:
            for item in sorted(shopping):
                amount, unit = shopping[item]
                name, _unit = item
                print("  - " + purchase_line(name, amount, unit))
        swaps = suggest_substitutions(list(shopping.items()), request.pantry,
                                      self.profile.diet, set(self.profile.allergies))
        if swaps:
            print("\nOPTIONAL SUBSTITUTIONS USING ITEMS ALREADY IN YOUR PANTRY")
            for missing, available in swaps:
                print(f"  - Try {available} in place of {missing}; adjust the recipe to taste.")
        print("\nRELATED RECIPE VARIANTS")
        variant_count = 0
        planned_ids = {recipe.id for recipe in plan}
        for recipe in plan:
            variants = []
            source = {canonical_item(item) for item in recipe.ingredients}
            for other in (candidates or RECIPES):
                if other.id in planned_ids:
                    continue
                other_items = {canonical_item(item) for item in other.ingredients}
                overlap = len(source & other_items) / max(len(source | other_items), 1)
                if overlap >= 0.2:
                    variants.append((overlap, other))
            variants.sort(key=lambda pair: pair[0], reverse=True)
            if variants:
                variant_count += len(variants[:2])
                print(f"  Instead of {recipe.name}:")
                for _score, other in variants[:2]:
                    labels = food_labels(other.name, list(other.ingredients), extra=tuple(sorted(other.tags)))
                    print(f"    - {other.name} [{', '.join(labels)}]")
        if not variant_count:
            print("  No close variants were found in the built-in catalog.")
        self.feedback(plan)

    def feedback(self, plan):
        answer = input("\nDid you like this plan? (y/n/skip) [skip]: ").strip().lower()
        if answer in {"y", "yes"}:
            self.profile.liked = list(dict.fromkeys(self.profile.liked + [r.id for r in plan]))
            print("Got it. I'll favor these recipes next time.")
        elif answer in {"n", "no"}:
            self.profile.avoided = list(dict.fromkeys(self.profile.avoided + [r.id for r in plan]))
            print("Thanks. I'll rank these recipes lower in future plans.")
        self.save_memory()


def pantry_coverage(r: Recipe, pantry: Dict[str, float], servings: int) -> Dict[str, float]:
    """Allocate available pantry quantities to one meal; units match recipe catalog."""
    used = {}
    for item, (amount, _unit) in r.ingredients.items():
        normalized_amount, normalized_unit = standardize_quantity(amount * servings, _unit)
        key = (canonical_item(item), normalized_unit)
        used[key] = min(pantry.get(key, 0), normalized_amount)
    return used


def pantry_fraction(r: Recipe, pantry_used: Dict[Tuple[str, str], float], servings: int) -> float:
    fractions = []
    for item, (amount, unit) in r.ingredients.items():
        required, normalized_unit = standardize_quantity(amount * servings, unit)
        available = pantry_used.get((canonical_item(item), normalized_unit), 0)
        fractions.append(min(1.0, available / required) if required else 0.0)
    return sum(fractions) / len(fractions) if fractions else 0.0


def grocery_list(plan: List[Recipe], req: Request):
    totals: Dict[str, List[float | str]] = {}
    for r in plan:
        for item, (amount, unit) in r.ingredients.items():
            key = canonical_item(item)
            normalized_amount, normalized_unit = standardize_quantity(amount * req.servings, unit)
            compound_key = f"{key}|{normalized_unit}"
            if compound_key not in totals:
                totals[compound_key] = [0.0, normalized_unit]
            multiplier = 2 if req.double_for_leftovers else 1
            totals[compound_key][0] += normalized_amount * multiplier
    for item in totals:
        name, unit = item.rsplit("|", 1)
        totals[item][0] = max(0, totals[item][0] - req.pantry.get((name, unit), 0))
    return {(item.rsplit("|", 1)[0], str(values[1])): (float(values[0]), str(values[1]))
            for item, values in totals.items() if values[0] > 0}


def ask_choice(label, options, default):
    prompt = f"{label} ({'/'.join(options)}) [{default}]: "
    while True:
        answer = input(prompt).strip().lower()
        if not answer:
            return default
        if answer in options:
            return answer
        print("Choose one of: " + ", ".join(options))


def ask_list(prompt, defaults):
    answer = input(f"{prompt} [{', '.join(sorted(defaults)) or 'none'}]: ").strip().lower()
    if not answer:
        return set(defaults)
    if answer in {"none", "clear"}:
        return set()
    return {item.strip() for item in answer.split(",") if item.strip()}


def ask_number(prompt, default, minimum, maximum):
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return float(default)
        try:
            value = float(raw)
            if minimum <= value <= maximum:
                return value
        except ValueError:
            pass
        print(f"Enter a number from {minimum} to {maximum}.")


def ask_pantry():
    print("Enter pantry amounts with units when possible (examples: rice=2 cups, tomatoes=3 pieces).")
    print("Items with no amount are treated as unavailable.")
    pantry = {}
    while True:
        raw = input("Pantry items as name=amount, comma separated [none]: ").strip().lower()
        if not raw:
            return pantry
        try:
            for part in raw.split(","):
                name, quantity = part.split("=", 1)
                fields = quantity.strip().split()
                key = canonical_item(name.strip())
                catalog_units = {u for r in RECIPES for ingredient, (_a, u) in r.ingredients.items()
                                 if canonical_item(ingredient) == key}
                if len(fields) > 1:
                    amount, unit = parse_measure(quantity)
                else:
                    amount = float(fields[0])
                    unit = next(iter(catalog_units)) if len(catalog_units) == 1 else "piece"
                amount, unit = standardize_quantity(amount, unit)
                pantry[(key, unit)] = pantry.get((key, unit), 0) + max(0, amount)
            return pantry
        except ValueError:
            print("Use name=amount pairs, such as rice=2, tomatoes=1.5")


def main():
    print("PantryPal | Intelligent Meal Planner")
    agent = PantryPalAgent()
    while True:
        print("\n1. Search live online recipes")
        print("2. Build a multi-meal plan from the built-in catalog")
        print("3. Exit")
        choice = input("Choose an option [1]: ").strip() or "1"
        if choice == "1":
            online_search_flow()
        elif choice == "2":
            request = agent.perceive()
            plan, candidates = agent.plan(request)
            if plan:
                agent.act(plan, request, candidates)
            else:
                print("\nI couldn't build a plan that satisfies every constraint and fits the budget.")
                print(f"Feasible individual recipes: {len(candidates)}; requested meals: {request.meals}.")
                print("Try a larger budget, more cooking time, a lower protein target, or fewer meals.")
        elif choice == "3":
            print("PantryPal saved your preferences. Happy cooking!")
            break
        else:
            print("Choose 1, 2, or 3.")


if __name__ == "__main__":
    from pantry_pal_ui import launch_ui
    launch_ui()
