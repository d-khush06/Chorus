import os
import sys
import time
import json
import argparse
import traceback
import glob

# Ensure we can import modules from the project root
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from run_vl_agent import run_vision_analysis, unload_vl_model
import cv2
from PIL import Image

def _emit_chunk_event(chunk_data):
    print(f"CHUNK_EVENT:{json.dumps(chunk_data)}", flush=True)

def _emit_observation_event(obs_data):
    print(f"OBSERVATION_EVENT:{json.dumps(obs_data)}", flush=True)

def _emit_alert_event(alert_data):
    print(f"ALERT_EVENT:{json.dumps(alert_data)}", flush=True)

def extract_frame_from_ts(ts_path):
    cap = cv2.VideoCapture(ts_path)
    if not cap.isOpened():
        return None
    
    # Try to grab a frame from the middle of the 2-second segment
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames // 2))
        
    ret, frame = cap.read()
    cap.release()
    
    if ret:
        import numpy as np
        # Check if frame is a corrupted solid color/gray frame (common in incomplete TS files)
        # If standard deviation is extremely low, the frame is just a solid color (e.g., all gray)
        if np.std(frame) < 5.0:
            print("[LiveWorker] Skipped corrupted/solid color frame", file=sys.stderr)
            return None
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return None

def main():
    parser = argparse.ArgumentParser(description="Live stream chunk observer")
    parser.add_argument("--hls-dir", required=True, help="Directory containing live HLS .ts chunks")
    parser.add_argument("--run-id", required=True, help="Run ID for this stream")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between observations")
    parser.add_argument("--question", type=str, default="Analyze this video.", help="Prompt for VL model")
    
    args = parser.parse_args()
    
    print(f"[LiveWorker] Starting chunk observer for {args.run_id} in {args.hls_dir}", file=sys.stderr)
    
    chunk_index = 0
    
    while True:
        loop_start = time.time()
        
        # 1. Find the newest .ts file in the directory
        ts_files = glob.glob(os.path.join(args.hls_dir, "*.ts"))
        if not ts_files:
            # Stream might not be ready yet, or is disconnected
            time.sleep(2)
            continue
            
        # Get the most recently modified .ts file
        latest_ts = max(ts_files, key=os.path.getmtime)
        ts_mtime = os.path.getmtime(latest_ts)
        
        # Prevent analyzing the exact same old chunk repeatedly if stream stalls
        if time.time() - ts_mtime > args.interval * 1.5:
            # Stream appears stalled, sleep and wait for fresh chunks
            time.sleep(2)
            continue
            
        # 2. Extract a frame
        frame = extract_frame_from_ts(latest_ts)
        
        if frame:
            # 3. Emit CHUNK_EVENT to notify the UI that a 30s chunk was "processed"
            _emit_chunk_event({
                "chunk_index": chunk_index,
                "duration": args.interval,
                "timestamp": chunk_index * args.interval,
                "tamper_detected": False
            })
            
            try:
                # 4. Run the local VL Model
                print(f"[LiveWorker] Analyzing chunk {chunk_index}...", file=sys.stderr)
                metadata = {
                    "video_title": f"Live Stream (Chunk {chunk_index})",
                    "duration_seconds": args.interval
                }
                analysis_text = run_vision_analysis([frame], args.question, metadata)
                if analysis_text:
                    _emit_observation_event({
                        "text": analysis_text,
                        "confidence": 0.95
                    })
            except Exception as e:
                print(f"[LiveWorker] Error running VL analysis: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
            finally:
                unload_vl_model()
                
            chunk_index += 1
            
            # 6. Sleep for the remainder of the interval only if we successfully analyzed a frame
            elapsed = time.time() - loop_start
            sleep_time = max(0, args.interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
        else:
            # If we failed to extract a frame (e.g. incomplete TS segment), retry quickly
            time.sleep(1)

if __name__ == "__main__":
    main()
