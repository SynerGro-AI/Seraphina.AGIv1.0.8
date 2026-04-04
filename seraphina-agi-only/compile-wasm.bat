@echo off
echo Compiling Glyph WASM Engine...
echo.

REM Check if AssemblyScript is installed
asc --version >nul 2>&1
if %errorlevel% neq 0 (
    echo AssemblyScript not found. Installing...
    npm install -g assemblyscript
    if %errorlevel% neq 0 (
        echo Failed to install AssemblyScript. Please install manually: npm install -g assemblyscript
        pause
        exit /b 1
    )
)

echo Compiling glyph-wasm.ts to glyph-wasm.wasm...
asc glyph-wasm.ts -o glyph-wasm.wasm --optimize --sourceMap

if %errorlevel% equ 0 (
    echo.
    echo ✅ WASM compilation successful!
    echo File: glyph-wasm.wasm
    echo.
    echo To use WASM acceleration in Python:
    echo pip install wasmtime
    echo Then call: call_glyph_wasm("--op react --name Test")
) else (
    echo.
    echo ❌ WASM compilation failed!
    echo Make sure AssemblyScript is properly installed.
)

pause