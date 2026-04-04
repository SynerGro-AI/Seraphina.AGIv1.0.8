// glyph-wasm.ts - WebAssembly Glyph Engine (AssemblyScript)
// Compile with: npm install -g assemblyscript && asc glyph-wasm.ts -o glyph-wasm.wasm

// Core gematria mapping (subset for WASM efficiency)
const gematriaMap: Map<string, u32> = new Map([
  ["a", 1], ["b", 2], ["c", 3], ["d", 4], ["e", 5], ["f", 6], ["g", 7], ["h", 8], ["i", 9], ["j", 10],
  ["k", 20], ["l", 30], ["m", 40], ["n", 50], ["o", 60], ["p", 70], ["q", 80], ["r", 90], ["s", 100],
  ["t", 200], ["u", 300], ["v", 400], ["w", 500], ["x", 600], ["y", 700], ["z", 800],
  ["glyph", 432], ["roman", 314], ["wheel", 271], ["function", 1372], ["component", 777], ["render", 432],
  ["react", 666], ["vue", 555], ["svelte", 444], ["angular", 333], ["props", 314], ["state", 555], ["ref", 271]
]);

// Simplified deterministic hash for WASM (faster than crypto)
export function hebrewNumericSeed(token: string): u32 {
  const lower = token.toLowerCase().trim();

  // Check gematria map first
  if (gematriaMap.has(lower)) {
    return gematriaMap.get(lower);
  }

  // Fallback: simple hash (deterministic)
  let hash: u32 = 0;
  for (let i = 0; i < lower.length; i++) {
    hash = ((hash << 5) - hash + lower.charCodeAt(i)) | 0;
  }
  return hash >>> 0; // Ensure positive
}

// Advanced Roman Wheel geometric seeding (WASM-optimized)
export function romanWheelSeedChain(seed: u32): u32 {
  let pos = seed;
  const params: u32[] = [137, 314, 555, 777]; // wheel multipliers
  const rotations: u32[] = [3, 5, 7, 11];     // bit rotation amounts

  for (let i = 0; i < 4; i++) {
    // Modular arithmetic transformation
    pos = ((pos * params[i]) + (i * 271)) & 0xFFFFFFFF;
    // Bit rotation for spiral modulation
    const r = rotations[i];
    pos = (pos << r) | (pos >>> (32 - r));
  }

  return pos;
}

// Main Glyph encryption function
export function encryptGlyph(token: string): string {
  const seed = hebrewNumericSeed(token);
  const final = romanWheelSeedChain(seed);
  return final.toString(36); // base-36 encoding
}

// Batch processing for multiple tokens
export function encryptGlyphBatch(tokens: string[]): string {
  const results: string[] = [];
  for (let i = 0; i < tokens.length; i++) {
    results.push(encryptGlyph(tokens[i]));
  }
  return results.join(':');
}

// Performance benchmark
export function benchmarkGlyph(iterations: u32): u32 {
  let total: u32 = 0;
  for (let i: u32 = 0; i < iterations; i++) {
    const seed = hebrewNumericSeed("test" + i.toString());
    total += romanWheelSeedChain(seed);
  }
  return total;
}

// Export chain for visualization
export function getRomanWheelChain(token: string): u32[] {
  const seed = hebrewNumericSeed(token);
  let pos = seed;
  const chain: u32[] = [pos];

  const params: u32[] = [137, 314, 555, 777];
  const rotations: u32[] = [3, 5, 7, 11];

  for (let i = 0; i < 4; i++) {
    pos = ((pos * params[i]) + (i * 271)) & 0xFFFFFFFF;
    const r = rotations[i];
    pos = (pos << r) | (pos >>> (32 - r));
    chain.push(pos);
  }

  return chain;
}