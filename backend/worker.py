#!/usr/bin/env python3
import sys
import os
import json
import re
import difflib
import html
import time
import urllib.request
import urllib.error
from datetime import datetime

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Load environment variables from .env file
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars

ENV_VARS = load_env()
SECRET_KEY = ENV_VARS.get('SECRET_KEY', '')
LLM_API_URL = ENV_VARS.get('LLM_API_URL', 'http://192.168.0.63:4000/v1/chat/completions')

def load_app_patterns():
    """Load application-specific patterns for better element finding.

    Priority:
      1. Import `backend.app_patterns.APP_PATTERNS` if available (preferred compact Python module)
      2. Fallback to reading `app-patterns.md` (markdown)
      3. Return empty string if neither available
    """
    # Try import first (compact Python module)
    try:
        # relative import when running as package; absolute fallback
        try:
            from .app_patterns import APP_PATTERNS as patterns
        except Exception:
            from app_patterns import APP_PATTERNS as patterns
        if patterns:
            return patterns
    except Exception:
        pass

    # Fallback: read markdown file if present
    patterns_path = os.path.join(os.path.dirname(__file__), 'app-patterns.md')
    try:
        if os.path.exists(patterns_path):
            with open(patterns_path, 'r', encoding='utf8') as f:
                return f.read()
    except Exception as e:
        print(f"[Patterns] Warning: Could not load patterns file: {e}", file=sys.stderr)

    return ""


APP_PATTERNS = load_app_patterns()

def write_progress(job_id, results, current_step, total_steps, current_description=''):
    """Write progress file so frontend can track execution in real-time"""
    path = os.path.join(UPLOAD_DIR, f"{job_id}.progress.json")
    progress = {
        'jobId': job_id,
        'currentStep': current_step,
        'totalSteps': total_steps,
        'currentDescription': current_description,
        'completedSteps': [r for r in results if r.get('ok') is True],
        'failedSteps': [r for r in results if r.get('ok') is False],
        'completed': current_step >= total_steps
    }
    try:
        with open(path, 'w', encoding='utf8') as f:
            json.dump(progress, f, indent=2)
    except Exception as e:
        print(f"[Progress] Error writing progress: {e}", file=sys.stderr)

def write_result(job_id, result):
    path = os.path.join(UPLOAD_DIR, f"{job_id}.result.json")
    with open(path, 'w', encoding='utf8') as f:
        json.dump(result, f, indent=2)


def append_debug_log(job_id, message):
    """Append diagnostic messages to per-job debug log."""
    path = os.path.join(UPLOAD_DIR, f"{job_id}.debug.log")
    try:
        with open(path, 'a', encoding='utf8') as f:
            f.write(str(message))
            if not str(message).endswith('\n'):
                f.write('\n')
    except Exception as e:
        print(f"[DEBUG] Failed to append debug log: {str(e)[:120]}")

def parse_excel(file_path):
    try:
        import pandas as pd
    except Exception as e:
        raise ImportError('pandas-missing')

    try:
        df = pd.read_excel(file_path, engine='openpyxl', header=None)
    except Exception:
        df = pd.read_excel(file_path, header=None)

    # Parse by COLUMNS (each column is a separate test case)
    test_cases = []
    
    for col_idx, col in enumerate(df.columns):
        col_data = df[col].dropna().astype(str).str.strip()
        
        if len(col_data) == 0:
            continue  # Skip empty columns
        
        # First value is test name, rest are steps
        test_name = col_data.iloc[0]
        steps = col_data.iloc[1:].tolist()
        
        if len(steps) > 0:  # Only add if there are steps
            test_cases.append({
                'test_name': test_name,
                'steps': steps
            })
    
    return test_cases


SIDEBAR_FILLER_WORDS = {
    'click', 'on', 'the', 'a', 'an', 'menu', 'sidebar', 'drawer', 'left', 'right',
    'navigation', 'nav', 'dropdown', 'option', 'item', 'button', 'tab', 'expand',
    'collapse', 'open', 'select', 'choose', 'tap', 'press', 'from', 'in', 'to',
    'of', 'for', 'and', 'then'
}

SIDEBAR_ACTION_PREFIX_RE = re.compile(
    r'^\s*(click|tap|press|open|expand|collapse|select|choose)\s+(on\s+)?',
    flags=re.IGNORECASE
)
SIDEBAR_HINT_RE = re.compile(
    r'\b(sidebar|left\s*menu|drawer|navigation|nav)\b',
    flags=re.IGNORECASE
)
MENU_ICON_RE = re.compile(r'\b(menu\s*icon|hamburger)\b', flags=re.IGNORECASE)

TOKEN_OVERLAP_THRESHOLD = 0.60
FUZZY_MATCH_THRESHOLD = 0.86
FUZZY_MARGIN_THRESHOLD = 0.05
CONTAINS_MATCH_THRESHOLD = 0.60


def _collapse_ws(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _basic_sidebar_text(value):
    return _collapse_ws(html.unescape(value)).lower()


def xpath_literal(value):
    """Return XPath-safe string literal."""
    value = str(value or '')
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


def normalize_sidebar_text(text):
    """Normalize free-form step text or labels for sidebar matching."""
    if not text:
        return ''

    cleaned = html.unescape(str(text))
    cleaned = SIDEBAR_ACTION_PREFIX_RE.sub('', cleaned).strip()
    cleaned = cleaned.strip(' "\'`')
    cleaned = cleaned.replace('&', ' and ')
    cleaned = cleaned.lower()
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', cleaned)
    cleaned = _collapse_ws(cleaned)

    tokens = [t for t in cleaned.split(' ') if t and t not in SIDEBAR_FILLER_WORDS]
    return _collapse_ws(' '.join(tokens))


def extract_sidebar_target(step_text):
    """Extract a sidebar target candidate from free-form click steps."""
    raw_step = _collapse_ws(step_text)
    step_lower = _basic_sidebar_text(raw_step)

    target_text = SIDEBAR_ACTION_PREFIX_RE.sub('', raw_step).strip()
    target_text = re.sub(r'^\s*(the|a|an)\s+', '', target_text, flags=re.IGNORECASE)
    target_text = target_text.strip(' "\'`')

    normalized_target = normalize_sidebar_text(target_text)
    explicit_sidebar = bool(SIDEBAR_HINT_RE.search(step_lower))
    mentions_menu_icon = bool(MENU_ICON_RE.search(step_lower))

    return {
        'raw_step': raw_step,
        'target_text': target_text,
        'normalized_target': normalized_target,
        'is_explicit_sidebar': explicit_sidebar,
        'mentions_menu_icon': mentions_menu_icon,
        'is_sidebar_candidate': bool(normalized_target) and not mentions_menu_icon,
        'target_tokens': [t for t in normalized_target.split(' ') if t],
    }


def _token_overlap_score(a_text, b_text):
    a_tokens = {t for t in normalize_sidebar_text(a_text).split(' ') if t}
    b_tokens = {t for t in normalize_sidebar_text(b_text).split(' ') if t}
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / float(max(len(a_tokens), len(b_tokens)))


def _build_top_candidates(candidates, limit=3):
    out = []
    for item in candidates[:limit]:
        out.append({
            'label': item.get('label_raw', ''),
            'score': round(float(item.get('_score', 0.0)), 4)
        })
    return out


def choose_best_menu_icon(menu_icons):
    """Choose the most reliable menu icon when there are duplicates."""
    if not menu_icons:
        return None

    visible_outside = [m for m in menu_icons if m.get('is_visible') and not m.get('inside_drawer')]
    if visible_outside:
        return visible_outside[0]

    visible_any = [m for m in menu_icons if m.get('is_visible')]
    if visible_any:
        return visible_any[0]

    outside_any = [m for m in menu_icons if not m.get('inside_drawer')]
    if outside_any:
        return outside_any[0]

    return menu_icons[0]


def build_sidebar_click_xpaths(label_raw):
    """Build drawer/overlay-scoped XPath candidates for a sidebar label."""
    label_raw = _collapse_ws(html.unescape(label_raw))
    if not label_raw:
        return []

    label_lit = xpath_literal(label_raw)
    lower_lit = xpath_literal(label_raw.lower())

    norm = normalize_sidebar_text(label_raw)
    safe_partial = norm.split(' and ')[0].strip() if ' and ' in norm else norm
    safe_partial_lit = xpath_literal(safe_partial.lower()) if safe_partial else None

    xpaths = [
        # Primary: strict drawer-scoped aria-label
        f"//*[contains(@class,'IvpLeftMenuDrawer')]//div[@aria-label={label_lit}]/ancestor::div[@role='button'][1]",
        # Fallback: drawer anchored from testDrawer node
        f"//*[@data-testid='testDrawer']/ancestor::*[contains(@class,'IvpLeftMenuDrawer') or contains(@class,'MuiDrawer-root')][1]//div[@aria-label={label_lit}]/ancestor::div[@role='button'][1]",
        # Text fallback in drawer
        f"//*[contains(@class,'IvpLeftMenuDrawer')]//span[normalize-space(text())={label_lit}]/ancestor::div[@role='button'][1]",
        # Case-insensitive aria-label fallback
        f"//*[contains(@class,'IvpLeftMenuDrawer')]//div[contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), {lower_lit})]/ancestor::div[@role='button'][1]",
        # Overlay/popper/menu scoped aria-label
        f"//*[contains(@class,'MuiPopper-root') or contains(@class,'MuiPopover-root') or @role='menu' or @role='listbox']//div[@aria-label={label_lit}]/ancestor::div[@role='button'][1]",
        # Overlay/popper/menu text fallback
        f"//*[contains(@class,'MuiPopper-root') or contains(@class,'MuiPopover-root') or @role='menu' or @role='listbox']//span[normalize-space(text())={label_lit}]/ancestor::div[@role='button'][1]",
        # Overlay/popper/menu case-insensitive aria-label fallback
        f"//*[contains(@class,'MuiPopper-root') or contains(@class,'MuiPopover-root') or @role='menu' or @role='listbox']//div[contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), {lower_lit})]/ancestor::div[@role='button'][1]",
    ]

    if safe_partial and len(safe_partial) >= 3 and safe_partial_lit:
        xpaths.extend([
            f"//*[contains(@class,'IvpLeftMenuDrawer')]//div[contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), {safe_partial_lit})]/ancestor::div[@role='button'][1]",
            f"//*[contains(@class,'IvpLeftMenuDrawer')]//span[contains(translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), {safe_partial_lit})]/ancestor::div[@role='button'][1]",
            f"//*[contains(@class,'MuiPopper-root') or contains(@class,'MuiPopover-root') or @role='menu' or @role='listbox']//div[contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), {safe_partial_lit})]/ancestor::div[@role='button'][1]",
            f"//*[contains(@class,'MuiPopper-root') or contains(@class,'MuiPopover-root') or @role='menu' or @role='listbox']//span[contains(translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), {safe_partial_lit})]/ancestor::div[@role='button'][1]",
        ])

    # Preserve order while removing duplicates.
    seen = set()
    deduped = []
    for xp in xpaths:
        if xp not in seen:
            seen.add(xp)
            deduped.append(xp)
    return deduped


def get_sidebar_state(page):
    """Read sidebar/menu state from the live page."""
    try:
        raw = page.evaluate('''() => {
            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (!style || style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    return false;
                }
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const drawerRoot =
                document.querySelector('.IvpLeftMenuDrawer') ||
                document.querySelector('[class*="IvpLeftMenuDrawer"]') ||
                null;
            const drawerPaper = drawerRoot ? drawerRoot.querySelector('.MuiDrawer-paper') : null;
            const drawerContainer = drawerPaper || drawerRoot;
            const overlayRoots = Array.from(
                document.querySelectorAll('[role="menu"], [role="listbox"], .MuiPopover-root, .MuiPopper-root')
            ).filter(isVisible);

            const allButtons = Array.from(
                document.querySelectorAll('.LeftMenuListItem div[role="button"], li.LeftMenuListItem div[role="button"]')
            );

            const inDrawer = (el) => !!(drawerContainer && drawerContainer.contains(el));
            const inOverlay = (el) => overlayRoots.some(root => root.contains(el));
            const itemButtons = allButtons
                .filter(btn => inDrawer(btn) || inOverlay(btn))
                .filter(isVisible);

            const items = itemButtons.map((btn, index) => {
                const row = btn.closest('.LeftMenuListItem') || btn;
                const labelNode = row.querySelector('[aria-label]') || btn.querySelector('[aria-label]');
                let labelRaw = '';
                if (labelNode) {
                    labelRaw = labelNode.getAttribute('aria-label') || '';
                }
                if (!labelRaw) {
                    const span = row.querySelector('span');
                    if (span) labelRaw = (span.textContent || '').trim();
                }

                const hasExpandIcon = !!row.querySelector(
                    '[data-testid="ExpandMoreIcon"], [data-testid="ExpandLessIcon"], [data-testid*="Expand"]'
                );

                return {
                    index,
                    label_raw: labelRaw,
                    is_visible: isVisible(btn),
                    has_expand_icon: hasExpandIcon,
                    in_overlay: inOverlay(btn)
                };
            });

            const menuIcons = Array.from(document.querySelectorAll('[data-testid="menu-icon"]')).map((el, index) => ({
                index,
                is_visible: isVisible(el),
                inside_drawer: !!(drawerContainer && drawerContainer.contains(el))
            }));

            const search = (drawerContainer || document).querySelector('input[placeholder="Search"]');
            const searchVisible = isVisible(search);
            const visibleItemCount = items.filter(i => i.is_visible).length;
            const visibleOverlayItemCount = items.filter(i => i.is_visible && i.in_overlay).length;

            return {
                drawer_present: !!drawerContainer,
                is_open: (!!drawerContainer && (visibleItemCount > 0 || searchVisible)) || visibleOverlayItemCount > 0,
                visible_item_count: visibleItemCount,
                visible_overlay_item_count: visibleOverlayItemCount,
                search_visible: searchVisible,
                items,
                menu_icons: menuIcons
            };
        }''')
    except Exception as e:
        print(f"[SIDEBAR] Failed to inspect sidebar state: {str(e)[:120]}")
        return {
            'drawer_present': False,
            'is_open': False,
            'visible_item_count': 0,
            'visible_overlay_item_count': 0,
            'search_visible': False,
            'items': [],
            'menu_icons': [],
        }

    items = []
    for item in raw.get('items', []):
        label_raw = _collapse_ws(html.unescape(item.get('label_raw', '')))
        items.append({
            'index': item.get('index'),
            'label_raw': label_raw,
            'label_normalized': normalize_sidebar_text(label_raw),
            'has_expand_icon': bool(item.get('has_expand_icon')),
            'is_visible': bool(item.get('is_visible')),
            'in_overlay': bool(item.get('in_overlay')),
            'click_xpath': (build_sidebar_click_xpaths(label_raw)[0] if label_raw else None),
        })

    return {
        'drawer_present': bool(raw.get('drawer_present')),
        'is_open': bool(raw.get('is_open')),
        'visible_item_count': int(raw.get('visible_item_count') or 0),
        'visible_overlay_item_count': int(raw.get('visible_overlay_item_count') or 0),
        'search_visible': bool(raw.get('search_visible')),
        'items': items,
        'menu_icons': raw.get('menu_icons', []),
    }


def ensure_sidebar_open(page, timeout_ms=3000):
    """Open sidebar when possible by selecting the best available menu icon."""
    state = get_sidebar_state(page)
    if state.get('is_open'):
        return True, {'auto_opened': False, 'state': state}

    chosen_icon = choose_best_menu_icon(state.get('menu_icons', []))
    if not chosen_icon:
        return False, {
            'auto_opened': False,
            'reason': 'No menu icon found',
            'state': state
        }

    try:
        clicked = page.evaluate(
            '''(iconIndex) => {
                const icons = Array.from(document.querySelectorAll('[data-testid="menu-icon"]'));
                if (!icons[iconIndex]) return false;
                icons[iconIndex].click();
                return true;
            }''',
            int(chosen_icon.get('index', 0))
        )
        if not clicked:
            return False, {
                'auto_opened': False,
                'reason': 'Menu icon index not found',
                'state': state
            }
    except Exception as e:
        return False, {
            'auto_opened': False,
            'reason': f'Failed to click menu icon: {str(e)[:100]}',
            'state': state
        }

    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        time.sleep(0.15)
        refreshed = get_sidebar_state(page)
        if refreshed.get('is_open'):
            return True, {
                'auto_opened': True,
                'used_menu_icon_index': chosen_icon.get('index'),
                'state': refreshed
            }

    return False, {
        'auto_opened': False,
        'reason': 'Sidebar did not open before timeout',
        'used_menu_icon_index': chosen_icon.get('index'),
        'state': get_sidebar_state(page)
    }


def match_sidebar_item(target, items):
    """
    Match a free-form target against sidebar items with tiered strict->fuzzy logic.
    Returns a dict containing status, candidate, score, and ambiguity diagnostics.
    """
    target_raw = _collapse_ws(html.unescape(target))
    target_basic = _basic_sidebar_text(target_raw)
    target_norm = normalize_sidebar_text(target_raw)

    prepared = []
    for item in items or []:
        label_raw = _collapse_ws(item.get('label_raw', ''))
        label_norm = item.get('label_normalized') or normalize_sidebar_text(label_raw)
        prepared.append({
            **item,
            'label_raw': label_raw,
            'label_normalized': label_norm,
        })

    if not target_norm:
        return {
            'ok': False,
            'status': 'no_target',
            'message': 'No sidebar target text after normalization',
            'target': target_raw,
            'target_normalized': target_norm,
            'topCandidates': []
        }

    if not prepared:
        return {
            'ok': False,
            'status': 'no_items',
            'message': 'No sidebar items found in DOM',
            'target': target_raw,
            'target_normalized': target_norm,
            'topCandidates': []
        }

    exact_raw = [
        dict(item, _score=1.0)
        for item in prepared
        if _basic_sidebar_text(item['label_raw']) == target_basic and target_basic
    ]
    if len(exact_raw) == 1:
        return {
            'ok': True,
            'status': 'matched',
            'matchTier': 'exact-label',
            'matchScore': 1.0,
            'candidate': exact_raw[0],
            'target': target_raw,
            'target_normalized': target_norm,
            'topCandidates': _build_top_candidates(exact_raw)
        }
    if len(exact_raw) > 1:
        return {
            'ok': False,
            'status': 'ambiguous',
            'message': 'Multiple exact sidebar labels matched',
            'target': target_raw,
            'target_normalized': target_norm,
            'topCandidates': _build_top_candidates(exact_raw)
        }

    exact_norm = [
        dict(item, _score=1.0)
        for item in prepared
        if item['label_normalized'] == target_norm
    ]
    if len(exact_norm) == 1:
        return {
            'ok': True,
            'status': 'matched',
            'matchTier': 'exact-normalized',
            'matchScore': 1.0,
            'candidate': exact_norm[0],
            'target': target_raw,
            'target_normalized': target_norm,
            'topCandidates': _build_top_candidates(exact_norm)
        }
    if len(exact_norm) > 1:
        return {
            'ok': False,
            'status': 'ambiguous',
            'message': 'Multiple normalized sidebar labels matched',
            'target': target_raw,
            'target_normalized': target_norm,
            'topCandidates': _build_top_candidates(exact_norm)
        }

    contains = []
    target_token_count = len([t for t in target_norm.split(' ') if t])
    for item in prepared:
        label_norm = item['label_normalized']
        if not label_norm:
            continue
        if target_norm in label_norm or label_norm in target_norm:
            score = difflib.SequenceMatcher(None, target_norm, label_norm).ratio()
            if score >= CONTAINS_MATCH_THRESHOLD or target_token_count <= 1:
                contains.append(dict(item, _score=score))
    contains.sort(key=lambda x: x.get('_score', 0.0), reverse=True)
    if len(contains) == 1:
        return {
            'ok': True,
            'status': 'matched',
            'matchTier': 'contains',
            'matchScore': round(float(contains[0].get('_score', 0.0)), 4),
            'candidate': contains[0],
            'target': target_raw,
            'target_normalized': target_norm,
            'topCandidates': _build_top_candidates(contains)
        }
    if len(contains) > 1:
        return {
            'ok': False,
            'status': 'ambiguous',
            'message': 'Multiple sidebar items matched by contains',
            'target': target_raw,
            'target_normalized': target_norm,
            'topCandidates': _build_top_candidates(contains)
        }

    token_scored = []
    for item in prepared:
        score = _token_overlap_score(target_norm, item['label_normalized'])
        if score >= TOKEN_OVERLAP_THRESHOLD:
            token_scored.append(dict(item, _score=score))
    token_scored.sort(key=lambda x: x.get('_score', 0.0), reverse=True)

    if token_scored:
        best = token_scored[0]
        second = token_scored[1] if len(token_scored) > 1 else None
        if second and (best.get('_score', 0.0) - second.get('_score', 0.0) < FUZZY_MARGIN_THRESHOLD):
            return {
                'ok': False,
                'status': 'ambiguous',
                'message': 'Token-overlap matching is ambiguous',
                'target': target_raw,
                'target_normalized': target_norm,
                'topCandidates': _build_top_candidates(token_scored)
            }
        return {
            'ok': True,
            'status': 'matched',
            'matchTier': 'token-overlap',
            'matchScore': round(float(best.get('_score', 0.0)), 4),
            'candidate': best,
            'target': target_raw,
            'target_normalized': target_norm,
            'topCandidates': _build_top_candidates(token_scored)
        }

    fuzzy = []
    for item in prepared:
        score = difflib.SequenceMatcher(None, target_norm, item['label_normalized']).ratio()
        fuzzy.append(dict(item, _score=score))
    fuzzy.sort(key=lambda x: x.get('_score', 0.0), reverse=True)

    if fuzzy and fuzzy[0].get('_score', 0.0) >= FUZZY_MATCH_THRESHOLD:
        best = fuzzy[0]
        second = fuzzy[1] if len(fuzzy) > 1 else None
        if second and (best.get('_score', 0.0) - second.get('_score', 0.0) < FUZZY_MARGIN_THRESHOLD):
            return {
                'ok': False,
                'status': 'ambiguous',
                'message': 'Fuzzy matching is ambiguous',
                'target': target_raw,
                'target_normalized': target_norm,
                'topCandidates': _build_top_candidates(fuzzy)
            }
        return {
            'ok': True,
            'status': 'matched',
            'matchTier': 'fuzzy',
            'matchScore': round(float(best.get('_score', 0.0)), 4),
            'candidate': best,
            'target': target_raw,
            'target_normalized': target_norm,
            'topCandidates': _build_top_candidates(fuzzy)
        }

    return {
        'ok': False,
        'status': 'no_match',
        'message': 'No sidebar item matched the target',
        'target': target_raw,
        'target_normalized': target_norm,
        'topCandidates': _build_top_candidates(fuzzy)
    }


def click_sidebar_target(page, step_text):
    """
    Deterministic sidebar click handler. Returns (ok, info).
    When successful, it performs the click directly and appends script lines.
    """
    target_info = extract_sidebar_target(step_text)
    info = {
        'resolver': 'sidebar-deterministic',
        'status': 'skipped',
        'is_sidebar_candidate': target_info.get('is_sidebar_candidate', False),
        'is_sidebar_context': bool(target_info.get('is_explicit_sidebar', False)),
        'target': target_info.get('target_text', ''),
        'target_normalized': target_info.get('normalized_target', ''),
        'sidebarAutoOpened': False,
        'topCandidates': []
    }

    if not target_info.get('is_sidebar_candidate'):
        return False, info

    state = get_sidebar_state(page)
    match = match_sidebar_item(target_info.get('target_text', ''), state.get('items', []))
    if match.get('ok') or match.get('status') == 'ambiguous':
        info['is_sidebar_context'] = True

    # If the user explicitly referred to sidebar/nav and drawer looks closed, open first then rematch.
    if (not match.get('ok')) and target_info.get('is_explicit_sidebar') and (not state.get('is_open')):
        opened, open_info = ensure_sidebar_open(page)
        info['sidebarAutoOpened'] = bool(open_info.get('auto_opened'))
        if not opened:
            info.update({
                'status': 'open_failed',
                'message': open_info.get('reason', 'Could not open sidebar'),
                'topCandidates': match.get('topCandidates', [])
            })
            return False, info
        state = get_sidebar_state(page)
        match = match_sidebar_item(target_info.get('target_text', ''), state.get('items', []))
        if match.get('ok') or match.get('status') == 'ambiguous':
            info['is_sidebar_context'] = True

    # If we already matched a sidebar item but the drawer is closed, auto-open then rematch.
    if match.get('ok') and not state.get('is_open'):
        opened, open_info = ensure_sidebar_open(page)
        info['sidebarAutoOpened'] = bool(open_info.get('auto_opened'))
        if not opened:
            info.update({
                'status': 'open_failed',
                'message': open_info.get('reason', 'Could not open sidebar'),
                'topCandidates': match.get('topCandidates', [])
            })
            return False, info
        state = get_sidebar_state(page)
        match = match_sidebar_item(target_info.get('target_text', ''), state.get('items', []))
        if match.get('ok') or match.get('status') == 'ambiguous':
            info['is_sidebar_context'] = True

    if not match.get('ok'):
        info.update({
            'status': match.get('status', 'no_match'),
            'message': match.get('message', ''),
            'topCandidates': match.get('topCandidates', [])
        })
        return False, info

    candidate = match.get('candidate', {}) or {}
    label_raw = candidate.get('label_raw', '')
    xpaths = build_sidebar_click_xpaths(label_raw)
    if not xpaths:
        info.update({
            'status': 'click_failed',
            'message': f'No XPath candidates could be built for "{label_raw}"',
            'topCandidates': match.get('topCandidates', [])
        })
        return False, info

    chosen_xpath = None
    last_error = ''
    for xpath in xpaths:
        try:
            loc = page.locator(f"xpath={xpath}")
            count = loc.count()
            if count <= 0:
                continue
            for i in range(count):
                row = loc.nth(i)
                if row.is_visible():
                    row.click(timeout=5000)
                    chosen_xpath = xpath
                    break
            if chosen_xpath:
                break
        except Exception as e:
            last_error = str(e)[:120]

    if not chosen_xpath:
        info.update({
            'status': 'click_failed',
            'message': f'Failed to click matched sidebar item "{label_raw}"' + (f' ({last_error})' if last_error else ''),
            'topCandidates': match.get('topCandidates', [])
        })
        return False, info

    # Persist deterministic click into generated script.
    try:
        init_script()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if step_text:
            append_script_line(f"// step: {step_text}")
        append_script_line(f"// {timestamp} click")
        append_script_line(f"await page.click(`{js_safe('xpath=' + chosen_xpath)}`);")
    except Exception as e:
        print(f"[SIDEBAR] Warning: could not append deterministic click to script: {str(e)[:100]}")

    info.update({
        'status': 'clicked',
        'locator': chosen_xpath,
        'type': 'xpath',
        'matchTier': match.get('matchTier'),
        'matchScore': match.get('matchScore'),
        'topCandidates': match.get('topCandidates', []),
        'itemLabel': label_raw,
    })
    return True, info

def try_fast_locator(page, step_description):
    """
    Try to find an element using common structural patterns BEFORE calling the LLM.
    This is a fast-path (milliseconds) that avoids expensive LLM calls for
    straightforward elements like sidebar items, buttons, links, inputs.

    Returns: (locator_string, locator_type) or (None, None) if no unique match.
    """
    target_info = extract_sidebar_target(step_description)
    target_text = target_info.get('target_text') or _collapse_ws(step_description)
    target_norm = target_info.get('normalized_target') or normalize_sidebar_text(target_text)

    if not target_text or len(target_text) < 2:
        return None, None

    print(f"[FAST-LOCATOR] Trying fast path for: '{target_text}' (normalized='{target_norm}')")

    drawer_xpaths = []
    if target_text:
        drawer_xpaths.extend(build_sidebar_click_xpaths(target_text))

    target_xpath_lit = xpath_literal(target_text)
    testid_contains = (target_text.lower().replace(' ', '-'))

    # Generic structural XPath patterns (not app-specific)
    fast_xpaths = [
        *drawer_xpaths,
        # aria-label exact match -> clickable ancestor (sidebar, nav items)
        f"//div[@aria-label={target_xpath_lit}]/ancestor::div[@role='button']",
        # aria-label on a clickable element itself
        f"//*[@aria-label={target_xpath_lit}][@role='button' or self::button or self::a]",
        # Span text exact match -> clickable ancestor (MUI list items)
        f"//span[normalize-space(text())={target_xpath_lit}]/ancestor::div[@role='button']",
        # Button with exact text
        f"//button[normalize-space(.)={target_xpath_lit}]",
        # Link with exact text
        f"//a[normalize-space(.)={target_xpath_lit}]",
        # Tab / role=tab
        f"//*[@role='tab'][.//text()[normalize-space(.)={target_xpath_lit}]]",
        # data-testid containing the text (case-insensitive)
        f"//*[@data-testid and contains(translate(@data-testid,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), {xpath_literal(testid_contains)})]",
    ]

    # For texts with special chars (& etc.), add contains() fallbacks.
    safe_text = target_text.split('&')[0].strip() if '&' in target_text else None
    if not safe_text and target_norm:
        safe_text = target_norm.split(' ')[0].strip() if ' ' in target_norm else target_norm
    if safe_text and len(safe_text) >= 3:
        safe_lit = xpath_literal(safe_text)
        fast_xpaths.extend([
            f"//div[contains(@aria-label,{safe_lit})]/ancestor::div[@role='button']",
            f"//span[contains(text(),{safe_lit})]/ancestor::div[@role='button']",
            f"//*[contains(@class,'IvpLeftMenuDrawer')]//div[contains(@aria-label,{safe_lit})]/ancestor::div[@role='button'][1]",
            f"//*[contains(@class,'IvpLeftMenuDrawer')]//span[contains(text(),{safe_lit})]/ancestor::div[@role='button'][1]",
        ])

    for xpath in fast_xpaths:
        try:
            loc = page.locator(f"xpath={xpath}")
            count = loc.count()
            if count <= 0:
                continue

            if count == 1 and loc.first.is_visible():
                print(f"[FAST-LOCATOR] Found unique visible match: {xpath}")
                return xpath, "xpath"

            # Drawer-scoped selectors can be accepted when exactly one visible match exists.
            if "IvpLeftMenuDrawer" in xpath or "testDrawer" in xpath:
                visible_matches = 0
                for i in range(count):
                    if loc.nth(i).is_visible():
                        visible_matches += 1
                if visible_matches == 1:
                    print(f"[FAST-LOCATOR] Found unique visible drawer match: {xpath}")
                    return xpath, "xpath"
        except Exception:
            pass

    print(f"[FAST-LOCATOR] No unique match, falling back to LLM")
    return None, None


def get_locator_from_ai(page_dom, step_description):
    """
    Send page DOM and step description to LLM to get a smart locator.
    Returns: (locator_string, locator_type) or (None, None) if failed
    """
    if not SECRET_KEY:
        print("[LLM] Skipped: SECRET_KEY not configured")
        return None, None
    
    try:
        print(f"[LLM] Sending request for step: {step_description[:60]}...")
        
        # Build the prompt with app patterns
        app_patterns_section = ""
        if APP_PATTERNS:
            app_patterns_section = f"\n## Application-Specific Patterns:\n{APP_PATTERNS}\n"

        prompt = f"""You are a web automation expert. Given the DOM of a webpage and a test step description, 
find a UNIQUE XPath to locate the PRIMARY element that should be interacted with.


## CRITICAL RULES:
1. Return ONLY ONE JSON object - NOT a list or array - this is MANDATORY
2. DO NOT Use svg tags in the XPath directly. Instead, identify the purpose of the icon (e.g. menu, upload) and look for parent buttons or aria-labels or any other reliable thing that indicate its function.
   - Focus on the PRIMARY element mentioned in the step (the one that will be acted upon first)
3. **PRIORITY**: Always look for and prioritize elements with `data-testid` attributes (very reliable)
4. Return ONLY XPath locators (no CSS selectors)
5. The XPath must be UNIQUE and reliable - it should match exactly ONE element
6. Prefer using attributes in this order:
   - `data-testid` (most reliable, explicitly set for testing)
   - `id`, `name`, `aria-label`, `placeholder`
   - Text content (exact or contains)
   - Combination of attributes for uniqueness
7. Make the XPath specific enough that it won't match other similar elements
8. For text-driven nodes (`div`, `span`, `li`, `td`, `th`), use robust text predicates like:
   - `normalize-space(text())='Exact Text'`
   - `contains(normalize-space(.), 'Partial Text')`
   Prefer `contains(normalize-space(.), ...)` when nested tags split text.
9. **For SVGs and icons**: Identify the action/purpose, not just the visual. Look for parent buttons or aria-labels
10. For hamburger icons or menu icons(svg), always return `//*[@data-testid='menu-icon']` if available. Only use fallbacks if not present.
11. **For sidebar / navigation menu items** (e.g. "Click on Configure", "Click Challenge"):
   - These are typically list items in a drawer/sidebar with `aria-label` on the text container or visible text in a `<span>`.
   - Use `aria-label` attribute: `//div[@aria-label='Configure']/ancestor::div[@role='button']` 
   - Or use text content: `//span[normalize-space(text())='Configure']/ancestor::div[@role='button']`
   - ALWAYS target the nearest CLICKABLE ancestor element (`div[@role='button']`, `button`, or `a`) — NOT the inner text span itself.
   - If the text uses HTML entities (e.g., `&amp;`), use `contains()` with partial text rather than exact match: `//span[contains(text(),'Challenge')]/ancestor::div[@role='button']`
12. **For elements with special characters in text** (like `&`, `<`, `>`): Use `contains()` with a safe substring instead of exact matching.
13. When the step says "click on X" and X appears both in a sidebar menu AND elsewhere on the page, prefer the sidebar menu item (inside a drawer/nav/MuiList container).
{app_patterns_section}
## Example good XPaths (with data-testid priority):
   - //button[@data-testid='upload-button']
   - //input[@data-testid='email-input']
   - //input[@placeholder='Email address']
   - //button[contains(text(), 'Login')]
   - //select[@name='country']
   - //button[@aria-label='Close']
   - //div[@aria-label='Configure']/ancestor::div[@role='button']
   - //span[contains(text(),'Challenge')]/ancestor::div[@role='button']

## Page DOM:
{page_dom}

## Test Step: {step_description}

## MUST RETURN exactly this structure (nothing else, NOT an array):
{{
    "locator": "//xpath/to/primary/element",
    "type": "xpath",
    "element_description": "brief description",
    "reasoning": "why this XPath works, especially if data-testid was used"
}}

## If no element found:
{{
    "locator": null,
    "type": null,
    "element_description": "reason element not found"
}}

DO NOT RETURN AN ARRAY. Return ONLY one JSON object."""

        payload = {
            "model": "gpt-5-mini",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        req_data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            LLM_API_URL,
            data=req_data,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {SECRET_KEY}'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"[LLM] Full response: {json.dumps(result, indent=2)}")
            
            # Extract the response content
            if result.get('choices') and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content']
                print(f"[LLM] Message content: {content}")
                
                # Parse JSON from response (may be wrapped in markdown code blocks)
                try:
                    # Extract JSON from markdown code blocks if present
                    json_str = content
                    if '```json' in content:
                        json_str = content.split('```json')[1].split('```')[0].strip()
                    elif '```' in content:
                        json_str = content.split('```')[1].split('```')[0].strip()
                    
                    locator_data = json.loads(json_str)
                    print(f"[LLM] Parsed response type: {type(locator_data)}, content: {locator_data}")
                    
                    # Handle if LLM returns a list instead of object
                    if isinstance(locator_data, list):
                        if len(locator_data) > 0:
                            locator_data = locator_data[0]  # Take first element
                            print(f"[LLM] Response was list with {len(locator_data) if isinstance(locator_data, (list, dict)) else '?'} items, extracted first element")
                        else:
                            print(f"[LLM] Response was empty list")
                            return None, None
                    
                    # Ensure locator_data is a dict
                    if not isinstance(locator_data, dict):
                        print(f"[LLM] ERROR: Response is not a dict: {type(locator_data)}")
                        return None, None
                    
                    locator = locator_data.get('locator')
                    loc_type = locator_data.get('type')
                    
                    # Validate that we got a locator value
                    if locator is None:
                        print(f"[LLM] Warning: locator value is null in response. Full response: {locator_data}")
                        return None, None
                    
                    print(f"[LLM] Found locator: {locator} (type: {loc_type})")
                    return locator, loc_type
                except json.JSONDecodeError as je:
                    print(f"[LLM] Failed to parse JSON: {je}")
                    print(f"[LLM] Raw content: {content}")
                    return None, None
        print("[LLM] No choices in response")
        return None, None
    except Exception as e:
        print(f"[LLM] Error: {str(e)}", file=sys.stderr)
        return None, None

def find_element_by_text(page, description):
    """
    Smart element finder: extracts all interactive elements from the page,
    matches them against the description using text similarity, and returns the best match selector.
    """
    try:
        # Get all interactive elements and their properties
        elements_info = page.evaluate('''() => {
            const elements = [];
            const selectors = new Set();
            
            // Find all interactive elements
            const interactiveSelectors = [
                'input', 'button', 'select', 'textarea', 
                '[role="button"]', '[role="link"]', '[onclick]',
                'a', 'label'
            ];
            
            interactiveSelectors.forEach(sel => {
                try {
                    document.querySelectorAll(sel).forEach((el, idx) => {
                        const label = el.getAttribute('aria-label') || 
                                     el.getAttribute('placeholder') ||
                                     el.getAttribute('name') ||
                                     el.textContent?.trim() ||
                                     el.getAttribute('title') || '';
                        
                        const type = el.getAttribute('type') || el.tagName.toLowerCase();
                        
                        // Try to generate a unique selector
                        let selector = null;
                        if (el.id) {
                            selector = `#${el.id}`;
                        } else if (el.className) {
                            const classes = el.className.split(' ').filter(c => c).join('.');
                            selector = `${el.tagName.toLowerCase()}.${classes}`;
                        } else {
                            selector = el.tagName.toLowerCase();
                        }
                        
                        if (label && selector && !selectors.has(selector)) {
                            elements.push({
                                selector: selector,
                                label: label,
                                type: type,
                                tagName: el.tagName
                            });
                            selectors.add(selector);
                        }
                    });
                } catch(e) {}
            });
            
            return elements;
        }''')
        
        # Find best match using text similarity
        best_match = None
        best_ratio = 0
        description_lower = description.lower()
        
        for elem in elements_info:
            label_lower = elem['label'].lower()
            # Check exact substring matches first
            if label_lower in description_lower or description_lower in label_lower:
                ratio = 1.0
            else:
                # Use difflib for fuzzy matching
                ratio = difflib.SequenceMatcher(None, description_lower, label_lower).ratio()
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = elem
        
        if best_match and best_ratio > 0.3:  # threshold for reasonable match
            return best_match['selector']
        
        return None
    except Exception as e:
        return None

def bring_window_to_front():
    """Bring the browser window to the front on Windows."""
    try:
        import subprocess
        import sys
        
        if sys.platform == 'win32':
            # Use PowerShell to bring Chromium window to front
            subprocess.run([
                'powershell', '-Command',
                '[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") > $null; '
                '$processes = Get-Process | Where-Object {$_.ProcessName -like "*chrome*" -or $_.ProcessName -like "*chromium*"}; '
                'foreach ($p in $processes) { '
                '  $hwnd = $p.MainWindowHandle; '
                '  if ($hwnd -ne 0) { '
                '    Add-Type -MemberDefinition "[DllImport(\\"user32.dll\\")] public static extern bool SetForegroundWindow(IntPtr hWnd);" -Name WinAPI -Namespace Native; '
                '    [Native.WinAPI]::SetForegroundWindow($hwnd); '
                '  } '
                '}'
            ], capture_output=True, timeout=5)
    except Exception as e:
        print(f"[BROWSER] Could not bring window to front: {e}")

def wait_for_loader(page):
    """
    Wait for the page loader to disappear before proceeding.
    Waits for the PMLoadingDivContent element to disappear (90 second timeout).
    """
    try:
        print("[LOADER] Waiting for page loader to clear...")
        page.evaluate('''() => {
            return new Promise((resolve, reject) => {
                let attempts = 0;
                const maxAttempts = 120;  // 120 seconds max wait
                
                function checkLoader() {
                    // Check multiple common loader selectors
                    const loaderSelectors = [
                        "//*[@class='PMLoadingDivContent']/*",
                        "//*[@class='loader']",
                        "//*[contains(@class, 'loading')]",
                        "//*[contains(@class, 'spinner')]"
                    ];
                    
                    let loaderPresent = false;
                    
                    for (let selector of loaderSelectors) {
                        try {
                            const result = document.evaluate(
                                selector, 
                                document, 
                                null, 
                                XPathResult.FIRST_ORDERED_NODE_TYPE, 
                                null
                            );
                            if (result.singleNodeValue !== null) {
                                loaderPresent = true;
                                break;
                            }
                        } catch (e) {}
                    }
                    
                    if (!loaderPresent) {
                        console.log('[LOADER] Loader cleared');
                        resolve('Loader cleared');
                    } else if (attempts >= maxAttempts) {
                        console.log('[LOADER] Timeout waiting for loader');
                        resolve('Timeout - proceeding anyway');
                    } else {
                        attempts++;
                        setTimeout(checkLoader, 1000);  // Check every 1 second
                    }
                }
                
                checkLoader();
            });
        }''')
        print("[LOADER] Loader check complete")
    except Exception as e:
        print(f"[LOADER] Error checking loader: {str(e)[:100]}")
        # Don't fail the whole process if loader check fails
        pass

def get_page_dom_simple(page):
    """Get complete DOM snapshot including iframes and Shadow DOM for AI analysis.
    Keeps structural/text context broad while trimming only obvious noise."""
    try:
        dom_snapshot = page.evaluate('''() => {
    function getVisibleDOMSnapshot() {
        const getAttributes = (node) => {
            if (!node.attributes) return '';
            let attrs = '';
            for (const attr of node.attributes) {
                const name = attr.name;
                let value = attr.value;

                // Only keep useful attributes
                if (!['id','class','name','data-testid','role','aria-label','aria-labelledby',
                       'aria-describedby','aria-controls','aria-hidden','placeholder','title',
                       'href','src','xlink:href','type','tabindex','aria-selected',
                       'aria-expanded','aria-haspopup','value','for','alt','disabled',
                       'readonly','checked','selected','colspan','rowspan'].includes(name)) {
                    continue;
                }

                // Truncate very long class names (MUI classes can be 300+ chars)
                if (name === 'class' && value.length > 100) {
                    value = value.substring(0, 100) + '...';
                }

                attrs += ` ${name}="${value}"`;
            }
            return attrs;
        };

        const serializeNode = (node, indent = '') => {
            if (node.nodeType !== Node.ELEMENT_NODE) return '';
            const tag = node.tagName.toLowerCase();

            // Skip non-visible / non-useful elements
            if (['script','style','link','meta','noscript'].includes(tag)) return '';

            // Skip SVG internals (path, circle, rect, etc.) — keep the SVG tag itself for context
            if (['path','circle','rect','line','polygon','polyline','ellipse','use','defs',
                 'clippath','lineargradient','radialgradient','stop','g','mask','filter',
                 'fegaussianblur','feoffset','feblend','fecolormatrix','fecomposite'].includes(tag)) {
                return '';
            }

            let output = `${indent}<${tag}${getAttributes(node)}>\n`;

            // Shadow DOM
            if (node.shadowRoot) {
                output += `${indent}  <!-- Shadow DOM -->\n`;
                for (const child of node.shadowRoot.childNodes) {
                    output += serializeNode(child, indent + '    ');
                }
            }

            // Children
            for (const child of node.childNodes) {
                if (child.nodeType === Node.TEXT_NODE && child.nodeValue.trim()) {
                    output += `${indent}  ${child.nodeValue.trim()}\n`;
                } else {
                    output += serializeNode(child, indent + '  ');
                }
            }

            output += `${indent}</${tag}>\n`;
            return output;
        };

        return serializeNode(document.body);
    }

    return getVisibleDOMSnapshot();
}''')
        return dom_snapshot
    except Exception as e:
        print(f"[DOM Capture Error] {str(e)}")
        return str(e)


def get_sidebar_dom_snapshot(page):
    """
    Capture a compact DOM snapshot focused on sidebar + active menu/listbox/popover surfaces.
    This keeps LLM prompts small and relevant for sidebar locator fallback.
    """
    try:
        sidebar_dom = page.evaluate('''() => {
            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (!style || style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    return false;
                }
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const keepAttr = new Set([
                'id', 'class', 'name', 'data-testid', 'role', 'aria-label',
                'aria-labelledby', 'aria-describedby', 'aria-controls', 'aria-hidden',
                'placeholder', 'title', 'type', 'aria-selected', 'aria-expanded',
                'aria-haspopup', 'tabindex', 'value', 'href', 'src', 'xlink:href',
                'for', 'alt', 'disabled', 'readonly', 'checked', 'selected',
                'colspan', 'rowspan'
            ]);

            const sanitizeAttr = (name, value) => {
                if (name === 'class' && value.length > 100) return value.substring(0, 100) + '...';
                return value;
            };

            const getAttributes = (node) => {
                if (!node.attributes) return '';
                let attrs = '';
                for (const attr of node.attributes) {
                    const name = attr.name;
                    if (!keepAttr.has(name)) continue;
                    const value = sanitizeAttr(name, attr.value || '');
                    attrs += ` ${name}="${value}"`;
                }
                return attrs;
            };

            const serializeNode = (node, indent = '') => {
                if (!node || node.nodeType !== Node.ELEMENT_NODE) return '';
                if (!isVisible(node)) return '';

                const tag = node.tagName.toLowerCase();
                if (['script', 'style', 'link', 'meta', 'noscript'].includes(tag)) return '';
                if (['path', 'defs', 'g', 'clippath', 'mask', 'filter'].includes(tag)) return '';

                let out = `${indent}<${tag}${getAttributes(node)}>` + '\\n';

                for (const child of node.childNodes) {
                    if (child.nodeType === Node.TEXT_NODE) {
                        const text = (child.nodeValue || '').trim().replace(/\\s+/g, ' ');
                        if (text) {
                            out += `${indent}  ${text}` + '\\n';
                        }
                    } else {
                        out += serializeNode(child, indent + '  ');
                    }
                }

                out += `${indent}</${tag}>` + '\\n';
                return out;
            };

            const roots = [];
            const drawerRoot =
                document.querySelector('.IvpLeftMenuDrawer') ||
                document.querySelector('[class*="IvpLeftMenuDrawer"]') ||
                document.querySelector('[data-testid="testDrawer"]')?.closest('.MuiDrawer-root');

            if (drawerRoot) roots.push(drawerRoot);

            const popovers = Array.from(
                document.querySelectorAll('[role="menu"], [role="listbox"], .MuiPopover-root, .MuiPopper-root')
            ).filter(isVisible).slice(0, 6);
            roots.push(...popovers);

            return roots.map((root, idx) => {
                const title = idx === 0 ? '## SIDEBAR ROOT' : `## ACTIVE OVERLAY ${idx}`;
                return title + '\\n' + serializeNode(root);
            }).join('\\n');
        }''')

        state = get_sidebar_state(page)
        labels = [item.get('label_raw') for item in state.get('items', []) if item.get('label_raw')]
        labels = list(dict.fromkeys(labels))
        labels_blob = "## SIDEBAR LABELS:\n" + "\n".join(f"- {label}" for label in labels) if labels else "## SIDEBAR LABELS:\n- (none found)"

        return labels_blob + "\n\n" + sidebar_dom
    except Exception as e:
        print(f"[SIDEBAR DOM] Error: {str(e)[:100]}")
        return get_page_dom_simple(page)

def extract_data_testid_summary(page):
    """Extract all elements with data-testid for quick reference"""
    try:
        testid_elements = page.evaluate('''() => {
            const elements = [];
            document.querySelectorAll('[data-testid]').forEach(el => {
                const testid = el.getAttribute('data-testid');
                const tag = el.tagName.toLowerCase();
                const text = el.textContent?.trim().substring(0, 50) || '';
                const role = el.getAttribute('role') || '';
                const type = el.getAttribute('type') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                
                elements.push({
                    testid,
                    tag,
                    text,
                    role,
                    type,
                    placeholder
                });
            });
            return elements;
        }''')
        
        if not testid_elements:
            return ""
        
        summary = "\n## AVAILABLE DATA-TESTID ELEMENTS (Quick Reference):\n"
        for elem in testid_elements:
            info_parts = [f"data-testid=\"{elem['testid']}\"", f"<{elem['tag']}>"]
            if elem['type']:
                info_parts.append(f"type=\"{elem['type']}\"")
            if elem['placeholder']:
                info_parts.append(f"placeholder=\"{elem['placeholder']}\"")
            if elem['role']:
                info_parts.append(f"role=\"{elem['role']}\"")
            if elem['text']:
                info_parts.append(f"text=\"{elem['text']}\"")
            
            summary += f"  - {' '.join(info_parts)}\n"
        
        return summary
    except Exception as e:
        print(f"[Data-TestID Extraction] Warning: {str(e)[:100]}")
        return ""

def find_element_by_ai(page, step_description):
    """
    Use AI to find element on page. Falls back to text-based finding if AI fails.
    Returns: (locator, locator_type, method) where:
      - locator: the CSS selector or XPath
      - locator_type: 'css' or 'xpath'
      - method: 'ai', 'text', or None
    """
    if not SECRET_KEY:
        return None, None, None
    
    try:
        dom = get_page_dom_simple(page)
        # Include data-testid summary for better element finding
        testid_summary = extract_data_testid_summary(page)
        dom_with_context = testid_summary + "\n" + dom if testid_summary else dom
        
        locator, locator_type = get_locator_from_ai(dom_with_context, step_description)
        
        if locator:
            print(f"[AI] Found locator: {locator} (type: {locator_type})")
            return locator, locator_type, 'ai'
    except Exception as e:
        print(f"[AI Locator Error] {str(e)}", file=sys.stderr)
    
    # Fallback to text-based finding
    selector = find_element_by_text(page, step_description)
    if selector:
        print(f"[TEXT] Found selector: {selector}")
        return selector, 'css', 'text'
    
    return None, None, None


SCRIPT_DIR = os.path.join(os.path.dirname(__file__), "playwright_script")
SCRIPT_FILE = None  # Set dynamically per test run
SCRIPT_URL = None   # Set by execute_single_test so init_script can add goto

def init_script(test_name=None):
    """Create JS playwright script with boilerplate. Uses unique timestamped filename."""
    global SCRIPT_FILE
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    
    # Only create a new file if one hasn't been created yet for this run
    if SCRIPT_FILE is None or not os.path.exists(SCRIPT_FILE):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', test_name or 'test')
        filename = f"{safe_name}_{timestamp}.spec.js"
        SCRIPT_FILE = os.path.join(SCRIPT_DIR, filename)
        
        display_name = test_name or 'Generated Test'
        goto_line = ""
        if SCRIPT_URL:
            goto_line = f"    await page.goto(`{js_safe(SCRIPT_URL)}`);"
        with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
            f.write(f"""import {{ test, expect }} from '@playwright/test';

test('{display_name}', async ({{ page }}) => {{
{goto_line}
""")
        print(f"[SCRIPT] Created new script: {filename}")
            
def append_script_line(line):
    if SCRIPT_FILE:
        with open(SCRIPT_FILE, "a", encoding="utf-8") as f:
            f.write(f"    {line}\n")

def close_script():
    global SCRIPT_FILE
    if SCRIPT_FILE and os.path.exists(SCRIPT_FILE):
        with open(SCRIPT_FILE, "a", encoding="utf-8") as f:
            f.write("});") 
        print(f"[SCRIPT] Closed script: {os.path.basename(SCRIPT_FILE)}")
    SCRIPT_FILE = None  # Reset so next run creates a new file

def js_safe(value):
    """Escape backticks and template expressions for safe JS template literal embedding"""
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

def use_locator(page, locator, locator_type, action, value=None, step_description=None):
    """
    Execute an action using the locator, handling both CSS selectors and XPath.
    Args:
        page: Playwright page object
        locator: CSS selector or XPath string
        locator_type: 'css' or 'xpath'
        action: 'click', 'fill', 'select', 'press'
        value: Value for fill/select actions
        step_description: Natural language description of what this step does (for AI healing)
    Returns:
        (success: bool, error: str or None)
    """
    try:
        init_script()
        # Format locator for Playwright
        if locator_type == 'xpath':
            formatted_locator = f'xpath={locator}'
        else:
            formatted_locator = locator
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[Locator] Using {locator_type}: {locator}")
        
        # Write step description comment for AI healing context
        if step_description:
            append_script_line(f"// step: {step_description}")
        
        if action == 'click':
            page.click(formatted_locator)
            append_script_line(f"// {timestamp} click")
            append_script_line(f"await page.click(`{js_safe(formatted_locator)}`);")
            return True, None
        
        elif action in ('fill', 'type'):
            page.fill(formatted_locator, str(value) if value else '')
            append_script_line(f"// {timestamp} fill")
            append_script_line(
                f"await page.fill(`{js_safe(formatted_locator)}`, `{js_safe(value)}`);")
            return True, None
        
        elif action == 'select':
            page.select_option(formatted_locator, str(value) if value else '')
            append_script_line(f"// {timestamp} select")
            append_script_line(
                f"await page.selectOption(`{js_safe(formatted_locator)}`, `{js_safe(value)}`);")
            return True, None
        
        elif action == 'press':
            press_key = str(value) if value else 'Enter'
            page.press(formatted_locator, press_key)
            append_script_line(f"// {timestamp} press")
            append_script_line(
                f"await page.press(`{js_safe(formatted_locator)}`, `{js_safe(press_key)}`);")
            return True, None
        
        elif action == 'hover':
            page.hover(formatted_locator)
            append_script_line(f"// {timestamp} hover")
            append_script_line(f"await page.hover(`{js_safe(formatted_locator)}`);")
            return True, None
        
        elif action == 'dblclick':
            page.dblclick(formatted_locator)
            append_script_line(f"// {timestamp} double click")
            append_script_line(f"await page.dblclick(`{js_safe(formatted_locator)}`);")
            return True, None
        
        elif action == 'rightclick':
            page.click(formatted_locator, button='right')
            append_script_line(f"// {timestamp} right click")
            append_script_line(f"await page.click(`{js_safe(formatted_locator)}`, {{ button: 'right' }});")
            return True, None
        
        elif action == 'scroll':
            # Scroll element into view
            page.locator(formatted_locator).scroll_into_view_if_needed()
            append_script_line(f"// {timestamp} scroll into view")
            append_script_line(f"await page.locator(`{js_safe(formatted_locator)}`).scrollIntoViewIfNeeded();")
            return True, None
        
        elif action == 'validate':
            # Validate that text exists on the page (using locator if provided, or page-wide search)
            # If locator is provided, check if the locator contains the text
            if locator and locator != 'null':
                try:
                    element_text = page.locator(formatted_locator).text_content()
                    if value and value.lower() in element_text.lower():
                        append_script_line(f"// {timestamp} validate text")
                        append_script_line(
                            f"await expect(page.locator(`{js_safe(formatted_locator)}`)).toContainText(`{js_safe(value)}`);")
                        return True, None
                    else:
                        return False, f"Element found but does not contain expected text '{value}'"
                except Exception as e:
                    return False, f"Could not validate element text: {str(e)[:80]}"
            else:
                # Page-wide search for text
                try:
                    if page.get_by_text(value, exact=False):
                        return True, None
                except:
                    pass
                
                # Fallback: check page content
                page_text = page.text_content()
                if value.lower() in page_text.lower():
                    append_script_line(f"// {timestamp} validate page text")
                    append_script_line(
                        f"await expect(page.locator(`body`)).toContainText(`{js_safe(value)}`);")
                    return True, None
                else:
                    return False, f"Text '{value}' not found on page"
        
        else:
            return False, f"Unknown action: {action}"
            
    except Exception as e:
        return False, str(e)[:100]

def parse_natural_language_step(description):
    """
    Parse a natural language step description and extract action, value, and search text.
    """
    description = str(description).strip()
    
    # Try to match quoted values
    quoted_match = re.search(r'"([^"]*)"', description)
    quoted_value = quoted_match.group(1) if quoted_match else None
    
    action = None
    value = None
    search_text = description  # Text to search for in the page DOM
    
    # Match action patterns (case-insensitive)
    if re.search(r'\bdouble\s*click\b', description, re.I) or re.search(r'\bdbl\s*click\b', description, re.I):
        action = 'dblclick'
        search_text = re.sub(r'\b(?:double|dbl)\s*click\s+(?:on|the)?\s*', '', description, flags=re.I).strip()
    
    elif re.search(r'\bright\s*click\b', description, re.I) or re.search(r'\bcontext\s*click\b', description, re.I):
        action = 'rightclick'
        search_text = re.sub(r'\b(?:right|context)\s*click\s+(?:on|the)?\s*', '', description, flags=re.I).strip()
    
    elif re.search(r'\bclick\b', description, re.I):
        action = 'click'
        # Remove action word for better matching
        search_text = re.sub(r'\bclick\s+(?:on|the)?\s*', '', description, flags=re.I).strip()
    
    elif re.search(r'\benter\b', description, re.I) or re.search(r'\btype\b', description, re.I):
        action = 'type'
        if quoted_value:
            value = quoted_value
        # Remove action words for better matching
        search_text = re.sub(r'\b(?:enter|type)\s+', '', description, flags=re.I).strip()
        search_text = re.sub(r'"[^"]*"', '', search_text).strip()  # Remove quoted values from search
    
    elif re.search(r'\bwait\b', description, re.I):
        action = 'wait'
        # Default to 2 seconds, or parse if mentioned
        time_match = re.search(r'(\d+)\s*(?:seconds?|sec|ms|milliseconds?)', description, re.I)
        if time_match:
            multiplier = 1000 if re.search(r'milliseconds?|ms', description, re.I) else 1000
            value = int(time_match.group(1)) * multiplier
        else:
            value = 2000  # 2 seconds default
    
    elif re.search(r'\bselect\b', description, re.I):
        action = 'select'
        if quoted_value:
            value = quoted_value
        search_text = re.sub(r'\bselect\s+', '', description, flags=re.I).strip()
    
    elif re.search(r'\bsubmit\b', description, re.I) or re.search(r'\bclick.*submit', description, re.I):
        action = 'click'
        search_text = 'submit'
    
    elif re.search(r'\bscreenshot\b', description, re.I):
        action = 'screenshot'
    
    elif re.search(r'\bscroll\b', description, re.I):
        action = 'scroll'
        # Check for direction
        if re.search(r'\b(?:to\s+the\s+)?top\b', description, re.I):
            value = 'top'
        elif re.search(r'\b(?:to\s+the\s+)?bottom\b', description, re.I):
            value = 'bottom'
        elif re.search(r'\bup\b', description, re.I):
            value = 'up'
        else:
            value = 'down'  # default direction
        # Check for pixel amount
        px_match = re.search(r'(\d+)\s*(?:pixels?|px)?', description, re.I)
        if px_match and not re.search(r'\b(?:top|bottom)\b', description, re.I):
            value = ('up' if re.search(r'\bup\b', description, re.I) else 'down') + ':' + px_match.group(1)
        # Check for element target ("scroll to the X")
        elem_match = re.search(r'scroll\s+(?:to|into\s+view(?:\s+of)?)\s+(?:the\s+)?(.+)', description, re.I)
        if elem_match:
            value = 'element'
            search_text = elem_match.group(1).strip()
        else:
            search_text = ''
    
    elif re.search(r'\bhover\b', description, re.I) or re.search(r'\bmouse\s*over\b', description, re.I) or re.search(r'\bmove\s+mouse\s+to\b', description, re.I):
        action = 'hover'
        search_text = re.sub(r'\b(?:hover|mouse\s*over|move\s+mouse\s+to)\s+(?:over|on|the)?\s*', '', description, flags=re.I).strip()
    
    elif re.search(r'\bdrag\b', description, re.I):
        action = 'drag'
        # Extract source and target: "drag X to Y" or "drag X and drop on Y"
        drag_match = re.search(r'drag\s+(?:the\s+)?(.+?)\s+(?:to|and\s+drop\s+(?:on|onto|to)?)\s+(?:the\s+)?(.+)', description, re.I)
        if drag_match:
            search_text = drag_match.group(1).strip()
            value = drag_match.group(2).strip()  # target element description
        else:
            search_text = re.sub(r'\bdrag\s+(?:the)?\s*', '', description, flags=re.I).strip()
    
    elif re.search(r'\bpress\b', description, re.I):
        action = 'press'
        key_match = re.search(r'\b(?:enter|return|escape|tab|backspace)\b', description, re.I)
        if key_match:
            value = key_match.group(0).lower()
        else:
            value = 'Enter'
    
    elif re.search(r'\bvalidate\b', description, re.I) or re.search(r'\bassert\b', description, re.I) or re.search(r'\bverify\b', description, re.I):
        action = 'validate'
        # For validation, extract the text we're looking for
        if quoted_value:
            value = quoted_value
            search_text = quoted_value
        else:
            # Extract text after "validate" or "assert" or "verify"
            search_text = re.sub(r'\b(?:validate|assert|verify)\s+(?:that\s+)?', '', description, flags=re.I).strip()
            search_text = re.sub(r'\s+(?:appears|exists|is|shows|displays|contains)\b.*', '', search_text, flags=re.I).strip()
            value = search_text
    
    return {
        'action': action,
        'value': value,
        'search_text': search_text,
        'original': description
    }


MULTI_ACTION_VERB_RE = re.compile(
    r'\b(?:click|select|choose|pick|open|expand|collapse|tap|press|hit|hover|double\s+click|right\s+click)\b',
    flags=re.IGNORECASE
)
MULTI_ACTION_SPLIT_RE = re.compile(
    r'\s+(?:and then|then|and)\s+(?=(?:click|select|choose|pick|open|expand|collapse|tap|press|hit|hover|double\s+click|right\s+click)\b)',
    flags=re.IGNORECASE
)


def should_force_multi_action_split(description):
    """Detect compound steps that contain multiple explicit action verbs."""
    text = _collapse_ws(description or '')
    if not text:
        return False
    lower = text.lower()
    if (' and ' not in lower) and (' then ' not in lower):
        return False
    return len(MULTI_ACTION_VERB_RE.findall(text)) >= 2


def heuristic_decompose_step(description):
    """
    Deterministic fallback decomposition for action chains like:
    'Select A and Click B and Click C'.
    """
    text = _collapse_ws(description or '')
    if not should_force_multi_action_split(text):
        return [text] if text else [description]

    parts = [p.strip(' ,.;') for p in MULTI_ACTION_SPLIT_RE.split(text) if p and p.strip(' ,.;')]
    if len(parts) <= 1:
        return [text]

    # Keep only actionable segments; otherwise keep original to avoid bad rewrites.
    if not all(MULTI_ACTION_VERB_RE.search(p) for p in parts):
        return [text]

    return parts


def decompose_step_with_ai(description):
    """
    Use AI to decompose a compound natural language step into atomic sub-steps.
    Also resolves dynamic values like 'current date', 'today', 'current time', etc.
    
    Returns: list of step description strings
    """
    heuristic_steps = heuristic_decompose_step(description)

    if not SECRET_KEY:
        print("[DECOMPOSE] Skipped: SECRET_KEY not configured")
        if len(heuristic_steps) > 1:
            print(f"[DECOMPOSE] Heuristic decomposition (no LLM): {heuristic_steps}")
            return heuristic_steps
        return [description]
    
    try:
        print(f"[DECOMPOSE] Analyzing step: {description}")
        
        # Get current date/time for dynamic value resolution
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        current_date_slash = now.strftime("%m/%d/%Y")
        current_time = now.strftime("%H:%M:%S")
        current_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
        
        prompt = (
            "You are a test automation assistant. Your job is to take a natural language "
            "test step and break it down into simple, atomic browser actions.\n\n"
            "Rules:\n"
            "1. Each atomic step should be ONE action: click, type/enter, select, hover, "
            "scroll, double click, right click, drag, wait, press, validate, or screenshot.\n"
            "2. ALWAYS CLICK BEFORE TYPING: Whenever ANY step involves entering/typing a value into a field, "
            "you MUST ALWAYS add a 'Click on [field]' step BEFORE the 'Enter' step. This applies even if "
            "the user only says 'Enter X' without mentioning a click. You must infer the target field from "
            "context and click it first. There are NO exceptions to this rule.\n"
            "3. Preserve quoted values EXACTLY as written.\n"
            "4. Resolve dynamic values:\n"
            f'   - "current date" or "today\'s date" or "today" -> "{current_date}" '
            f'(or "{current_date_slash}" if a slash format seems expected)\n'
            f'   - "current time" -> "{current_time}"\n'
            f'   - "current date and time" or "now" -> "{current_datetime}"\n'
            "5. If the step is already a single atomic action (e.g., 'Click login button'), "
            "return it as-is in the array.\n"
            "6. Each sub-step should be a clear, complete instruction that can be understood independently.\n"
            "7. Be smart about field identification - if the user says 'enter email abc@gmail.com', "
            "the field is the email field.\n"
            "8. DROPDOWN / SELECT INTERACTIONS: Selecting a value from a dropdown is a MULTI-STEP process. "
            "You must: (a) Click on the dropdown element to open it, (b) Add a short 'Wait 1 second' step "
            "for the dropdown options to appear, (c) Click on the specific option text. "
            "Do NOT use a bare 'select' action unless the element is a native HTML <select>. "
            "Most custom dropdowns (Material UI, Ant Design, PrimeNG, etc.) need click-wait-click.\n"
            "9. NTH ELEMENT / ORDINAL SELECTION: When the user references an ordinal like "
            "'second', 'third', '2nd', '3rd', etc., ALWAYS preserve the ordinal in the sub-step. "
            "E.g., 'Click the second Delete button' should stay as 'Click the second Delete button', "
            "NOT 'Click Delete button'.\n"
            "10. CHECKBOX / RADIO / TOGGLE: If the user says 'check', 'uncheck', 'toggle', or 'select' "
            "a checkbox or radio button, decompose as a click on that specific element.\n"
            "11. CLEAR THEN TYPE: If the user says 'clear and type', 'replace with', or 'change to', "
            "decompose as: (a) Click on the field, (b) Clear the field (output 'Clear the [field]'), "
            "(c) Enter the new value.\n"
            "12. KEYBOARD NAVIGATION: If the user mentions pressing Tab, Escape, Arrow keys, etc., "
            "output 'Press [Key]' as a separate atomic step.\n"
            "13. MULTI-FIELD FORMS: For steps like 'fill out the form with X, Y, Z', decompose "
            "into separate click + enter pairs for EACH field.\n"
            "14. CONFIRMATION DIALOGS / ALERTS: If the user says 'click X and confirm', decompose "
            "into: (a) Click the button, (b) Wait 1 second, (c) Click the confirm/OK/Yes button.\n"
            "15. AUTOCOMPLETE / SEARCH-SELECT: If the user says 'search and select X' or 'type X in "
            "the search dropdown and select it', decompose as: (a) Click on the search/input field, "
            "(b) Enter the search text, (c) Wait 1 second for results, (d) Click on the matching option.\n"
            "16. MULTIPLE SAME-NAMED ELEMENTS: If the user says something like 'click the Save button "
            "in the modal' or 'click the Submit button at the bottom', preserve the location/context qualifier "
            "in the sub-step so the locator AI can differentiate between multiple matching elements.\n"
            "17. FILE UPLOAD: If the user says 'upload file' or 'attach file', decompose as a click on "
            "the file input / upload button. The actual file selection is handled separately.\n"
            "18. FLEXIBLE PHRASING - PREPOSITIONS: Users write steps in many informal ways. "
            "ALL of these patterns mean the same thing and you MUST handle them identically:\n"
            "   - 'Select X from Y' / 'Select X in Y' / 'Select X as Y' / 'Select X Y' / 'Choose X Y' / 'Pick X Y'\n"
            "   - 'Enter X in Y' / 'Enter X into Y' / 'Type X in Y' / 'Put X in Y' / 'Write X in Y' / 'Enter X Y'\n"
            "   - 'Click X' / 'Click on X' / 'Press X' / 'Hit X' / 'Tap X'\n"
            "   - 'Check X' / 'Tick X' / 'Mark X' / 'Enable X' / 'Turn on X'\n"
            "   - 'Go to X' / 'Open X' / 'Navigate to X' / 'Visit X'\n"
            "   Regardless of which preposition or verb is used, understand the user's INTENT and decompose correctly.\n"
            "19. FLEXIBLE PHRASING - ACTION VERBS: Map informal verbs to correct browser actions:\n"
            "   - 'pick', 'choose', 'select' + field name -> dropdown interaction (click-wait-click)\n"
            "   - 'put', 'write', 'fill', 'input' -> type/enter into a text field\n"
            "   - 'hit', 'tap', 'press', 'push' a button -> click\n"
            "   - 'tick', 'mark', 'enable', 'turn on' -> click on a checkbox\n"
            "   - 'untick', 'unmark', 'disable', 'turn off' -> click on a checkbox to uncheck\n"
            "   - 'go to', 'open', 'visit', 'navigate to' -> navigate\n"
            "   - 'look for', 'find', 'search for', 'search' -> type in a search field\n"
            "20. INFER ELEMENT TYPE FROM CONTEXT: When the user doesn't explicitly say 'dropdown', 'field', "
            "'button', etc., INFER the element type from clues:\n"
            "   - 'Select X instance' / 'Select X in instance' -> 'instance' is most likely a dropdown\n"
            "   - 'Enter X username' / 'Type X in username' -> 'username' is most likely a text field\n"
            "   - 'Click submit' / 'Hit save' -> 'submit'/'save' are most likely buttons\n"
            "   - 'Check terms' / 'Tick agree' -> most likely checkboxes\n"
            "   Any field name the user mentions (instance, country, gender, role, status, category, priority, "
            "   department, etc.) should be treated as the element's label/name on the page.\n\n"
            "Examples:\n"
            '- Input: "Enter email \\"admin@test.com\\" and password \\"pass123\\""\n'
            '  Output: ["Click on email field", "Enter \\"admin@test.com\\" in email field", '
            '"Click on password field", "Enter \\"pass123\\" in password field"]\n\n'
            '- Input: "Enter current date in the date field"\n'
            f'  Output: ["Click on date field", "Enter \\"{current_date}\\" in date field"]\n\n'
            '- Input: "Double click on text and type \\"hello\\""\n'
            '  Output: ["Double click on text field", "Enter \\"hello\\" in text field"]\n\n'
            '- Input: "Click login button"\n'
            '  Output: ["Click login button"]\n\n'
            '- Input: "Select \\"India\\" from the Country dropdown"\n'
            '  Output: ["Click on the Country dropdown", "Wait 1 second", "Click on \\"India\\" option"]\n\n'
            '- Input: "Select \\"Male\\" from Gender dropdown and \\"India\\" from Country dropdown"\n'
            '  Output: ["Click on the Gender dropdown", "Wait 1 second", "Click on \\"Male\\" option", '
            '"Click on the Country dropdown", "Wait 1 second", "Click on \\"India\\" option"]\n\n'
            '- Input: "Click the second Delete button"\n'
            '  Output: ["Click the second Delete button"]\n\n'
            '- Input: "Check the Remember me checkbox"\n'
            '  Output: ["Click on the Remember me checkbox"]\n\n'
            '- Input: "Clear the search field and type \\"new query\\""\n'
            '  Output: ["Click on the search field", "Clear the search field", '
            '"Enter \\"new query\\" in the search field"]\n\n'
            '- Input: "Click Save and confirm the dialog"\n'
            '  Output: ["Click Save button", "Wait 1 second", "Click the confirm button in the dialog"]\n\n'
            '- Input: "Search for \\"React\\" in the skills dropdown and select it"\n'
            '  Output: ["Click on the skills dropdown", "Enter \\"React\\" in the skills search field", '
            '"Wait 1 second", "Click on \\"React\\" option"]\n\n'
            '- Input: "Select abcd instance"\n'
            '  Output: ["Click on the instance dropdown", "Wait 1 second", "Click on \\"abcd\\" option"]\n\n'
            '- Input: "Select abcd as instance"\n'
            '  Output: ["Click on the instance dropdown", "Wait 1 second", "Click on \\"abcd\\" option"]\n\n'
            '- Input: "Select abcd in instance"\n'
            '  Output: ["Click on the instance dropdown", "Wait 1 second", "Click on \\"abcd\\" option"]\n\n'
            '- Input: "Choose \\"Admin\\" role"\n'
            '  Output: ["Click on the role dropdown", "Wait 1 second", "Click on \\"Admin\\" option"]\n\n'
            '- Input: "Pick High priority"\n'
            '  Output: ["Click on the priority dropdown", "Wait 1 second", "Click on \\"High\\" option"]\n\n'
            '- Input: "Put \\"john@test.com\\" in email"\n'
            '  Output: ["Click on the email field", "Enter \\"john@test.com\\" in email field"]\n\n'
            '- Input: "Write \\"Hello World\\" in description"\n'
            '  Output: ["Click on the description field", "Enter \\"Hello World\\" in description field"]\n\n'
            '- Input: "Hit the submit button"\n'
            '  Output: ["Click the submit button"]\n\n'
            '- Input: "Tick the agree to terms checkbox"\n'
            '  Output: ["Click on the agree to terms checkbox"]\n\n'
            '- Input: "Go to settings page"\n'
            '  Output: ["Click on settings page"]\n\n'
            '- Input: "Enter \\"admin@test.com\\""\n'
            '  Output: ["Click on the email field", "Enter \\"admin@test.com\\" in the email field"]\n\n'
            '- Input: "Enter \\"admin@test.com\\" email"\n'
            '  Output: ["Click on email field", "Enter \\"admin@test.com\\" in email field"]\n\n'
            '- Input: "Type \\"john\\" username"\n'
            '  Output: ["Click on username field", "Enter \\"john\\" in username field"]\n\n'
            '- Input: "Enter \\"pass123\\" in the password field"\n'
            '  Output: ["Click on the password field", "Enter \\"pass123\\" in the password field"]\n\n'
            f'Now decompose this step:\n"{description}"\n\n'
            "Return ONLY a JSON array of strings. No explanation, no markdown, just the JSON array."
        )

        payload = {
            "model": "gpt-5-mini",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        req_data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            LLM_API_URL,
            data=req_data,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {SECRET_KEY}'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode('utf-8'))
            
            if result.get('choices') and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].strip()
                print(f"[DECOMPOSE] LLM response: {content}")
                
                # Parse JSON from response (may be wrapped in markdown code blocks)
                json_str = content
                if '```json' in content:
                    json_str = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    json_str = content.split('```')[1].split('```')[0].strip()
                
                sub_steps = json.loads(json_str)
                
                if isinstance(sub_steps, list) and len(sub_steps) > 0:
                    sub_steps = [s.strip() for s in sub_steps if isinstance(s, str) and s.strip()]
                    if sub_steps:
                        if len(sub_steps) == 1 and len(heuristic_steps) > 1:
                            # Prevent false "single-click pass" for chained action instructions.
                            print(f"[DECOMPOSE] Heuristic override for multi-action step: {heuristic_steps}")
                            return heuristic_steps
                        print(f"[DECOMPOSE] Decomposed into {len(sub_steps)} sub-steps: {sub_steps}")
                        return sub_steps
        
        print(f"[DECOMPOSE] No decomposition needed, using original step")
        if len(heuristic_steps) > 1:
            print(f"[DECOMPOSE] Heuristic decomposition fallback: {heuristic_steps}")
            return heuristic_steps
        return [description]
        
    except Exception as e:
        print(f"[DECOMPOSE] Error: {str(e)[:100]}, using original step")
        if len(heuristic_steps) > 1:
            print(f"[DECOMPOSE] Heuristic decomposition after error: {heuristic_steps}")
            return heuristic_steps
        return [description]


def execute_all_tests_with_playwright(test_cases, website_url, job_id):
    """Execute all test cases using a single browser instance."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ImportError(f'playwright-missing: {str(e)}')

    if not website_url:
        raise ValueError('website_url is required for execution')

    all_test_results = []
    browser = None
    
    try:
        with sync_playwright() as p:
            try:
                # Launch ONCE for all tests with specific viewport
                browser = p.chromium.launch(headless=False)
                print(f"[BROWSER] Launched browser instance with 1920x1080 resolution")
                # Bring window to front
                bring_window_to_front()
                print(f"[BROWSER] Bringing window to front...")
            except Exception as e:
                raise Exception(f'Failed to launch browser: {str(e)}')
            
            # Execute each test case in the same browser with reused page
            page = None
            for test_idx, test_case in enumerate(test_cases):
                test_name = test_case.get('test_name', 'Unknown')
                steps = test_case.get('steps', [])
                
                print(f"\n\n{'='*70}")
                print(f"TEST {test_idx + 1}/{len(test_cases)}: {test_name}")
                print(f"{'='*70}\n")
                
                # Execute test case with shared browser and page
                test_output, page = execute_single_test(browser, steps, website_url, job_id, test_name, page)
                all_test_results.append({
                    'test_name': test_name,
                    'results': test_output["steps"],
                    'networkLogs': test_output["networkLogs"],
                    'consoleLogs': test_output["consoleLogs"]
                })
            
            # Close page after all tests
            if page:
                page.close()
                print(f"[BROWSER] Page closed")
            
            # Close the playwright script
            close_script()
            
            # Close browser after all tests
            browser.close()
            print(f"\n[BROWSER] Browser closed")
    
    except Exception as e:
        if browser:
            try:
                browser.close()
            except:
                pass
        raise
    
    return all_test_results

def execute_single_test(browser, steps, website_url, job_id, test_name, page=None):
    """Execute a single test case within an existing browser. Reuses page if provided."""
    results = []
    network_logs = []
    console_logs = []
    page_created_here = False
    last_dom_snapshot = None
    last_dom_kind = None
    last_dom_reason = ''
    last_dom_marker = None
    current_step_marker = None
    last_sidebar_click_key = None

    def capture_and_store_dom(snapshot_kind='full', include_testid=True, reason=''):
        """Capture DOM snapshot for diagnostics and LLM context reuse."""
        nonlocal last_dom_snapshot, last_dom_kind, last_dom_reason, last_dom_marker
        try:
            raw_dom = get_sidebar_dom_snapshot(page) if snapshot_kind == 'sidebar' else get_page_dom_simple(page)
            dom_payload = raw_dom
            if include_testid:
                testid_summary = extract_data_testid_summary(page)
                dom_payload = testid_summary + "\n" + raw_dom if testid_summary else raw_dom

            last_dom_snapshot = dom_payload
            last_dom_kind = snapshot_kind
            last_dom_reason = reason or ''
            last_dom_marker = current_step_marker
            print(f"[DOM] Captured {snapshot_kind} DOM" + (f" ({reason})" if reason else ""))
            return dom_payload
        except Exception as e:
            err = f"[DOM Capture Error] {str(e)[:120]}"
            print(err)
            last_dom_snapshot = err
            last_dom_kind = snapshot_kind
            last_dom_reason = reason or 'capture-error'
            last_dom_marker = current_step_marker
            return None

    def wait_for_dom_settle(timeout_ms=1800, quiet_ms=300, label=''):
        """Wait briefly for delayed DOM mutations to settle."""
        try:
            info = page.evaluate(
                '''async ({timeoutMs, quietMs}) => {
                    const root = document.body || document.documentElement;
                    if (!root) return { changed: false, mutationCount: 0, timedOut: false };

                    return await new Promise((resolve) => {
                        let mutationCount = 0;
                        let done = false;
                        let quietTimer = null;
                        let hardTimer = null;

                        const finish = (timedOut = false) => {
                            if (done) return;
                            done = true;
                            if (quietTimer) clearTimeout(quietTimer);
                            if (hardTimer) clearTimeout(hardTimer);
                            observer.disconnect();
                            resolve({
                                changed: mutationCount > 0,
                                mutationCount,
                                timedOut
                            });
                        };

                        const onMutation = (mutations) => {
                            mutationCount += (mutations || []).length;
                            if (quietTimer) clearTimeout(quietTimer);
                            quietTimer = setTimeout(() => finish(false), quietMs);
                        };

                        const observer = new MutationObserver(onMutation);
                        observer.observe(root, {
                            subtree: true,
                            childList: true,
                            attributes: true,
                            characterData: true
                        });

                        // If no mutations occur, settle quickly.
                        quietTimer = setTimeout(() => finish(false), quietMs);
                        hardTimer = setTimeout(() => finish(true), timeoutMs);
                    });
                }''',
                {'timeoutMs': int(timeout_ms), 'quietMs': int(quiet_ms)}
            )
            info = info or {}
            print(
                f"[DOM] Settle check{f' ({label})' if label else ''}: "
                f"changed={bool(info.get('changed'))}, "
                f"mutations={int(info.get('mutationCount') or 0)}, "
                f"timedOut={bool(info.get('timedOut'))}"
            )
            return info
        except Exception as e:
            print(f"[DOM] Settle check failed{f' ({label})' if label else ''}: {str(e)[:120]}")
            return {'changed': False, 'mutationCount': 0, 'timedOut': True}

    def refresh_dom_after_click(reason_prefix):
        """
        Capture DOM immediately after click, then recapture if delayed mutations appear.
        Latest capture overwrites older snapshot so stale DOM is discarded.
        """
        capture_and_store_dom('full', include_testid=True, reason=f'{reason_prefix}-initial')
        settle_info = wait_for_dom_settle(timeout_ms=2500, quiet_ms=300, label=reason_prefix)
        if settle_info.get('changed'):
            capture_and_store_dom('full', include_testid=True, reason=f'{reason_prefix}-after-mutation')
            print(f"[DOM] Refreshed post-click DOM after delayed mutations ({reason_prefix})")
    
    try:
        # Reuse page if provided, otherwise create new page
        if page is None:
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page_created_here = True
            print(f"[BROWSER] Created new page with 1920x1080 resolution")
            page.on("console", lambda msg: console_logs.append({
                "type": msg.type,
                "text": msg.text,
                "location": msg.location
            }))

            page.on("request", lambda request: network_logs.append({
                "event": "request",
                "url": request.url,
                "method": request.method,
                "resourceType": request.resource_type
            }))

            page.on("response", lambda response: network_logs.append({
                "event": "response",
                "url": response.url,
                "status": response.status,
                "ok": response.ok
            }))

            page.on("requestfailed", lambda request: network_logs.append({
                "event": "requestfailed",
                "url": request.url,
                "failure": request.failure
            }))
            
            # Make browser window active
            page.evaluate("window.focus()")
            bring_window_to_front()
            print(f"[BROWSER] Browser window activated and brought to front")
        else:
            print(f"[BROWSER] Reusing existing page from previous test")
        
        # Navigate to the website
        global SCRIPT_URL
        SCRIPT_URL = website_url
        try:
            page.goto(website_url, timeout=30000)
            print(f"[EXECUTE] Navigated to {website_url}")
            # Wait for any initial loaders to clear
            wait_for_loader(page)
            results.append({'step': 'navigate', 'ok': True, 'url': website_url})
            print(f"[EXECUTE] Page ready after navigation")
        except Exception as e:
            page.close()
            raise Exception(f'Failed to navigate to {website_url}: {str(e)}')
        
        # Execute each step
        total_steps = len(steps)
        for idx, step in enumerate(steps):
            # Check for stop signal before each step
            stop_path = os.path.join(UPLOAD_DIR, f".{job_id}.stop")
            if os.path.exists(stop_path):
                print(f"\n[EXECUTE] STOP SIGNAL RECEIVED - Halting execution at step {idx+1}/{total_steps}")
                try:
                    os.remove(stop_path)
                except:
                    pass
                break  # Exit the loop
            
            print(f"\n[EXECUTE] ========== Step {idx+1}/{total_steps} ==========")
            
            # Handle both string steps (new format) and dict steps (legacy format)
            if isinstance(step, str):
                # New format: step is just a string description
                description = step
                raw_action = ''
            else:
                # Legacy format: step is a dictionary
                raw_action = str(step.get('action', '')).strip().lower()
                description = None
                
                # Find description from non-action columns
                for col, val in step.items():
                    col_lower = str(col).lower()
                    if col_lower not in ['action', 'selector', 'value', 'url']:
                        val_str = str(val).strip()
                        if val_str and not description:
                            description = val_str
                            break
            
            # === AI STEP DECOMPOSITION ===
            # Break compound steps into atomic sub-steps using AI
            if not raw_action and description:
                sub_steps = decompose_step_with_ai(description)
            else:
                sub_steps = [description or '']
            
            # Execute each sub-step (usually 1, but compound steps produce multiple)
            step_failed = False
            for sub_idx, sub_step_desc in enumerate(sub_steps):
                if len(sub_steps) > 1:
                    print(f"[EXECUTE]   --- Sub-step {sub_idx+1}/{len(sub_steps)}: {sub_step_desc} ---")
                
                # Write progress
                progress_desc = f"{description} (sub-step {sub_idx+1}/{len(sub_steps)})" if len(sub_steps) > 1 else (description or '')
                write_progress(job_id, results, idx, total_steps, progress_desc)
                
                # Use the sub-step description for parsing and execution
                description_for_exec = sub_step_desc
                current_step_marker = f"{idx}:{sub_idx}"
                previous_substep_sidebar_click = (
                    sub_idx > 0 and last_sidebar_click_key == f"{idx}:{sub_idx - 1}"
                )
                substep_sidebar_click_success = False
                
                # Parse the (sub-)step
                if not raw_action and sub_step_desc:
                    parsed = parse_natural_language_step(sub_step_desc)
                    action = parsed.get('action')
                    value = parsed.get('value')
                    search_text = parsed.get('search_text', '')
                    print(f"[EXECUTE] Step: {sub_step_desc}")
                    print(f"[EXECUTE] Parsed action: {action}, value: {value}")
                elif raw_action:
                    action = raw_action
                    value = step.get('value') if isinstance(step, dict) else None
                    search_text = description if description else ''
                    description_for_exec = description
                    print(f"[EXECUTE] Step: {description if description else action}")
                    print(f"[EXECUTE] Action: {action}, value: {value}")
                else:
                    result_item = {'step': idx, 'description': description or '', 'action': '', 'ok': False, 'error': 'No action or description found'}
                    results.append(result_item)
                    print(f"[EXECUTE] FAILED: No action found - stopping execution")
                    step_failed = True
                    break
                
                # Handle different actions
                action_failed = False
                try:
                    if action in ('goto', 'navigate'):
                        url = step.get('url') or website_url
                        print(f"[EXECUTE] Navigating to: {url}")
                        page.goto(url, timeout=30000)
                        results.append({'step': idx, 'action': 'navigate', 'ok': True, 'url': url})
                        print(f"[EXECUTE] SUCCESS: Navigated")
                        import time
                        time.sleep(1)  # Wait for page to load
                        
                    elif action == 'wait':
                        import time
                        ms = int(value) if value else 2000
                        print(f"[EXECUTE] Waiting {ms}ms")
                        time.sleep(ms / 1000.0)
                        results.append({'step': idx, 'action': 'wait', 'ok': True, 'ms': ms})
                        print(f"[EXECUTE] SUCCESS: Wait completed")
                        
                    elif action == 'screenshot':
                        out = os.path.join(UPLOAD_DIR, f"{int(__import__('time').time())}-step{idx}-shot.png")
                        page.screenshot(path=out)
                        print(f"[EXECUTE] Screenshot saved: {out}")
                        results.append({'step': idx, 'action': 'screenshot', 'ok': True, 'path': out})
                        print(f"[EXECUTE] SUCCESS: Screenshot taken")
                        
                    elif action == 'scroll' and value != 'element':
                        # Standalone scroll (no element target) — no locator needed
                        import time
                        print(f"[EXECUTE] Scrolling: {value}")
                        if value == 'top':
                            page.evaluate("window.scrollTo(0, 0)")
                        elif value == 'bottom':
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        else:
                            # Parse direction and optional pixel amount
                            direction = 'down'
                            pixels = 300  # default
                            if ':' in str(value):
                                parts = str(value).split(':')
                                direction = parts[0]
                                pixels = int(parts[1])
                            elif value == 'up':
                                direction = 'up'
                            
                            scroll_amount = -pixels if direction == 'up' else pixels
                            page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                        
                        time.sleep(0.3)  # let the scroll settle
                        results.append({'step': idx, 'description': description_for_exec, 'action': 'scroll', 'ok': True, 'value': str(value)})
                        print(f"[EXECUTE] SUCCESS: Scroll {value}")
                    
                    elif action == 'drag':
                        # Drag and drop needs TWO locators: source and target
                        print(f"[EXECUTE] Action 'drag' - Waiting for page to be ready...")
                        wait_for_loader(page)
                        print(f"[EXECUTE] Capturing DOM...")
                        dom = capture_and_store_dom('full', include_testid=True, reason='drag-locator')
                        
                        # Find source element
                        source_desc = search_text
                        print(f"[EXECUTE] Finding drag source: {source_desc}")
                        src_locator, src_type = get_locator_from_ai(dom, f"Find the element to drag: {source_desc}")
                        if not src_locator:
                            error_msg = f'Could not find drag source: "{source_desc}"'
                            print(f"[EXECUTE] FAILED: {error_msg}")
                            results.append({'step': idx, 'description': description_for_exec, 'action': 'drag', 'ok': False, 'error': error_msg})
                            action_failed = True
                        else:
                            # Find target element
                            target_desc = value
                            print(f"[EXECUTE] Finding drop target: {target_desc}")
                            tgt_locator, tgt_type = get_locator_from_ai(dom, f"Find the drop target element: {target_desc}")
                            if not tgt_locator:
                                error_msg = f'Could not find drop target: "{target_desc}"'
                                print(f"[EXECUTE] FAILED: {error_msg}")
                                results.append({'step': idx, 'description': description_for_exec, 'action': 'drag', 'ok': False, 'error': error_msg})
                                action_failed = True
                            else:
                                try:
                                    src_fmt = f'xpath={src_locator}' if src_type == 'xpath' else src_locator
                                    tgt_fmt = f'xpath={tgt_locator}' if tgt_type == 'xpath' else tgt_locator
                                    print(f"[EXECUTE] Dragging {src_fmt} -> {tgt_fmt}")
                                    page.drag_and_drop(src_fmt, tgt_fmt)
                                    init_script()
                                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    if description_for_exec:
                                        append_script_line(f"// step: {description_for_exec}")
                                    append_script_line(f"// {timestamp} drag and drop")
                                    append_script_line(f"await page.dragAndDrop(`{js_safe(src_fmt)}`, `{js_safe(tgt_fmt)}`);")
                                    results.append({'step': idx, 'description': description_for_exec, 'action': 'drag', 'ok': True, 'source': src_locator, 'target': tgt_locator})
                                    print(f"[EXECUTE] SUCCESS: {description_for_exec}")
                                    wait_for_loader(page)
                                except Exception as e:
                                    error_msg = str(e)[:150]
                                    print(f"[EXECUTE] FAILED: Drag and drop - {error_msg}")
                                    results.append({'step': idx, 'description': description_for_exec, 'action': 'drag', 'ok': False, 'error': error_msg})
                                    action_failed = True
                    
                    elif action in ('click', 'type', 'fill', 'select', 'press', 'validate', 'hover', 'dblclick', 'rightclick') or (action == 'scroll' and value == 'element'):
                        # For ALL interactive actions, wait for loader first
                        print(f"[EXECUTE] Action '{action}' - Waiting for page to be ready...")
                        wait_for_loader(page)
                        if action == 'click':
                            # Allow previous click-triggered async UI changes to materialize.
                            wait_for_dom_settle(timeout_ms=1500, quiet_ms=250, label='pre-click-locator')

                        if action == 'press':
                            # Press action doesn't need LLM locator, but still gets DOM for context
                            key = str(value) if value else 'Enter'
                            print(f"[EXECUTE] Pressing key: {key}")
                            page.press('body', key)
                            results.append({'step': idx, 'action': 'press', 'ok': True, 'key': key})
                            print(f"[EXECUTE] SUCCESS: Pressed key '{key}'")
                        
                        elif action == 'validate':
                            # Validate action: check if text exists on page or in specific element
                            print(f"[EXECUTE] Validating: {value}")
                            
                            # Check if text appears anywhere on page
                            try:
                                page_text = page.locator('body').text_content()
                                if value.lower() in page_text.lower():
                                    results.append({
                                        'step': idx, 
                                        'description': description_for_exec,
                                        'action': 'validate', 
                                        'ok': True, 
                                        'validated_text': value
                                    })
                                    print(f"[EXECUTE] SUCCESS: {description_for_exec}")
                                else:
                                    error_msg = f'Validation failed: Text "{value}" not found on page'
                                    print(f"[EXECUTE] FAILED: {description_for_exec} - {error_msg}")
                                    results.append({'step': idx, 'description': description_for_exec, 'action': 'validate', 'ok': False, 'error': error_msg})
                                    action_failed = True
                            except Exception as e:
                                error_msg = f'Validation error: {str(e)[:100]}'
                                print(f"[EXECUTE] FAILED: {description_for_exec} - {error_msg}")
                                results.append({'step': idx, 'description': description_for_exec, 'action': 'validate', 'ok': False, 'error': error_msg})
                                action_failed = True
                        
                        else:
                            sidebar_info = None
                            action_handled = False
                            effective_sidebar_context = False

                            # 1) Deterministic sidebar resolver first for click actions.
                            if action == 'click':
                                print("[EXECUTE] Trying deterministic sidebar resolver...")
                                sidebar_ok, sidebar_info = click_sidebar_target(page, description_for_exec or search_text)
                                effective_sidebar_context = bool(sidebar_info and sidebar_info.get('is_sidebar_context'))

                                if previous_substep_sidebar_click and not effective_sidebar_context:
                                    if sidebar_info is None:
                                        sidebar_info = {}
                                    sidebar_info['is_sidebar_context'] = True
                                    sidebar_info['contextHint'] = 'previous-sub-step-sidebar-click'
                                    effective_sidebar_context = True
                                    print("[EXECUTE] Forcing sidebar context from previous sidebar sub-step")

                                if sidebar_ok:
                                    locator = sidebar_info.get('locator')
                                    locator_type = sidebar_info.get('type', 'xpath')
                                    print(f"[EXECUTE] Sidebar resolver clicked: {locator}")

                                    wait_for_loader(page)
                                    refresh_dom_after_click('post-click-sidebar-deterministic')
                                    results.append({
                                        'step': idx,
                                        'description': description_for_exec,
                                        'action': action,
                                        'ok': True,
                                        'locator': locator,
                                        'type': locator_type,
                                        'value': str(value)[:50] if value else None,
                                        'resolver': 'sidebar-deterministic',
                                        'matchTier': sidebar_info.get('matchTier'),
                                        'matchScore': sidebar_info.get('matchScore'),
                                        'sidebarAutoOpened': sidebar_info.get('sidebarAutoOpened', False),
                                    })
                                    print(f"[EXECUTE] SUCCESS: {description_for_exec} (sidebar-deterministic)")
                                    action_handled = True
                                    substep_sidebar_click_success = True
                                elif sidebar_info and sidebar_info.get('status') == 'ambiguous':
                                    # For ambiguous sidebar targets, fail explicitly to avoid wrong clicks.
                                    candidates = sidebar_info.get('topCandidates') or []
                                    candidate_blob = ", ".join(
                                        f"{c.get('label')}({c.get('score')})" for c in candidates
                                    ) if candidates else "none"
                                    error_msg = (
                                        f'Sidebar target is ambiguous for "{description_for_exec}". '
                                        f'Candidates: {candidate_blob}'
                                    )
                                    print(f"[EXECUTE] FAILED: {error_msg}")
                                    results.append({
                                        'step': idx,
                                        'description': description_for_exec,
                                        'action': action,
                                        'ok': False,
                                        'error': error_msg,
                                        'resolver': 'sidebar-deterministic',
                                        'matchTier': sidebar_info.get('matchTier'),
                                        'matchScore': sidebar_info.get('matchScore'),
                                        'sidebarAutoOpened': sidebar_info.get('sidebarAutoOpened', False),
                                    })
                                    action_failed = True
                                    action_handled = True
                                elif sidebar_info:
                                    print(
                                        f"[EXECUTE] Sidebar resolver fallback: "
                                        f"status={sidebar_info.get('status')} reason={sidebar_info.get('message', '')}"
                                    )

                            if not action_handled and not action_failed:
                                resolver = 'llm'
                                locator, locator_type = None, None

                                # 2) Fast structural resolver is sidebar-only.
                                use_fast_sidebar = (
                                    action == 'click'
                                    and sidebar_info
                                    and effective_sidebar_context
                                )
                                if use_fast_sidebar:
                                    resolver = 'fast-locator'
                                    locator, locator_type = try_fast_locator(page, description_for_exec or search_text)

                                # 3) LLM remains the main locator path.
                                llm_attempted = False
                                llm_used_sidebar_dom = False
                                if not locator:
                                    resolver = 'llm'
                                    print(f"[EXECUTE] Capturing DOM for LLM locator...")
                                    if action == 'click' and sidebar_info and effective_sidebar_context:
                                        print("[EXECUTE] Using sidebar-focused DOM snapshot for LLM fallback")
                                        dom = capture_and_store_dom('sidebar', include_testid=True, reason='llm-sidebar')
                                        llm_used_sidebar_dom = True
                                    else:
                                        print("[EXECUTE] Using full-page DOM snapshot for LLM fallback")
                                        dom = capture_and_store_dom('full', include_testid=True, reason='llm-full')

                                    llm_attempted = True
                                    locator, locator_type = get_locator_from_ai(dom or '', description_for_exec or search_text)

                                if (
                                    not locator
                                    and llm_attempted
                                    and action == 'click'
                                    and effective_sidebar_context
                                ):
                                    print("[EXECUTE] LLM returned no locator; retrying once with fresh sidebar DOM...")
                                    wait_for_dom_settle(timeout_ms=1600, quiet_ms=250, label='llm-null-sidebar-retry')
                                    retry_dom = capture_and_store_dom('sidebar', include_testid=True, reason='llm-sidebar-retry')
                                    llm_used_sidebar_dom = True
                                    locator, locator_type = get_locator_from_ai(
                                        retry_dom or '',
                                        description_for_exec or search_text
                                    )

                                if not locator:
                                    error_msg = f'Could not find locator for: "{description_for_exec or search_text}"'
                                    print(f"[EXECUTE] FAILED: {description_for_exec} - {error_msg}")
                                    results.append({
                                        'step': idx,
                                        'description': description_for_exec,
                                        'action': action,
                                        'ok': False,
                                        'error': error_msg,
                                        'resolver': resolver,
                                        'sidebarAutoOpened': (sidebar_info.get('sidebarAutoOpened') if sidebar_info else False),
                                    })
                                    action_failed = True
                                else:
                                    # Got locator from fast resolver or LLM, now perform the action
                                    print(f"[EXECUTE] Got locator: {locator} (type: {locator_type}, resolver: {resolver})")
                                    print(f"[EXECUTE] Performing action: {action}...")

                                    success, error = use_locator(
                                        page, locator, locator_type, action, value, step_description=description_for_exec
                                    )

                                    if success:
                                        # After click/interactive action, wait for any loaders
                                        if action in ('click', 'hover', 'dblclick', 'rightclick'):
                                            print(f"[EXECUTE] {action.title()} executed, waiting for page to settle...")
                                            wait_for_loader(page)
                                        if action == 'click':
                                            refresh_dom_after_click(f'post-click-{resolver}')
                                        elif action in ('dblclick', 'rightclick'):
                                            capture_and_store_dom(
                                                'full',
                                                include_testid=True,
                                                reason=f'post-{action}-{resolver}'
                                            )

                                        results.append({
                                            'step': idx,
                                            'description': description_for_exec,
                                            'action': action,
                                            'ok': True,
                                            'locator': locator,
                                            'type': locator_type,
                                            'value': str(value)[:50] if value else None,
                                            'resolver': resolver,
                                            'sidebarAutoOpened': (sidebar_info.get('sidebarAutoOpened') if sidebar_info else False),
                                        })
                                        print(f"[EXECUTE] SUCCESS: {description_for_exec}")
                                        if action == 'click':
                                            substep_sidebar_click_success = bool(effective_sidebar_context or llm_used_sidebar_dom)
                                    else:
                                        results.append({
                                            'step': idx,
                                            'description': description_for_exec,
                                            'action': action,
                                            'ok': False,
                                            'error': error,
                                            'locator': locator,
                                            'type': locator_type,
                                            'resolver': resolver,
                                            'sidebarAutoOpened': (sidebar_info.get('sidebarAutoOpened') if sidebar_info else False),
                                        })
                                        print(f"[EXECUTE] FAILED: {description_for_exec} - {error}")
                                        action_failed = True
                    
                    else:
                        result_item = {'step': idx, 'description': description_for_exec, 'action': action, 'ok': False, 'error': f'Unknown action: {action}'}
                        results.append(result_item)
                        print(f"[EXECUTE] FAILED: Unknown action: {action}")
                        action_failed = True
                    
                    # Delay between steps
                    import time
                    time.sleep(0.5)
                    
                except Exception as e:
                    error_msg = str(e)[:200]
                    print(f"[EXECUTE] EXCEPTION: {error_msg}")
                    results.append({'step': idx, 'description': description_for_exec if 'description_for_exec' in locals() else '', 'action': action if 'action' in locals() else '', 'ok': False, 'error': error_msg})
                    action_failed = True

                if action_failed:
                    # Ensure latest DOM snapshot is persisted to debug log for this failed step.
                    if last_dom_marker != current_step_marker:
                        capture_and_store_dom('full', include_testid=True, reason='failure-step-final')
                    if results and results[-1].get('ok') is False:
                        if last_dom_snapshot:
                            debug_block = (
                                "\n[FAILED_STEP_DOM]\n"
                                f"step_index={idx}\n"
                                f"sub_step_index={sub_idx}\n"
                                f"description={description_for_exec if 'description_for_exec' in locals() else ''}\n"
                                f"action={action if 'action' in locals() else ''}\n"
                                f"dom_kind={last_dom_kind}\n"
                                f"dom_reason={last_dom_reason}\n"
                                f"{last_dom_snapshot}\n"
                                "[END_FAILED_STEP_DOM]\n"
                            )
                            append_debug_log(job_id, debug_block)

                if not action_failed:
                    last_sidebar_click_key = current_step_marker if substep_sidebar_click_success else None
  
                # STOP SUB-STEP EXECUTION IF FAILED
                if action_failed:
                    print(f"[EXECUTE] Sub-step failed - stopping execution")
                    step_failed = True
                    break
            
            # STOP EXECUTION IF STEP FAILED
            if step_failed:
                print(f"[EXECUTE] Step {idx} failed - stopping execution")
                break
        
        # Return results and page (don't close page - will reuse for next test)
        return {
            "steps": results,
            "networkLogs": network_logs,
            "consoleLogs": console_logs
        }, page
    
    except Exception as e:
        # Only close page if we created it here and something failed
        if page and page_created_here:
            try:
                page.close()
            except:
                pass
        raise

def main():
    if len(sys.argv) < 3:
        print('Usage: worker.py <filePath> <jobId> [websiteUrl]')
        sys.exit(2)

    file_path = sys.argv[1]
    job_id = sys.argv[2]
    website_url = sys.argv[3] if len(sys.argv) > 3 else ''
    
    # Debug: log received arguments
    import sys as _sys
    with open(os.path.join(UPLOAD_DIR, f"{job_id}.debug.log"), 'w') as f:
        f.write(f"Args: {_sys.argv}\n")
        f.write(f"file_path: {file_path}\n")
        f.write(f"job_id: {job_id}\n")
        f.write(f"website_url: '{website_url}'\n")
        f.write(f"website_url type: {type(website_url)}\n")
        f.write(f"website_url bool: {bool(website_url)}\n")
        f.write(f"len(website_url): {len(website_url)}\n")
    
    result = {'success': False, 'jobId': job_id, 'parsed': None, 'executed': None, 'error': None}

    try:
        test_cases = parse_excel(file_path)
        result['parsed'] = test_cases
    except ImportError as e:
        result['error'] = f'parse-failed:{e}'
        write_result(job_id, result)
        sys.exit(0)
    except Exception as e:
        result['error'] = f'parse-failed:{e}'
        write_result(job_id, result)
        sys.exit(0)

    # Try to execute each test case using Playwright if available and websiteUrl is provided
    if website_url and len(website_url) > 0:
        try:
            # Execute all test cases with a single browser
            exec_res = execute_all_tests_with_playwright(test_cases, website_url, job_id)
            result['executed'] = exec_res
            result['success'] = True
        except ImportError as e:
            result['success'] = False
            result['error'] = f'execution-skipped:{e}'
        except Exception as e:
            result['success'] = False
            result['error'] = f'execution-failed:{e}'
    else:
        # No website URL provided, just return parsed steps
        result['success'] = True
        result['error'] = f'execution-skipped:no-website-url-provided (url="{website_url}")'

    write_result(job_id, result)

if __name__ == '__main__':
    main()
