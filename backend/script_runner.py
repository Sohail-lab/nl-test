#!/usr/bin/env python3
"""
Playwright Script Runner with AI Self-Healing Locators

Runs generated .spec.js Playwright test scripts using Python Playwright.
When a locator fails (element not found), it automatically:
  1. Captures the current page DOM
  2. Sends the step description + DOM to the AI (LLM) for a new locator
  3. Retries the action with the healed locator
  4. Updates the .spec.js file in-place with the new locator
  5. Logs the healing event to heal_log.json

Usage:
    python script_runner.py <path_to_spec.js>       # Run a specific script
    python script_runner.py                           # Run the latest script in playwright_script/
"""

import sys
import os
import re
import json
import glob
import time
from datetime import datetime

# Add backend dir to path so we can import from worker
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from worker import (
    get_locator_from_ai,
    get_page_dom_simple,
    extract_data_testid_summary,
    wait_for_loader,
    bring_window_to_front,
)

SCRIPT_DIR = os.path.join(BACKEND_DIR, "playwright_script")
HEAL_LOG_FILE = os.path.join(SCRIPT_DIR, "heal_log.json")


# ─── Spec File Parser ──────────────────────────────────────────────────────────

def parse_spec_file(file_path):
    """
    Parse a .spec.js file and extract the goto URL and action list.

    Supports both old single-quote format and new backtick format:
        Old:  await page.click('xpath=//input[@id=\\'username\\']');
        New:  await page.click(`xpath=//input[@id='username']`);

    Returns:
        (goto_url, actions)  where each action is a dict with:
            - line_index:     0-based index in the raw lines list
            - comment:        the // comment above the action (step description)
            - raw_line:       full original line from the file
            - action_type:    click | fill | selectOption | press | hover | dblclick | goto | ...
            - locator:        the selector string
            - value:          second argument (for fill/press/selectOption) or None
    """
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    goto_url = None
    actions = []
    pending_comment = None

    # Regex to pull the string content from either 'xxx' or `xxx`
    # We capture the delimiter to know which format we're in
    STR_PAT = r"""(?:'((?:[^'\\]|\\.)*)'|`((?:[^`\\]|\\.)*)`)"""

    for idx, raw_line in enumerate(lines):
        stripped = raw_line.strip()

        # Capture comments as step descriptions
        if stripped.startswith("//"):
            pending_comment = stripped.lstrip("/").strip()
            continue

        # ── page.goto ──
        m = re.search(r'await\s+page\.goto\(' + STR_PAT + r'\)', stripped)
        if m:
            goto_url = m.group(1) if m.group(1) is not None else m.group(2)
            pending_comment = None
            continue

        # ── page.click / page.dblclick / page.hover ──
        for action_name in ("click", "dblclick", "hover"):
            m = re.search(
                r'await\s+page\.' + action_name + r'\(' + STR_PAT + r'(?:\s*,\s*\{[^}]*\})?\s*\)',
                stripped,
            )
            if m:
                locator = m.group(1) if m.group(1) is not None else m.group(2)
                actions.append(_action(idx, pending_comment, raw_line, action_name, locator))
                pending_comment = None
                break
        else:
            # ── page.fill / page.selectOption / page.press  (two-arg) ──
            for action_name in ("fill", "selectOption", "press"):
                m = re.search(
                    r'await\s+page\.' + action_name + r'\(' + STR_PAT + r'\s*,\s*' + STR_PAT + r'\s*\)',
                    stripped,
                )
                if m:
                    locator = m.group(1) if m.group(1) is not None else m.group(2)
                    value   = m.group(3) if m.group(3) is not None else m.group(4)
                    actions.append(_action(idx, pending_comment, raw_line, action_name, locator, value))
                    pending_comment = None
                    break
            else:
                # ── page.dragAndDrop ──
                m = re.search(
                    r'await\s+page\.dragAndDrop\(' + STR_PAT + r'\s*,\s*' + STR_PAT + r'\s*\)',
                    stripped,
                )
                if m:
                    locator = m.group(1) if m.group(1) is not None else m.group(2)
                    value   = m.group(3) if m.group(3) is not None else m.group(4)
                    actions.append(_action(idx, pending_comment, raw_line, "dragAndDrop", locator, value))
                    pending_comment = None
                    continue

                # ── page.locator(...).scrollIntoViewIfNeeded() ──
                m = re.search(
                    r'await\s+page\.locator\(' + STR_PAT + r'\)\.scrollIntoViewIfNeeded\(\)',
                    stripped,
                )
                if m:
                    locator = m.group(1) if m.group(1) is not None else m.group(2)
                    actions.append(_action(idx, pending_comment, raw_line, "scroll", locator))
                    pending_comment = None
                    continue

                # ── expect(...).toContainText(...) ──
                m = re.search(
                    r'await\s+expect\(page\.locator\(' + STR_PAT + r'\)\)\.toContainText\(' + STR_PAT + r'\)',
                    stripped,
                )
                if m:
                    locator = m.group(1) if m.group(1) is not None else m.group(2)
                    value   = m.group(3) if m.group(3) is not None else m.group(4)
                    actions.append(_action(idx, pending_comment, raw_line, "validate", locator, value))
                    pending_comment = None
                    continue

    return goto_url, actions, lines


def _action(line_index, comment, raw_line, action_type, locator, value=None):
    return {
        "line_index": line_index,
        "comment": comment,
        "raw_line": raw_line,
        "action_type": action_type,
        "locator": locator,
        "value": value,
    }


# ─── Action Execution ──────────────────────────────────────────────────────────

def execute_action(page, action_type, locator, value=None, timeout=8000):
    """Execute a single Playwright action. Raises on failure."""
    if action_type == "click":
        page.click(locator, timeout=timeout)
    elif action_type == "dblclick":
        page.dblclick(locator, timeout=timeout)
    elif action_type == "hover":
        page.hover(locator, timeout=timeout)
    elif action_type == "fill":
        page.fill(locator, value or "", timeout=timeout)
    elif action_type == "selectOption":
        page.select_option(locator, value or "", timeout=timeout)
    elif action_type == "press":
        page.press(locator, value or "Enter", timeout=timeout)
    elif action_type == "scroll":
        page.locator(locator).scroll_into_view_if_needed(timeout=timeout)
    elif action_type == "dragAndDrop":
        page.drag_and_drop(locator, value, timeout=timeout)
    elif action_type == "validate":
        text = page.locator(locator).text_content(timeout=timeout)
        if value and value.lower() not in (text or "").lower():
            raise AssertionError(f"Expected text '{value}' not found in element")
    else:
        print(f"  ⚠  Unknown action type: {action_type}")


# ─── AI Self-Healing ───────────────────────────────────────────────────────────

def heal_locator(page, step_description, old_locator):
    """
    Ask the AI for a new locator when the old one can't find the element.

    Returns the new formatted locator string (e.g. 'xpath=//...' or CSS),
    or None if healing failed.
    """
    print(f"  🔧 HEALING: old locator = {old_locator}")
    print(f"  🔧 Step description: {step_description}")

    try:
        dom = get_page_dom_simple(page)
        testid_summary = extract_data_testid_summary(page)
        dom_with_context = testid_summary + "\n" + dom if testid_summary else dom

        heal_desc = f"{step_description} (previous locator that no longer works: {old_locator})"
        new_locator, locator_type = get_locator_from_ai(dom_with_context, heal_desc)

        if new_locator:
            formatted = f"xpath={new_locator}" if locator_type == "xpath" else new_locator
            print(f"  ✅ HEALED: new locator = {formatted}")
            return formatted
        else:
            print(f"  ❌ HEALING FAILED: AI returned no locator")
            return None
    except Exception as e:
        print(f"  ❌ HEALING ERROR: {str(e)[:120]}")
        return None


def log_healing(spec_path, step_index, comment, old_locator, new_locator):
    """Append a healing event to heal_log.json."""
    log = []
    if os.path.exists(HEAL_LOG_FILE):
        try:
            with open(HEAL_LOG_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        except (json.JSONDecodeError, IOError):
            log = []

    log.append({
        "timestamp": datetime.now().isoformat(),
        "script": os.path.basename(spec_path),
        "step": step_index + 1,
        "description": comment or "",
        "old_locator": old_locator,
        "new_locator": new_locator,
    })

    with open(HEAL_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
    print(f"  📝 Healing logged to {os.path.basename(HEAL_LOG_FILE)}")


def update_spec_file(spec_path, lines, line_index, old_locator, new_locator):
    """
    Replace the old locator with the new one in the .spec.js file in-place.
    Preserves every other line intact.
    """
    original_line = lines[line_index]
    # Escape for regex
    escaped_old = re.escape(old_locator)
    updated_line = re.sub(escaped_old, new_locator, original_line, count=1)

    if updated_line != original_line:
        lines[line_index] = updated_line
        with open(spec_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"  📄 Updated {os.path.basename(spec_path)} line {line_index + 1}")
    else:
        print(f"  ⚠  Could not find old locator in line to replace")


# ─── Main Runner ───────────────────────────────────────────────────────────────

def run_script(spec_path):
    """
    Run a .spec.js Playwright script with AI self-healing locators.
    """
    spec_path = os.path.abspath(spec_path)
    if not os.path.exists(spec_path):
        print(f"❌ File not found: {spec_path}")
        return False

    print(f"\n{'='*70}")
    print(f"  SCRIPT RUNNER — {os.path.basename(spec_path)}")
    print(f"{'='*70}\n")

    # Parse the spec file
    goto_url, actions, lines = parse_spec_file(spec_path)

    if not goto_url:
        print("⚠  No page.goto() found in script. Cannot determine URL.")
        return False

    if not actions:
        print("⚠  No actions found in script.")
        return False

    print(f"  URL:     {goto_url}")
    print(f"  Steps:   {len(actions)}")
    print()

    # Launch browser via Playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright is not installed. Run: pip install playwright && playwright install")
        return False

    passed = 0
    failed = 0
    healed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        bring_window_to_front()

        # Navigate
        print(f"  🌐 Navigating to {goto_url}")
        try:
            page.goto(goto_url, timeout=30000)
            wait_for_loader(page)
            print(f"  ✅ Page loaded\n")
        except Exception as e:
            print(f"  ❌ Navigation failed: {str(e)[:100]}")
            browser.close()
            return False

        # Execute each action
        for i, action in enumerate(actions):
            step_num = i + 1
            desc = action["comment"] or action["action_type"]
            locator = action["locator"]
            value = action["value"]
            a_type = action["action_type"]

            label = f"[{step_num}/{len(actions)}]"
            print(f"  {label} {desc}")
            print(f"         action={a_type}  locator={locator[:80]}{'...' if len(locator) > 80 else ''}")
            if value:
                print(f"         value={value[:60]}{'...' if len(str(value)) > 60 else ''}")

            # Wait for page to be ready
            try:
                wait_for_loader(page)
            except Exception:
                pass

            # Attempt the action
            try:
                execute_action(page, a_type, locator, value)
                print(f"         ✅ PASS\n")
                passed += 1
                time.sleep(0.3)  # small settle delay

            except Exception as original_error:
                error_msg = str(original_error)[:120]
                print(f"         ❌ FAILED: {error_msg}")

                # ── Self-heal ──
                step_description = desc if desc != a_type else f"{a_type} on element"
                new_locator = heal_locator(page, step_description, locator)

                if new_locator:
                    # Retry with healed locator
                    try:
                        execute_action(page, a_type, new_locator, value)
                        print(f"         ✅ HEALED & PASS\n")
                        healed += 1
                        passed += 1

                        # Update the spec file
                        update_spec_file(spec_path, lines, action["line_index"], locator, new_locator)

                        # Log the healing
                        log_healing(spec_path, i, desc, locator, new_locator)

                        time.sleep(0.3)

                    except Exception as retry_error:
                        print(f"         ❌ HEALED LOCATOR ALSO FAILED: {str(retry_error)[:100]}")
                        print(f"         ❌ FAIL\n")
                        failed += 1
                else:
                    print(f"         ❌ FAIL (healing unsuccessful)\n")
                    failed += 1

        # Done
        print(f"\n{'='*70}")
        print(f"  RESULTS")
        print(f"{'='*70}")
        print(f"  ✅ Passed:  {passed}")
        print(f"  ❌ Failed:  {failed}")
        print(f"  🔧 Healed:  {healed}")
        print(f"{'='*70}\n")

        browser.close()

    return failed == 0


# ─── CLI ────────────────────────────────────────────────────────────────────────

def find_latest_spec():
    """Find the most recently modified .spec.js file in the scripts directory."""
    pattern = os.path.join(SCRIPT_DIR, "*.spec.js")
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def main():
    if len(sys.argv) > 1:
        spec_path = sys.argv[1]
        # Allow relative paths from the scripts dir
        if not os.path.isabs(spec_path):
            candidate = os.path.join(SCRIPT_DIR, spec_path)
            if os.path.exists(candidate):
                spec_path = candidate
    else:
        spec_path = find_latest_spec()
        if not spec_path:
            print("❌ No .spec.js files found in playwright_script/ directory.")
            print("   Usage: python script_runner.py <path_to_spec.js>")
            sys.exit(1)
        print(f"No file specified — running latest: {os.path.basename(spec_path)}")

    success = run_script(spec_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
