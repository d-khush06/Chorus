import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

LOCAL_MODEL_PATH = os.path.join(".", "models", "Qwen2.5-7B-Browser-Agent-Merged")

# Check if model is already downloaded locally, otherwise load from Hugging Face hub
if os.path.exists(LOCAL_MODEL_PATH):
    model_source = LOCAL_MODEL_PATH
    print(f"Loading model locally from: {LOCAL_MODEL_PATH}")
else:
    model_source = "dkhush06/Qwen2.5-7B-Browser-Agent-Merged"
    print(f"Loading model directly from Hugging Face: {model_source}")

# Load Tokenizer
tokenizer = AutoTokenizer.from_pretrained(model_source)

# Load Model on CPU (or GPU if available)
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Running on device: {device.upper()}")

model = AutoModelForCausalLM.from_pretrained(
    model_source,
    torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
    device_map="auto" if torch.cuda.is_available() else None,
    low_cpu_mem_usage=True
)

if device == "cpu":
    model.to("cpu")

print("\nModel loaded successfully! Ready for prompt.\n")

# Prompt template for Qwen2.5 Chat format
prompt = "You are a helpful browser automation assistant. Describe how you would navigate to a search engine and search for news."

messages = [
    {"role": "system", "content": "You are a helpful browser agent assistant."},
    {"role": "user", "content": prompt}
]

text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True
)

model_inputs = tokenizer([text], return_tensors="pt").to(device)

print("Generating response locally...")
generated_ids = model.generate(
    **model_inputs,
    max_new_tokens=256
)

generated_ids = [
    output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
]

response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
print("\n--- Model Output ---")
print(response)
