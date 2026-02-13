# Compact application patterns for LLM prompts
# Keep this small and focused. Update as the app grows.

PATTERNS = {
    "menu_icon": {
        "summary": "Menu icon / Hamburger",
        "description": (
            "The application menu icon (hamburger/menu) is typically an SVG inside a <button> or a button with a "
            "data-testid='menu-icon'. Activating it opens the main navigation menu."
        ),
        "priority_selectors": [
            # Hardcoded reliable XPath first to prevent LLM failures
            "//*[@data-testid='menu-icon']",
            
            # Fallbacks for older steps or mis-labeled elements
            "//button[@data-testid and contains(translate(@data-testid, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'menu')]",
            "//button[@data-testid and contains(translate(@data-testid, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'hamburger')]",
            "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'menu')]",
            "//button[.//svg][contains(@class, 'hamburger')]",
            "//svg[contains(@class, 'hamburger')]/ancestor::button[1]"
        ],
        "notes": (
            "Always use the data-testid='menu-icon' XPath first. Only use fallback selectors if the main one is not present. "
            "Return a unique XPath matching exactly one element."
        )
    }
}

# Human-readable/LLM-friendly blob (kept small). The worker imports APP_PATTERNS and injects it into prompts.
import json

APP_PATTERNS = (
    "# Application patterns (compact)\n"
    "- PRIORITY: Always use `data-testid='menu-icon'` for menu/hamburger icon.\n"
    "- Attribute priority (highest → lowest): data-testid, id, name, aria-label, placeholder, text, class, position.\n"
    "- Pattern examples follow as JSON for exact matching.\n\n"
    "PATTERN_JSON: " + json.dumps(PATTERNS, indent=2)
)
