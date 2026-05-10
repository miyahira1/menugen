#!/usr/bin/env python3
"""AI-assisted cookbook CLI — recipes live in Markdown, rendered in Obsidian."""

import os
import re
import sys
import json
from datetime import date
from pathlib import Path

import click
import frontmatter
import anthropic
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

REPO_ROOT = Path(__file__).parent
RECIPES_DIR = REPO_ROOT / "recipes"
CATEGORIES = ["breakfast", "lunch", "dinner", "desserts", "snacks", "sides"]
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]Error:[/] ANTHROPIC_API_KEY is not set.")
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def recipe_path(title: str, category: str) -> Path:
    return RECIPES_DIR / category / f"{slug(title)}.md"


def all_recipes() -> list[dict]:
    results = []
    for md_file in sorted(RECIPES_DIR.rglob("*.md")):
        try:
            post = frontmatter.load(md_file)
            results.append({"path": md_file, "meta": post.metadata, "body": post.content})
        except Exception:
            pass
    return results


def find_recipe(name: str) -> tuple[Path, frontmatter.Post] | None:
    target = slug(name)
    for md_file in RECIPES_DIR.rglob("*.md"):
        if slug(md_file.stem) == target or target in slug(md_file.stem):
            post = frontmatter.load(md_file)
            return md_file, post
    return None


def save_recipe(path: Path, post: frontmatter.Post) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(frontmatter.dumps(post))


SYSTEM_PROMPT = """You are a professional chef and recipe writer. You write clear,
delicious recipes scaled for exactly 4 portions. Your recipes include precise
quantities, timings, and practical tips. You format everything in clean Markdown
with YAML frontmatter. Never add commentary outside the requested format."""


def call_claude(client: anthropic.Anthropic, user_prompt: str, *, cache: bool = True) -> str:
    messages = [{"role": "user", "content": user_prompt}]
    system = [{"type": "text", "text": SYSTEM_PROMPT}]
    if cache:
        system[0]["cache_control"] = {"type": "ephemeral"}

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system,
        messages=messages,
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """AI-assisted cookbook. Recipes are stored as Markdown files for Obsidian."""


@cli.command()
@click.option("--title", prompt="Recipe name", help="Name of the dish")
@click.option("--category", type=click.Choice(CATEGORIES), prompt="Category", default="dinner", show_default=True)
@click.option("--description", prompt="Brief description or idea (ingredients, cuisine, style…)", default="", show_default=False)
def new(title: str, category: str, description: str):
    """Generate a new recipe with AI."""
    path = recipe_path(title, category)
    if path.exists():
        console.print(f"[yellow]Recipe already exists:[/] {path.relative_to(REPO_ROOT)}")
        if not click.confirm("Overwrite?"):
            return

    console.print(f"[cyan]Generating recipe for[/] [bold]{title}[/]…")
    client = get_client()

    prompt = f"""Create a complete recipe for "{title}" ({category}).
{f'Additional notes: {description}' if description else ''}

Return ONLY the Markdown document with this exact structure:

---
title: "{title}"
category: {category}
tags: [tag1, tag2, tag3]
servings: 4
prep_time: "X mins"
cook_time: "X mins"
difficulty: easy|medium|hard
rating: null
last_cooked: null
times_cooked: 0
source: "AI generated"
---

# {title}

> One-sentence description.

## Ingredients

- precise quantity + ingredient (for 4 portions)

## Instructions

1. Numbered steps with timings and temperatures.

## Chef's Tips

- Practical tips and variations.

## Notes

*Space for personal notes after cooking.*

## Iterations

| Date | Rating | Changes Made |
|------|--------|--------------|
|      |        |              |
"""

    raw = call_claude(client, prompt)

    # Strip any markdown code fences Claude might add
    raw = re.sub(r"^```(?:markdown)?\n?", "", raw).rstrip("`").strip()

    post = frontmatter.loads(raw)
    save_recipe(path, post)
    console.print(f"[green]Saved:[/] {path.relative_to(REPO_ROOT)}")
    console.print(Markdown(post.content))


@cli.command()
@click.argument("ingredients")
@click.option("--category", type=click.Choice(CATEGORIES), default="dinner", show_default=True)
@click.option("--style", default="", help="Cuisine style, e.g. 'Italian', 'quick weeknight'")
def from_ingredients(ingredients: str, category: str, style: str):
    """Generate a recipe from a list of INGREDIENTS you have on hand.

    Example: cookbook.py from-ingredients "chicken, lemon, garlic, thyme"
    """
    client = get_client()
    console.print(f"[cyan]Creating recipe from:[/] {ingredients}")

    prompt = f"""I have these ingredients: {ingredients}.
{'Cuisine/style preference: ' + style if style else ''}
Suggest ONE recipe for 4 portions that uses most of them. Invent a short catchy name.

Return ONLY the Markdown document using this structure:

---
title: "INVENTED_TITLE"
category: {category}
tags: [tag1, tag2]
servings: 4
prep_time: "X mins"
cook_time: "X mins"
difficulty: easy|medium|hard
rating: null
last_cooked: null
times_cooked: 0
source: "AI generated"
---

# INVENTED_TITLE

> One-sentence description.

## Ingredients

- precise quantity + ingredient (4 portions)

## Instructions

1. Steps with timings.

## Chef's Tips

- Tips and substitutions.

## Notes

*Add your notes after cooking.*

## Iterations

| Date | Rating | Changes Made |
|------|--------|--------------|
|      |        |              |
"""

    raw = call_claude(client, prompt)
    raw = re.sub(r"^```(?:markdown)?\n?", "", raw).rstrip("`").strip()
    post = frontmatter.loads(raw)

    title = post.metadata.get("title", "untitled")
    path = recipe_path(title, category)
    save_recipe(path, post)
    console.print(f"[green]Saved:[/] {path.relative_to(REPO_ROOT)}")
    console.print(Markdown(post.content))


@cli.command("list")
@click.option("--category", type=click.Choice(CATEGORIES + ["all"]), default="all")
@click.option("--min-rating", type=float, default=0.0, help="Show only recipes with rating ≥ this value")
def list_recipes(category: str, min_rating: float):
    """List all saved recipes."""
    recipes = all_recipes()
    if category != "all":
        recipes = [r for r in recipes if r["meta"].get("category") == category]
    if min_rating > 0:
        recipes = [r for r in recipes if (r["meta"].get("rating") or 0) >= min_rating]

    if not recipes:
        console.print("[yellow]No recipes found.[/]")
        return

    table = Table(title="My Cookbook", show_lines=True)
    table.add_column("Title", style="bold")
    table.add_column("Category")
    table.add_column("Difficulty")
    table.add_column("Prep + Cook")
    table.add_column("Rating")
    table.add_column("Cooked")

    for r in recipes:
        m = r["meta"]
        rating_str = f"{'★' * int(m.get('rating') or 0)}" if m.get("rating") else "-"
        prep = m.get("prep_time", "?")
        cook = m.get("cook_time", "?")
        table.add_row(
            m.get("title", r["path"].stem),
            m.get("category", "-"),
            m.get("difficulty", "-"),
            f"{prep} + {cook}",
            rating_str,
            str(m.get("times_cooked", 0)),
        )

    console.print(table)


@cli.command()
@click.argument("name")
def show(name: str):
    """Show a recipe by name."""
    result = find_recipe(name)
    if not result:
        console.print(f"[red]Recipe not found:[/] {name}")
        return
    path, post = result
    console.print(Panel(Markdown(post.content), title=post.metadata.get("title", name)))


@cli.command()
@click.argument("name")
@click.option("--rating", type=click.FloatRange(1, 5), prompt="Rating (1–5)", help="How did it taste?")
@click.option("--notes", prompt="What did you change or notice?", default="", show_default=False)
def cook(name: str, rating: float, notes: str):
    """Log a cooking session — update rating and add iteration notes."""
    result = find_recipe(name)
    if not result:
        console.print(f"[red]Recipe not found:[/] {name}")
        return
    path, post = result

    today = date.today().isoformat()
    post.metadata["last_cooked"] = today
    post.metadata["rating"] = rating
    post.metadata["times_cooked"] = int(post.metadata.get("times_cooked", 0)) + 1

    # Append row to the Iterations table in the body
    iteration_row = f"| {today} | {'★' * int(rating)} ({rating}) | {notes or '—'} |"
    if "## Iterations" in post.content:
        post.content = post.content.replace(
            "| Date | Rating | Changes Made |\n|------|--------|--------------|",
            f"| Date | Rating | Changes Made |\n|------|--------|--------------|",
        )
        # Insert before the first empty table row
        post.content = re.sub(
            r"(\| Date \| Rating \| Changes Made \|\n\|[-|]+\|)\n\|[  ]*\|[  ]*\|[  ]*\|",
            f"\\1\n{iteration_row}",
            post.content,
        )
    else:
        post.content += f"\n\n## Iterations\n\n| Date | Rating | Changes Made |\n|------|--------|--------------||\n{iteration_row}\n"

    save_recipe(path, post)
    console.print(f"[green]Updated:[/] {path.relative_to(REPO_ROOT)} — cooked {post.metadata['times_cooked']}× — rated {rating}/5")


@cli.command()
@click.argument("name")
def improve(name: str):
    """Ask Claude to suggest improvements for a recipe."""
    result = find_recipe(name)
    if not result:
        console.print(f"[red]Recipe not found:[/] {name}")
        return
    path, post = result

    client = get_client()
    meta = post.metadata
    console.print(f"[cyan]Analysing[/] [bold]{meta.get('title', name)}[/]…")

    prompt = f"""Here is one of my recipes. I've cooked it {meta.get('times_cooked', 0)} time(s) with a rating of {meta.get('rating', 'not yet rated')}/5.

{frontmatter.dumps(post)}

Please suggest 3–5 concrete improvements to make this recipe better. Focus on:
- Flavour development
- Technique refinements
- Ingredient substitutions or additions
- Presentation tips

Format as a numbered Markdown list. Be specific and actionable."""

    suggestions = call_claude(client, prompt)
    console.print(Panel(Markdown(suggestions), title=f"Improvement suggestions for {meta.get('title', name)}"))

    if click.confirm("Save these suggestions to the recipe's Notes section?"):
        note_block = f"\n\n### AI Suggestions ({date.today().isoformat()})\n\n{suggestions}"
        if "## Notes" in post.content:
            post.content = post.content.replace("## Notes\n\n*Add your notes after cooking.*", f"## Notes\n\n*Add your notes after cooking.*{note_block}")
        else:
            post.content += f"\n\n## Notes{note_block}"
        save_recipe(path, post)
        console.print("[green]Saved suggestions to recipe.[/]")


@cli.command()
@click.argument("name")
@click.option("--servings", type=int, prompt="Scale to how many servings?", default=2)
def scale(name: str, servings: int):
    """Show a recipe scaled to a different number of servings."""
    result = find_recipe(name)
    if not result:
        console.print(f"[red]Recipe not found:[/] {name}")
        return
    path, post = result

    client = get_client()
    original_servings = post.metadata.get("servings", 4)
    console.print(f"[cyan]Scaling from {original_servings} to {servings} servings…[/]")

    prompt = f"""Here is a recipe written for {original_servings} servings:

{frontmatter.dumps(post)}

Rewrite ONLY the Ingredients section scaled to exactly {servings} servings.
Keep all quantities precise (round to sensible fractions like ½, ¼, etc.).
Return ONLY the scaled ingredients as a Markdown list, nothing else."""

    scaled = call_claude(client, prompt)
    title = post.metadata.get("title", name)
    console.print(Panel(Markdown(f"## Ingredients ({servings} servings)\n\n{scaled}"), title=f"{title} — scaled to {servings}"))


@cli.command()
def favourites():
    """Show your top-rated recipes (rating ≥ 4)."""
    recipes = [r for r in all_recipes() if (r["meta"].get("rating") or 0) >= 4]
    recipes.sort(key=lambda r: r["meta"].get("rating", 0), reverse=True)

    if not recipes:
        console.print("[yellow]No recipes rated 4 or above yet. Get cooking![/]")
        return

    table = Table(title="Favourites ★★★★+", show_lines=True)
    table.add_column("Title", style="bold")
    table.add_column("Category")
    table.add_column("Rating")
    table.add_column("Cooked")
    table.add_column("Last Cooked")

    for r in recipes:
        m = r["meta"]
        rating = m.get("rating", 0)
        table.add_row(
            m.get("title", r["path"].stem),
            m.get("category", "-"),
            f"{'★' * int(rating)} ({rating})",
            str(m.get("times_cooked", 0)),
            str(m.get("last_cooked", "-")),
        )

    console.print(table)


if __name__ == "__main__":
    cli()
