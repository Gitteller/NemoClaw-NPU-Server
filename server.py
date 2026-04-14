"""
NemoClaw NPU Inference Server
OpenAI-compatible REST API backed by Intel NPU via OpenVINO GenAI
Listens on 0.0.0.0:11435 — accessible from WSL2 at host IP
"""

import json
import time
import uuid
import threading
import sys
import os
from pathlib import Path
from flask import Flask, request, jsonify, Response, stream_with_context

try:
    import openvino_genai as ov_genai
except ImportError:
    print("ERROR: openvino-genai not installed. Run: pip install openvino-genai")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL_DIR = Path(__file__).parent / "model"
PORT = 11435
# AUTO:NPU,GPU  — tries NPU first, offloads unsupported layers to Arc GPU
# AUTO:NPU,CPU  — NPU + CPU fallback (slower but always works)
# CPU           — pure CPU fallback
DEVICE = "AUTO:NPU,GPU"
MODEL_NAME = "phi-3.5-mini-npu"   # Reported name in /v1/models

# ---------------------------------------------------------------------------
app = Flask(__name__)
pipe = None
pipe_lock = threading.Lock()
active_device = DEVICE

def load_model():
    global pipe
    model_path = str(MODEL_DIR)
    if not Path(model_path).exists() or not any(Path(model_path).iterdir()):
        print(f"ERROR: No model found in {model_path}")
        print("Run download_model.py first to fetch a pre-converted OpenVINO model.")
        sys.exit(1)
    actual_device = DEVICE
    print(f"Loading model from {model_path} on device={DEVICE} ...")
    for attempt_device in [DEVICE, "AUTO:GPU,CPU", "CPU"]:
        try:
            pipe = ov_genai.LLMPipeline(model_path, attempt_device)
            actual_device = attempt_device
            print(f"Model loaded on {actual_device}.")
            break
        except Exception as e:
            print(f"WARNING: Failed to load on {attempt_device}: {e}")
            if attempt_device == "CPU":
                raise
    return actual_device

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def messages_to_prompt(messages):
    """Convert OpenAI messages list to a single prompt string."""
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            parts.append(f"<|system|>\n{content}<|end|>")
        elif role == "user":
            parts.append(f"<|user|>\n{content}<|end|>")
        elif role == "assistant":
            parts.append(f"<|assistant|>\n{content}<|end|>")
    parts.append("<|assistant|>")
    return "\n".join(parts)

def make_chunk(content, model, finish_reason=None):
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"content": content} if content else {},
            "finish_reason": finish_reason
        }]
    }

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/v1/models", methods=["GET"])
def list_models():
    return jsonify({
        "object": "list",
        "data": [{
            "id": MODEL_NAME,
            "object": "model",
            "created": 0,
            "owned_by": "local-npu"
        }]
    })

@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    data = request.get_json(force=True)
    messages = data.get("messages", [])
    stream = data.get("stream", False)
    max_tokens = data.get("max_tokens", 512)
    temperature = float(data.get("temperature", 0.7))
    model = data.get("model", MODEL_NAME)

    prompt = messages_to_prompt(messages)

    config = ov_genai.GenerationConfig()
    config.max_new_tokens = max_tokens
    config.temperature = temperature
    if temperature == 0:
        config.do_sample = False
    else:
        config.do_sample = True

    if stream:
        def generate():
            chunks = []
            with pipe_lock:
                for token in pipe.generate(prompt, config, streamer=lambda s: chunks.append(s)):
                    pass
            # Stream accumulated tokens
            for token in chunks:
                chunk = make_chunk(token, model)
                yield f"data: {json.dumps(chunk)}\n\n"
            yield f"data: {json.dumps(make_chunk('', model, finish_reason='stop'))}\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(generate()),
                        mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    else:
        t0 = time.time()
        with pipe_lock:
            result = pipe.generate(prompt, config)
        elapsed = time.time() - t0
        text = result if isinstance(result, str) else str(result)
        return jsonify({
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(text.split()),
                "total_tokens": len(prompt.split()) + len(text.split()),
                "elapsed_seconds": round(elapsed, 2)
            }
        })

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "device": active_device, "model": MODEL_NAME})

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    active_device = load_model()
    print(f"NemoClaw NPU server listening on 0.0.0.0:{PORT} (device: {active_device})")
    app.run(host="0.0.0.0", port=PORT, threaded=False)
