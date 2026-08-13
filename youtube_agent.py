"""
YouTube Live Search Agent - Powered by Qwen2.5-7B (Local) + Playwright
=======================================================================
Navigates directly to YouTube search, scrapes results, then asks the
model to summarize them as a clean final list.

Usage:
    python youtube_agent.py
"""

import os
import sys
import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from playwright.sync_api import sync_playwright

# Fix Windows encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

LOCAL_MODEL_PATH = os.path.join(".", "models", "Qwen2.5-7B-Browser-Agent-Merged")
HF_MODEL_ID = "dkhush06/Qwen2.5-7B-Browser-Agent-Merged"
MAX_NEW_TOKENS = 1024

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
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        print("   [GPU] 4-bit NF4 quantization on RTX A2000 12GB")
        model = AutoModelForCausalLM.from_pretrained(
            model_source,
            quantization_config=bnb_config,
            device_map="auto",
            low_cpu_mem_usage=True,
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_source,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
        )
        model.to("cpu")

    print("   [OK] Model loaded!\n")
    return tokenizer, model, device


# ─────────────────────────────────────────────────────────────────────────────
# BROWSER SCRAPER - goes directly to YouTube search results
# ─────────────────────────────────────────────────────────────────────────────
def scrape_youtube(search_query: str) -> dict:
    """Open real Chromium, go to YouTube search results, extract video data."""
    encoded_query = search_query.replace(" ", "+")
    url = f"https://www.youtube.com/results?search_query={encoded_query}"

    results = {"url": url, "videos": [], "titles_text": ""}

    print(f"\n[BROWSER] Opening Chromium...")
    print(f"[BROWSER] Searching YouTube for: '{search_query}'")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print(f"[BROWSER] Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Wait for YouTube to load its JavaScript content
        print("[BROWSER] Waiting for YouTube to load results...")
        time.sleep(4)

        # Scroll down a bit to trigger lazy loading
        page.evaluate("window.scrollBy(0, 500)")
        time.sleep(2)

        # Extract YouTube video cards using ytd-video-renderer
        videos = page.evaluate("""() => {
            const results = [];
            const renderers = document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer');
            renderers.forEach(r => {
                const titleEl = r.querySelector('a#video-title, #video-title');
                const linkEl = r.querySelector('a#video-title, a#thumbnail');
                const metaEl = r.querySelector('#metadata-line span, .ytd-video-meta-block');
                const channelEl = r.querySelector('#channel-name, ytd-channel-name');
                if (titleEl && linkEl && linkEl.href && linkEl.href.includes('/watch?v=')) {
                    results.push({
                        title: titleEl.innerText.trim(),
                        url: linkEl.href,
                        channel: channelEl ? channelEl.innerText.trim() : '',
                        meta: metaEl ? metaEl.innerText.trim() : ''
                    });
                }
            });
            return results.slice(0, 15);
        }""")

        # Fallback: grab any watch links with visible text
        if not videos:
            print("[BROWSER] Using fallback link extractor...")
            videos = page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('a[href*="/watch?v="]').forEach(a => {
                    const text = a.innerText.trim() || a.getAttribute('title') || '';
                    if (text && text.length > 5 && !results.find(r => r.url === a.href)) {
                        results.push({title: text, url: a.href, channel: '', meta: ''});
                    }
                });
                return results.slice(0, 15);
            }""")

        results["videos"] = videos
        print(f"[BROWSER] Found {len(videos)} video(s).")

        # Keep browser visible for 5 seconds
        time.sleep(5)
        browser.close()

    return results


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
# MAIN AGENT
# ─────────────────────────────────────────────────────────────────────────────
def run_search_agent(user_query: str, tokenizer, model, device):
    print(f"\n{'='*60}")
    print(f"TASK: {user_query}")
    print(f"{'='*60}")

    # Step 1: Browser scrapes YouTube directly
    data = scrape_youtube(user_query)
    videos = data["videos"]

    if not videos:
        print("[WARN] No videos found from scraper. Check your internet connection.")
        return

    # Format scraped data for model
    scraped_text = f"YouTube search results for: '{user_query}'\n"
    scraped_text += f"Search URL: {data['url']}\n\n"
    scraped_text += "Videos found:\n"
    for i, v in enumerate(videos, 1):
        scraped_text += f"  {i}. Title: {v['title']}\n"
        scraped_text += f"     URL:   {v['url']}\n"
        if v.get('channel'):
            scraped_text += f"     Channel: {v['channel']}\n"
        scraped_text += "\n"

    print(f"\n[SCRAPED DATA]\n{scraped_text}")

    # Step 2: Model summarizes and presents results
    print("\n[MODEL] Summarizing results...")
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Given YouTube search results scraped from a real browser, present the top videos in a clean, readable format with their titles and clickable links."
        },
        {
            "role": "user",
            "content": f"Here are the YouTube search results I fetched live right now:\n\n{scraped_text}\n\nPlease present the top 10 most relevant motivational videos with their titles and YouTube links in a clean numbered list."
        }
    ]

    response = run_model(tokenizer, model, device, messages)

    print(f"\n{'='*60}")
    print("FINAL ANSWER FROM MODEL:")
    print(f"{'='*60}")
    print(response)
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tokenizer, model, device = load_model()

    print("\n" + "="*60)
    print("YouTube Live Search Agent Ready!")
    print("Type your search query. Type 'exit' to quit.")
    print("="*60)

    while True:
        query = input("\nSearch Query > ").strip()
        if not query:
            continue
        if query.lower() in ["exit", "quit", "q"]:
            print("Goodbye!")
            break
        run_search_agent(query, tokenizer, model, device)
