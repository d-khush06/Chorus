import os
import sys
import json
import re
from datasets import load_from_disk
from tqdm import tqdm

# ─────────────────────────────────────────────────────────────────────────────
# CHORUS ORCHESTRATOR DATASET BUILDER  (v2 - CPU only, no GPU needed)
# Converts locally-downloaded Hermes datasets into Chorus multi-agent
# negotiation dialogues using a fast programmatic CPU-only converter.
#
# Source datasets (pre-downloaded to ./datasets/):
#   D1: hermes_reasoning_tool_use  → 3000 examples (chain-of-thought reasoning)
#   D2: hermes_function_calling_v1 → 1893 examples (parallel tool dispatch)
#   Total: 4893 examples
#
# Run:  python prepare_negotiation_dataset.py
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DS1_PATH = os.path.join(BASE_DIR, "datasets", "hermes_reasoning_tool_use")
DS2_PATH = os.path.join(BASE_DIR, "datasets", "hermes_function_calling_v1")


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_tools(tools_raw):
    """Parse tools field — may be a JSON string or already a list."""
    if tools_raw is None:
        return []
    if isinstance(tools_raw, list):
        tools = tools_raw
    elif isinstance(tools_raw, str):
        try:
            tools = json.loads(tools_raw)
        except Exception:
            return []
    else:
        return []
    # Unwrap OpenAI-style {"type":"function","function":{...}} wrapper
    result = []
    for t in tools:
        if isinstance(t, dict):
            if "function" in t and isinstance(t["function"], dict):
                result.append(t["function"])
            else:
                result.append(t)
    return result


def extract_called_tools(conversations, tools):
    """
    Scan GPT turns for <tool_call> JSON blocks.
    Returns list of tool names that were actually called, in order.
    """
    called = []
    seen = set()
    tool_names = [t.get("name", "") for t in tools]

    for msg in conversations:
        if msg.get("from") not in ("gpt", "assistant"):
            continue
        val = msg.get("value", "")

        # Primary: parse <tool_call>{...}</tool_call>
        for block in re.findall(r"<tool_call>(.*?)</tool_call>", val, re.DOTALL):
            try:
                obj = json.loads(block.strip())
                name = obj.get("name", "")
                if name and name not in seen:
                    called.append(name)
                    seen.add(name)
            except Exception:
                pass

        # Fallback: check tool name appears in text
        if not called:
            for name in tool_names:
                if name and name in val and name not in seen:
                    called.append(name)
                    seen.add(name)

    return called


def extract_reasoning(conversations):
    """Extract <think>...</think> chain-of-thought from a GPT response."""
    for msg in conversations:
        if msg.get("from") not in ("gpt", "assistant"):
            continue
        val = msg.get("value", "")
        match = re.search(r"<think>(.*?)</think>", val, re.DOTALL)
        if match:
            return match.group(1).strip()[:600]
    return ""


def build_dialogue(task, tools, called_tools, reasoning=""):
    """
    Assembles a Chorus multi-agent negotiation dialogue:
      orchestrator (opening)  →  each agent (self_report)  →  orchestrator (final_decision)
    """
    excluded_tools = [t.get("name", "") for t in tools
                      if t.get("name", "") not in called_tools]

    opening_content = "Initiating Chorus pipeline for: " + task
    if reasoning:
        opening_content += "\n\n[Reasoning]: " + reasoning

    dialogue = [
        {
            "speaker": "orchestrator",
            "turn": "opening",
            "content": opening_content
        }
    ]

    for t in tools:
        name  = t.get("name", "unknown_agent")
        desc  = t.get("description", "No description provided.")
        props = list((t.get("parameters") or {}).get("properties", {}).keys())
        is_called = name in called_tools
        confidence = 0.90 if is_called else 0.15

        if is_called:
            report = (
                "I am [" + name + "]. " + desc + " "
                "I can handle this request. Required parameters: " +
                str(props if props else "none") + ". Ready to execute."
            )
        else:
            report = (
                "I am [" + name + "]. " + desc + " "
                "This task does not require my capabilities. I should be excluded."
            )

        dialogue.append({
            "speaker": name,
            "turn": "self_report",
            "content": report,
            "confidence": confidence
        })

    # Build tool_calls for the final decision block
    tool_calls = []
    for step, name in enumerate(called_tools, start=1):
        args = {}
        for t in tools:
            if t.get("name") == name:
                props = (t.get("parameters") or {}).get("properties", {})
                args = {k: "<required>" for k in props.keys()}
                break
        tool_calls.append({"step": step, "tool": name, "arguments": args})

    decision_content = json.dumps({
        "tool_calls": tool_calls,
        "excluded": excluded_tools,
        "reasoning_summary": (
            "Selected agents: " + str(called_tools) + ". "
            "Excluded: " + str(excluded_tools) + ". "
            "Order follows dependency chain."
        )
    })

    dialogue.append({
        "speaker": "orchestrator",
        "turn": "final_decision",
        "content": decision_content
    })

    return dialogue


# ── Per-dataset converters ─────────────────────────────────────────────────────

def convert_d1_example(example):
    """hermes_reasoning_tool_use → Chorus format."""
    task          = example.get("task", "Process user request")
    tools         = parse_tools(example.get("tools", "[]"))
    conversations = example.get("conversations", [])
    called_tools  = extract_called_tools(conversations, tools)
    reasoning     = extract_reasoning(conversations)
    dialogue      = build_dialogue(task, tools, called_tools, reasoning)
    return {
        "source_dataset": "hermes_reasoning_tool_use",
        "scenario": task,
        "category": example.get("category", ""),
        "dialogue": dialogue
    }


def convert_d2_example(example):
    """hermes_function_calling_v1 → Chorus format."""
    task          = example.get("task", "Process user request")
    tools         = parse_tools(example.get("tools", "[]"))
    conversations = example.get("conversations", [])
    called_tools  = extract_called_tools(conversations, tools)
    dialogue      = build_dialogue(task, tools, called_tools)
    return {
        "source_dataset": "hermes_function_calling_v1",
        "scenario": task,
        "category": example.get("category", ""),
        "dialogue": dialogue
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main(output_file="chorus_negotiations.json", d1_count=3000, d2_count=None):
    print("=" * 65)
    print("CHORUS ORCHESTRATOR DATASET BUILDER  (CPU-only)")
    print("=" * 65)

    # Load D1
    print("\n[1/4] Loading D1: hermes_reasoning_tool_use ...")
    if not os.path.exists(DS1_PATH):
        print("ERROR: Not found at " + DS1_PATH)
        print("Run: python download_datasets.py")
        sys.exit(1)
    ds1 = load_from_disk(DS1_PATH)
    ds1 = ds1.shuffle(seed=42).select(range(min(d1_count, len(ds1))))
    print("      Loaded " + str(len(ds1)) + " examples  (total in D1: 51004)")

    # Load D2
    print("\n[2/4] Loading D2: hermes_function_calling_v1 ...")
    if not os.path.exists(DS2_PATH):
        print("ERROR: Not found at " + DS2_PATH)
        print("Run: python download_datasets.py")
        sys.exit(1)
    ds2 = load_from_disk(DS2_PATH)
    if d2_count:
        ds2 = ds2.shuffle(seed=42).select(range(min(d2_count, len(ds2))))
    print("      Loaded " + str(len(ds2)) + " examples  (total in D2: 1893)")

    total = len(ds1) + len(ds2)
    print("\n[3/4] Converting " + str(total) + " examples to Chorus negotiation format ...")

    processed = []
    err1 = 0
    err2 = 0

    print("  D1 (" + str(len(ds1)) + " examples) ...")
    for i in tqdm(range(len(ds1)), desc="D1", ncols=80):
        try:
            processed.append(convert_d1_example(ds1[i]))
        except Exception:
            err1 += 1

    print("  D2 (" + str(len(ds2)) + " examples) ...")
    for i in tqdm(range(len(ds2)), desc="D2", ncols=80):
        try:
            processed.append(convert_d2_example(ds2[i]))
        except Exception:
            err2 += 1

    print("\n[4/4] Saving " + str(len(processed)) + " examples to " + output_file + " ...")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)

    size_mb = round(os.path.getsize(output_file) / 1024 / 1024, 1)

    print()
    print("=" * 65)
    print("DONE!")
    print("  D1 converted : " + str(len(ds1) - err1) + "  (errors: " + str(err1) + ")")
    print("  D2 converted : " + str(len(ds2) - err2) + "  (errors: " + str(err2) + ")")
    print("  Total saved  : " + str(len(processed)))
    print("  Output file  : " + os.path.abspath(output_file))
    print("  File size    : " + str(size_mb) + " MB")
    print()
    print("Next: run  python fine_tune_orchestrator.py")
    print("=" * 65)


if __name__ == "__main__":
    output   = "chorus_negotiations.json"
    d1_count = 3000  # examples from hermes_reasoning_tool_use
    d2_count = None  # None = use ALL 1893 from hermes_function_calling_v1

    if len(sys.argv) > 1:
        output = sys.argv[1]
    if len(sys.argv) > 2:
        d1_count = int(sys.argv[2])
    if len(sys.argv) > 3:
        d2_count = int(sys.argv[3])

    main(output, d1_count, d2_count)
