// benchmark_v8.7.js
// Comprehensive Benchmark for Glyph Language Engine v8.7

const { AdvancedLanguageEngine } = require('./advanced-language-engine.js');
const engine = new AdvancedLanguageEngine();

console.log('🌟 Glyph Language Engine v8.7 — 16D Binary/Float Hyper-Wheel Benchmark');
console.log('================================================================================');

const tokens = ['merkabah', 'seraphina', 'quantumfibonacci', 'fibonacci', 'goldenratio', 'einsof', 'resonance', 'glyph', 'romanwheel', 'merkleroot'];
const dimensions = [4, 8, 16];

let totalTime = 0;
let totalOps = 0;

dimensions.forEach(dim => {
  console.log(`\n📐 ${dim}D Dimension Benchmark:`);
  console.log('─'.repeat(50));

  tokens.forEach(token => {
    const start = process.hrtime.bigint();
    const result = engine.glyphGematriaBinaryFloat(token, dim);
    const end = process.hrtime.bigint();
    const timeMs = Number(end - start) / 1000000;

    totalTime += timeMs;
    totalOps++;

    console.log(`${token.padEnd(15)} → ${result.finalGlyph.padEnd(8)} | ${result.resonance.padEnd(8)} | ${timeMs.toFixed(3)}ms`);
  });
});

console.log(`\n📊 Performance Summary:`);
console.log('─'.repeat(50));
console.log(`Total Operations: ${totalOps}`);
console.log(`Total Time: ${totalTime.toFixed(2)}ms`);
console.log(`Average per Operation: ${(totalTime/totalOps).toFixed(3)}ms`);
console.log(`Operations per Second: ${(1000/(totalTime/totalOps)).toFixed(1)} ops/sec`);

console.log(`\n🔬 Deep Analysis (16D Merkabah):`);
const deepResult = engine.glyphGematriaBinaryFloat('merkabah', 16);
console.log(`Token: ${deepResult.token}`);
console.log(`Gematria Seed: ${deepResult.gematriaSeed}`);
console.log(`Binary Digest: ${deepResult.binaryDigest}`);
console.log(`Float Chain Length: ${deepResult.floatChain.length}`);
console.log(`Final Glyph: ${deepResult.finalGlyph}`);
console.log(`Resonance: ${deepResult.resonance}`);
console.log(`Kabbalistic Note: ${deepResult.kabbalisticNote}`);