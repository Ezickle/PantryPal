# PantryPal: Intelligent Meal Planning Agent

PantryPal now has two recipe sources. Its live search connects to TheMealDB using up to three dish names or main ingredients and food moods such as sweet, spicy, savory, comfort, fresh, creamy, smoky, breakfast, seafood, or cuisine styles including Japanese, Italian, Mexican, Thai, French, and Vietnamese. Enter several moods separated by commas to require all of them. It combines results into a multi-meal plan, ranks plans by pantry use and shared ingredients, and builds one grocery list. It normalizes common ingredient aliases, alternate spellings, plural forms, and recipe units, supports doubling recipe batches for leftovers, screens listed ingredients against diet and allergy preferences, and shows instructions with source links. Grocery quantities use common normalized units and include approximate package-size suggestions for selected ingredients. It labels meals with inferred food categories, suggests related recipes as variants, and offers optional ingredient swaps when a suitable replacement is already in the pantry. Its built-in planner also supports leftovers, ingredient reuse, a weekly estimated budget, dietary preferences, allergies, pantry quantities, servings, cooking time, protein goals, and saved feedback.

## Run it

Install Python 3.10 or later, open a terminal in this folder, and run:

```text
python pantry_pal.py
```

PantryPal opens a desktop window with a home screen featuring a rotating recipe banner and clickable popular recipe cards, plus separate screens for live recipe search and the built-in meal planner. The program uses only Python's standard library. It saves built-in planner preferences in `pantry_pal_memory.json` beside the program. Delete that file to reset the saved preferences. Live search needs an internet connection.

## Run the web app

PantryPal also has a local browser interface that uses only Python's standard library. From this folder, run:

```text
python pantry_pal_web.py
```

It opens `http://127.0.0.1:8765` in your browser. The server is available only on your own computer; it does not publish the app to the internet or require paid hosting or a subscription. The browser home page loads a rotating carousel of cached recipe picks, photos, and details from TheMealDB; discovery results appear directly below the search form. The browser interface also includes the built-in planner, saved recipes, an editable and checkable shopping list, and meal plan export. Browser-saved recipes and shopping-list progress are stored in that browser's local storage. Built-in meal planning works offline. Live recipe search, discovery, and homepage picks need an internet connection.

## Live recipe source

Live search uses TheMealDB's free V1 API and its documented learning/test key (`1`). The free API searches by name and supports filtering on one main ingredient; PantryPal fetches recipe details for the results and ranks them locally. See the [TheMealDB API guide](https://www.themealdb.com/docs_api_guide.php).

Food moods use TheMealDB recipe categories and cuisine metadata when available, plus ingredient and title terms for flavor moods. Ingredient aliases include examples such as aubergine/eggplant, courgette/zucchini, cilantro/coriander, and garbanzo beans/chickpeas. For likely typos, PantryPal cleans punctuation and spacing with regular expressions, then compares the input with TheMealDB's ingredient list and suggests a close match (for example, eggplnt to eggplant). The live search includes a Surprise Me button, which picks randomly from matching search results or requests a random TheMealDB recipe when no filters are entered. Online recipe details display approximate whole-recipe calories and protein estimated locally from the ingredient list and measures; TheMealDB does not supply nutrition values, and the estimates can be inaccurate when measures are missing or ingredient profiles are not recognized. The built-in planner uses approximate example costs and nutrition values. Dietary and allergy screening compares user selections with ingredient names returned by the service. Ingredient lists may omit sub-ingredients or cross-contact information, so treat these results as suggestions and check the linked recipe and product labels.

## What makes it an agent

The program follows a goal-based agent loop:

1. **Perceive:** collect the user's constraints and current pantry inventory.
2. **Reason:** filter out recipes that violate hard constraints, then use beam search to compare multi-meal plans within the total budget.
3. **Act:** present the selected plan, cooking instructions, cost estimate, and aggregated grocery list after pantry stock is used.
4. **Learn:** save liked and disliked recipes and use that feedback to adjust future rankings.

The recipe objective rewards use of pantry stock and protein while accounting for cost and time. Shared ingredients across selected meals add a small score bonus. Dietary needs, allergens, time limits, protein minimums, and estimated total budget are treated as hard constraints. If no feasible plan exists, PantryPal explains which limits to adjust.

## Project structure

Online recipe likes and dislikes are stored in pantry_pal_online_feedback.json. If a misspelling is similarly close to multiple ingredient names, the search asks the user to choose rather than guessing.

Run the checks with: python -m unittest -v test_pantry_pal.py. The standard-library test suite covers planning, unit conversion, package estimates, mood filtering, API response parsing, substitutions, variants, typo matching, and saved online feedback.

- `pantry_pal.py` — built-in recipe catalog, agent policy, grocery calculations, and main interface.
- `online_recipes.py` — short live-search command-line flow and compatibility imports.
- `recipe_api.py` — TheMealDB requests, recipe parsing, typo matching, preference screening, and saved online feedback.
- `recipe_planner.py` — online meal selection, labels, recipe variants, substitutions, grocery output, and feedback prompts.
- `pantry_pal_ui.py` — dark desktop interface with a sliding home carousel, clickable recipe detail panels, quick-add search chips, pantry item builder, both planners, results, and feedback.
- `pantry_pal_web.py` — local browser interface for live recipe search and built-in meal planning.
- `assets/` — bundled food photos and a translucent banner overlay; image source links are listed in `assets/PHOTO_CREDITS.md`.
- `food_data.py` — JSON loading and shared ingredient, mood, and quantity helpers.
- `data/ingredient_aliases.json` — editable ingredient aliases and alternate spellings.
- `data/food_categories.json` — editable cuisines, mood aliases, labels, match rules, and search terms.
- `data/dietary_rules.json`, `data/substitutions.json`, and `data/grocery_data.json` — editable screening, swap, and grocery quantity data.
- `pantry_pal_memory.json` — created at runtime to store preferences and feedback.

Recipe nutrition and cost values are approximate example data. Add or edit recipes in `RECIPES`; ingredient amounts are per serving and pantry units should match the units shown by each recipe.