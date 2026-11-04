"""Free local browser interface for PantryPal (Python standard library only)."""

from __future__ import annotations

from html import escape
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import random
import threading
import time
from urllib.parse import parse_qs
import webbrowser

import pantry_pal as core
from food_data import ALIASES, canonical_ingredient, parse_measure, standardize_quantity
from online_recipes import food_labels, make_online_plan, search_many
from recipe_api import RecipeSearchError, api_get, estimate_nutrition, parse_meal


HOST = "127.0.0.1"
PORT = 8765
_QUICK_CACHE = []
_QUICK_CACHE_AT = 0.0
_QUICK_CACHE_LOCK = threading.Lock()


def parse_inventory(raw: str):
    inventory = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise ValueError(f"Use item=quantity format (for example: rice=2 cups). Problem: {entry}")
        name, quantity = entry.split("=", 1)
        name = canonical_ingredient(name)
        amount, unit = parse_measure(quantity)
        amount, unit = standardize_quantity(amount, unit)
        key = (name, unit)
        inventory[key] = inventory.get(key, 0.0) + amount
    return inventory


def esc(value):
    return escape(str(value), quote=True)


def shopping_rows(items):
    rows = []
    for name, amount, unit in items:
        key = f"{name}|{unit}"
        quantity = esc(f"{amount:g} {unit}")
        rows.append(
            f'<li class="shopping-row" data-key="{esc(key)}" data-name="{esc(name)}">'
            f'<label><input class="shop-check" type="checkbox"><span class="shopping-name">{esc(name)}</span></label>'
            f'<input class="shop-quantity" type="text" value="{quantity}" aria-label="Quantity for {esc(name)}"></li>')
    return "".join(rows)


def online_ingredient_text(item):
    measure = item.get("measure") or f"{item.get('amount', 0):g} {item.get('unit', '')}".strip()
    return f"{measure} {item['name']}".strip()


def load_quick_meals():
    """Return a short, cached set of full meals from TheMealDB."""
    global _QUICK_CACHE, _QUICK_CACHE_AT
    now = time.monotonic()
    with _QUICK_CACHE_LOCK:
        if _QUICK_CACHE_AT and now - _QUICK_CACHE_AT < (1800 if _QUICK_CACHE else 120):
            return list(_QUICK_CACHE)
        # Search several first-letter groups in parallel, then shuffle and
        # deduplicate a larger carousel pool from TheMealDB.
        def search_letter(letter):
            try:
                return api_get("search.php", {"f": letter}).get("meals") or []
            except RecipeSearchError:
                return []

        letters = random.sample("abcfhklmnoprstw", 4)
        with ThreadPoolExecutor(max_workers=4) as executor:
            raw_groups = list(executor.map(search_letter, letters))
        by_id = {}
        for raw_meals in raw_groups:
            for raw in raw_meals:
                meal_id = raw.get("idMeal")
                if meal_id and raw.get("strMealThumb"):
                    try:
                        by_id[meal_id] = parse_meal(raw)
                    except (KeyError, TypeError, ValueError):
                        continue
        meals = list(by_id.values())
        random.shuffle(meals)
        _QUICK_CACHE = meals[:10]
        _QUICK_CACHE_AT = now
        return list(_QUICK_CACHE)


def page(result="", values=None, discovery_result="", quick_picks=""):
    values = values or {}

    def field(name, label, placeholder="", wide=False):
        value = esc(values.get(name, ""))
        return (f'<label class="field {"wide" if wide else ""}"><span>{label}</span>'
                f'<input name="{name}" value="{value}" placeholder="{esc(placeholder)}"></label>')

    def token_field(name, label, placeholder, wide=False):
        raw_tokens = [token.strip() for token in values.get(name, "").split(",") if token.strip()]
        chips = "".join(f'<span class="input-chip">{esc(token)}<button type="button" aria-label="Remove {esc(token)}">×</button></span>'
                        for token in raw_tokens)
        return (f'<div class="field {"wide" if wide else ""}"><span>{label}</span>'
                f'<div class="token-box" data-token-field="{esc(name)}"><div class="token-chips">{chips}</div>'
                f'<input class="token-entry" list="ingredient-options" placeholder="{esc(placeholder)}" autocomplete="off">'
                f'<input type="hidden" name="{esc(name)}" value="{esc(values.get(name, ""))}"></div></div>')

    diet = esc(values.get("diet", "none"))
    diet_options = "".join(
        f'<option value="{choice}"{" selected" if diet == choice else ""}>{choice.title()}</option>'
        for choice in ("none", "vegan", "vegetarian", "pescatarian", "dairy-free", "gluten-free")
    )
    checked = " checked" if values.get("leftovers") == "yes" else ""
    ingredient_options = sorted(set(ALIASES) | set(ALIASES.values()) |
                                {name for recipe in core.RECIPES for name in recipe.ingredients})
    ingredient_datalist = "".join(f'<option value="{esc(name)}">' for name in ingredient_options)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PantryPal · Meal planner</title><style>
:root{{--bg:#0c100e;--panel:#151b17;--panel2:#1b241e;--text:#eef4ef;--muted:#9aa69d;--green:#b5e7c8;--line:#29352d}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(ellipse at 78% 5%,#254532 0,transparent 38%),var(--bg);color:var(--text);font:15px/1.55 Segoe UI,Arial,sans-serif}}
main{{width:min(1100px,94vw);margin:34px auto 70px}}header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}}.brand{{font-size:22px;font-weight:750;letter-spacing:.3px}}.brand b{{color:var(--green)}}.badge{{color:var(--green);border:1px solid #42634d;border-radius:99px;padding:6px 12px;font-size:12px}}
h1{{font-size:clamp(30px,5vw,48px);line-height:1.1;margin:12px 0}}.lead{{color:var(--muted);margin:0 0 25px}}.card{{background:linear-gradient(145deg,#19211cfa,#111713f5);border:1px solid var(--line);border-radius:22px;padding:24px;box-shadow:0 18px 60px #0005;margin:18px 0}}
.tabs{{display:flex;gap:10px;margin-bottom:18px}}.tab{{background:var(--panel2);color:var(--muted);border:1px solid var(--line);padding:9px 16px;border-radius:99px;cursor:pointer}}.tab.active{{background:#274233;color:var(--green);border-color:#45664f}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.field{{display:flex;flex-direction:column;gap:6px;color:#d7e1d9;font-size:13px}}.field input,.field select{{width:100%;height:44px;background:#101612;border:1px solid #334138;border-radius:12px;padding:0 13px;color:var(--text);font:inherit;outline:none}}.field input:focus,.field select:focus{{border-color:#82c99a;box-shadow:0 0 0 3px #82c99a20}}.wide{{grid-column:1/-1}}.hint{{font-size:12px;color:var(--muted);margin:8px 0 0}}.options{{display:flex;gap:18px;align-items:center;margin:14px 0;color:#d7e1d9}}.options label{{display:flex;align-items:center;gap:7px}}button,.button{{border:0;border-radius:12px;padding:12px 18px;background:var(--green);color:#102017;font-size:14px;font-weight:700;cursor:pointer;text-decoration:none}}button:hover,.button:hover{{background:#d0f2dc}}.submit{{margin-top:18px}}.subtle{{background:#25332a;color:var(--green);border:1px solid #38503f}}.result h2{{color:var(--green);font-size:15px;letter-spacing:1px}}.meal{{padding:17px 0;border-top:1px solid var(--line)}}.meal:first-of-type{{border:0}}.meal h3{{margin:0 0 5px;font-size:21px}}.meta,.source{{color:var(--muted);font-size:13px}}.tags{{color:var(--green);font-size:12px}}ul,ol{{padding-left:22px}}li{{padding:2px 0}}.shopping{{background:#101612;border-radius:14px;padding:14px 18px}}.error{{border-color:#743e3e;color:#ffc2b7}}[hidden]{{display:none!important}}footer{{color:#78857c;font-size:12px;margin:20px 4px}}@media(max-width:700px){{main{{margin-top:20px}}.card{{padding:18px}}.grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}header{{align-items:flex-start;gap:10px}}.badge{{font-size:11px}}}}
</style><style>
.discover-form{{display:grid;grid-template-columns:1fr 1fr auto auto;gap:11px;align-items:end}}.discover-form label{{display:flex;flex-direction:column;gap:6px;color:#d7e1d9;font-size:13px}}.discover-form input{{height:44px;background:#101612;border:1px solid #334138;border-radius:12px;padding:0 13px;color:var(--text);font:inherit}}.discover-results{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}}.discover-result-card{{padding:0;text-align:left;overflow:hidden;background:linear-gradient(145deg,#1a241e,#111713);border:1px solid var(--line);border-radius:17px;color:var(--text)}}.discover-result-card img{{width:100%;height:160px;display:block;object-fit:cover}}.discover-result-card strong,.discover-result-card small{{display:block;padding:0 13px}}.discover-result-card strong{{padding-top:10px}}.discover-result-card small{{padding-bottom:12px;color:var(--muted)}}.quick-carousel{{display:grid;grid-template-columns:42px minmax(0,1fr) 42px;gap:9px;align-items:center}}.carousel-viewport{{overflow:hidden;border-radius:18px;border:1px solid #344238}}.carousel-track{{display:flex;transition:transform .62s cubic-bezier(.22,.72,.18,1);will-change:transform}}.quick-slide{{flex:0 0 100%;display:grid;grid-template-columns:42% 1fr;min-height:270px;border:0;border-radius:0;text-align:left;cursor:pointer}}.quick-slide img{{width:100%;height:100%;min-height:270px;object-fit:cover;padding:0}}.quick-slide-copy{{display:flex;flex-direction:column;justify-content:center;gap:11px;padding:26px;background:linear-gradient(145deg,#1b241e,#101612);text-align:left}}.quick-slide-copy small{{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--green)}}.quick-slide-copy strong{{font-size:clamp(20px,3vw,32px);line-height:1.15;padding:0}}.quick-slide-copy>span{{color:var(--muted);font-size:13px}}.carousel-arrow{{width:42px;height:42px;padding:0;border-radius:50%;display:grid;place-items:center;background:#1b241e;color:var(--green);border:1px solid #344238;font-size:29px;line-height:1}}.carousel-dots{{display:flex;justify-content:center;gap:7px;margin-top:11px}}.carousel-dot{{width:8px;height:8px;padding:0;border-radius:99px;background:#536057;transition:width .2s,background .2s}}.carousel-dot.active{{width:24px;background:var(--green)}}.nutrition-estimate{{margin:9px 0;padding:10px 12px;border-radius:10px;background:#202b23;color:#c9ecd4;font-size:13px}}.nutrition-estimate small{{display:block;margin-top:3px;color:var(--muted)}}@media(max-width:700px){{.discover-form{{grid-template-columns:1fr}}.discover-results{{grid-template-columns:1fr}}.quick-carousel{{grid-template-columns:32px minmax(0,1fr) 32px;gap:5px}}.carousel-arrow{{width:32px;height:32px;font-size:24px}}.quick-slide{{grid-template-columns:1fr;grid-template-rows:190px auto;min-height:380px}}.quick-slide img{{height:190px;min-height:190px}}.quick-slide-copy{{padding:18px}}}}
.popular{{margin:24px 0 25px}}.popular-heading{{display:flex;align-items:baseline;gap:12px;margin:0 2px 12px}}.popular-heading h2{{font-size:20px;margin:0}}.popular-heading span{{font-size:12px;color:var(--muted)}}
.recipe-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}}.recipe-card{{padding:0;overflow:hidden;text-align:left;background:linear-gradient(145deg,#1a241e,#111713);color:var(--text);border:1px solid var(--line);border-radius:17px;box-shadow:0 8px 25px #0003;transition:transform .2s,border-color .2s}}.recipe-card:hover{{transform:translateY(-3px);border-color:#55745d;background:linear-gradient(145deg,#202d25,#151c18)}}.recipe-card img{{display:block;width:100%;height:160px;object-fit:cover}}.recipe-card-copy{{display:flex;flex-direction:column;gap:4px;padding:12px 14px 14px}}.recipe-card-copy strong{{font-size:15px}}.recipe-card-copy small{{font-size:12px;color:var(--muted)}}
.catalog-tools{{display:flex;gap:9px;margin:13px 0;flex-wrap:wrap}}.catalog-tools input,.catalog-tools select{{min-height:40px;background:#101612;color:var(--text);border:1px solid #334138;border-radius:11px;padding:0 11px}}.catalog-tools input{{flex:1;min-width:210px}}.recipe-placeholder{{display:grid;place-items:center;height:160px;background:radial-gradient(circle at 50% 30%,#35513d,#162019 72%);font-size:50px}}.save-recipe{{background:#26362c;color:var(--green);border:1px solid #3e5845;padding:7px 12px;font-size:12px;margin:5px 0 12px}}.saved-section{{margin:24px 0}}.saved-section h2{{font-size:20px;margin-bottom:4px}}.saved-list{{display:flex;flex-wrap:wrap;gap:8px}}.saved-item{{display:flex;align-items:center;gap:5px;background:#172019;border:1px solid var(--line);border-radius:12px;padding:5px}}.saved-item button{{background:transparent;color:var(--text);padding:6px 9px;font-size:13px}}.saved-item .remove-saved{{color:#efa9a0}}.saved-detail{{margin-top:10px;padding:18px;border:1px solid #3b5542;border-radius:15px;background:#141b16}}.result-actions{{display:flex;justify-content:flex-end;margin-bottom:8px}}.shopping-row{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid #243027}}.shopping-row label{{display:flex;align-items:center;gap:9px}}.shopping-row input[type=checkbox]{{accent-color:#8bc69a;width:17px;height:17px}}.shopping-row input[type=text]{{width:145px;background:#171f1a;border:1px solid #344238;color:var(--text);border-radius:8px;padding:7px}}.shopping-row:has(input:checked) .shopping-name{{text-decoration:line-through;color:var(--muted)}}.export-button{{padding:8px 12px;background:#26362c;color:var(--green);border:1px solid #3e5845}}.recipe-detail{{position:relative;margin-top:14px;padding:20px 22px;background:linear-gradient(135deg,#1a241e,#111713);border:1px solid #3b5542;border-radius:18px;box-shadow:0 16px 45px #0004;animation:appear .22s ease-out}}.recipe-detail h3{{margin:5px 0;font-size:24px}}.eyebrow{{color:var(--green);text-transform:uppercase;font-size:11px;letter-spacing:1px;font-weight:700}}.detail-columns{{display:grid;grid-template-columns:1fr 1.35fr;gap:20px}}.detail-columns h4{{margin-bottom:5px}}.close-detail{{float:right;background:#29372e;color:var(--text);padding:4px 11px;font-size:20px;line-height:1.3}}@keyframes appear{{from{{opacity:0;transform:translateY(5px)}}to{{opacity:1;transform:translateY(0)}}}}@media(max-width:700px){{.recipe-grid{{grid-template-columns:1fr}}.recipe-card img,.recipe-placeholder{{height:190px}}.detail-columns{{grid-template-columns:1fr;gap:5px}}.shopping-row{{align-items:flex-start;flex-direction:column}}}}
.token-box{{display:flex;min-height:46px;align-items:center;gap:6px;flex-wrap:wrap;background:#101612;border:1px solid #334138;border-radius:13px;padding:6px 9px}}.token-box:focus-within,.pantry-builder:focus-within{{border-color:#82c99a;box-shadow:0 0 0 3px #82c99a20}}.token-entry{{flex:1;min-width:200px;height:32px!important;padding:0 5px!important;border:0!important;box-shadow:none!important;background:transparent!important}}.token-chips,.pantry-chips{{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}}.token-chips:empty{{display:none}}.input-chip,.pantry-chip{{display:inline-flex;align-items:center;gap:5px;background:#22372a;color:#c9ecd4;border:1px solid #385443;border-radius:99px;padding:4px 9px;font-size:12px}}.input-chip button,.pantry-chip button{{padding:0 2px;background:transparent;color:#b5e7c8;font-size:15px;line-height:1}}.pantry-builder{{display:grid;grid-template-columns:minmax(140px,1fr) 90px 105px auto;gap:7px;padding:7px;background:#101612;border:1px solid #334138;border-radius:13px}}.pantry-builder input,.pantry-builder select,.paste-pantry input{{min-width:0;height:39px;background:#171f1a;color:var(--text);border:1px solid #344238;border-radius:9px;padding:0 10px}}.pantry-builder button,.paste-pantry button{{padding:8px 12px;white-space:nowrap}}.paste-pantry{{margin-top:8px;color:var(--muted);font-size:12px}}.paste-pantry summary{{cursor:pointer}}.paste-pantry>div{{display:flex;gap:7px;margin-top:6px}}.paste-pantry input{{flex:1}}@media(max-width:650px){{.pantry-builder{{grid-template-columns:1fr 85px}}.pantry-builder button{{grid-column:1/-1}}}}
</style><style>
.carousel-track{{gap:12px}}.quick-card{{flex:0 0 calc((100% - 24px)/3);display:flex;flex-direction:column;border-radius:15px;min-width:0}}.quick-card img{{width:100%;height:180px;min-height:0;object-fit:cover;padding:0}}.quick-card-copy{{display:flex;flex-direction:column;align-items:flex-start;gap:8px;padding:13px}}.quick-card-copy strong{{padding:0;font-size:15px;line-height:1.25}}.recipe-labels{{display:flex;flex-wrap:wrap;gap:5px}}.recipe-label{{display:inline-flex;padding:3px 7px;border-radius:99px;background:#22372a;border:1px solid #385443;color:#c9ecd4;font-size:10px;line-height:1.25}}@media(max-width:700px){{.quick-carousel{{grid-template-columns:25px minmax(0,1fr) 25px;gap:4px}}.carousel-arrow{{width:25px;height:32px;font-size:22px}}.carousel-track{{gap:7px}}.quick-card{{flex-basis:calc((100% - 14px)/3)}}.quick-card img{{height:100px}}.quick-card-copy{{padding:8px 6px}}.quick-card-copy strong{{font-size:12px}}.recipe-label{{font-size:8px;padding:2px 5px}}}}
</style></head><body><main>
<header><div class="brand">🥬 Pantry<b>Pal</b></div><div class="badge">FREE · RUNS ON YOUR COMPUTER</div></header>
<h1>Make something good<br>with what you have.</h1><p class="lead">Plan meals, use your pantry, and get a combined shopping list.</p>
<section class="card discover-card"><div class="popular-heading"><h2>Explore TheMealDB</h2><span>Search live recipes across the database</span></div>
<form class="discover-form" method="post" action="/discover"><label><span>Recipe name or ingredient</span><input name="discover_query" value="{esc(values.get("discover_query", ""))}" placeholder="Try eggplant, salmon, or curry"></label><label><span>Cuisine or food mood (optional)</span><input name="discover_mood" value="{esc(values.get("discover_mood", ""))}" placeholder="Japanese, spicy, Italian"></label><button type="submit">Find recipes <span aria-hidden="true">→</span></button><button type="submit" name="surprise" value="1" class="subtle">Surprise me ✨</button></form><p class="hint">Results, photos, and details come from TheMealDB. Quick picks below are also loaded from TheMealDB.</p></section>
{discovery_result}{quick_picks}
<section class="saved-section"><h2>Saved recipes</h2><p class="meta" id="saved-empty">Your saved recipes stay in this browser.</p><div class="saved-list" id="saved-list"></div><article class="saved-detail" id="saved-detail" hidden></article></section>
<section class="card"><div class="tabs"><button type="button" class="tab active" data-mode="online">Live recipes</button><button type="button" class="tab" data-mode="built-in">Built-in planner</button></div>
<form method="post" action="/plan"><input type="hidden" name="mode" id="mode" value="online">
<datalist id="ingredient-options">{ingredient_datalist}</datalist>
<div id="online-fields" class="grid">
{token_field("queries", "Dish names or ingredients", "Type an ingredient and press Enter", True)}
{field("moods", "Food mood or cuisine", "spicy, Japanese, comfort")}
</div>
<div id="local-fields" class="grid" hidden>
{field("servings", "Servings per meal", "2")}{field("minutes", "Maximum cooking time (minutes)", "40")}
{field("budget", "Estimated grocery budget ($)", "30")}{field("protein", "Minimum protein (g per serving)", "0")}
</div>
<div class="grid" style="margin-top:14px">{field("allergies", "Allergies to exclude", "peanuts, shellfish")}
<label class="field"><span>Diet</span><select name="diet">{diet_options}</select></label>
<div class="field wide"><span>What’s already in your pantry?</span>
<div class="pantry-builder"><input id="pantry-name" list="ingredient-options" placeholder="Search ingredients…" autocomplete="off"><input id="pantry-amount" type="number" min="0.01" step="any" value="1" aria-label="Pantry quantity"><select id="pantry-unit" aria-label="Pantry unit"><option>piece</option><option>cup</option><option>tbsp</option><option>tsp</option><option>g</option><option>kg</option><option>oz</option><option>lb</option><option>can</option><option>clove</option><option>ml</option><option>l</option></select><button id="add-pantry" type="button">＋ Add</button></div>
<div class="pantry-chips" id="pantry-chips"></div><input type="hidden" name="pantry" id="pantry-value" value="{esc(values.get("pantry", ""))}">
<details class="paste-pantry"><summary>Paste or edit a pantry list</summary><div><input id="paste-pantry" placeholder="rice=2 cups, eggs=4"><button type="button" id="import-pantry">Use this list</button></div></details>
</div>
{field("dislikes", "Ingredients to avoid", "mushrooms, cilantro")}
<label class="field"><span>Number of meals</span><input name="count" type="number" min="1" max="7" value="{esc(values.get("count", "3"))}"></label>
</div><div class="options"><label><input type="checkbox" name="leftovers" value="yes"{checked}> Double recipes for leftovers</label></div>
<p class="hint">Press Enter after each search ingredient to add it. Add pantry items with a quantity and unit, or paste a list in item=amount format.</p>
<button class="submit" type="submit">Build my meal plan <span aria-hidden="true">→</span></button></form></section>
{result}
<footer>Live recipe search needs an internet connection. The built-in planner works offline. Your browser connects only to this computer.</footer>
</main><script>
const tabs=document.querySelectorAll('.tab'),mode=document.querySelector('#mode'),online=document.querySelector('#online-fields'),local=document.querySelector('#local-fields');
function setMode(value){{mode.value=value;online.hidden=value!=='online';local.hidden=value!=='built-in';tabs.forEach(t=>t.classList.toggle('active',t.dataset.mode===value))}}
tabs.forEach(t=>t.addEventListener('click',()=>setMode(t.dataset.mode)));setMode('{esc(values.get("mode", "online"))}');
document.querySelectorAll('.token-box').forEach(box=>{{const hidden=box.querySelector('input[type=hidden]'),entry=box.querySelector('.token-entry'),chips=box.querySelector('.token-chips');let tokens=hidden.value.split(',').map(value=>value.trim()).filter(Boolean);function sync(){{hidden.value=tokens.join(', ');chips.replaceChildren();tokens.forEach((token,index)=>{{const chip=document.createElement('span');chip.className='input-chip';chip.append(document.createTextNode(token));const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label','Remove '+token);remove.addEventListener('click',()=>{{tokens.splice(index,1);sync()}});chip.append(remove);chips.append(chip)}})}}function add(value){{value.split(',').map(token=>token.trim()).filter(Boolean).forEach(token=>{{if(!tokens.some(old=>old.toLowerCase()===token.toLowerCase()))tokens.push(token)}});entry.value='';sync()}}entry.addEventListener('keydown',event=>{{if(event.key==='Enter'||event.key===','){{event.preventDefault();add(entry.value)}}}});entry.addEventListener('change',()=>{{if(entry.value.trim())add(entry.value)}});sync()}});
const pantryValue=document.querySelector('#pantry-value'),pantryChips=document.querySelector('#pantry-chips');
function drawPantry(){{pantryChips.replaceChildren();const entries=pantryValue.value.split(',').map(value=>value.trim()).filter(Boolean);entries.forEach((entry,index)=>{{const chip=document.createElement('span');chip.className='pantry-chip';chip.append(document.createTextNode(entry));const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label','Remove '+entry);remove.addEventListener('click',()=>{{const current=pantryValue.value.split(',').map(value=>value.trim()).filter(Boolean);current.splice(index,1);pantryValue.value=current.join(', ');drawPantry()}});chip.append(remove);pantryChips.append(chip)}})}}
function addPantryItem(){{const name=document.querySelector('#pantry-name').value.trim(),amount=Number(document.querySelector('#pantry-amount').value),unit=document.querySelector('#pantry-unit').value;if(!name){{document.querySelector('#pantry-name').focus();return}}if(!Number.isFinite(amount)||amount<=0){{document.querySelector('#pantry-amount').focus();return}}const current=pantryValue.value.split(',').map(value=>value.trim()).filter(Boolean);current.push(name+'='+amount+' '+unit);pantryValue.value=current.join(', ');document.querySelector('#pantry-name').value='';document.querySelector('#pantry-amount').value='1';drawPantry();document.querySelector('#pantry-name').focus()}}
document.querySelector('#add-pantry').addEventListener('click',addPantryItem);document.querySelector('#pantry-name').addEventListener('keydown',event=>{{if(event.key==='Enter'){{event.preventDefault();addPantryItem()}}}});document.querySelector('#pantry-amount').addEventListener('keydown',event=>{{if(event.key==='Enter'){{event.preventDefault();addPantryItem()}}}});
document.querySelector('#import-pantry').addEventListener('click',()=>{{const pasted=document.querySelector('#paste-pantry').value.trim();if(pasted){{pantryValue.value=pasted;drawPantry();document.querySelector('#paste-pantry').value=''}}}});drawPantry();
document.addEventListener('click',event=>{{const card=event.target.closest('.discover-result-card');if(!card)return;document.querySelectorAll('.recipe-detail').forEach(detail=>detail.hidden=true);const detail=document.getElementById(card.dataset.detailTarget||('discover-detail-'+card.dataset.discoverId));if(detail){{detail.hidden=false;detail.scrollIntoView({{behavior:'smooth',block:'nearest'}})}}}});
document.querySelectorAll('.close-detail').forEach(button=>button.addEventListener('click',()=>button.closest('.recipe-detail').hidden=true));
const carousel=document.querySelector('.quick-carousel'),track=document.querySelector('.carousel-track');
if(carousel&&track){{const realCount=track.children.length,dots=[...document.querySelectorAll('.carousel-dot')],reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;let index=0,timer=null;for(let i=0;i<Math.min(3,realCount);i++)track.append(track.children[i].cloneNode(true));function stepSize(){{const card=track.querySelector('.quick-card'),gap=parseFloat(getComputedStyle(track).columnGap)||0;return card?card.getBoundingClientRect().width+gap:0}}function position(){{track.style.transform='translateX(-'+(index*stepSize())+'px)'}}function showDot(){{dots.forEach((dot,i)=>dot.classList.toggle('active',i===index%realCount))}}function moveTo(next){{index=next;track.style.transition='';position();showDot();if(index===realCount)window.setTimeout(()=>{{track.style.transition='none';index=0;position();showDot();requestAnimationFrame(()=>track.style.transition='')}} ,640)}}function nextSlide(){{moveTo(index+1)}}function previousSlide(){{if(index===0){{index=realCount;track.style.transition='none';position();requestAnimationFrame(()=>moveTo(realCount-1))}}else moveTo(index-1)}}carousel.querySelector('.next').addEventListener('click',nextSlide);carousel.querySelector('.previous').addEventListener('click',previousSlide);dots.forEach((dot,i)=>dot.addEventListener('click',()=>moveTo(i)));window.addEventListener('resize',position);function pause(){{if(timer)window.clearInterval(timer);timer=null}}function resume(){{if(!reducedMotion&&!timer)timer=window.setInterval(nextSlide,6500)}}carousel.addEventListener('mouseenter',pause);carousel.addEventListener('mouseleave',resume);carousel.addEventListener('focusin',pause);carousel.addEventListener('focusout',event=>{{if(!carousel.contains(event.relatedTarget))resume()}});resume()}}
const savedKey='pantrypal:saved-recipes';
function readSaved(){{try{{return JSON.parse(localStorage.getItem(savedKey)||'[]')}}catch(_error){{return []}}}}
function writeSaved(items){{localStorage.setItem(savedKey,JSON.stringify(items));renderSaved()}}
function renderSaved(){{const list=document.querySelector('#saved-list'),empty=document.querySelector('#saved-empty');list.replaceChildren();const items=readSaved();empty.hidden=items.length>0;items.forEach(item=>{{const row=document.createElement('div');row.className='saved-item';const open=document.createElement('button');open.type='button';open.textContent=item.name;open.addEventListener('click',()=>showSaved(item));const remove=document.createElement('button');remove.type='button';remove.className='remove-saved';remove.textContent='×';remove.title='Remove saved recipe';remove.addEventListener('click',()=>writeSaved(readSaved().filter(saved=>saved.id!==item.id)));row.append(open,remove);list.append(row)}})}}
function showSaved(item){{const panel=document.querySelector('#saved-detail');panel.replaceChildren();const title=document.createElement('h3');title.textContent=item.name;const meta=document.createElement('p');meta.className='meta';meta.textContent=item.meta||'';panel.append(title,meta);for(const [heading,values,tag] of [['Ingredients',item.ingredients,'ul'],['Instructions',item.instructions,'ol']]){{const h=document.createElement('h4');h.textContent=heading;const list=document.createElement(tag);(values||[]).forEach(value=>{{const li=document.createElement('li');li.textContent=value;list.append(li)}});panel.append(h,list)}}panel.hidden=false;panel.scrollIntoView({{behavior:'smooth',block:'nearest'}})}}
document.querySelectorAll('.save-recipe').forEach(button=>button.addEventListener('click',()=>{{try{{const item=JSON.parse(button.dataset.recipeJson);const items=readSaved().filter(saved=>saved.id!==item.id);items.unshift(item);writeSaved(items);button.textContent='Saved ✓'}}catch(_error){{button.textContent='Could not save'}}}}));
renderSaved();
let shoppingState={{}};try{{shoppingState=JSON.parse(localStorage.getItem('pantrypal:shopping')||'{{}}')}}catch(_error){{}}
document.querySelectorAll('.shopping-row').forEach(row=>{{const saved=shoppingState[row.dataset.key]||{{}};const check=row.querySelector('.shop-check'),quantity=row.querySelector('.shop-quantity');check.checked=!!saved.checked;if(saved.quantity)quantity.value=saved.quantity;const persist=()=>{{shoppingState[row.dataset.key]={{checked:check.checked,quantity:quantity.value}};localStorage.setItem('pantrypal:shopping',JSON.stringify(shoppingState))}};check.addEventListener('change',persist);quantity.addEventListener('input',persist)}});
document.querySelectorAll('.export-button').forEach(button=>button.addEventListener('click',()=>{{const copy=document.querySelector('.result').cloneNode(true);copy.querySelectorAll('.result-actions,.save-recipe').forEach(node=>node.remove());copy.querySelectorAll('.shopping-row').forEach(row=>{{const line=document.createElement('p');line.textContent='['+(row.querySelector('.shop-check').checked?'x':' ')+'] '+row.dataset.name+' - '+row.querySelector('.shop-quantity').value;row.replaceWith(line)}});const blob=new Blob([copy.innerText],{{type:'text/plain;charset=utf-8'}}),link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='pantrypal-meal-plan.txt';link.click();URL.revokeObjectURL(link.href)}}));
</script></body></html>'''


def render_online(plan, candidates, pantry, form):
    multiplier = 2 if form.get("leftovers") == "yes" else 1
    chunks = ['<section class="card result"><div class="result-actions"><button type="button" class="export-button">Export plan (.txt)</button></div><h2>YOUR MEAL PLAN</h2>']
    totals = {}
    for index, meal in enumerate(plan, 1):
        ingredients = [item["name"] for item in meal["ingredients"]]
        labels = food_labels(meal["name"], ingredients, meal["category"], meal["area"])
        recipe_data = {
            "id": "online-" + str(meal["id"]), "name": meal["name"],
            "meta": f"{meal['area']} · {meal['category']}", "tags": labels,
            "ingredients": [f"{item['amount']:g} {item['unit']} {item['name']}" for item in meal["ingredients"]],
            "instructions": list(meal["steps"]),
        }
        chunks.append(f'<article class="meal"><h3>{esc(index)}. {esc(meal["name"])}</h3>'
                      f'<div class="meta">{esc(meal["area"])} · {esc(meal["category"])}</div>'
                      f'<div class="tags">{esc(", ".join(labels))}</div>'
                      f'<button type="button" class="save-recipe" data-recipe-json="{esc(json.dumps(recipe_data))}">Save recipe</button>'
                      f'<h4>Ingredients</h4><ul>')
        for item in meal["ingredients"]:
            amount = item["amount"] * multiplier
            ingredient_line = f"{amount:g} {item['unit']} {item['name']}"
            chunks.append(f'<li>{esc(ingredient_line)}</li>')
            key = (item["canonical"], item["unit"])
            totals[key] = totals.get(key, 0.0) + amount
        chunks.append('</ul><h4>Instructions</h4><ol>')
        chunks.extend(f'<li>{esc(step)}</li>' for step in meal["steps"])
        chunks.append(f'</ol><a class="source" href="{esc(meal["url"])}" target="_blank" rel="noopener">View source recipe ↗</a></article>')
    shopping = [(key, max(0, amount - pantry.get(key, 0))) for key, amount in totals.items()]
    shopping = [(key, amount) for key, amount in shopping if amount > 0]
    chunks.append('<h2>SHOPPING LIST</h2><p class="meta">Check off items and edit quantities. Your list is remembered in this browser.</p><div class="shopping"><ul>')
    chunks.append(shopping_rows((name, amount, unit) for (name, unit), amount in sorted(shopping)))
    if not shopping:
        chunks.append('<li>Nothing to buy from your listed pantry stock.</li>')
    chunks.append('</ul></div></section>')
    return "".join(chunks)


def render_builtin(plan, request):
    if not plan:
        return '<section class="card result error"><h2>NO PLAN FOUND</h2><p>Try increasing your budget or cooking time, lowering the protein target, or requesting fewer meals.</p></section>'
    chunks = ['<section class="card result"><div class="result-actions"><button type="button" class="export-button">Export plan (.txt)</button></div><h2>YOUR BUILT-IN MEAL PLAN</h2>']
    shopping = core.grocery_list(plan, request)
    for index, recipe in enumerate(plan, 1):
        labels = food_labels(recipe.name, list(recipe.ingredients), extra=tuple(sorted(recipe.tags)))
        recipe_data = {
            "id": recipe.id, "name": recipe.name,
            "meta": f"{recipe.minutes} min · ${recipe.cost:.2f} / serving · {recipe.protein}g protein",
            "tags": labels,
            "ingredients": [f"{amount:g} {unit} {name}" for name, (amount, unit) in recipe.ingredients.items()],
            "instructions": list(recipe.instructions),
        }
        chunks.append(f'<article class="meal"><h3>{index}. {esc(recipe.name)}</h3>'
                      f'<div class="meta">{recipe.minutes} min · {recipe.protein}g protein · ${recipe.cost * request.servings * (2 if request.double_for_leftovers else 1):.2f} estimated</div>'
                      f'<div class="tags">{esc(", ".join(labels))}</div>'
                      f'<button type="button" class="save-recipe" data-recipe-json="{esc(json.dumps(recipe_data))}">Save recipe</button>'
                      f'<h4>Ingredients</h4><ul>')
        multiplier = request.servings * (2 if request.double_for_leftovers else 1)
        chunks.extend("<li>{}</li>".format(esc(f"{amount * multiplier:g} {unit} {name}"))
                      for name, (amount, unit) in recipe.ingredients.items())
        chunks.append('</ul><h4>Instructions</h4><ol>')
        chunks.extend(f'<li>{esc(step)}</li>' for step in recipe.instructions)
        chunks.append('</ol></article>')
    chunks.append('<h2>SHOPPING LIST</h2><p class="meta">Check off items and edit quantities. Your list is remembered in this browser.</p><div class="shopping"><ul>')
    chunks.append(shopping_rows((name, amount, unit) for (name, unit), (amount, _u) in sorted(shopping.items())))
    if not shopping:
        chunks.append('<li>Nothing to buy from your listed pantry stock.</li>')
    chunks.append('</ul></div></section>')
    return "".join(chunks)


def render_quick_carousel(meals):
    if not meals:
        return ('<section class="card result"><h2>RECIPE PICKS</h2><p class="meta">Connect to the internet to load recipe picks. '
                'You can still search TheMealDB or use the built-in planner below.</p></section>')
    slides, details, dots = [], [], []
    for index, meal in enumerate(meals):
        meal_id = str(meal["id"])
        detail_id = "quick-detail-" + meal_id
        nutrition = estimate_nutrition(meal)
        labels = food_labels(meal["name"], [item["name"] for item in meal["ingredients"]],
                             meal["category"], meal["area"])
        recipe_data = {
            "id": "online-" + meal_id, "name": meal["name"],
            "meta": f"{meal['area']} · {meal['category']}", "tags": labels,
            "ingredients": [online_ingredient_text(item) for item in meal["ingredients"]],
            "instructions": list(meal["steps"]),
        }
        label_chips = "".join(f'<span class="recipe-label">{esc(label)}</span>' for label in labels[:3])
        slides.append(
            f'<button type="button" class="discover-result-card quick-card" data-discover-id="{esc(meal_id)}" '
            f'data-detail-target="{esc(detail_id)}" aria-label="View {esc(meal["name"])} recipe">'
            f'<img src="{esc(meal["thumbnail"])}" alt="{esc(meal["name"])}" loading="lazy">'
            f'<span class="quick-card-copy"><strong>{esc(meal["name"])}</strong>'
            f'<span class="recipe-labels">{label_chips}</span></span></button>')
        dots.append(f'<button type="button" class="carousel-dot{" active" if index == 0 else ""}" data-slide="{index}" aria-label="Show recipe {index + 1}"></button>')
        ingredients = "".join("<li>{}</li>".format(esc(online_ingredient_text(item)))
                               for item in meal["ingredients"])
        steps = "".join(f'<li>{esc(step)}</li>' for step in meal["steps"])
        details.append(
            f'<article class="recipe-detail quick-recipe-detail" id="{esc(detail_id)}" hidden>'
            f'<button type="button" class="close-detail" aria-label="Close recipe">×</button>'
            f'<div class="eyebrow">{esc(" · ".join(labels))}</div><h3>{esc(meal["name"])}</h3>'
            f'<p class="meta">{esc(meal["area"])} · {esc(meal["category"])}</p>'
            f'<p class="nutrition-estimate">About {nutrition["calories"]:,} kcal · {nutrition["protein"]} g protein <small>Rough estimate for the whole recipe from listed ingredients; actual values vary.</small></p>'
            f'<button type="button" class="save-recipe" data-recipe-json="{esc(json.dumps(recipe_data))}">Save recipe</button>'
            f'<div class="detail-columns"><div><h4>Ingredients</h4><ul>{ingredients}</ul></div>'
            f'<div><h4>Instructions</h4><ol>{steps}</ol><a class="source" href="{esc(meal["url"])}" target="_blank" rel="noopener">View source recipe ↗</a></div></div></article>')
    return (f'<section class="card quick-picks"><div class="popular-heading"><h2>Quick picks from TheMealDB</h2>'
            f'<span>{len(slides)} recipes · refreshed every 30 minutes</span></div>'
            f'<div class="quick-carousel"><button type="button" class="carousel-arrow previous" aria-label="Previous recipe">‹</button>'
            f'<div class="carousel-viewport"><div class="carousel-track">{"".join(slides)}</div></div>'
            f'<button type="button" class="carousel-arrow next" aria-label="Next recipe">›</button></div>'
            f'<div class="carousel-dots">{"".join(dots)}</div>{"".join(details)}</section>')


def render_discovery(meals, heading="LIVE RESULTS FROM THEMEALDB"):
    if not meals:
        return '<section class="card result"><h2>NO LIVE RECIPES FOUND</h2><p>Try another name, ingredient, or cuisine. The built-in planner remains available below.</p></section>'
    cards, details = [], []
    for meal in meals[:12]:
        meal_id = str(meal["id"])
        nutrition = estimate_nutrition(meal)
        labels = food_labels(meal["name"], [item["name"] for item in meal["ingredients"]],
                             meal["category"], meal["area"])
        recipe_data = {
            "id": "online-" + meal_id, "name": meal["name"],
            "meta": f"{meal['area']} · {meal['category']}", "tags": labels,
            "ingredients": [online_ingredient_text(item) for item in meal["ingredients"]],
            "instructions": list(meal["steps"]),
        }
        image = (f'<img src="{esc(meal["thumbnail"])}" alt="{esc(meal["name"])}" loading="lazy">'
                 if meal.get("thumbnail") else '<span class="recipe-placeholder">🍲</span>')
        cards.append(
            f'<button type="button" class="discover-result-card" data-discover-id="{esc(meal_id)}">{image}'
            f'<strong>{esc(meal["name"])}</strong><small>{esc(meal["area"])} · {esc(meal["category"])}</small></button>')
        ingredients = "".join("<li>{}</li>".format(esc(online_ingredient_text(item)))
                               for item in meal["ingredients"])
        steps = "".join(f'<li>{esc(step)}</li>' for step in meal["steps"])
        details.append(
            f'<article class="recipe-detail" id="discover-detail-{esc(meal_id)}" hidden>'
            f'<button type="button" class="close-detail" aria-label="Close recipe">×</button>'
            f'<div class="eyebrow">{esc(" · ".join(labels))}</div><h3>{esc(meal["name"])}</h3>'
            f'<p class="meta">{esc(meal["area"])} · {esc(meal["category"])}</p>'
            f'<p class="nutrition-estimate">About {nutrition["calories"]:,} kcal · {nutrition["protein"]} g protein <small>Rough estimate for the whole recipe from listed ingredients; actual values vary.</small></p>'
            f'<button type="button" class="save-recipe" data-recipe-json="{esc(json.dumps(recipe_data))}">Save recipe</button>'
            f'<div class="detail-columns"><div><h4>Ingredients</h4><ul>{ingredients}</ul></div>'
            f'<div><h4>Instructions</h4><ol>{steps}</ol><a class="source" href="{esc(meal["url"])}" target="_blank" rel="noopener">View source recipe ↗</a></div></div></article>')
    return (f'<section class="card result"><h2>{esc(heading)}</h2>'
            f'<p class="meta">{len(cards)} recipe(s) found. Select a card to view its details.</p>'
            f'<div class="discover-results">{"".join(cards)}</div>{"".join(details)}</section>')


class PantryPalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        meals = load_quick_meals()
        quick_picks = (render_quick_carousel(meals) if meals else
                       '<section class="card result"><h2>QUICK PICKS</h2><p class="meta">Connect to the internet to load recipe photos and details. You can still search TheMealDB or use the built-in planner below.</p></section>')
        self._send(page(quick_picks=quick_picks))

    def do_POST(self):
        if self.path == "/discover":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(min(length, 100_000)).decode("utf-8", "replace")
            form = {key: values[-1] for key, values in parse_qs(raw).items()}
            queries = [item.strip() for item in form.get("discover_query", "").split(",") if item.strip()][:3]
            moods = [item.strip() for item in form.get("discover_mood", "").split(",") if item.strip()]
            try:
                surprise = form.get("surprise") == "1"
                if surprise and (queries or moods):
                    candidates = search_many(queries, {}, "none", set(), moods)
                    meals = [random.choice(candidates)] if candidates else []
                elif surprise:
                    raw_meals = api_get("random.php", {}).get("meals") or []
                    meals = [parse_meal(raw_meals[0])] if raw_meals else []
                elif not queries and not moods:
                    raise ValueError("Enter a recipe name, ingredient, cuisine, or mood to search TheMealDB.")
                else:
                    meals = search_many(queries, {}, "none", set(), moods)
                result = render_discovery(meals, "YOUR SURPRISE RECIPE" if surprise else "LIVE RESULTS FROM THEMEALDB")
            except Exception as exc:
                result = f'<section class="card result error"><h2>LIVE SEARCH UNAVAILABLE</h2><p>{esc(exc)}</p><p>Try again when the internet connection is available.</p></section>'
            form["mode"] = "online"
            quick_meals = load_quick_meals()
            quick_picks = render_quick_carousel(quick_meals) if quick_meals else ""
            self._send(page(values=form, discovery_result=result, quick_picks=quick_picks))
            return
        if self.path != "/plan":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(min(length, 100_000)).decode("utf-8", "replace")
        form = {key: values[-1] for key, values in parse_qs(raw).items()}
        form.setdefault("pantry", "")
        form.setdefault("leftovers", "no")
        try:
            count = int(form.get("count", "3"))
            if not 1 <= count <= 7:
                raise ValueError("Choose between 1 and 7 meals.")
            allergies = {item.strip().lower() for item in form.get("allergies", "").split(",") if item.strip()}
            diet = form.get("diet", "none")
            if form.get("mode") == "built-in":
                pantry = parse_inventory(form.get("pantry", ""))
                servings = int(form.get("servings") or 2)
                minutes = int(form.get("minutes") or 40)
                budget = float(form.get("budget") or 30)
                protein = int(form.get("protein") or 0)
                if not 1 <= servings <= 12 or not 5 <= minutes <= 180 or budget <= 0 or protein < 0:
                    raise ValueError("Check servings (1–12), cooking time (5–180), budget, and protein target.")
                agent = core.PantryPalAgent()
                agent.profile = core.UserProfile(diet, frozenset(allergies),
                    frozenset(item.strip().lower() for item in form.get("dislikes", "").split(",") if item.strip()),
                    agent.profile.liked, agent.profile.avoided)
                request = core.Request(count, servings, minutes, budget, protein, pantry,
                                       form.get("leftovers") == "yes")
                plan, _candidates = agent.plan(request)
                result = render_builtin(plan, request)
            else:
                queries = [item.strip() for item in form.get("queries", "").split(",") if item.strip()][:3]
                moods = [item.strip() for item in form.get("moods", "").split(",") if item.strip()]
                if not queries and not moods:
                    raise ValueError("Enter at least one dish, ingredient, food mood, or cuisine.")
                pantry = parse_inventory(form.get("pantry", ""))
                meals = search_many(queries, pantry, diet, allergies, moods)
                if not meals:
                    result = '<section class="card result"><h2>NO MATCHES</h2><p>Try another dish, ingredient, mood, or cuisine.</p></section>'
                else:
                    plan = make_online_plan(meals, min(count, len(meals)), pantry, form.get("leftovers") == "yes")
                    result = render_online(plan, meals, pantry, form)
        except Exception as exc:
            result = f'<section class="card result error"><h2>COULDN’T BUILD A PLAN</h2><p>{esc(exc)}</p></section>'
        self._send(page(result, form))

    def _send(self, content):
        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[PantryPal] {self.address_string()} - {fmt % args}")


def main():
    server = ThreadingHTTPServer((HOST, PORT), PantryPalHandler)
    url = f"http://{HOST}:{PORT}"
    print(f"PantryPal web app is running at {url}\nPress Ctrl+C to stop.")
    try:
        webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPantryPal stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
