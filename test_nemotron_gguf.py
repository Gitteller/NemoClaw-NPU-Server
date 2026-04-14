import openvino_genai as ov
import time, os

# Try directory first, then direct file path
paths_to_try = [
    r"C:\WSL\NemoClaw\npu-server\nemotron",
    r"C:\WSL\NemoClaw\npu-server\nemotron\nemotron-3-nano-4b.gguf",
]

devices_to_try = ["AUTO:NPU,GPU", "GPU", "CPU"]

for model_path in paths_to_try:
    exists = os.path.exists(model_path)
    print(f"\nPath: {model_path}")
    print(f"Exists: {exists}")
    if not exists:
        continue
    for device in devices_to_try:
        print(f"  Trying device={device}...")
        t = time.time()
        try:
            pipe = ov.LLMPipeline(model_path, device)
            elapsed = time.time() - t
            print(f"  LOADED in {elapsed:.1f}s on {device}")
            cfg = ov.GenerationConfig()
            cfg.max_new_tokens = 8
            cfg.do_sample = False
            r = pipe.generate("Say only: OK", cfg)
            print(f"  Response: {r!r}")
            break
        except Exception as e:
            print(f"  FAILED on {device}: {e}")
    else:
        continue
    break
