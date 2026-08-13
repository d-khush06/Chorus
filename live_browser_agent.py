"""
Live Browser Agent - Powered by Qwen2.5-7B (Local) + Playwright
================================================================
The model acts as the brain, generating tool_call actions.
Playwright executes those actions on a real live Chromium browser.

Usage:
    python live_browser_agent.py
"""

import os
import re
from transformers import BitsAndBytesConfig
import json
import time
import sys
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from playwright.sync_api import sync_playwright, Page

# Fix Windows encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
LOCAL_MODEL_PATH = os.path.join(".", "models", "Qwen2.5-7B-Browser-Agent-Merged")
HF_MODEL_ID = "dkhush06/Qwen2.5-7B-Browser-Agent-Merged"
MAX_STEPS = 10
MAX_NEW_TOKENS = 512

# ─────────────────────────────────────────────────────────────────────────────
# TOOL DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────
TOOLS_SCHEMA = """
You are a browser automation agent. Control a real web browser using these tools:

[browser_navigate]: Navigate to a URL.
  {"name": "browser_navigate", "arguments": {"url": "https://..."}}

[browser_type]: Type text into an input field.
  {"name": "browser_type", "arguments": {"selector": "search", "text": "text to type"}}

[browser_click]: Click an element by text or selector.
  {"name": "browser_click", "arguments": {"selector": "button text or CSS selector"}}

[browser_scrape]: Scrape all visible text and links from the current page.
  {"name": "browser_scrape", "arguments": {}}

[browser_wait]: Wait for page to load.
  {"name": "browser_wait", "arguments": {"seconds": 2}}

[finish]: You are done. Output the final answer.
  {"name": "finish", "arguments": {"answer": "Your final answer here"}}

IMPORTANT TIPS:
- To search YouTube, navigate directly to: https://www.youtube.com/results?search_query=YOUR+QUERY
- After navigating to search results, use browser_scrape to get video titles and links.
- YouTube links look like: https://www.youtube.com/watch?v=XXXX
- Always call browser_scrape after navigating to collect results.
- Call finish when you have the video titles and links.

Always output exactly ONE <tool_call> block per response.
"""

SYSTEM_PROMPT = f"You are a helpful browser automation agent with access to a real live web browser.\n{TOOLS_SCHEMA}"


# ─────────────────────────────────────────────────────────────────────────────
# BROWSER TOOLS
# ─────────────────────────────────────────────────────────────────────────────
class BrowserTools:
    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str) -> str:
        print(f"  [NAV] Navigating to: {url}")
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        return f"Navigated to {url}. Page title: '{self.page.title()}'"

    def type_text(self, selector: str, text: str) -> str:
        print(f"  [TYPE] Typing '{text}' into '{selector}'")
        for sel in [
            f'[placeholder*="{selector}" i]',
            f'[aria-label*="{selector}" i]',
            f'[name*="{selector}" i]',
            "input[type='search']",
            "input[type='text']",
            selector
        ]:
            try:
                el = self.page.locator(sel).first
                el.click(timeout=3000)
                el.fill(text)
                return f"Typed '{text}' into element."
            except Exception:
                continue
        return "Could not find input element."

    def click(self, selector: str) -> str:
        print(f"  [CLICK] Clicking: '{selector}'")
        for sel in [
            f'text="{selector}"',
            f'[aria-label*="{selector}" i]',
            selector,
            f'button:has-text("{selector}")',
        ]:
            try:
                el = self.page.locator(sel).first
                el.click(timeout=3000)
                time.sleep(1.5)
                return f"Clicked '{selector}'."
            except Exception:
                continue
        self.page.keyboard.press("Enter")
        time.sleep(1.5)
        return "Pressed Enter (fallback)."

    def scrape(self) -> str:
        print("  [SCRAPE] Scraping page content...")
        title = self.page.title()
        url = self.page.url

        # Wait a moment for dynamic content
        self.page.wait_for_load_state("networkidle", timeout=5000)

        links = self.page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const text = a.innerText.trim();
                const href = a.href;
                if (text && href && !href.startsWith('javascript') && text.length > 3) {
                    results.push({text: text.substring(0, 120), href: href});
                }
            });
            return results.slice(0, 50);
        }""")

        # Specifically extract YouTube video IDs and titles
        yt_videos = self.page.evaluate("""() => {
            const videos = [];
            // ytd-video-renderer is the YouTube search result component
            const renderers = document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer');
            renderers.forEach(r => {
                const titleEl = r.querySelector('#video-title, a#video-title');
                const linkEl = r.querySelector('a#thumbnail, a#video-title');
                if (titleEl && linkEl) {
                    videos.push({
                        title: titleEl.innerText.trim(),
                        url: linkEl.href
                    });
                }
            });
            return videos.slice(0, 20);
        }""")

        page_text = self.page.evaluate("""() => {
            const els = document.querySelectorAll('h1, h2, h3, [id*="title"], [class*="title"], #video-title');
            return Array.from(els).map(e => e.innerText.trim()).filter(t => t.length > 2).slice(0, 30).join('\\n');
        }""")

        output = f"=== PAGE SCRAPED ===\nURL: {url}\nTitle: {title}\n\n"

        if yt_videos:
            output += "--- YOUTUBE VIDEOS FOUND ---\n"
            for i, v in enumerate(yt_videos, 1):
                output += f"  [{i}] {v['title']} -> {v['url']}\n"
            output += "\n"

        if page_text:
            output += f"--- HEADINGS/TITLES ---\n{page_text}\n\n"

        if links:
            output += "--- ALL LINKS FOUND ---\n"
            for i, link in enumerate(links[:30], 1):
                output += f"  [{i}] {link['text']} -> {link['href']}\n"
        return output[:5000]

    def wait(self, seconds: int = 2) -> str:
        print(f"  [WAIT] Waiting {seconds}s...")
        time.sleep(seconds)
        return f"Waited {seconds} seconds."


# ─────────────────────────────────────────────────────────────────────────────
# MODEL LOADER
# ─────────────────────────────────────────────────────────────────────────────
def load_model():
    model_source = LOCAL_MODEL_PATH if os.path.exists(LOCAL_MODEL_PATH) else HF_MODEL_ID
    print(f"\n[LOADING] Model from: {model_source}")
    tokenizer = AutoTokenizer.from_pretrained(model_source)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"   Device: {device.upper()}")

    if device == "cuda":
        # 4-bit quantization: fits 7B model into 12GB VRAM (uses only ~5-6GB)
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        print("   [GPU] Using 4-bit quantization (NF4) for RTX A2000 12GB")
        model = AutoModelForCausalLM.from_pretrained(
            model_source,
            quantization_config=bnb_config,
            device_map="auto",
            low_cpu_mem_usage=True,
        )
    else:
        print("   [CPU] Loading in float32 (no GPU found)")
        model = AutoModelForCausalLM.from_pretrained(
            model_source,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
        )
        model.to("cpu")

    print("   [OK] Model loaded!\n")
    return tokenizer, model, device


# ─────────────────────────────────────────────────────────────────────────────
# PARSE TOOL CALL  (handles nested JSON and missing </tool_call> closing tag)
# ─────────────────────────────────────────────────────────────────────────────
def extract_balanced_json(text: str, start: int) -> str:
    """Extract a complete JSON object starting at 'start' by counting braces."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\' and in_string:
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if not in_string:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i+1]
    return ""


def parse_tool_call(text: str):
    # Find the start of the first JSON object anywhere in text
    # Prioritise content inside <tool_call> tag (with or without closing tag)
    tag_match = re.search(r"<tool_call>", text)
    search_text = text[tag_match.end():] if tag_match else text

    # Find first '{' and extract balanced JSON
    brace_pos = search_text.find('{')
    if brace_pos == -1:
        return None

    raw = extract_balanced_json(search_text, brace_pos)
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                return json.loads(raw.replace("'", '"'))
            except Exception:
                pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# MODEL INFERENCE
# ─────────────────────────────────────────────────────────────────────────────
def run_model(tokenizer, model, device, messages) -> str:
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer([text], return_tensors="pt").to(device)
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            temperature=None,
            top_p=None,
        )
    new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_ids, skip_special_tokens=True).strip()


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTE TOOL
# ─────────────────────────────────────────────────────────────────────────────
def execute_tool(tool_call: dict, browser_tools: BrowserTools):
    name = tool_call.get("name", "")
    args = tool_call.get("arguments", {})
    if name == "browser_navigate":
        return browser_tools.navigate(args.get("url", ""))
    elif name == "browser_type":
        return browser_tools.type_text(args.get("selector", ""), args.get("text", ""))
    elif name == "browser_click":
        return browser_tools.click(args.get("selector", ""))
    elif name == "browser_scrape":
        return browser_tools.scrape()
    elif name == "browser_wait":
        return browser_tools.wait(int(args.get("seconds", 2)))
    elif name == "finish":
        return None
    else:
        return f"Unknown tool: {name}"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AGENT LOOP
# ─────────────────────────────────────────────────────────────────────────────
def run_agent(user_task: str, tokenizer, model, device):
    print(f"\n{'='*60}")
    print(f"TASK: {user_task}")
    print(f"{'='*60}\n")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_task},
    ]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        tools = BrowserTools(page)
        final_answer = None

        MAX_STEPS = 15
        for step in range(1, MAX_STEPS + 1):
            print(f"\n--- STEP {step}/{MAX_STEPS} ---")
            print("[THINKING] Model is generating next action...")
            response = run_model(tokenizer, model, device, messages)
            print(f"[MODEL OUTPUT]\n{response}\n")

            tool_call = parse_tool_call(response)
            if not tool_call:
                print("[WARN] No valid tool call found. Stopping.")
                final_answer = response
                break

            tool_name = tool_call.get("name", "")
            print(f"[TOOL] Executing: [{tool_name}]")
            messages.append({"role": "assistant", "content": response})

            if tool_name == "finish":
                final_answer = tool_call.get("arguments", {}).get("answer", response)
                print("[DONE] Agent finished!")
                break

            tool_result = execute_tool(tool_call, tools)
            print(f"[RESULT]\n{tool_result}\n")

            messages.append({
                "role": "user",
                "content": f"<tool_response>\n{tool_result}\n</tool_response>\nContinue to the next action."
            })

        else:
            print(f"\n[WARN] Reached max steps ({MAX_STEPS}). Scraping final state...")
            final_answer = tools.scrape()

        print("\n[INFO] Keeping browser open for 5 seconds...")
        time.sleep(5)
        browser.close()

    print(f"\n{'='*60}")
    print("FINAL ANSWER:")
    print(f"{'='*60}")
    print(final_answer)
    print(f"{'='*60}\n")
    return final_answer


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tokenizer, model, device = load_model()

    print("\n" + "="*60)
    print("Live Browser Agent Ready!")
    print("Type your task and press Enter. Type 'exit' to quit.")
    print("="*60)

    while True:
        task = input("\nYour Task > ").strip()
        if not task:
            continue
        if task.lower() in ["exit", "quit", "q"]:
            print("Goodbye!")
            break
        run_agent(task, tokenizer, model, device)
