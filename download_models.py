import os
from huggingface_hub import snapshot_download

# Select which model to download:
# 1. dkhush06/Qwen2.5-7B-Browser-Agent-Merged
# 2. dkhush06/Qwen2.5-VL-Agent2-Merged

MODEL_ID = "dkhush06/Qwen2.5-7B-Browser-Agent-Merged"
LOCAL_DIR = os.path.join(".", "models", "Qwen2.5-7B-Browser-Agent-Merged")

print(f"Downloading model '{MODEL_ID}' locally to '{LOCAL_DIR}'...")

# Download files to local directory without paying any API costs
snapshot_download(
    repo_id=MODEL_ID,
    local_dir=LOCAL_DIR,
    local_dir_use_symlinks=False
)

print("\nDownload finished successfully!")
print(f"Model saved locally at: {os.path.abspath(LOCAL_DIR)}")
