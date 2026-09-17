import sys, json, re
from pipeline_runner import load_orchestrator

model, tokenizer = load_orchestrator()
system_prompt = 'You are the ORCHESTRATOR for the Chorus video-intelligence pipeline. Decide which agents to call in what order. Return ONLY valid JSON: {"mode": "general"|"cyber", "tool_calls": [...], "excluded": [...], "reasoning_summary": "..."}'
scenario = 'SCENARIO: source_type: local_upload | user_question: Summarize this video | mode_hint: general | governance_approved: False | manipulation_verdict: CLEAN | has_audio: True | has_video: True'

messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': scenario}]
text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
import torch
device = 'cuda' if torch.cuda.is_available() else 'cpu'
inputs = tokenizer([text], return_tensors='pt').to(device)
out = model.generate(**inputs, max_new_tokens=256, do_sample=False)
trimmed = out[0][inputs.input_ids.shape[1]:]
raw = tokenizer.decode(trimmed, skip_special_tokens=True).strip()
print('RAW OUTPUT:')
print(raw)
