import subprocess
import sys
import os
import time

def run():
    print("=" * 65)
    print("CHORUS ORCHESTRATOR FULL TRAINING PIPELINE")
    print("=" * 65)
    print()
    print("Step 1: Build 4893-example dataset (CPU-only, ~60 seconds)")
    print("Step 2: Fine-tune orchestrator with QLoRA (crash-safe settings)")
    print()

    # Step 1: Build the negotiation dataset (CPU-only, no GPU needed)
    # Mixes 3000 from hermes_reasoning_tool_use + 1893 from hermes_function_calling_v1
    print(">>> STEP 1: Building Chorus negotiation dataset from local files...")
    gen_cmd = [
        "python", "prepare_negotiation_dataset.py",
        "chorus_negotiations.json",   # output file
        "3000",                        # D1 count (hermes_reasoning_tool_use)
        # D2 count omitted = use all 1893 from hermes_function_calling_v1
    ]
    res = subprocess.run(gen_cmd)
    if res.returncode != 0:
        print("Dataset build failed! Stopping pipeline.")
        sys.exit(1)

    print()
    print(">>> STEP 2: Fine-tuning orchestrator with crash-safe QLoRA settings...")
    # Step 2: Fine-tune on chorus_negotiations.json
    # Settings: max_length=1024, paged_adamw_8bit, save_steps=50
    train_cmd = [
        "python", "fine_tune_orchestrator.py",
        "chorus_negotiations.json",                  # dataset (local JSON)
        "models/Qwen2.5-7B-Browser-Agent-Merged",    # base model
        "./orchestrator_lora"                         # output dir
    ]
    res2 = subprocess.run(train_cmd)
    if res2.returncode != 0:
        print("Fine-tuning failed! Check output above.")
        sys.exit(1)

    print()
    print("=" * 65)
    print("PIPELINE COMPLETED SUCCESSFULLY")
    print("LoRA adapter saved to: ./orchestrator_lora")
    print("=" * 65)

if __name__ == "__main__":
    run()
