"""Tkinter desktop interface for PantryPal."""

from __future__ import annotations

import math
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path

import pantry_pal as core
from food_data import canonical_ingredient, parse_measure, purchase_line, standardize_quantity
from online_recipes import (food_labels, load_online_feedback,
                            make_online_plan, search_many, save_online_feedback,
                            suggest_substitutions)


def parse_inventory(text: str):
    """Parse comma-separated pantry quantities such as rice=2 cups."""
    inventory = {}
    for entry in text.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise ValueError(f"Use name=quantity for pantry items (problem: {entry}).")
        name, quantity = entry.split("=", 1)
        name = canonical_ingredient(name)
        amount, unit = parse_measure(quantity)
        amount, unit = standardize_quantity(amount, unit)
        key = (name, unit)
        inventory[key] = inventory.get(key, 0.0) + amount
    return inventory


class PantryPalUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.agent = core.PantryPalAgent()
        self.root.title("PantryPal | Intelligent Meal Planner")
        self.root.geometry("1060x780")
        self.root.minsize(820, 620)
        self.root.configure(bg="#0c100e")
        self.featured_ids = ("tomato_pasta", "chickpea_curry", "greek_chickpea_bowl")
        self.featured = [next(recipe for recipe in core.RECIPES if recipe.id == recipe_id)
                         for recipe_id in self.featured_ids]
        self.carousel_index = 0
        self.current_view = "home"
        self.is_animating = False
        self._setup_style()
        self._build()

    def _setup_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#151b17")
        style.configure("Card.TFrame", background="#151b17")
        style.configure("TLabel", background="#151b17", foreground="#e9eee9", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"), foreground="#f3f6f3")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground="#a1ada5")
        style.configure("TButton", background="#252d28", foreground="#e9eee9", font=("Segoe UI", 10), padding=(10, 7), borderwidth=0)
        style.map("TButton", background=[("active", "#333d36")])
        style.configure("Accent.TButton", background="#b5e7c8", foreground="#102018", font=("Segoe UI", 10, "bold"), padding=(12, 8))
        style.map("Accent.TButton", background=[("active", "#c9f3d8")])
        style.configure("TNotebook", background="#111613", borderwidth=0)
        style.configure("TNotebook.Tab", background="#151b17", foreground="#aeb9b1", padding=(16, 10), font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", "#252e28")], foreground=[("selected", "#c1f0d1")])
        style.configure("TEntry", fieldbackground="#222a25", foreground="#f0f4f0", insertcolor="#ffffff", bordercolor="#303a33", lightcolor="#303a33", darkcolor="#303a33", padding=8)
        style.configure("TCombobox", fieldbackground="#222a25", background="#222a25", foreground="#f0f4f0", arrowcolor="#b5e7c8", bordercolor="#303a33", padding=7)
        style.map("TCombobox", fieldbackground=[("readonly", "#222a25")], foreground=[("readonly", "#f0f4f0")])
        style.configure("TCheckbutton", background="#151b17", foreground="#d8e0da")
        style.map("TCheckbutton", background=[("active", "#151b17")], foreground=[("active", "#ffffff")])

    def _build(self):
        self._load_hero_photos()
        nav = tk.Frame(self.root, bg="#101512", height=58,
                       highlightthickness=1, highlightbackground="#202a23")
        nav.pack(fill="x", padx=18, pady=(14, 12))
        nav.pack_propagate(False)
        brand = tk.Frame(nav, bg="#101512")
        brand.pack(side="left", padx=(18, 30))
        tk.Label(brand, text="P", bg="#b5e7c8", fg="#102018", width=2,
                 font=("Segoe UI", 14, "bold"), padx=5, pady=2).pack(side="left", padx=(0, 9))
        tk.Label(brand, text="PantryPal", bg="#101512", fg="#f1f5f1",
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        self.nav_buttons = {}
        for key, label in (("home", "Home"), ("online", "Find recipes"), ("built_in", "Meal planner")):
            button = tk.Button(nav, text=label, relief="flat", bd=0, padx=14, pady=8,
                               font=("Segoe UI", 10, "bold"), cursor="hand2",
                               command=lambda page=key: self._navigate(page))
            button.pack(side="left", padx=3)
            self.nav_buttons[key] = button
        tk.Label(nav, text="PLAN  •  COOK  •  ENJOY", bg="#101512", fg="#7f8c82",
                 font=("Segoe UI", 8, "bold")).pack(side="right", padx=20)

        self.page_content = tk.Frame(self.root, bg="#0c100e")
        self.page_content.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self.home_view = tk.Frame(self.page_content, bg="#0c100e")
        self.planner_view = tk.Frame(self.page_content, bg="#0c100e")
        self.detail_view = tk.Frame(self.page_content, bg="#0c100e")
        self._build_home()

        self.mode_content = tk.Frame(self.planner_view, bg="#151b17")
        self.mode_content.pack(fill="x", pady=(0, 13))
        self.online_tab = ttk.Frame(self.mode_content, style="Card.TFrame", padding=(18, 14))
        self.built_in_tab = ttk.Frame(self.mode_content, style="Card.TFrame", padding=(18, 14))
        self.pantry_items = {"online": [], "local": []}
        self.pantry_inputs = {}
        self._build_online_form()
        self._build_builtin_form()

        output_card = ttk.Frame(self.planner_view, style="Card.TFrame", padding=14)
        output_card.pack(fill="both", expand=True)
        output_header = ttk.Frame(output_card, style="Card.TFrame")
        output_header.pack(fill="x", pady=(0, 8))
        title_group = ttk.Frame(output_header, style="Card.TFrame")
        title_group.pack(side="left")
        ttk.Label(title_group, text="PLAN PREVIEW", background="#151b17", foreground="#eef4ef",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(title_group, text="Your recipes, steps, and shopping list", background="#151b17",
                  foreground="#849188", font=("Segoe UI", 9)).pack(anchor="w", pady=(1, 0))
        self.status_var = tk.StringVar(value="READY")
        tk.Label(output_header, textvariable=self.status_var, bg="#25372c", fg="#b5e7c8",
                 font=("Segoe UI", 8, "bold"), padx=10, pady=5).pack(side="right", padx=(8, 0))
        ttk.Button(output_header, text="Clear", command=self._clear).pack(side="right")
        body = ttk.Frame(output_card, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        self.output = tk.Text(body, wrap="word", font=("Segoe UI", 10), bg="#151a17", fg="#e4ebe5",
                              insertbackground="#ffffff", selectbackground="#315641", relief="flat",
                              padx=14, pady=12, state="disabled")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scrollbar.set)
        self.output.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.output.tag_configure("section", foreground="#b5e7c8", font=("Segoe UI", 10, "bold"), spacing1=9, spacing3=4)
        self.output.tag_configure("meal", foreground="#f2f5f2", font=("Segoe UI", 12, "bold"), spacing1=7, spacing3=2)
        self.output.tag_configure("muted", foreground="#98a49b")
        self.output.tag_configure("accent", foreground="#d4f2de")
        self.feedback = ttk.Frame(output_card, style="Card.TFrame")
        self.feedback.pack(fill="x", pady=(8, 0))
        self._write("Choose a planner above to get started. Your results will appear here.")
        self.home_view.pack(fill="both", expand=True)
        self._set_nav_active("home")
        self.root.after(7000, self._rotate_featured)

    def _build_home(self):
        intro = tk.Frame(self.home_view, bg="#0c100e")
        intro.pack(fill="x", pady=(2, 10))
        tk.Label(intro, text="A little inspiration for what’s next.", bg="#0c100e", fg="#eff4ef",
                 font=("Segoe UI", 16, "bold")).pack(side="left")
        tk.Label(intro, text="FEATURED  •  POPULAR PICKS", bg="#0c100e", fg="#93a197",
                 font=("Segoe UI", 8, "bold")).pack(side="right", padx=10)

        self.hero = tk.Canvas(self.home_view, height=350, bg="#111613", highlightthickness=0,
                              cursor="hand2")
        self.hero.pack(fill="x", pady=(0, 19))
        self.hero.bind("<Configure>", self._draw_featured)
        self.hero.bind("<Button-1>", self._hero_click)
        self._draw_featured()

        heading = tk.Frame(self.home_view, bg="#0c100e")
        heading.pack(fill="x", pady=(0, 9))
        tk.Label(heading, text="Popular recipes", bg="#0c100e", fg="#f0f4f0",
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(heading, text="A few ideas to get you started", bg="#0c100e", fg="#88948b",
                 font=("Segoe UI", 9)).pack(side="left", padx=(10, 0), pady=(3, 0))
        cards = tk.Frame(self.home_view, bg="#0c100e")
        cards.pack(fill="x")
        self.card_photos = [photo.subsample(5, 5) for photo in self.hero_photos]
        self.recipe_cards = []
        for index, recipe in enumerate(self.featured):
            cards.grid_columnconfigure(index, weight=1, uniform="recipe")
            card = tk.Canvas(cards, width=310, height=204, bg="#0c100e",
                             highlightthickness=0, cursor="hand2")
            self.recipe_cards.append(card)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 8, 0), pady=2)
            card.bind("<Configure>", lambda _event, item=index: self._draw_recipe_card(item))
            card.bind("<Button-1>", lambda _event, item=index: self._open_recipe(item))
            card.bind("<Enter>", lambda _event, item=index: self._draw_recipe_card(item, hover=True))
            card.bind("<Leave>", lambda _event, item=index: self._draw_recipe_card(item))
            self._draw_recipe_card(index)

    @staticmethod
    def _rounded_panel(canvas, x1, y1, x2, y2, radius, fill, outline=""):
        radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
        points = [x1 + radius, y1, x2 - radius, y1, x2, y1,
                  x2, y1 + radius, x2, y2 - radius, x2, y2,
                  x2 - radius, y2, x1 + radius, y2, x1, y2,
                  x1, y2 - radius, x1, y1 + radius, x1, y1]
        return canvas.create_polygon(points, smooth=True, splinesteps=20,
                                     fill=fill, outline=outline)

    def _draw_recipe_card(self, index, hover=False):
        card = self.recipe_cards[index]
        width = max(card.winfo_width(), 250)
        height = 204
        card.delete("all")
        fill = "#202a23" if hover else "#151b17"
        self._rounded_panel(card, 2, 2, width - 2, height - 2, 18, fill)
        card.create_image(width // 2, 67, image=self.card_photos[index])
        recipe = self.featured[index]
        card.create_text(17, 145, anchor="w", text=recipe.name, fill="#eff4ef",
                         font=("Segoe UI", 10, "bold"))
        card.create_text(17, 172, anchor="w",
                         text=f"{recipe.minutes} min   ·   ${recipe.cost:.2f} / serving",
                         fill="#93a197", font=("Segoe UI", 8))

    def _load_hero_photos(self):
        assets = Path(__file__).with_name("assets")
        self.hero_photos = []
        for filename in ("hero-pasta.png", "hero-curry.png", "hero-vegetables.png"):
            try:
                self.hero_photos.append(tk.PhotoImage(file=str(assets / filename)))
            except tk.TclError:
                self.hero_photos.append(tk.PhotoImage(width=700, height=350))
        try:
            self.hero_overlay_photo = tk.PhotoImage(file=str(assets / "hero-overlay.png"))
        except tk.TclError:
            self.hero_overlay_photo = tk.PhotoImage(width=1100, height=560)

    def _draw_featured(self, _event=None):
        canvas = self.hero
        if not hasattr(self, "hero_photos") or not self.hero_photos:
            return
        if getattr(self, "is_animating", False):
            return
        width = max(canvas.winfo_width(), 700)
        height = 350
        canvas.delete("all")
        self._draw_slide(self.carousel_index, 0, "slide_current")
        self._draw_hero_controls(width, height)
        self._round_canvas_corners(canvas, width, height, 18)

    @staticmethod
    def _mix_color(first: str, second: str, amount: float):
        left = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
        right = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
        mixed = tuple(round(a + (b - a) * amount) for a, b in zip(left, right))
        return "#" + "".join(f"{channel:02x}" for channel in mixed)

    def _draw_gradient(self, canvas, x, y, width, height, start, end, steps=48, tag=None):
        for step in range(steps):
            left = x + width * step / steps
            right = x + width * (step + 1) / steps + 1
            color = self._mix_color(start, end, step / max(steps - 1, 1))
            tags = (tag,) if tag else ()
            canvas.create_rectangle(left, y, right, y + height, fill=color,
                                   outline=color, tags=tags)

    @staticmethod
    def _round_canvas_corners(canvas, width, height, radius):
        corners = (
            ((0, 0), (radius, 0), (radius, radius), -math.pi / 2, -math.pi),
            ((width, 0), (width - radius, 0), (width - radius, radius), -math.pi / 2, 0),
            ((width, height), (width, height - radius), (width - radius, height - radius), 0, math.pi / 2),
            ((0, height), (radius, height), (radius, height - radius), math.pi / 2, math.pi),
        )
        for corner, edge_start, center, first_angle, last_angle in corners:
            points = [*corner, *edge_start]
            for step in range(1, 13):
                angle = first_angle + (last_angle - first_angle) * step / 12
                points.extend((center[0] + radius * math.cos(angle),
                               center[1] + radius * math.sin(angle)))
            points.extend(corner)
            canvas.create_polygon(points, fill="#0c100e", outline="#0c100e",
                                  tags=("rounded_mask",))

    def _draw_slide(self, index, offset, tag):
        canvas = self.hero
        width = max(canvas.winfo_width(), 700)
        height = 350
        recipe = self.featured[index]
        canvas.create_image(width // 2 + offset, height // 2, image=self.hero_photos[index],
                            anchor="center", tags=(tag, "hero_image"))
        # Alpha gradient keeps the title readable without hiding the food photo.
        canvas.create_image(width // 2 + offset, height // 2, image=self.hero_overlay_photo,
                            anchor="center", tags=(tag, "hero_overlay"))
        canvas.create_text(42 + offset, 38, anchor="w", text="PANTRYPAL  /  POPULAR RECIPE",
                           fill="#b5e7c8", font=("Segoe UI", 9, "bold"), tags=(tag,))
        canvas.create_text(42 + offset, 100, anchor="w", text=recipe.name,
                           width=min(540, width * .58), fill="#f5f7f5",
                           font=("Segoe UI", 29, "bold"), tags=(tag,))
        tags = "  ·  ".join(sorted(recipe.tags)[:2]).upper()
        canvas.create_text(44 + offset, 151, anchor="w",
                           text=f"★  {recipe.minutes} MIN   ·   ${recipe.cost:.2f} / SERVING   ·   {tags}",
                           fill="#d1d8d2", font=("Segoe UI", 9, "bold"), tags=(tag,))
        summary = recipe.instructions[0] if recipe.instructions else "A PantryPal favorite, ready to add to your meal plan."
        canvas.create_text(44 + offset, 203, anchor="nw", text=summary,
                           width=min(490, width * .48), fill="#c0c9c1",
                           font=("Segoe UI", 11), tags=(tag,))
        canvas.create_rectangle(43 + offset, 274, 166 + offset, 311,
                               fill="#b5e7c8", outline="", tags=(tag, "hero_cta"))
        canvas.create_text(104 + offset, 293, text="View recipe  →", fill="#102018",
                           font=("Segoe UI", 10, "bold"), tags=(tag, "hero_cta"))

    def _draw_hero_controls(self, width, height):
        canvas = self.hero
        # Dark footer strips blend the picture into the app background.
        self._draw_gradient(canvas, 0, height - 28, width, 28,
                            "#151a17", "#0c100e", steps=28, tag="hero_controls")
        for i in range(len(self.featured)):
            x = 45 + i * 24
            canvas.create_oval(x, 326, x + (18 if i == self.carousel_index else 8), 334,
                               fill="#b5e7c8" if i == self.carousel_index else "#748078", outline="",
                               tags=("hero_controls", f"dot{i}"))
        canvas.create_oval(12, height // 2 - 21, 54, height // 2 + 21,
                           fill="#111613", outline="#39443c", tags=("hero_controls", "carousel_left"))
        canvas.create_text(33, height // 2, text="‹", fill="#eff4ef",
                           font=("Segoe UI", 19), tags=("hero_controls", "carousel_left"))
        canvas.create_oval(width - 54, height // 2 - 21, width - 12, height // 2 + 21,
                           fill="#111613", outline="#39443c", tags=("hero_controls", "carousel_right"))
        canvas.create_text(width - 33, height // 2, text="›", fill="#eff4ef",
                           font=("Segoe UI", 19), tags=("hero_controls", "carousel_right"))

    def _set_featured(self, index):
        target = index % len(self.featured)
        if target == self.carousel_index or self.is_animating:
            return
        direction = 1 if (target - self.carousel_index) % len(self.featured) == 1 else -1
        self._animate_featured(target, direction)

    def _step_featured(self, amount):
        if self.is_animating:
            return
        self._animate_featured((self.carousel_index + amount) % len(self.featured), 1 if amount > 0 else -1)

    def _animate_featured(self, target, direction):
        if target == self.carousel_index or self.is_animating:
            return
        self.is_animating = True
        canvas = self.hero
        width = max(canvas.winfo_width(), 700)
        self._draw_slide(target, direction * width, "slide_next")
        canvas.tag_raise("hero_controls")
        self._round_canvas_corners(canvas, width, 350, 18)
        canvas.tag_raise("rounded_mask")
        frames = 20
        delta = -direction * width / frames

        def animate(frame=0):
            if not canvas.winfo_exists():
                self.is_animating = False
                return
            canvas.move("slide_current", delta, 0)
            canvas.move("slide_next", delta, 0)
            if frame + 1 >= frames:
                self.carousel_index = target
                self.is_animating = False
                self._draw_featured()
            else:
                self.root.after(15, lambda: animate(frame + 1))

        animate()

    def _hero_click(self, event):
        if self.is_animating:
            return "break"
        current = self.hero.find_withtag("current")
        tags = set(self.hero.gettags(current[0])) if current else set()
        if "carousel_left" in tags:
            self._step_featured(-1)
        elif "carousel_right" in tags:
            self._step_featured(1)
        elif "hero_cta" in tags:
            self._open_featured()
        else:
            dot = next((tag for tag in tags if tag.startswith("dot")), None)
            if dot:
                self._set_featured(int(dot[3:]))
            else:
                self._open_featured()
        return "break"

    def _rotate_featured(self):
        if self.current_view == "home":
            self._step_featured(1)
        self.root.after(7000, self._rotate_featured)

    def _open_featured(self):
        self._open_recipe(self.carousel_index)

    def _open_recipe(self, index):
        recipe = self.featured[index]
        for view in (self.home_view, self.planner_view, self.detail_view):
            view.pack_forget()
        for child in self.detail_view.winfo_children():
            child.destroy()
        self.current_view = "recipe_detail"
        self._set_nav_active("home")

        topbar = tk.Frame(self.detail_view, bg="#0c100e")
        topbar.pack(fill="x", pady=(0, 10))
        tk.Button(topbar, text="←  Back to home", command=lambda: self._navigate("home"),
                  bg="#19211c", fg="#c6d2c9", activebackground="#27352c", relief="flat",
                  bd=0, padx=13, pady=8, font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="left")
        tk.Label(topbar, text="RECIPE DETAILS", bg="#0c100e", fg="#8e9b92",
                 font=("Segoe UI", 8, "bold")).pack(side="right", padx=4)

        banner = tk.Canvas(self.detail_view, height=205, bg="#151b17", highlightthickness=0)
        banner.pack(fill="x", pady=(0, 12))
        banner.bind("<Configure>", lambda event, i=index: self._draw_detail_banner(event, i))
        self.detail_banner = banner
        self.detail_recipe_index = index
        self._draw_detail_banner()

        columns = tk.Frame(self.detail_view, bg="#0c100e")
        columns.pack(fill="both", expand=True)
        ingredients_panel = tk.Frame(columns, bg="#151b17", padx=18, pady=15)
        ingredients_panel.pack(side="left", fill="y", padx=(0, 10))
        method_panel = tk.Frame(columns, bg="#151b17", padx=18, pady=15)
        method_panel.pack(side="left", fill="both", expand=True)
        tk.Label(ingredients_panel, text="INGREDIENTS", bg="#151b17", fg="#b5e7c8",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 9))
        ingredients_text = tk.Text(ingredients_panel, wrap="word", width=28, height=13,
                                   bg="#151b17", fg="#e4ebe5", relief="flat",
                                   font=("Segoe UI", 10), padx=0, pady=0)
        ingredients_text.pack(fill="both", expand=True)
        for name, (amount, unit) in recipe.ingredients.items():
            ingredients_text.insert("end", f"• {amount:g} {unit} {name}\n")
        ingredients_text.configure(state="disabled")
        tk.Label(method_panel, text="METHOD", bg="#151b17", fg="#b5e7c8",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 9))
        method_text = tk.Text(method_panel, wrap="word", bg="#151b17", fg="#e4ebe5",
                              relief="flat", font=("Segoe UI", 10), padx=0, pady=0)
        method_text.pack(fill="both", expand=True)
        for step, instruction in enumerate(recipe.instructions, 1):
            method_text.insert("end", f"{step}. {instruction}\n\n")
        method_text.configure(state="disabled")
        footer = tk.Frame(self.detail_view, bg="#0c100e")
        footer.pack(fill="x", pady=(11, 0))
        tk.Button(footer, text="Build a meal plan with these recipes", command=lambda: self._navigate("built_in"),
                  bg="#b5e7c8", fg="#102018", activebackground="#c9f3d8", relief="flat", bd=0,
                  padx=15, pady=9, font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="right")
        self.detail_view.pack(fill="both", expand=True)

    def _draw_detail_banner(self, _event=None, index=None):
        index = self.detail_recipe_index if index is None else index
        recipe = self.featured[index]
        canvas = self.detail_banner
        width = max(canvas.winfo_width(), 700)
        canvas.delete("all")
        canvas.create_image(width // 2, 102, image=self.hero_photos[index], anchor="center")
        canvas.create_image(width // 2, 102, image=self.hero_overlay_photo, anchor="center")
        canvas.create_text(28, 41, anchor="w", text=recipe.name, fill="#f3f6f3",
                           font=("Segoe UI", 24, "bold"), width=width * .62)
        tags = "  ·  ".join(sorted(recipe.tags)[:2]).upper()
        canvas.create_text(30, 91, anchor="w",
                           text=f"{recipe.minutes} MIN  ·  ${recipe.cost:.2f} / SERVING  ·  {tags}",
                           fill="#cfdbd1", font=("Segoe UI", 9, "bold"))
        summary = recipe.instructions[0] if recipe.instructions else "A PantryPal favorite."
        canvas.create_text(30, 122, anchor="nw", text=summary, width=width * .55,
                           fill="#aebbb1", font=("Segoe UI", 10))
        self._round_canvas_corners(canvas, width, 205, 18)

    def _navigate(self, page):
        for view in (self.home_view, self.planner_view, self.detail_view):
            view.pack_forget()
        if page == "home":
            self.home_view.pack(fill="both", expand=True)
            self.current_view = "home"
            self._set_nav_active("home")
        else:
            self.planner_view.pack(fill="both", expand=True)
            self.current_view = page
            self._select_mode(page)

    def _set_nav_active(self, page):
        for key, button in self.nav_buttons.items():
            active = key == page
            button.configure(bg="#b5e7c8" if active else "#101512",
                             fg="#102018" if active else "#b3bdb5",
                             activebackground="#c9f3d8" if active else "#222b25",
                             activeforeground="#102018" if active else "#ffffff")

    def _select_mode(self, mode):
        for child in (self.online_tab, self.built_in_tab):
            child.pack_forget()
        panel = self.online_tab if mode == "online" else self.built_in_tab
        panel.pack(fill="x")
        self.current_view = mode
        self._set_nav_active(mode)

    def _entry(self, parent, label, default="", width=32):
        box = ttk.Frame(parent)
        box.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=4)
        ttk.Label(box, text=label).pack(anchor="w", pady=(0, 3))
        variable = tk.StringVar(value=default)
        entry = tk.Entry(box, textvariable=variable, width=width, relief="flat", bd=0,
                         bg="#202922", fg="#eef4ef", insertbackground="#ffffff",
                         highlightthickness=1, highlightbackground="#2c3930",
                         highlightcolor="#78a989", font=("Segoe UI", 9))
        entry.pack(fill="x", ipady=7, padx=1)
        return variable

    def _choice(self, parent, label, values, default):
        box = ttk.Frame(parent)
        box.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=4)
        ttk.Label(box, text=label).pack(anchor="w", pady=(0, 3))
        variable = tk.StringVar(value=default)
        ttk.Combobox(box, textvariable=variable, values=values, state="readonly").pack(fill="x")
        return variable

    def _quick_chip(self, parent, variable, text, token=None):
        token = token or text
        button = tk.Button(parent, text=f"＋ {text}", relief="flat", bd=0, padx=9, pady=5,
                           bg="#222d26", fg="#c8dfce", activebackground="#314236",
                           activeforeground="#f2f7f3", font=("Segoe UI", 8, "bold"),
                           cursor="hand2", command=lambda: self._append_token(variable, token))
        button.pack(side="left", padx=(0, 6), pady=2)
        return button

    @staticmethod
    def _append_token(variable, token):
        values = [value.strip() for value in variable.get().split(",") if value.strip()]
        if token.casefold() not in {value.casefold() for value in values}:
            values.append(token)
        variable.set(", ".join(values))

    def _build_pantry_builder(self, parent, key):
        self.pantry_vars = getattr(self, "pantry_vars", {})
        self.pantry_vars[key] = tk.StringVar(value="")
        setattr(self, "online_pantry" if key == "online" else "local_pantry", self.pantry_vars[key])
        section = ttk.Frame(parent)
        section.pack(fill="x", pady=(6, 0))
        heading = tk.Frame(section, bg="#151b17")
        heading.pack(fill="x", pady=(0, 4))
        tk.Label(heading, text="PANTRY", bg="#151b17", fg="#c6ebd2",
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(heading, text="Add what you already have to improve the shopping list.",
                 bg="#151b17", fg="#89978d", font=("Segoe UI", 8)).pack(side="left", padx=(9, 0))

        manual = ttk.Frame(section)
        manual.pack(fill="x")
        ttk.Label(manual, text="Pantry list", width=13).pack(side="left", padx=(0, 8))
        manual_entry = tk.Entry(manual, textvariable=self.pantry_vars[key], relief="flat", bd=0,
                                bg="#202922", fg="#eef4ef", insertbackground="#ffffff",
                                highlightthickness=1, highlightbackground="#2c3930",
                                highlightcolor="#78a989", font=("Segoe UI", 9))
        manual_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=1)

        add_row = tk.Frame(section, bg="#151b17")
        add_row.pack(fill="x", pady=(6, 0))
        tk.Label(add_row, text="QUICK ADD", bg="#151b17", fg="#849389",
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 9))
        inputs = {}
        for field, label, width in (("name", "Ingredient", 18), ("amount", "Qty", 7)):
            field_box = tk.Frame(add_row, bg="#151b17")
            field_box.pack(side="left", padx=(0, 8))
            tk.Label(field_box, text=label, bg="#151b17", fg="#aab6ad",
                     font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
            variable = tk.StringVar()
            entry = tk.Entry(field_box, textvariable=variable, width=width, relief="flat", bd=0,
                             bg="#202922", fg="#eef4ef", insertbackground="#ffffff",
                             font=("Segoe UI", 9))
            entry.pack(fill="x", ipady=5, ipadx=7)
            entry.bind("<Return>", lambda _event, pantry_key=key: self._add_pantry_item(pantry_key))
            inputs[field] = variable
        unit = tk.StringVar(value="piece")
        unit_field = tk.Frame(add_row, bg="#151b17")
        unit_field.pack(side="left", padx=(0, 8))
        tk.Label(unit_field, text="Unit", bg="#151b17", fg="#aab6ad",
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
        unit_box = ttk.Combobox(unit_field, textvariable=unit, state="readonly", width=9,
                                values=("piece", "can", "cup", "tbsp", "tsp", "g", "kg", "oz", "lb", "ml", "l"))
        unit_box.pack(fill="x", ipady=2)
        inputs["unit"] = unit
        self.pantry_inputs = getattr(self, "pantry_inputs", {})
        self.pantry_inputs[key] = inputs
        tk.Button(add_row, text="＋ Add item", relief="flat", bd=0, padx=11, pady=6,
                  bg="#25372c", fg="#c6ebd2", activebackground="#314a39",
                  font=("Segoe UI", 8, "bold"), cursor="hand2",
                  command=lambda pantry_key=key: self._add_pantry_item(pantry_key)).pack(side="left", pady=(14, 0))

        chips = tk.Frame(section, bg="#151b17")
        chips.pack(fill="x", pady=(4, 0))
        self.pantry_chip_frames = getattr(self, "pantry_chip_frames", {})
        self.pantry_chip_frames[key] = chips
        self.pantry_vars[key].trace_add("write", lambda *_args, pantry_key=key: self._refresh_pantry_chips(pantry_key))

    def _add_pantry_item(self, key):
        fields = self.pantry_inputs[key]
        name = fields["name"].get().strip()
        raw_amount = fields["amount"].get().strip()
        unit = fields["unit"].get().strip()
        try:
            amount = float(raw_amount)
            if not name or amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showinfo("Add a pantry item", "Enter an ingredient and a quantity greater than zero.", parent=self.root)
            return
        variable = self.pantry_vars[key]
        item = f"{name}={amount:g} {unit}"
        variable.set(f"{variable.get().strip()}, {item}".strip(", "))
        fields["name"].set("")
        fields["amount"].set("")

    def _refresh_pantry_chips(self, key):
        frame = self.pantry_chip_frames[key]
        for child in frame.winfo_children():
            child.destroy()
        items = [item.strip() for item in self.pantry_vars[key].get().split(",") if item.strip()]
        if not items:
            tk.Label(frame, text="No pantry items added", bg="#151b17", fg="#758278",
                     font=("Segoe UI", 8)).pack(side="left", pady=(3, 0))
            return
        for index, item in enumerate(items):
            tk.Button(frame, text=f"{item}   ×", relief="flat", bd=0, padx=8, pady=3,
                      bg="#26372c", fg="#d3e9d9", activebackground="#354b3b",
                      font=("Segoe UI", 8), cursor="hand2",
                      command=lambda i=index, pantry_key=key: self._remove_pantry_item(pantry_key, i)).pack(side="left", padx=(0, 5), pady=2)

    def _remove_pantry_item(self, key, index):
        items = [item.strip() for item in self.pantry_vars[key].get().split(",") if item.strip()]
        if 0 <= index < len(items):
            del items[index]
            self.pantry_vars[key].set(", ".join(items))

    def _build_online_form(self):
        ttk.Label(self.online_tab, text="Search live recipes from TheMealDB.").pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(self.online_tab)
        row.pack(fill="x")
        self.online_queries = self._entry(row, "Dish names or ingredients (comma separated)", "")
        self.online_moods = self._entry(row, "Food mood or cuisine (comma separated)", "")
        quick = tk.Frame(self.online_tab, bg="#151b17")
        quick.pack(fill="x", pady=(3, 2))
        tk.Label(quick, text="INGREDIENTS", bg="#151b17", fg="#849389",
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))
        for token in ("Chicken", "Pasta", "Rice", "Tomato", "Eggplant"):
            self._quick_chip(quick, self.online_queries, token)
        moods = tk.Frame(self.online_tab, bg="#151b17")
        moods.pack(fill="x", pady=(0, 4))
        tk.Label(moods, text="MOOD", bg="#151b17", fg="#849389",
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))
        for token in ("Sweet", "Spicy", "Japanese", "Italian", "Fresh", "Comfort"):
            self._quick_chip(moods, self.online_moods, token)
        row2 = ttk.Frame(self.online_tab)
        row2.pack(fill="x")
        self.online_diet = self._choice(row2, "Diet", ["none", "vegan", "vegetarian", "pescatarian", "dairy-free", "gluten-free"], self.agent.profile.diet)
        self.online_allergies = self._entry(row2, "Allergies to exclude", ", ".join(sorted(self.agent.profile.allergies)))
        self.online_count = self._entry(row2, "Meals", "3", width=8)
        self.online_leftovers = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Double for leftovers", variable=self.online_leftovers).pack(side="left", pady=(20, 0))
        self._build_pantry_builder(self.online_tab, "online")
        ttk.Button(self.online_tab, text="Search and build my plan", style="Accent.TButton",
                   command=self._online_search).pack(anchor="e", pady=(8, 0))

    def _build_builtin_form(self):
        ttk.Label(self.built_in_tab, text="Build a plan from PantryPal’s built-in recipes.").pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(self.built_in_tab)
        row.pack(fill="x")
        profile = self.agent.profile
        self.local_diet = self._choice(row, "Diet", ["none", "vegan", "vegetarian", "pescatarian", "dairy-free", "gluten-free"], profile.diet)
        self.local_meals = self._entry(row, "Meals", "3", width=8)
        self.local_servings = self._entry(row, "Servings per meal", "2", width=8)
        self.local_time = self._entry(row, "Max cooking minutes", "40", width=8)
        row2 = ttk.Frame(self.built_in_tab)
        row2.pack(fill="x")
        self.local_budget = self._entry(row2, "Estimated grocery budget ($)", "30", width=12)
        self.local_protein = self._entry(row2, "Minimum protein per serving (g)", "0", width=12)
        self.local_allergies = self._entry(row2, "Allergies", ", ".join(sorted(profile.allergies)))
        row3 = ttk.Frame(self.built_in_tab)
        row3.pack(fill="x")
        self.local_dislikes = self._entry(row3, "Ingredients to avoid", ", ".join(sorted(profile.dislikes)))
        quick = tk.Frame(self.built_in_tab, bg="#151b17")
        quick.pack(fill="x", pady=(1, 2))
        tk.Label(quick, text="QUICK AVOID", bg="#151b17", fg="#849389",
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))
        for token in ("Mushrooms", "Onion", "Peanuts", "Cilantro"):
            self._quick_chip(quick, self.local_dislikes, token)
        self._build_pantry_builder(self.built_in_tab, "local")
        self.local_leftovers = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.built_in_tab, text="Double recipes for leftovers", variable=self.local_leftovers).pack(anchor="w", pady=(5, 0))
        ttk.Button(self.built_in_tab, text="Build my meal plan", style="Accent.TButton",
                   command=self._builtin_plan).pack(anchor="e", pady=(6, 0))

    def _write(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            tag = None
            if stripped and stripped.upper() == stripped and any(letter.isalpha() for letter in stripped):
                tag = "section"
            elif stripped[:1].isdigit() and ". " in stripped[:4]:
                tag = "meal"
            elif stripped.startswith("Source:") or stripped.startswith("   Source:"):
                tag = "muted"
            elif stripped.startswith("Labels:") or stripped.startswith("   Labels:"):
                tag = "accent"
            self.output.insert("end", line, tag or "body")
        self.output.configure(state="disabled")
        self.output.see("1.0")

    def _clear(self):
        self.status_var.set("READY")
        self._write("Choose a planner above to get started. Your results will appear here.")
        for child in self.feedback.winfo_children():
            child.destroy()

    def _busy(self, message):
        self.status_var.set("WORKING…")
        self._write(message)
        for child in self.feedback.winfo_children():
            child.destroy()

    def _run_async(self, work):
        self._busy("Working on your plan…")
        def runner():
            try:
                result = work()
                self.root.after(0, lambda: result())
            except Exception as exc:
                self.root.after(0, lambda error=exc: self._show_error(error))
        threading.Thread(target=runner, daemon=True).start()

    def _show_error(self, error):
        self.status_var.set("CHECK INPUT")
        messagebox.showerror("PantryPal", str(error), parent=self.root)

    @staticmethod
    def _list(text):
        return {item.strip().lower() for item in text.split(",") if item.strip()}

    def _online_search(self):
        queries = [item.strip() for item in self.online_queries.get().split(",") if item.strip()][:3]
        moods = [item.strip() for item in self.online_moods.get().split(",") if item.strip()]
        if not queries and not moods:
            messagebox.showinfo("Add a search", "Enter a dish, ingredient, food mood, or cuisine first.", parent=self.root)
            return
        try:
            pantry = parse_inventory(self.online_pantry.get())
            count = int(self.online_count.get())
            if not 1 <= count <= 7:
                raise ValueError("Choose between 1 and 7 meals.")
        except ValueError as exc:
            messagebox.showerror("Check your entries", str(exc), parent=self.root)
            return
        diet = self.online_diet.get()
        allergies = self._list(self.online_allergies.get())
        leftovers = self.online_leftovers.get()
        def work():
            meals = search_many(queries, pantry, diet, allergies, moods)
            if not meals:
                return lambda: self._show_empty("No recipes matched those search terms and filters. Try another dish, mood, or cuisine.")
            actual_count = min(count, len(meals))
            plan = make_online_plan(meals, actual_count, pantry, leftovers)
            return lambda: self._show_online(plan, meals, pantry, leftovers, moods, diet, allergies)
        self._run_async(work)

    def _show_empty(self, message):
        self.status_var.set("NO MATCHES")
        self._write(message)

    def _show_online(self, plan, candidates, pantry, leftovers, moods, diet, allergies):
        multiplier = 2 if leftovers else 1
        lines = ["YOUR ONLINE MEAL PLAN", "Food mood filters: " + (", ".join(moods) or "none"), ""]
        for index, meal in enumerate(plan, 1):
            labels = food_labels(meal["name"], [item["name"] for item in meal["ingredients"]], meal["category"], meal["area"])
            lines += [f"{index}. {meal['name']} — {meal['area']} / {meal['category']}", f"   Labels: {', '.join(labels)}", "   Ingredients:"]
            lines += [f"   • {item['amount'] * multiplier:g} {item['unit']} {item['name']}" for item in meal["ingredients"]]
            lines.append("   Instructions:")
            lines += [f"   {step_no}. {step}" for step_no, step in enumerate(meal["steps"], 1)]
            lines.append(f"   Source: {meal['url']}\n")
        totals = {}
        for meal in plan:
            for item in meal["ingredients"]:
                key = (item["canonical"], item["unit"])
                totals[key] = totals.get(key, 0) + item["amount"] * multiplier
        shopping = [(key, max(0, amount - pantry.get(key, 0))) for key, amount in totals.items()]
        shopping = [(key, amount) for key, amount in shopping if amount > 0]
        lines.append("COMBINED GROCERY LIST (after pantry stock)")
        lines.extend("• " + purchase_line(name, amount, unit) for (name, unit), amount in sorted(shopping))
        if not shopping:
            lines.append("Nothing to buy from the listed quantities.")
        swaps = suggest_substitutions(shopping, pantry, diet, allergies)
        if swaps:
            lines.append("\nOPTIONAL SUBSTITUTIONS USING ITEMS IN YOUR PANTRY")
            lines.extend(f"• Try {available} in place of {missing}." for missing, available in swaps)
        ids = {meal["id"] for meal in plan}
        alternatives = [meal for meal in candidates if meal["id"] not in ids]
        lines.append("\nRELATED RECIPE VARIANTS")
        variant_count = 0
        from recipe_planner import related_variants
        for meal in plan:
            variants = related_variants(meal, alternatives)
            if variants:
                variant_count += len(variants)
                lines.append(f"Instead of {meal['name']}:")
                lines.extend(f"• {variant['name']} — {variant['url']}" for variant in variants)
        if not variant_count:
            lines.append("No close variants were found in the current search results.")
        self.status_var.set("PLAN READY")
        self._write("\n".join(lines))
        self._feedback_buttons(plan, online=True)

    def _builtin_plan(self):
        try:
            meals = int(self.local_meals.get())
            servings = int(self.local_servings.get())
            max_minutes = int(self.local_time.get())
            budget = float(self.local_budget.get())
            min_protein = int(self.local_protein.get())
            if not 1 <= meals <= 7 or not 1 <= servings <= 12 or not 5 <= max_minutes <= 180 or budget <= 0 or min_protein < 0:
                raise ValueError("Check meal count (1–7), servings (1–12), cooking time (5–180), budget, and protein target.")
            pantry = parse_inventory(self.local_pantry.get())
        except ValueError as exc:
            messagebox.showerror("Check your entries", str(exc), parent=self.root)
            return
        profile = self.agent.profile
        diet = self.local_diet.get()
        allergies = self._list(self.local_allergies.get())
        dislikes = self._list(self.local_dislikes.get())
        leftovers = self.local_leftovers.get()
        self.agent.profile = core.UserProfile(diet, frozenset(allergies), frozenset(dislikes), profile.liked, profile.avoided)
        request = core.Request(meals, servings, max_minutes, budget, min_protein, pantry, leftovers)
        def work():
            plan, candidates = self.agent.plan(request)
            return lambda: self._show_builtin(plan, candidates, request)
        self._run_async(work)

    def _show_builtin(self, plan, candidates, request):
        if not plan:
            self.status_var.set("NO PLAN")
            self._write(f"I couldn't build a plan that meets all the limits.\n\nFeasible recipes: {len(candidates)}; meals requested: {request.meals}.\nTry increasing the budget or cooking time, lowering the protein target, or requesting fewer meals.")
            return
        lines = ["YOUR MEAL PLAN"]
        for index, recipe in enumerate(plan, 1):
            labels = food_labels(recipe.name, list(recipe.ingredients), extra=tuple(sorted(recipe.tags)))
            lines += [f"\n{index}. {recipe.name}", f"   Labels: {', '.join(labels)}", f"   Time: {recipe.minutes} minutes | Protein: {recipe.protein} g per serving | Estimated cost: ${recipe.cost * request.servings * (2 if request.double_for_leftovers else 1):.2f}", "   Ingredients:"]
            multiplier = request.servings * (2 if request.double_for_leftovers else 1)
            lines += [f"   • {amount * multiplier:g} {unit} {name}" for name, (amount, unit) in recipe.ingredients.items()]
            lines.append("   Instructions:")
            lines += [f"   {step_no}. {step}" for step_no, step in enumerate(recipe.instructions, 1)]
        lines.append(f"\nEstimated total: ${sum(r.cost for r in plan) * request.servings * (2 if request.double_for_leftovers else 1):.2f} of ${request.budget:.2f}")
        shopping = core.grocery_list(plan, request)
        lines.append("\nCOMBINED GROCERY LIST (after using your pantry)")
        lines.extend("• " + purchase_line(name, amount, unit) for (name, unit), (amount, _unit) in sorted(shopping.items()))
        if not shopping:
            lines.append("Nothing to buy from the listed quantities.")
        lines.append("\nRELATED RECIPE VARIANTS")
        planned_ids = {recipe.id for recipe in plan}
        variant_count = 0
        for recipe in plan:
            source = {canonical_ingredient(item) for item in recipe.ingredients}
            ranked = []
            for other in candidates:
                if other.id in planned_ids:
                    continue
                other_ingredients = {canonical_ingredient(item) for item in other.ingredients}
                overlap = len(source & other_ingredients) / max(len(source | other_ingredients), 1)
                if overlap >= .2:
                    ranked.append((overlap, other))
            if ranked:
                ranked.sort(key=lambda pair: pair[0], reverse=True)
                lines.append(f"Instead of {recipe.name}:")
                for _, other in ranked[:2]:
                    lines.append(f"• {other.name}")
                    variant_count += 1
        if not variant_count:
            lines.append("No close variants were found in the built-in catalog.")
        self.agent.save_memory()
        self.status_var.set("PLAN READY")
        self._write("\n".join(lines))
        self._feedback_buttons(plan, online=False)

    def _feedback_buttons(self, plan, online):
        for child in self.feedback.winfo_children():
            child.destroy()
        if not plan:
            return
        ttk.Label(self.feedback, text="How did you like these recommendations?", background="#151b17", foreground="#aeb9b1").pack(side="left", padx=(0, 10))
        ttk.Button(self.feedback, text="Like", style="Accent.TButton", command=lambda: self._save_feedback(plan, True, online)).pack(side="left", padx=3)
        ttk.Button(self.feedback, text="Dislike", command=lambda: self._save_feedback(plan, False, online)).pack(side="left", padx=3)
        ttk.Button(self.feedback, text="Skip", command=lambda: self._clear_feedback()).pack(side="left", padx=3)

    def _save_feedback(self, plan, liked, online):
        if online:
            saved_likes, saved_avoided = load_online_feedback()
            for recipe in plan:
                target, other = (saved_likes, saved_avoided) if liked else (saved_avoided, saved_likes)
                target.add(recipe["id"])
                other.discard(recipe["id"])
            try:
                save_online_feedback(saved_likes, saved_avoided)
            except OSError as exc:
                messagebox.showerror("Could not save feedback", str(exc), parent=self.root)
                return
        else:
            target = self.agent.profile.liked if liked else self.agent.profile.avoided
            other = self.agent.profile.avoided if liked else self.agent.profile.liked
            for recipe in plan:
                recipe_id = recipe.id
                if recipe_id not in target:
                    target.append(recipe_id)
                if recipe_id in other:
                    other.remove(recipe_id)
            self.agent.save_memory()
        self._clear_feedback()
        self._write(self.output.get("1.0", "end-1c") + "\n\nFeedback saved. PantryPal will use it to rank future recommendations.")

    def _clear_feedback(self):
        for child in self.feedback.winfo_children():
            child.destroy()


def launch_ui():
    root = tk.Tk()
    PantryPalUI(root)
    root.mainloop()
