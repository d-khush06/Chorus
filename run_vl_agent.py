import os
import json
import torch
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

MODEL_ID = "dkhush06/Qwen2.5-VL-Agent2-Merged"
LOCAL_MODEL_PATH = os.path.join(".", "models", "Qwen2.5-VL-Agent2-Merged")

_model = None
_processor = None
_device = "cuda" if torch.cuda.is_available() else "cpu"

def load_vl_model():
    global _model, _processor
    if _model is not None and _processor is not None:
        return _model, _processor

    if os.path.exists(LOCAL_MODEL_PATH):
        model_source = LOCAL_MODEL_PATH
        print(f"  [VL Agent] Loading vision model locally from: {LOCAL_MODEL_PATH}")
    else:
        model_source = MODEL_ID
        print(f"  [VL Agent] Loading vision model directly from Hugging Face: {model_source}")

    print(f"  [VL Agent] Running on device: {_device.upper()}")
    
    try:
        from qwen_vl_utils import process_vision_info
    except ImportError:
        print("  [VL Agent ERROR] Missing qwen-vl-utils. Please stop and run: pip install qwen-vl-utils")
        raise

    _processor = AutoProcessor.from_pretrained(model_source)
    _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_source,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
        load_in_4bit=True if torch.cuda.is_available() else False,
        low_cpu_mem_usage=True
    )
    if _device == "cpu":
        _model.to("cpu")
    print("  [VL Agent] Qwen2.5-VL Vision Model loaded successfully!")
    return _model, _processor


def unload_vl_model():
    """Release the VL Vision Brain model from VRAM/CPU memory."""
    global _model, _processor
    if _model is not None:
        try:
            del _model
        except Exception:
            pass
        _model = None
        _processor = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("  [VL Agent] Vision model unloaded from memory.", flush=True)

def run_vision_analysis(frames, user_prompt, metadata):
    """
    Takes a list of PIL Images (frames), passes them to Qwen2.5-VL,
    and requests a detailed analysis including timeline and objects.
    Saves outputs to vl_output.json and vl_output.txt.
    """
    if not frames:
        print("  [VL Agent] No frames provided. Skipping analysis.")
        return None

    try:
        model, processor = load_vl_model()
        from qwen_vl_utils import process_vision_info
    except Exception as e:
        print(f"  [VL Agent ERROR] Initialization failed: {e}")
        return None

    print(f"  [VL Agent] Analyzing {len(frames)} frames...")

    ai_gen = metadata.get("ai_generated_flag", False) if metadata else False
    deepfake = metadata.get("deepfake_flag", False) if metadata else False
    
    forensic_alert = ""
    if ai_gen or deepfake:
        signals = []
        if ai_gen: signals.append("Synthetic/Diffusion artifacts flagged by baseline classifier")
        if deepfake: signals.append("Facial anomaly flagged by face forgery scanner")
        
        forensic_alert = (
            f"\n[Automated Pre-Scanner Signals: {', '.join(signals)}]\n"
            f"- Evaluate visual evidence objectively (look for hands/fingers, lighting consistency, natural skin textures, reflections, motion continuity, and physical physics).\n"
            f"- If asked whether the video is real or AI-generated/deepfake, provide an honest, evidence-backed verdict based on what is genuinely visible in the frames rather than blindly assuming it is fake."
        )

    system_prompt = (
        f"You are an expert video analysis and forensic intelligence AI. Analyze the provided sequence of frames thoroughly.\n"
        f"{forensic_alert}\n"
        f"Provide a detailed, conversational response answering the user's question, just like a helpful AI chatbot.\n"
        f"In your analysis, automatically perform fine-grained detection and extraction:\n"
        f"- **Vehicles & Transport**: Specifically identify the exact make, model, type, color, and transcribe visible license plate numbers or registration plates (OCR).\n"
        f"- **Text & OCR**: Transcribe any visible text, street signs, shop names, brand logos, badges, or writing on clothing/objects.\n"
        f"- **People & Identities**: Note identifiable roles, names on badges, distinct attire, and accessories.\n"
        f"- **Objects & Environment**: Identify specific object models/brands rather than generic categories.\n"
        f"Use clean markdown formatting, bullet points, and clear sections to present your findings."
    )

    content = []
    for frame in frames:
        # High-definition resolution for reading license plates, text, and fine details on GPU
        frame.thumbnail((768, 768))
        content.append({"type": "image", "image": frame})
    
    content.append({"type": "text", "text": f"{system_prompt}\n\nUser Question: {user_prompt}"})

    messages = [
        {"role": "user", "content": content}
    ]

    try:
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        )
        inputs = inputs.to(_device)
        
        # Generate output
        generated_ids = model.generate(**inputs, max_new_tokens=1024)
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        
        output_text = processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        
        # Save Text Output
        with open("vl_output.txt", "w", encoding="utf-8") as f:
            f.write(output_text)
            
        # Attempt to extract JSON from output
        json_str = output_text
        if "```json" in output_text:
            json_str = output_text.split("```json")[1].split("```")[0].strip()
        elif "```" in output_text:
            json_str = output_text.split("```")[1].split("```")[0].strip()
            
        try:
            parsed_json = json.loads(json_str)
            with open("vl_output.json", "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=4)
        except json.JSONDecodeError:
            # Fallback if model didn't output strict JSON
            with open("vl_output.json", "w", encoding="utf-8") as f:
                json.dump({"raw_output": output_text}, f, indent=4)
                
        print("  [VL Agent] Analysis complete! DONE")
        print(f"  [VL Agent] Results saved to: {os.path.abspath('vl_output.txt')} and vl_output.json")
        return output_text

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  [VL Agent ERROR] Generation failed: {e}")
        return None
