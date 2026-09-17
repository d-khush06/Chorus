import os
import sys
import torch

from datasets import load_dataset, load_from_disk
from trl import SFTTrainer
from transformers import TrainingArguments
from unsloth import FastLanguageModel

# ─────────────────────────────────────────────────────────────────────────────
# CHORUS ORCHESTRATOR FINE-TUNING PIPELINE (UNSLOTH VERSION)
# 2x Faster, 40% less VRAM. Optimized for RTX A2000 (12GB VRAM).
# ─────────────────────────────────────────────────────────────────────────────

def map_dataset_to_messages(example):
    """Standardizes dataset dialogues into a 'messages' list for Unsloth chat templates."""
    messages = []
    
    if "dialogue" in example and example["dialogue"] is not None:
        scenario = example.get("scenario", "Process request")
        messages.append({
            "role": "system",
            "content": "You are the ORCHESTRATOR for the Chorus video-intelligence pipeline. Decide which available tools to call, in what order, and with what arguments, based on the user's request. Return only structured JSON."
        })
        messages.append({
            "role": "user",
            "content": f"User Request/Scenario: {scenario}"
        })
        
        for turn in example["dialogue"]:
            speaker = turn.get("speaker", "orchestrator")
            content = turn.get("content", "")
            
            if speaker == "orchestrator":
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": "user", "content": f"[{speaker}]: {content}"})
                
    return {"messages": messages}

def main(dataset_name: str, model_id: str, output_dir: str, sample_size: int = 1500):
    print("=" * 65)
    print("🚀 STARTING FAST UNSLOTH TRAINING PIPELINE")
    print("=" * 65)

    max_seq_length = 1024
    dtype = None
    load_in_4bit = True

    # 1. Load Unsloth Model & Tokenizer
    print(f"\n[1/4] Loading {model_id} via Unsloth (4-bit)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name = model_id,
        max_seq_length = max_seq_length,
        dtype = dtype,
        load_in_4bit = load_in_4bit,
    )

    # Add LoRA adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r = 16,
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha = 32,
        lora_dropout = 0,
        bias = "none",
        use_gradient_checkpointing = "unsloth", 
        random_state = 3407,
        use_rslora = False,
        loftq_config = None,
    )

    # 2. Load & Prepare Dataset
    print(f"\n[2/4] Loading Dataset: {dataset_name}...")
    if dataset_name.endswith(".json") and os.path.isfile(dataset_name):
        dataset = load_dataset("json", data_files=dataset_name, split="train")
    else:
        dataset = load_dataset(dataset_name, split="train")

    if sample_size and sample_size < len(dataset):
        import random
        dynamic_seed = random.randint(0, 100000)
        print(f"      Subsampling {sample_size} examples (out of {len(dataset)}) using random seed {dynamic_seed}...")
        dataset = dataset.shuffle(seed=dynamic_seed).select(range(sample_size))

    print("      Formatting to Chat Template...")
    dataset = dataset.map(map_dataset_to_messages, remove_columns=dataset.column_names)
    
    # Apply Unsloth formatting
    from unsloth.chat_templates import get_chat_template
    tokenizer = get_chat_template(
        tokenizer,
        chat_template = "chatml",
        mapping = {"role" : "role", "content" : "content", "user" : "user", "assistant" : "assistant"}, 
    )
    
    def formatting_prompts_func(examples):
        convos = examples["messages"]
        texts = [tokenizer.apply_chat_template(convo, tokenize = False, add_generation_prompt = False) for convo in convos]
        return { "text" : texts, }

    dataset = dataset.map(formatting_prompts_func, batched = True,)

    # 3. Configure Trainer
    print("\n[3/4] Configuring SFTTrainer (1 Epoch)...")
    trainer = SFTTrainer(
        model = model,
        tokenizer = tokenizer,
        train_dataset = dataset,
        dataset_text_field = "text",
        max_seq_length = max_seq_length,
        dataset_num_proc = 2,
        packing = False, # Can make training 5x faster for short sequences.
        args = TrainingArguments(
            per_device_train_batch_size = 1,
            gradient_accumulation_steps = 4,
            warmup_steps = 10,
            num_train_epochs = 1,           # ← Changed to 1 Epoch
            learning_rate = 2e-4,
            fp16 = not torch.cuda.is_bf16_supported(),
            bf16 = torch.cuda.is_bf16_supported(),
            logging_steps = 10,
            optim = "adamw_8bit",
            weight_decay = 0.01,
            lr_scheduler_type = "linear",
            seed = 3407,
            output_dir = output_dir,
            save_strategy = "no",           # Don't save midway for short runs
            report_to = "none"
        ),
    )

    # 4. Start Training
    print("\n[4/4] Starting Training...")
    trainer_stats = trainer.train()

    # 5. Save Model
    print(f"\n✅ Training Complete. Saving LoRA adapter to {output_dir}...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print("Done!")

if __name__ == "__main__":
    # Default parameters: 1500 examples
    dataset = "chorus_negotiations.json"
    model   = "models/Qwen2.5-7B-Browser-Agent-Merged"
    output  = "./orchestrator_lora_unsloth"
    
    main(dataset, model, output, sample_size=1500)
