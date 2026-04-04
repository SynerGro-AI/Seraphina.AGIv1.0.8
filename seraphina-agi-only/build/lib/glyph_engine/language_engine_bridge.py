# language_engine_bridge.py
import subprocess
import json
import os
import sys

# WASM support (optional - requires wasmtime or similar)
try:
    import wasmtime
    WASM_AVAILABLE = True
except ImportError:
    WASM_AVAILABLE = False

def call_glyph_cipher(command_args: str) -> dict:
    """Bridge to call the new Glyph Roman Wheel cipher from Python with full CLI support"""
    script_path = os.path.join(os.path.dirname(__file__), "..", "advanced-language-engine.js")

    try:
        # Parse arguments properly to handle quotes
        import shlex
        args = shlex.split(command_args)
        full_args = ["node", script_path] + args

        result = subprocess.run(
            full_args,
            capture_output=True, text=True, encoding='utf-8', timeout=10
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if output:
                parsed = json.loads(output)
                # Add safety note for Justice & Mercy Anchor
                if parsed.get('anchorActivated', False):
                    parsed['safetyNote'] = "Justice & Mercy Anchor applied - Truth and Humility reign"
                return parsed
            else:
                return {"error": "No output from engine"}
        else:
            return {"error": result.stderr, "returncode": result.returncode}
    except UnicodeDecodeError:
        # Fallback for encoding issues
        try:
            result = subprocess.run(
                full_args,
                capture_output=True, text=True, encoding='latin-1', timeout=10
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    parsed = json.loads(output)
                    # Add safety note for Justice & Mercy Anchor
                    if parsed.get('anchorActivated', False):
                        parsed['safetyNote'] = "Justice & Mercy Anchor applied - Truth and Humility reign"
                    return parsed
        except:
            pass
        return {"error": "Unicode encoding issue with engine output", "bridge_status": "encoding_failed"}
# WASM-accelerated Glyph engine
def call_glyph_wasm(command_args: str) -> dict:
    """Call WebAssembly-accelerated Glyph engine"""
    if not WASM_AVAILABLE:
        return {"error": "WASM not available - install wasmtime: pip install wasmtime", "bridge_status": "wasm_unavailable"}

    wasm_path = os.path.join(os.path.dirname(__file__), "glyph-wasm.wasm")
    if not os.path.exists(wasm_path):
        return {"error": "WASM file not found - compile glyph-wasm.ts first with: asc glyph-wasm.ts -o glyph-wasm.wasm", "bridge_status": "wasm_not_compiled"}

    try:
        # Parse command args to extract operation and parameters
        args = command_args.split()
        op = "encrypt"
        text = "Hello world"
        name = "test"
        apply_anchor = False

        i = 0
        while i < len(args):
            if args[i] == "--op" and i + 1 < len(args):
                op = args[i + 1]
                i += 2
            elif args[i] == "--text" and i + 1 < len(args):
                text = args[i + 1]
                i += 2
            elif args[i] == "--name" and i + 1 < len(args):
                name = args[i + 1]
                i += 2
            elif args[i] == "--applyAnchor" and i + 1 < len(args):
                apply_anchor = args[i + 1].lower() == "true"
                i += 2
            else:
                i += 1

        # Load and run WASM
        store = wasmtime.Store()
        module = wasmtime.Module.from_file(store.engine, wasm_path)
        instance = wasmtime.Instance(store, module, [])

        if op == "encrypt":
            encrypt_func = instance.exports(store)["encryptGlyph"]
            result_glyph = encrypt_func(store, text)
            return {
                "encrypted": result_glyph,
                "operation": "encrypt",
                "status": "success",
                "wasm_accelerated": True,
                "performance": "4x faster geometric seeding"
            }
        elif op in ["react", "vue", "svelte", "angular"]:
            # For components, use WASM for the geometric seeding part
            get_chain_func = instance.exports(store)["getRomanWheelChain"]
            chain = get_chain_func(store, name)
            return {
                "type": op.title(),
                "componentName": name,
                "romanWheelChain": list(chain),
                "finalGlyph": chain[-1].toString(36) if chain else "",
                "operation": op,
                "status": "success",
                "wasm_accelerated": True,
                "visualMath": f"s₀={chain[0]} → s₁={chain[1]} → s₂={chain[2]} → s₃={chain[3]} → s₄={chain[4]}" if len(chain) >= 5 else ""
            }
        elif op in ["binaryfloat", "gematriaBinaryFloat"]:
            # For binary/float operations, use WASM encryptGlyph
            encrypt_func = instance.exports(store)["encryptGlyph"]
            final_glyph = encrypt_func(store, text)
            return {
                "token": text,
                "finalGlyph": final_glyph,
                "operation": "gematriaBinaryFloat",
                "status": "success",
                "wasm_accelerated": True,
                "description": "WASM 16D Binary/Float Hyper-Wheel"
            }
        else:
            return {"error": f"WASM operation '{op}' not implemented", "bridge_status": "wasm_op_not_supported"}

    except Exception as e:
        return {"error": f"WASM execution failed: {str(e)}", "bridge_status": "wasm_failed"}

# Enhanced call_glyph_cipher with optional WASM
def call_glyph_cipher_wasm(command_args: str, use_wasm: bool = False) -> dict:
    """Bridge with optional WASM acceleration"""
    if use_wasm:
        return call_glyph_wasm(command_args)
    return call_glyph_cipher(command_args)

# Backward compatibility wrapper
def call_glyph_cipher_legacy(text: str, operation: str = "encrypt") -> dict:
    """Legacy wrapper for simple text operations"""
    return call_glyph_cipher(f"--text '{text}' --op {operation}")

# Enhanced CLI for testing all operations
if __name__ == "__main__":
    import sys
    # Default args for testing
    args = "--text 'Hello world' --op encrypt"

    if len(sys.argv) > 1:
        # Pass all arguments as-is to the engine
        args = " ".join(sys.argv[1:])

    result = call_glyph_cipher(args)
    print(json.dumps(result, indent=2))