# Menugen — AI-Assisted Cookbook

## What this is

A personal cookbook where recipes are stored as Markdown files (YAML frontmatter + Markdown body) for rendering in Obsidian. A Python CLI (`cookbook.py`) uses the Claude API to generate, improve, and manage recipes. All recipes are scaled to **4 portions** by default.

## Repository structure

```
menugen/
├── cookbook.py              # Main CLI — all commands live here
├── requirements.txt
├── CLAUDE.md
├── _templates/
│   └── recipe_template.md   # Blank template for manual recipes
└── recipes/
    ├── breakfast/
    ├── lunch/
    ├── dinner/
    ├── desserts/
    ├── snacks/
    └── sides/
```

## Recipe file format

Each recipe is a `.md` file with YAML frontmatter:

```yaml
---
title: "Recipe Name"
category: dinner          # breakfast | lunch | dinner | desserts | snacks | sides
tags: [italian, quick]
servings: 4               # always 4 (use `scale` command to adjust)
prep_time: "15 mins"
cook_time: "30 mins"
difficulty: medium        # easy | medium | hard
rating: null              # updated by `cook` command (1–5)
last_cooked: null         # ISO date, updated by `cook` command
times_cooked: 0           # incremented by `cook` command
source: "AI generated"
---
```

The Markdown body follows this section order:
1. One-line description blockquote
2. `## Ingredients` — quantities for 4 portions
3. `## Instructions` — numbered steps with timings/temps
4. `## Chef's Tips`
5. `## Notes` — personal notes
6. `## Iterations` — table updated by `cook` command

## CLI usage

```bash
# Install deps
pip install -r requirements.txt

# Set your API key
export ANTHROPIC_API_KEY=sk-...

# Generate a new recipe interactively
python cookbook.py new

# Generate from ingredients on hand
python cookbook.py from-ingredients "chicken, lemon, garlic, thyme"

# List all recipes (or filter)
python cookbook.py list
python cookbook.py list --category dinner --min-rating 4

# Show a recipe
python cookbook.py show "cacio e pepe"

# Log a cooking session (updates rating + iterations table)
python cookbook.py cook "shakshuka"

# Ask Claude for improvement suggestions
python cookbook.py improve "lemon garlic roast chicken"

# Scale ingredients to a different serving count
python cookbook.py scale "chocolate fondant" --servings 8

# Show favourites (rating ≥ 4)
python cookbook.py favourites
```

## Development conventions

- **No new files** for one-off features — extend `cookbook.py` with new `@cli.command()` blocks.
- Recipes are always 4 portions. The `scale` command is read-only (display only, never overwrites the file).
- The `cook` command is the only command that writes to an existing recipe's frontmatter.
- `improve` writes to the recipe only if the user explicitly confirms.
- Claude model: `claude-sonnet-4-6`. Use `SYSTEM_PROMPT` with `cache_control: ephemeral` on the system block for prompt caching.
- Rich console for all output — no bare `print()` calls.
- Slug filenames: lowercase, hyphens, no special chars (via `slug()` helper).

## Obsidian setup

Open the repo root as an Obsidian vault. Recommended plugins:
- **Dataview** — query recipes by rating, category, tags (the YAML frontmatter is queryable)
- **Templater** — use `_templates/recipe_template.md` for manual recipe creation

Example Dataview query (paste into any note):
```dataview
TABLE rating, difficulty, last_cooked
FROM "recipes"
WHERE rating >= 4
SORT rating DESC
```
