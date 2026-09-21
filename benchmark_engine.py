import os
import time
from video_engine import VideoEngine, TechnicalAnalyzer, MotionAnalyzer, ShotsAnalyzer, TextAndCodeAnalyzer

def benchmark_engine(video_path: str):
    if not os.path.exists(video_path):
        print(f"Video not found for benchmark: {video_path}")
        return
        
    print(f"Starting single-pass engine benchmark on {video_path}...")
    engine = VideoEngine(video_path, max_downscale_width=640)
    engine.add_analyzer(TechnicalAnalyzer())
    engine.add_analyzer(MotionAnalyzer(compute_heatmap=False))
    engine.add_analyzer(ShotsAnalyzer())
    engine.add_analyzer(TextAndCodeAnalyzer())
    
    start_time = time.time()
    results = engine.run(sample_rate_fps=0) # Process all frames
    end_time = time.time()
    
    elapsed = end_time - start_time
    total_frames = results["metadata"]["total_frames"]
    fps = total_frames / elapsed if elapsed > 0 else 0
    
    print("--- BENCHMARK RESULTS ---")
    print(f"Total Frames Processed: {total_frames}")
    print(f"Elapsed Time: {elapsed:.2f} seconds")
    print(f"Throughput: {fps:.2f} frames per second")
    print(f"Analyzers Run: Technical, Motion, Shots, TextAndCode")

if __name__ == "__main__":
    benchmark_engine("synthetic_test.mp4")
