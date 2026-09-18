import os
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

LOCAL_MODEL_PATH = os.path.join(".", "models", "Qwen2.5-7B-Browser-Agent-Merged")
MODEL_ID = "dkhush06/Qwen2.5-7B-Browser-Agent-Merged"

_model = None
_tokenizer = None
_device = "cuda" if torch.cuda.is_available() else "cpu"

def load_text_model():
    global _model, _tokenizer
    if _model is not None and _tokenizer is not None:
        return _model, _tokenizer

    if os.path.exists(LOCAL_MODEL_PATH):
        model_source = LOCAL_MODEL_PATH
        print(f"  [Text Agent] Loading model locally from: {LOCAL_MODEL_PATH}")
    else:
        model_source = MODEL_ID
        print(f"  [Text Agent] Loading model directly from Hugging Face: {model_source}")

    print(f"  [Text Agent] Running on device: {_device.upper()}")

    _tokenizer = AutoTokenizer.from_pretrained(model_source)

    if torch.cuda.is_available():
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        _model = AutoModelForCausalLM.from_pretrained(
            model_source,
            quantization_config=bnb_config,
            device_map="auto",
            low_cpu_mem_usage=True,
        )
    else:
        _model = AutoModelForCausalLM.from_pretrained(
            model_source,
            torch_dtype=torch.float32,
            device_map=None,
            low_cpu_mem_usage=True,
        )
        _model.to("cpu")

    print("  [Text Agent] Qwen2.5-7B Text Model loaded successfully!")
    return _model, _tokenizer


def unload_text_model():
    """Release the Text Brain model from VRAM/CPU memory."""
    global _model, _tokenizer
    if _model is not None:
        try:
            del _model
        except Exception:
            pass
        _model = None
        _tokenizer = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("  [Text Agent] Model unloaded from memory.", flush=True)

def run_text_analysis(user_prompt, metadata, raw_text=""):
    """
    Takes a user prompt and optional scraped text, passes them to Qwen2.5-7B,
    and requests an analysis/answer. Saves outputs to text_output.json and text_output.txt.
    """
    try:
        model, tokenizer = load_text_model()
    except Exception as e:
        print(f"  [Text Agent ERROR] Initialization failed: {e}")
        return None

    print(f"  [Text Agent] Processing text query...")

    system_prompt = (
        "You are an expert AI assistant. Analyze the provided query and any supplementary scraped text. "
        "Answer the user's question directly. "
        "Format your final response strictly as a JSON object with two keys: "
        "'summary' (string) and 'detailed_answer' (string)."
    )

    context = ""
    if raw_text:
        context = f"\n\nContext / Scraped Text:\n{raw_text[:32000]}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"User Question: {user_prompt}{context}"}
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    model_inputs = tokenizer([text], return_tensors="pt").to(_device)

    try:
        generated_ids = model.generate(**model_inputs, max_new_tokens=2048)
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(model_inputs.input_ids, generated_ids)
        ]
        
        output_text = tokenizer.batch_decode(generated_ids_trimmed, skip_special_tokens=True)[0]
        
        # Save Text Output
        with open("text_output.txt", "w", encoding="utf-8") as f:
            f.write(output_text)
            
        # Attempt to extract JSON from output
        json_str = output_text
        if "```json" in output_text:
            json_str = output_text.split("```json")[1].split("```")[0].strip()
        elif "```" in output_text:
            json_str = output_text.split("```")[1].split("```")[0].strip()
            
        try:
            parsed_json = json.loads(json_str)
            with open("text_output.json", "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=4)
        except json.JSONDecodeError:
            with open("text_output.json", "w", encoding="utf-8") as f:
                json.dump({"raw_output": output_text}, f, indent=4)
                
        print("  [Text Agent] Analysis complete! \\u2713")
        print(f"  [Text Agent] Results saved to: {os.path.abspath('text_output.txt')} and text_output.json")
        return output_text

    except Exception as e:
        print(f"  [Text Agent ERROR] Generation failed: {e}")
        return None
