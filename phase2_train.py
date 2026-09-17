"""
phase2_train.py
===============
QLoRA fine-tuning on chorus_v2.json using your existing local model.
Reads from: chorus_v2.json    (built by phase1_build_dataset.py)
Saves to  : orchestrator_lora_v2/

GPU required. Estimated time on RTX A2000 12GB: ~3-4 hours (718 steps).
Checkpoints every 50 steps — safe to Ctrl+C and resume.

Run:
    python phase2_train.py

To resume after a crash or Ctrl+C:
    python phase2_train.py          (auto-detects checkpoint, resumes)
"""

import os, sys, datetime, subprocess

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATASET    = os.path.join(BASE_DIR, "chorus_v2.json")
MODEL_PATH = os.path.join(BASE_DIR, "models", "Qwen2.5-7B-Browser-Agent-Merged")
OUTPUT_DIR = os.path.join(BASE_DIR, "orchestrator_lora_v2")
MAX_SEQ    = 1024   # tokens — keeps VRAM inside 12 GB

# ─────────────────────────────────────────────────────────────────────────────

def install_deps():
    for pkg in ["peft", "trl", "datasets", "accelerate", "bitsandbytes"]:
        try:
            __import__(pkg)
        except ImportError:
            print(f"[setup] Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

install_deps()

import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    BitsAndBytesConfig, TrainingArguments,
    Trainer, DataCollatorForSeq2Seq,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# ─────────────────────────────────────────────────────────────────────────────

def map_to_messages(example):
    """Convert Chorus negotiation dialogue → chat messages list."""
    messages = []

    if "dialogue" in example and example["dialogue"] is not None:
        sys_prompt = example.get("_system_prompt") or (
            "You are the ORCHESTRATOR for the Chorus video-intelligence pipeline. "
            "Decide which tools to call, in what order. Return only structured JSON."
        )
        scenario = example.get("scenario", "Process request")
        messages.append({"role": "system",    "content": sys_prompt})
        messages.append({"role": "user",      "content": f"Scenario: {scenario}"})

        for turn in example["dialogue"]:
            speaker = turn.get("speaker", "orchestrator")
            content = turn.get("content", "")
            if speaker == "orchestrator":
                messages.append({"role": "assistant", "content": content})
            elif speaker == "user":
                messages.append({"role": "user",      "content": content})
            else:
                messages.append({"role": "user",      "content": f"[{speaker}]: {content}"})

    elif "messages" in example and example["messages"]:
        for m in example["messages"]:
            messages.append({"role": m.get("role","user"), "content": m.get("content","")})

    elif "conversations" in example and example["conversations"]:
        for m in example["conversations"]:
            role = {"human":"user","gpt":"assistant"}.get(m.get("from","user"), m.get("from","user"))
            if role not in ("system","user","assistant"):
                role = "user"
            messages.append({"role": role, "content": m.get("value","")})

    return {"messages": messages}


def main():
    print("="*60)
    print("PHASE 2 — QLoRA FINE-TUNING")
    print(f"Started: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    print("="*60)

    # ── Pre-flight checks ────────────────────────────────────────────────────
    if not os.path.isfile(DATASET):
        print(f"\nERROR: {DATASET} not found.")
        print("Run phase1_build_dataset.py first.")
        sys.exit(1)
    if not os.path.isdir(MODEL_PATH):
        print(f"\nERROR: Model not found at {MODEL_PATH}")
        sys.exit(1)

    print(f"\n  Dataset    : {DATASET}")
    print(f"  Model      : {MODEL_PATH}")
    print(f"  Output     : {OUTPUT_DIR}")
    print(f"  Device     : {'CUDA — ' + torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU (will be very slow)'}")
    if torch.cuda.is_available():
        vram = round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1)
        print(f"  VRAM       : {vram} GB")

    # ── 4-bit quantization ───────────────────────────────────────────────────
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    )

    # ── Tokenizer ────────────────────────────────────────────────────────────
    print("\n[1/5] Loading tokenizer...")
    tok = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    # ── Model (pinned to GPU 0) ───────────────────────────────────────────────
    print("[2/5] Loading model in 4-bit...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        quantization_config=bnb,
        device_map={"": 0},          # pin to GPU 0 — avoids multi-GPU slowdown
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    # ── LoRA ─────────────────────────────────────────────────────────────────
    model = get_peft_model(model, LoraConfig(
        r=16, lora_alpha=32,
        target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
        lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
    ))
    model.print_trainable_parameters()

    # ── Dataset ───────────────────────────────────────────────────────────────
    print("\n[3/5] Loading and tokenizing dataset...")
    raw = load_dataset("json", data_files=DATASET, split="train")
    print(f"  Rows loaded: {len(raw)}")

    raw = raw.map(map_to_messages, remove_columns=raw.column_names)

    def fmt(batch):
        texts = []
        for msgs in batch["messages"]:
            try:
                texts.append(tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False))
            except Exception:
                texts.append("")
        return {"text": texts}

    raw = raw.map(fmt, batched=True)
    raw = raw.filter(lambda x: len(x["text"]) > 50)

    def tokenize(examples):
        t = tok(examples["text"], truncation=True, max_length=MAX_SEQ, padding=False)
        t["labels"] = t["input_ids"].copy()
        return t

    tokenized = raw.map(tokenize, batched=True, remove_columns=raw.column_names)
    print(f"  Tokenized rows: {len(tokenized)}")

    # ── Auto-resume from checkpoint ────────────────────────────────────────────
    checkpoint = None
    if os.path.isdir(OUTPUT_DIR):
        ckpts = sorted(
            [os.path.join(OUTPUT_DIR, d) for d in os.listdir(OUTPUT_DIR)
             if d.startswith("checkpoint-")],
            key=os.path.getmtime,
        )
        if ckpts:
            checkpoint = ckpts[-1]
            print(f"\n  Resuming from: {checkpoint}")

    # ── Training args ──────────────────────────────────────────────────────────
    print("\n[4/5] Configuring trainer...")
    args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,   # effective batch = 8
        warmup_steps=50,
        num_train_epochs=1,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=5,
        save_strategy="steps",
        save_steps=50,                   # checkpoint every 50 steps
        save_total_limit=5,
        optim="paged_adamw_8bit",        # saves ~2 GB VRAM vs 32-bit
        gradient_checkpointing=True,
        report_to="none",
        ddp_find_unused_parameters=False,
    )

    trainer = Trainer(
        model=model, args=args,
        train_dataset=tokenized,
        data_collator=DataCollatorForSeq2Seq(tok, pad_to_multiple_of=8,
                                             return_tensors="pt", padding=True),
    )

    # ── Train ──────────────────────────────────────────────────────────────────
    print("\n[5/5] Training started. Ctrl+C to pause — it will auto-resume next run.\n")
    t0 = datetime.datetime.now()
    try:
        trainer.train(resume_from_checkpoint=checkpoint)
    except KeyboardInterrupt:
        print("\n\nCtrl+C detected. Saving current state...")
        trainer.model.save_pretrained(OUTPUT_DIR)
        tok.save_pretrained(OUTPUT_DIR)
        print(f"Checkpoint saved to {OUTPUT_DIR}. Run again to resume.")
        sys.exit(0)
    except Exception as e:
        print(f"\nTraining error: {e}")
        trainer.model.save_pretrained(OUTPUT_DIR)
        tok.save_pretrained(OUTPUT_DIR)
        raise

    # ── Save final adapter ─────────────────────────────────────────────────────
    elapsed = datetime.datetime.now() - t0
    print(f"\nTraining complete in {str(elapsed).split('.')[0]}")
    print(f"Saving final adapter to {OUTPUT_DIR} ...")
    trainer.model.save_pretrained(OUTPUT_DIR)
    tok.save_pretrained(OUTPUT_DIR)

    print("\n" + "="*60)
    print("PHASE 2 DONE.")
    print(f"Adapter saved : {OUTPUT_DIR}")
    print("Next          : python phase3_evaluate.py")
    print("="*60)


if __name__ == "__main__":
    main()
