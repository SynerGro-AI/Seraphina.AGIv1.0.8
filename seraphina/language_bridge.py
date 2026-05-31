# language_engine_bridge.py
import subprocess
import json
import os

def call_glyph_cipher(input_data: dict) -> dict:
    """Bridge to Glyph Language Engine CLI (base64 JSON input)"""
    import base64
    import json
    script_path = os.path.join(os.path.dirname(__file__), "advanced-language-engine.js")
    
    try:
        input_json = json.dumps(input_data)
        input_b64 = base64.b64encode(input_json.encode('utf-8')).decode('utf-8')
        result = subprocess.run(
            ["node", script_path, "--input", input_b64],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {"error": result.stderr}
    except Exception as e:
        return {"error": str(e), "bridge_status": "failed"}

# Simple CLI for testing
if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "Hello world peace abundance"
    print(json.dumps(call_glyph_cipher(text), indent=2))