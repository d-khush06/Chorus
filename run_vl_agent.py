import os
import torch
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

MODEL_ID = "dkhush06/Qwen2.5-VL-Agent2-Merged"
LOCAL_MODEL_PATH = os.path.join(".", "models", "Qwen2.5-VL-Agent2-Merged")

if os.path.exists(LOCAL_MODEL_PATH):
    model_source = LOCAL_MODEL_PATH
    print(f"Loading vision model locally from: {LOCAL_MODEL_PATH}")
else:
    model_source = MODEL_ID
    print(f"Loading vision model directly from Hugging Face: {model_source}")

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Running on device: {device.upper()}")

# Load Model & Processor
processor = AutoProcessor.from_pretrained(model_source)
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    model_source,
    torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
    device_map="auto" if torch.cuda.is_available() else None,
    low_cpu_mem_usage=True
)

if device == "cpu":
    model.to("cpu")

print("\nQwen2.5-VL Vision Model loaded successfully!")
