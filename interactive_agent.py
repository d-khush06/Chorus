import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

LOCAL_MODEL_PATH = os.path.join(".", "models", "Qwen2.5-7B-Browser-Agent-Merged")

if os.path.exists(LOCAL_MODEL_PATH):
    model_source = LOCAL_MODEL_PATH
    print(f"Loading local model from: {LOCAL_MODEL_PATH}")
else:
    model_source = "dkhush06/Qwen2.5-7B-Browser-Agent-Merged"
    print(f"Loading model from Hugging Face: {model_source}")

# Load Tokenizer & Model
tokenizer = AutoTokenizer.from_pretrained(model_source)
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {device.upper()}")

model = AutoModelForCausalLM.from_pretrained(
    model_source,
    torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
    device_map="auto" if torch.cuda.is_available() else None,
    low_cpu_mem_usage=True
)

if device == "cpu":
    model.to("cpu")

print("\n" + "="*50)
print("🚀 Model Loaded Successfully!")
print("Type your prompt and press Enter. Type 'exit' or 'quit' to stop.")
print("="*50 + "\n")

conversation_history = [
    {"role": "system", "content": "You are a helpful browser agent assistant."}
]

while True:
    try:
        user_prompt = input("\n👤 Your Prompt > ").strip()
        if not user_prompt:
            continue
        if user_prompt.lower() in ["exit", "quit", "q"]:
            print("Exiting interactive test. Goodbye!")
            break

        # Append user message to history
        current_messages = conversation_history + [{"role": "user", "content": user_prompt}]

        text = tokenizer.apply_chat_template(
            current_messages,
            tokenize=False,
            add_generation_prompt=True
        )

        model_inputs = tokenizer([text], return_tensors="pt").to(device)

        print("🤖 Generating response...")
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=256,
            do_sample=False  # Deterministic generation for agent tools
        )

        generated_ids = [
            output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]

        response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        print("\n--- 🤖 Model Response ---")
        print(response)

    except KeyboardInterrupt:
        print("\nExiting. Goodbye!")
        break
