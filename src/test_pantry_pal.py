"""Standard-library regression tests for PantryPal's planning and recipe helpers."""

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import online_recipes as online
import recipe_api as api
import recipe_planner as planner
import pantry_pal as pantry


def online_meal(id_, name, ingredients, area="Japanese", category="Seafood"):
    return {
        "id": id_,
        "name": name,
        "area": area,
        "category": category,
        "ingredients": [
            {"name": ingredient, "canonical": online.canonical_ingredient(ingredient),
             "measure": "1 piece", "amount": 1.0, "unit": "piece"}
            for ingredient in ingredients
        ],
        "steps": ["Cook it."],
        "url": "https://example.test/recipe",
        "score": 0.0,
    }


class IngredientAndUnitTests(unittest.TestCase):
    def test_aliases_accents_and_plural_forms(self):
        self.assertEqual(online.canonical_ingredient("aubergine"), "eggplant")
        self.assertEqual(online.canonical_ingredient("courgettes"), "zucchini")
        self.assertEqual(online.canonical_ingredient("jalapeño"), "jalapeno")
        self.assertEqual(online.canonical_ingredient("garbanzo beans"), "chickpea")

    def test_allergy_and_diet_screening(self):
        chicken_cream = {"ingredients": [{"name": "chicken"}, {"name": "cream"}]}
        vegan_soup = {"ingredients": [{"name": "lentils"}, {"name": "tomatoes"}]}
        self.assertTrue(online.violates_preferences(chicken_cream, "vegan", set()))
        self.assertTrue(online.violates_preferences(chicken_cream, "none", {"dairy"}))
        self.assertFalse(online.violates_preferences(vegan_soup, "vegan", set()))

    def test_api_network_errors_are_wrapped(self):
        from urllib.error import URLError
        with patch.object(api, "urlopen", side_effect=URLError("offline")):
            with self.assertRaises(online.RecipeSearchError):
                online.api_get("search.php", {"s": "rice"})

    def test_typo_matching(self):
        with patch.object(api, "ingredient_vocabulary", return_value={"eggplant"}):
            self.assertEqual(online.closest_ingredient("eggplnt"), "eggplant")

    def test_ambiguous_typo_asks_user(self):
        with patch.object(api, "ingredient_vocabulary", return_value={"eggplant", "egg plant"}), \
                patch("builtins.input", return_value="2"):
            self.assertEqual(online.closest_ingredient("eggplnt"), "egg plant")

    def test_measure_conversion(self):
        amount, unit = online.parse_measure("1 1/2 cups")
        self.assertAlmostEqual(amount, 360)
        self.assertEqual(unit, "ml")
        amount, unit = online.standardize_quantity(16, "oz")
        self.assertAlmostEqual(amount, 453.592, places=2)
        self.assertEqual(unit, "g")

    def test_purchase_package_rounds_up(self):
        self.assertIn("buy 1 × 500 g package", online.purchase_line("pasta", 220, "g"))
        self.assertIn("buy 2 can(s)", online.purchase_line("chickpea", 1.2, "can"))


class PlanningTests(unittest.TestCase):
    def test_builtin_plan_respects_diet_and_budget(self):
        agent = pantry.PantryPalAgent()
        agent.profile = pantry.UserProfile(diet="vegan")
        request = pantry.Request(1, 2, 60, 100, 0, {})
        plan, candidates = agent.plan(request)
        self.assertEqual(len(plan), 1)
        self.assertTrue(all("vegan" in recipe.tags for recipe in candidates))

    def test_every_builtin_recipe_has_valid_ingredient_quantities(self):
        self.assertGreaterEqual(len(pantry.RECIPES), 10)
        for recipe in pantry.RECIPES:
            with self.subTest(recipe=recipe.id):
                self.assertTrue(recipe.ingredients)
                self.assertTrue(recipe.instructions)
                self.assertTrue(all(amount > 0 for amount, _unit in recipe.ingredients.values()))

    def test_catalog_filters_all_supported_diets(self):
        for diet in ("vegan", "vegetarian", "pescatarian", "dairy-free", "gluten-free"):
            with self.subTest(diet=diet):
                agent = pantry.PantryPalAgent()
                agent.profile = pantry.UserProfile(diet=diet)
                request = pantry.Request(1, 1, 180, 100, 0, {})
                _plan, candidates = agent.plan(request)
                self.assertTrue(candidates)
                self.assertTrue(all(diet in recipe.tags for recipe in candidates))

    def test_catalog_filters_allergen_constraints(self):
        agent = pantry.PantryPalAgent()
        agent.profile = pantry.UserProfile(allergies=frozenset({"dairy", "wheat"}))
        request = pantry.Request(1, 1, 180, 100, 0, {})
        _plan, candidates = agent.plan(request)
        self.assertTrue(candidates)
        self.assertTrue(all(not ({"dairy", "wheat"} & recipe.allergens) for recipe in candidates))

    def test_builtin_interactive_flow_completes(self):
        answers = [
            "2", "none", "", "", "1", "1", "50", "20", "0", "",
            "n", "skip", "3",
        ]
        output = StringIO()
        with tempfile.TemporaryDirectory() as directory:
            memory_path = Path(directory) / "memory.json"
            with patch.object(pantry, "MEMORY_FILE", memory_path), \
                    patch("builtins.input", side_effect=answers), \
                    redirect_stdout(output):
                pantry.main()
        self.assertIn("YOUR MEAL PLAN", output.getvalue())
        self.assertIn("COMBINED GROCERY LIST", output.getvalue())
        self.assertIn("RELATED RECIPE VARIANTS", output.getvalue())
        self.assertIn("Happy cooking!", output.getvalue())

    def test_shopping_uses_normalized_units_and_pantry(self):
        recipe = pantry.RECIPES[[r.id for r in pantry.RECIPES].index("tomato_pasta")]
        request = pantry.Request(1, 2, 60, 100, 0, {("pasta", "g"): 100})
        shopping = pantry.grocery_list([recipe], request)
        self.assertEqual(shopping[("pasta", "g")][1], "g")
        self.assertAlmostEqual(shopping[("pasta", "g")][0], 70.097, places=1)

    def test_leftovers_double_quantities(self):
        recipe = pantry.RECIPES[[r.id for r in pantry.RECIPES].index("tomato_pasta")]
        request = pantry.Request(1, 1, 60, 100, 0, {}, True)
        shopping = pantry.grocery_list([recipe], request)
        self.assertAlmostEqual(shopping[("pasta", "g")][0], 170.097, places=1)

    def test_online_combination_rewards_shared_ingredients(self):
        first = online_meal("1", "First", ["rice", "ginger"])
        second = online_meal("2", "Second", ["rice", "fish"])
        third = online_meal("3", "Third", ["beef", "carrot"], area="Mexican", category="Beef")
        first["score"] = second["score"] = third["score"] = 1
        plan = online.make_online_plan([first, second, third], 2, {}, False)
        self.assertEqual({meal["id"] for meal in plan}, {"1", "2"})

    def test_food_labels_and_related_variants(self):
        first = online_meal("1", "Chili fish", ["chili", "fish"])
        second = online_meal("2", "Hot fish stew", ["chili", "fish", "tomato"])
        labels = online.food_labels(first["name"], ["chili", "fish"], "Seafood", "Japanese")
        self.assertIn("Japanese", labels)
        self.assertIn("Seafood", labels)
        self.assertIn("Spicy", labels)
        self.assertEqual(online.related_variants(first, [first, second])[0]["id"], "2")

    def test_substitutions_respect_diet_and_allergies(self):
        shopping = [(("chicken", "g"), 200)]
        pantry = {("tofu", "g"): 300}
        self.assertEqual(online.suggest_substitutions(shopping, pantry, "vegan", set()),
                         [("chicken", "tofu")])
        self.assertEqual(online.suggest_substitutions(shopping, pantry, "vegan", {"soy"}), [])

    def test_online_feedback_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feedback.json"
            with patch.object(api, "ONLINE_FEEDBACK_FILE", path):
                online.save_online_feedback({"liked-id"}, {"avoided-id"})
                liked, avoided = online.load_online_feedback()
            self.assertEqual(liked, {"liked-id"})
            self.assertEqual(avoided, {"avoided-id"})

    def test_saved_online_feedback_changes_ranking(self):
        disliked = online_meal("disliked", "Disliked", ["rice"])
        liked = online_meal("liked", "Liked", ["rice"])
        disliked["score"] = liked["score"] = 1.0
        with patch.object(api, "search_meals", return_value=[disliked, liked]), \
                patch.object(api, "load_online_feedback", return_value=({"liked"}, {"disliked"})):
            results = online.search_many(["rice"], {}, "none", set())
        self.assertEqual(results[0]["id"], "liked")
        self.assertEqual(results[1]["id"], "disliked")

    def test_online_search_displays_network_error_without_crashing(self):
        answers = ["Japanese", "", "", "none", ""]
        output = StringIO()
        with patch("builtins.input", side_effect=answers), \
                patch.object(online, "search_many", side_effect=online.RecipeSearchError("offline")), \
                redirect_stdout(output):
            online.online_search_flow()
        self.assertIn("offline", output.getvalue())
        self.assertIn("built-in planner is still available", output.getvalue())

    def test_online_search_corrects_typo_and_uses_api_details(self):
        raw = {
            "idMeal": "42", "strMeal": "Eggplant curry", "strCategory": "Vegan",
            "strArea": "Indian", "strInstructions": "Cook the eggplant.",
            "strIngredient1": "Eggplant", "strMeasure1": "1 piece",
        }
        def fake_api(endpoint, params):
            if endpoint == "search.php":
                self.assertEqual(params["s"], "eggplnt")
                return {"meals": None}
            if endpoint == "filter.php":
                self.assertEqual(params["i"], "eggplant")
                return {"meals": [{"idMeal": "42"}]}
            if endpoint == "lookup.php":
                return {"meals": [raw]}
            raise AssertionError(f"Unexpected endpoint: {endpoint}")
        with patch.object(api, "api_get", side_effect=fake_api), \
                patch.object(api, "ingredient_vocabulary", return_value={"eggplant"}):
            results = online.search_meals("eggplnt", {}, "none", set())
        self.assertEqual([meal["id"] for meal in results], ["42"])

    def test_online_search_skips_single_timed_out_detail(self):
        raw = {
            "idMeal": "43", "strMeal": "Eggplant soup", "strCategory": "Vegan",
            "strArea": "Italian", "strInstructions": "Cook it.",
            "strIngredient1": "Eggplant", "strMeasure1": "1 piece",
        }
        def fake_api(endpoint, params):
            if endpoint == "search.php":
                return {"meals": [{"idMeal": "bad"}, {"idMeal": "good"}]}
            if endpoint == "lookup.php" and params["i"] == "bad":
                raise online.RecipeSearchError("simulated timeout")
            if endpoint == "lookup.php" and params["i"] == "good":
                return {"meals": [raw]}
            raise AssertionError(f"Unexpected endpoint: {endpoint}")
        with patch.object(api, "api_get", side_effect=fake_api):
            results = online.search_meals("eggplant", {}, "none", set())
        self.assertEqual([meal["id"] for meal in results], ["43"])

    def test_online_interactive_flow_end_to_end_with_mock_api(self):
        raw = {
            "idMeal": "99", "strMeal": "Japanese rice bowl", "strCategory": "Seafood",
            "strArea": "Japanese", "strInstructions": "Cook rice.\nAdd salmon.",
            "strIngredient1": "Rice", "strMeasure1": "1 cup",
            "strIngredient2": "Salmon", "strMeasure2": "200 g",
        }
        def fake_api(endpoint, params):
            if endpoint == "list.php":
                return {"meals": [{"strIngredient": "Rice"}, {"strIngredient": "Salmon"}]}
            if endpoint == "filter.php":
                self.assertEqual(params, {"a": "Japanese"})
                return {"meals": [{"idMeal": "99"}]}
            if endpoint == "lookup.php":
                return {"meals": [raw]}
            raise AssertionError(f"Unexpected endpoint: {endpoint}")
        answers = ["Japanese", "", "rice=2 cups", "none", "", "1", "n", "skip"]
        output = StringIO()
        with tempfile.TemporaryDirectory() as directory:
            feedback_path = Path(directory) / "online-feedback.json"
            with patch.object(api, "api_get", side_effect=fake_api), \
                    patch.object(api, "ONLINE_FEEDBACK_FILE", feedback_path), \
                    patch("builtins.input", side_effect=answers), \
                    redirect_stdout(output):
                online.online_search_flow()
        result = output.getvalue()
        self.assertIn("Food mood filters: Japanese", result)
        self.assertIn("Japanese rice bowl", result)
        self.assertIn("COMBINED GROCERY LIST", result)
        self.assertIn("salmon", result.lower())
        self.assertFalse(feedback_path.exists())

    def test_online_feedback_records_each_recipe(self):
        first = online_meal("liked-id", "Liked", ["rice"])
        second = online_meal("avoided-id", "Avoided", ["rice"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feedback.json"
            with patch.object(api, "ONLINE_FEEDBACK_FILE", path), \
                    patch("builtins.input", side_effect=["y", "n"]):
                online.record_online_feedback([first, second])
                liked, avoided = online.load_online_feedback()
        self.assertEqual(liked, {"liked-id"})
        self.assertEqual(avoided, {"avoided-id"})

    def test_japanese_mood_uses_area_filter(self):
        raw = {
            "idMeal": "99", "strMeal": "Miso salmon", "strCategory": "Seafood",
            "strArea": "Japanese", "strInstructions": "Cook the fish.",
            "strIngredient1": "salmon", "strMeasure1": "200 g",
        }
        def fake_api(endpoint, params):
            if endpoint == "filter.php":
                self.assertEqual(params, {"a": "Japanese"})
                return {"meals": [{"idMeal": "99"}]}
            if endpoint == "lookup.php":
                return {"meals": [raw]}
            raise AssertionError(f"Unexpected endpoint: {endpoint}")
        with patch.object(api, "api_get", side_effect=fake_api), \
                patch.object(api, "load_online_feedback", return_value=(set(), set())):
            results = online.search_many([], {}, "none", set(), ["Japanese"])
        self.assertEqual([meal["id"] for meal in results], ["99"])


if __name__ == "__main__":
    unittest.main()
