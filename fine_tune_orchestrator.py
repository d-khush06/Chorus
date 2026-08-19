import os
import sys
import torch
import time

from datasets import load_dataset, load_from_disk
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# ─────────────────────────────────────────────────────────────────────────────
# CHORUS ORCHESTRATOR FINE-TUNING PIPELINE (HERMES FUNCTION CALLING / REASONING)
# Optimized for RTX A2000 (12GB VRAM) via QLoRA.
# Fully resilient to network/data errors and supports checkpoint resuming.
# ─────────────────────────────────────────────────────────────────────────────

def install_dependencies():
    """Verify and install dependencies for local fine-tuning."""
    print("Checking fine-tuning dependencies...")
    import subprocess
    packages = ["peft", "trl", "datasets", "accelerate", "bitsandbytes"]
    for pkg in packages:
        try:
            __import__(pkg)
        except ImportError:
            print(f"Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

def map_dataset_to_messages(example):
    """
    Standardizes ShareGPT, OpenAI, or Chorus custom dialogue format
    to standard chat messages.
    """
    messages = []
    
    # 1. Custom Chorus Dialogue format (negotiation format)
    if "dialogue" in example and example["dialogue"] is not None:
        scenario = example.get("scenario", "Process request")
        # System prompt setting the context
        messages.append({
            "role": "system",
            "content": "You are the ORCHESTRATOR for the Chorus video-intelligence pipeline. Decide which available tools to call, in what order, and with what arguments, based on the user's request. Return only structured JSON."
        })
        # The initial user prompt starts the conversation
        messages.append({
            "role": "user",
            "content": f"User Request/Scenario: {scenario}"
        })
        
        for turn in example["dialogue"]:
            speaker = turn.get("speaker", "orchestrator")
            content = turn.get("content", "")
            
            if speaker == "orchestrator":
                # Orchestrator is the Assistant role
                messages.append({"role": "assistant", "content": content})
            else:
                # Other candidate agents act as User inputs (debate responses)
                messages.append({"role": "user", "content": f"[{speaker}]: {content}"})
                
    # 2. ShareGPT format
    elif "conversations" in example and example["conversations"] is not None:
        for msg in example["conversations"]:
            role = msg.get("from", "user")
            content = msg.get("value", "")
            
            if role == "human":
                role = "user"
            elif role == "gpt":
                role = "assistant"
            elif role not in ["system", "user", "assistant"]:
                role = "user"
                
            messages.append({"role": role, "content": content})
            
    # 3. Standard messages format
    elif "messages" in example and example["messages"] is not None:
        for msg in example["messages"]:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
            
    return {"messages": messages}

def load_and_prepare_dataset(dataset_name_or_path: str, tokenizer, sample_size: int = None):
    """
    Loads dataset from either:
      - A local JSON file (chorus_negotiations.json)  ← preferred, no GPU needed to prepare
      - A local Arrow directory saved with save_to_disk()
      - A HuggingFace Hub dataset name (requires internet)
    Robust against corrupted rows or parsing errors.
    """
    print(f"Loading dataset: {dataset_name_or_path}...")
    try:
        if dataset_name_or_path.endswith(".json") and os.path.isfile(dataset_name_or_path):
            # Local JSON file (our chorus_negotiations.json)
            dataset = load_dataset("json", data_files=dataset_name_or_path, split="train")
        elif os.path.isdir(dataset_name_or_path):
            # Local Arrow dataset saved with save_to_disk()
            dataset = load_from_disk(dataset_name_or_path)
        else:
            # HuggingFace Hub
            dataset = load_dataset(dataset_name_or_path, split="train")
    except Exception as e:
        print(f"Error loading dataset {dataset_name_or_path}: {e}")
        sys.exit(1)

    # Optional sampling to limit duration/memory if requested
    if sample_size and sample_size < len(dataset):
        print(f"Sampling {sample_size} examples out of {len(dataset)} for training...")
        dataset = dataset.shuffle(seed=42).select(range(sample_size))

    # Standardize data structure
    print("Standardizing dataset conversations...")
    dataset = dataset.map(map_dataset_to_messages, remove_columns=dataset.column_names)

    # Convert to chat template text
    def format_prompts(batch):
        formatted_texts = []
        for messages in batch["messages"]:
            try:
                formatted_text = tokenizer.apply_chat_template(
                    messages, 
                    tokenize=False, 
                    add_generation_prompt=False
                )
                formatted_texts.append(formatted_text)
            except Exception as e:
                # Handle templates that fail gracefully
                formatted_texts.append("")
        return {"text": formatted_texts}

    dataset = dataset.map(format_prompts, batched=True)
    
    # Filter out empty or broken rows
    dataset = dataset.filter(lambda x: len(x["text"]) > 0)

    # Tokenize input sequences
    # max_length=1024: halves peak VRAM vs 2048, prevents nvlddmkm TDR crash
    def tokenize_function(examples):
        tokenized = tokenizer(
            examples["text"],
            truncation=True,
            max_length=1024,
            padding=False
        )
        tokenized["labels"] = tokenized["input_ids"].copy()
        return tokenized

    print("Tokenizing dataset...")
    tokenized_dataset = dataset.map(
        tokenize_function, 
        batched=True, 
        remove_columns=dataset.column_names
    )
    return tokenized_dataset

def main(dataset_name: str, model_id: str, output_dir: str, sample_size: int = None):
    install_dependencies()

    # 1. Quantization configuration for RTX A2000 12GB VRAM
    print(f"Configuring 4-bit loading parameters for base model: {model_id}...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load base model in 4-bit
    print("Loading base model in 4-bit...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True
    )

    # Prepare model for PEFT
    model = prepare_model_for_kbit_training(model)

    # 2. PEFT LoRA Config targeting Qwen projections
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 3. Load & Process Dataset
    tokenized_dataset = load_and_prepare_dataset(dataset_name, tokenizer, sample_size)

    # 4. Training Arguments — crash-safe for RTX A2000 12GB VRAM
    # Changes vs original:
    #   gradient_accumulation_steps: 16→8   (less VRAM pressure per backward pass)
    #   save_steps:                  100→50  (more frequent checkpoints = less work lost on crash)
    #   optim: paged_adamw_32bit→paged_adamw_8bit  (4x less optimizer memory, ~2GB saved)
    print("Configuring training arguments...")
    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,   # Effective batch 8 — stable and memory-efficient
        warmup_steps=50,
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=5,
        save_strategy="steps",
        save_steps=50,              # Save every 50 steps — crash-safe
        save_total_limit=5,         # Keep last 5 checkpoints
        optim="paged_adamw_8bit",   # 8-bit optimizer: saves ~2GB VRAM vs 32bit
        gradient_checkpointing=True,
        report_to="none",
        ddp_find_unused_parameters=False
    )

    # 5. Initialize Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=DataCollatorForSeq2Seq(tokenizer, pad_to_multiple_of=8, return_tensors="pt", padding=True)
    )

    # 6. Execute Training (resumes automatically from output_dir if checkpoint exists)
    checkpoint = None
    if os.path.exists(output_dir):
        checkpoints = [
            os.path.join(output_dir, d) for d in os.listdir(output_dir)
            if d.startswith("checkpoint-") and os.path.isdir(os.path.join(output_dir, d))
        ]
        if checkpoints:
            # Sort checkpoints chronologically
            checkpoints.sort(key=os.path.getmtime)
            checkpoint = checkpoints[-1]
            print(f"Found existing training checkpoint: {checkpoint}. Resuming training...")

    print("Starting fine-tuning...")
    try:
        trainer.train(resume_from_checkpoint=checkpoint)
    except Exception as e:
        print(f"Training was interrupted or encountered an error: {e}")
        print("Saving current adapter checkpoint...")
        trainer.model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)
        raise e

    # 7. Save Final Adapter Model
    print(f"Training completed successfully! Saving final adapter to: {output_dir}")
    trainer.model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print("All tasks complete. Happy serving!")

if __name__ == "__main__":
    # Default: use local chorus_negotiations.json (4893 examples, already prepared)
    dataset = "chorus_negotiations.json"
    model   = "models/Qwen2.5-7B-Browser-Agent-Merged"
    output  = "./orchestrator_lora"
    samples = None
    
    if len(sys.argv) > 1:
        dataset = sys.argv[1]
    if len(sys.argv) > 2:
        model = sys.argv[2]
    if len(sys.argv) > 3:
        output = sys.argv[3]
    if len(sys.argv) > 4:
        try:
            samples = int(sys.argv[4])
        except ValueError:
            samples = None
            
    main(dataset, model, output, samples)
