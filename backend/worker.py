#!/usr/bin/env python3
import sys
import os
import json
import re
import difflib
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
        prompt = f"""You are a web automation expert. Given the DOM of a webpage and a test step description, 
find a UNIQUE XPath to locate the PRIMARY element that should be interacted with.


## CRITICAL RULES:
1. Return ONLY ONE JSON object - NOT a list or array - this is MANDATORY
2. DO NOT Use svg tags in the XPath directly. Instead, identify the purpose of the icon (e.g. menu, upload) and look for parent buttons or aria-labels or any other reliable thing that indicate its function.
2. Focus on the PRIMARY element mentioned in the step (the one that will be acted upon first)
3. **PRIORITY**: Always look for and prioritize elements with `data-testid` attributes (very reliable)
4. Return ONLY XPath locators (no CSS selectors)
5. The XPath must be UNIQUE and reliable - it should match exactly ONE element
6. Prefer using attributes in this order:
   - `data-testid` (most reliable, explicitly set for testing)
   - `id`, `name`, `aria-label`, `placeholder`
   - Text content (exact or contains)
   - Combination of attributes for uniqueness
7. Make the XPath specific enough that it won't match other similar elements
8. **For SVGs and icons**: Identify the action/purpose, not just the visual. Look for parent buttons or aria-labels
9. For hamburger icons or menu icons(svg), always return `//*[@data-testid='menu-icon']` if available. Only use fallbacks if not present.

## Example good XPaths (with data-testid priority):
   - //button[@data-testid='upload-button']
   - //input[@data-testid='email-input']
   - //input[@placeholder='Email address']
   - //button[contains(text(), 'Login')]
   - //select[@name='country']
   - //button[@aria-label='Close']

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
    """Get complete DOM snapshot including iframes and Shadow DOM for AI analysis"""
    try:
        dom_snapshot = page.evaluate('''() => {
    function getVisibleDOMSnapshot() {
        const getAttributes = (node) => {
            if (!node.attributes) return '';
            let attrs = '';
            for (const attr of node.attributes) {
                if (['id','class','name','data-testid','role','aria-label','placeholder','title','href'].includes(attr.name)) {
                    attrs += ` ${attr.name}="${attr.value}"`;
                }
            }
            return attrs;
        };

        const serializeNode = (node, indent = '') => {
            if (node.nodeType !== Node.ELEMENT_NODE) return '';
            const tag = node.tagName.toLowerCase();
            if (['script','style','link','meta'].includes(tag)) return '';

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

def use_locator(page, locator, locator_type, action, value=None):
    """
    Execute an action using the locator, handling both CSS selectors and XPath.
    Args:
        page: Playwright page object
        locator: CSS selector or XPath string
        locator_type: 'css' or 'xpath'
        action: 'click', 'fill', 'select', 'press'
        value: Value for fill/select actions
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


def decompose_step_with_ai(description):
    """
    Use AI to decompose a compound natural language step into atomic sub-steps.
    Also resolves dynamic values like 'current date', 'today', 'current time', etc.
    
    Returns: list of step description strings
    """
    if not SECRET_KEY:
        print("[DECOMPOSE] Skipped: SECRET_KEY not configured")
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
                        print(f"[DECOMPOSE] Decomposed into {len(sub_steps)} sub-steps: {sub_steps}")
                        return sub_steps
        
        print(f"[DECOMPOSE] No decomposition needed, using original step")
        return [description]
        
    except Exception as e:
        print(f"[DECOMPOSE] Error: {str(e)[:100]}, using original step")
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
                        dom = get_page_dom_simple(page)
                        testid_summary = extract_data_testid_summary(page)
                        dom = testid_summary + "\n" + dom if testid_summary else dom
                        
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
                        
                        # Get DOM and send to LLM
                        print(f"[EXECUTE] Capturing DOM...")
                        dom = get_page_dom_simple(page)
                        # Include data-testid summary for better element finding
                        testid_summary = extract_data_testid_summary(page)
                        dom = testid_summary + "\n" + dom if testid_summary else dom
                        print(f"[EXECUTE] DOM captured, sending to LLM for locator...")
                        
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
                            # Send DOM to LLM to get locator for interactive actions
                            locator, locator_type = get_locator_from_ai(dom, description_for_exec or search_text)
                            
                            if not locator:
                                error_msg = f'LLM could not find locator for: "{description_for_exec or search_text}"'
                                print(f"[EXECUTE] FAILED: {description_for_exec} - {error_msg}")
                                results.append({'step': idx, 'description': description_for_exec, 'action': action, 'ok': False, 'error': error_msg})
                                action_failed = True
                            else:
                                # Got locator from LLM, now perform the action
                                print(f"[EXECUTE] Got locator: {locator} (type: {locator_type})")
                                print(f"[EXECUTE] Performing action: {action}...")
                                
                                success, error = use_locator(page, locator, locator_type, action, value)
                                
                                if success:
                                    # After click/interactive action, wait for any loaders
                                    if action in ('click', 'hover', 'dblclick', 'rightclick'):
                                        print(f"[EXECUTE] {action.title()} executed, waiting for page to settle...")
                                        wait_for_loader(page)
                                    
                                    results.append({
                                        'step': idx, 
                                        'description': description_for_exec,
                                        'action': action, 
                                        'ok': True, 
                                        'locator': locator, 
                                        'type': locator_type,
                                        'value': str(value)[:50] if value else None
                                    })
                                    print(f"[EXECUTE] SUCCESS: {description_for_exec}")
                                    
                                    # Get new DOM after action (for next step to see updated page)
                                    print(f"[EXECUTE] Getting DOM after action...")
                                else:
                                    results.append({
                                        'step': idx, 
                                        'description': description_for_exec,
                                        'action': action, 
                                        'ok': False, 
                                        'error': error,
                                        'locator': locator,
                                        'type': locator_type
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
