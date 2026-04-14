"""
NemoClaw NPU Inference Server
OpenAI-compatible REST API backed by Intel NPU via OpenVINO GenAI
Listens on 0.0.0.0:11435 — accessible from WSL2 at host IP

Security:
  NPU_API_KEY   — Bearer token required on all /v1/* endpoints (set in .env)
  NPU_TLS_CERT  — Path to TLS certificate file (enables HTTPS)
  NPU_TLS_KEY   — Path to TLS private key file

Run in production via gunicorn:
  gunicorn --bind 0.0.0.0:11435 --workers 1 --timeout 120 server:app
  (or with TLS): gunicorn --bind 0.0.0.0:11435 --certfile server.crt --keyfile server.key ...
"""

import json
import time
import uuid
import threading
import sys
import os
import ssl
import secrets
from pathlib import Path
from flask import Flask, request, jsonify, Response, stream_with_context

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False
    print("[warn] flask-limiter not installed — rate limiting disabled. Run: pip install flask-limiter")

try:
    import openvino_genai as ov_genai
except ImportError:
    print("ERROR: openvino-genai not installed. Run: pip install openvino-genai")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL_DIR   = Path(__file__).parent / "model"
PORT        = 11435
DEVICE      = "AUTO:NPU,GPU"
MODEL_NAME  = "phi-3.5-mini-npu"

# Server-side hard cap on generated tokens — prevents runaway inference
MAX_TOKENS_LIMIT = 2048

# API key auth — set NPU_API_KEY env var to enable; empty = auth disabled
API_KEY = os.environ.get("NPU_API_KEY", "").strip()
if API_KEY:
    print(f"[security] API key authentication ENABLED")
else:
    print(f"[security] WARNING: API key authentication DISABLED (set NPU_API_KEY)")

# TLS — set NPU_TLS_CERT and NPU_TLS_KEY to enable HTTPS
TLS_CERT = os.environ.get("NPU_TLS_CERT", "").strip()
TLS_KEY  = os.environ.get("NPU_TLS_KEY",  "").strip()
if TLS_CERT and TLS_KEY:
    print(f"[security] TLS ENABLED — cert: {TLS_CERT}")
else:
    print(f"[security] TLS DISABLED — traffic is plaintext HTTP")

# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB max request body

# Rate limiting (requires flask-limiter)
if LIMITER_AVAILABLE:
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["120/minute"],
        storage_uri="memory://",
    )
    print("[security] Rate limiting ENABLED (120 req/min global, 10 req/min inference)")
else:
    limiter = None

pipe      = None
pipe_lock = threading.Lock()
active_device = DEVICE

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def check_auth():
    """Return 401 response if API key is set and request lacks valid Bearer token."""
    if not API_KEY:
        return None
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": {"message": "Missing Authorization header", "type": "auth_error"}}), 401
    token = auth_header[len("Bearer "):]
    if not secrets.compare_digest(token, API_KEY):
        return jsonify({"error": {"message": "Invalid API key", "type": "auth_error"}}), 401
    return None

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
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
    """Convert OpenAI messages list to a Phi-3.5 prompt string."""
    parts = []
    for m in messages:
        role    = m.get("role", "user")
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
            "finish_reason": finish_reason,
        }],
    }

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    """Minimal health check — intentionally returns no device/model fingerprint."""
    return jsonify({"status": "ok"})


@app.route("/v1/models", methods=["GET"])
def list_models():
    auth_err = check_auth()
    if auth_err:
        return auth_err
    return jsonify({
        "object": "list",
        "data": [{
            "id": MODEL_NAME,
            "object": "model",
            "created": 0,
            "owned_by": "local-npu",
        }],
    })


@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    auth_err = check_auth()
    if auth_err:
        return auth_err

    # Apply rate limit if available
    if limiter:
        limiter.limit("10/minute")(lambda: None)()

    data        = request.get_json(force=True)
    messages    = data.get("messages", [])
    stream      = data.get("stream", False)
    # Server-side cap — client cannot request more than MAX_TOKENS_LIMIT
    max_tokens  = min(int(data.get("max_tokens", 512)), MAX_TOKENS_LIMIT)
    temperature = float(data.get("temperature", 0.7))
    model       = data.get("model", MODEL_NAME)

    prompt = messages_to_prompt(messages)

    config = ov_genai.GenerationConfig()
    config.max_new_tokens = max_tokens
    config.temperature    = temperature
    config.do_sample      = temperature > 0

    if stream:
        def generate():
            chunks = []
            with pipe_lock:
                for token in pipe.generate(prompt, config, streamer=lambda s: chunks.append(s)):
                    pass
            for token in chunks:
                yield f"data: {json.dumps(make_chunk(token, model))}\n\n"
            yield f"data: {json.dumps(make_chunk('', model, finish_reason='stop'))}\n\n"
            yield "data: [DONE]\n\n"
        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens":     len(prompt.split()),
            "completion_tokens": len(text.split()),
            "total_tokens":      len(prompt.split()) + len(text.split()),
            "elapsed_seconds":   round(elapsed, 2),
        },
    })


# ---------------------------------------------------------------------------
# Entry point
#   - With TLS certs:  Flask + ssl_context  (Python ssl module, TLS 1.2+)
#   - Without TLS:     waitress             (production WSGI, no dev-server warning)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    active_device = load_model()

    has_tls = bool(TLS_CERT and TLS_KEY and os.path.exists(TLS_CERT) and os.path.exists(TLS_KEY))

    if has_tls:
        # Flask handles TLS natively via Python's ssl module when given (cert, key) tuple
        print(f"NemoClaw NPU server -> https://0.0.0.0:{PORT}  [Flask+TLS]  device={active_device}")
        app.run(host="0.0.0.0", port=PORT, ssl_context=(TLS_CERT, TLS_KEY), threaded=False)
    else:
        try:
            from waitress import serve as waitress_serve
            print(f"NemoClaw NPU server -> http://0.0.0.0:{PORT}  [waitress]  device={active_device}")
            waitress_serve(app, host="0.0.0.0", port=PORT, threads=1)
        except ImportError:
            print(f"[warn] waitress not installed, using Flask dev server")
            app.run(host="0.0.0.0", port=PORT, threaded=False)
