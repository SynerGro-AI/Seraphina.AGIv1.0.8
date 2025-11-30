const assert = require('assert');
const { buildPlaneSeeds, RomanDecoderWheel, RomanCodeWheel } = require('../lib/roman-wheel');

// Deterministic test inputs
const job = { part1: '00010203aabbccddeeff', coinb1: '', jobId: 'test-job-001' };
const extranonce1 = 'deadbeefcafebabe';

function runDeterminismChecks(){
  const a = buildPlaneSeeds(job, extranonce1, {});
  const b = buildPlaneSeeds(job, extranonce1, {});

  // Basic structural checks
  assert.ok(a && b, 'buildPlaneSeeds returned falsy result');
  assert.ok(Array.isArray(a.planeSeeds), 'planeSeeds should be an array');
  assert.strictEqual(a.planeSeeds.length, b.planeSeeds.length, 'planeSeeds length should be stable');
  assert.strictEqual(a.aggregate, b.aggregate, 'aggregate must be identical across runs');

  // Each plane seed should be stable
  for (let i=0;i<a.planeSeeds.length;i++){
    assert.strictEqual(a.planeSeeds[i], b.planeSeeds[i], `planeSeeds[${i}] must be stable`);
  }

  // Aggregate shape check
  assert.strictEqual(typeof a.aggregate, 'string', 'aggregate should be a string');
  assert.ok(a.aggregate.length >= 1, 'aggregate should be non-empty');

  // Regression: lock expected canonical outputs for this representative input
  const expectedPlaneSeeds = [
    '02bb6d587896ca235743bd9942973683a5dfc3540af52a7d573d572d60556ed4',
    '65f19f302ec3c5293f7f17de05114f539c10f76d2354419d13788d39dc12f3b5',
    '5b7b99c632a762e12780e164bf9eecc2a1eb0085111918ba44dbec54b5b2941b',
    '07b94ea6c99bb0b6517442c23a2a8566bb02fb209dcc93f17b5ef93c8d3daae8'
  ];
  const expectedAggregate = 'e87aa014f0d5249f5990dde8b37de76618a085df0785db8516d8fedc172ae3fa';

  // Full canonical expected object for regression testing (subset of fields)
  const expected = {
    planeSeeds: expectedPlaneSeeds,
    aggregate: expectedAggregate,
    wheels: [
        { plane: 'xy', freq: 438, hue: 567, theta: 0.734505201, r: 0.567 },
        { plane: 'xz', freq: 417, hue: 624, theta: 0.621825307, r: 0.624 },
        { plane: 'yz', freq: 417, hue: 582, theta: 0.740396003, r: 0.582 },
        { plane: 'w4d', freq: 430, hue: 652, theta: 0.452805466, r: 0.652 }
    ]
  };

  // Compare only the canonical subset (planeSeeds, aggregate, wheels) to avoid brittle extras
  const actualSubset = { 
    planeSeeds: a.planeSeeds, 
    aggregate: a.aggregate, 
    wheels: (a.wheels || []).map(w => ({ plane: w.plane, freq: w.freq, hue: w.hue, theta: w.theta, r: w.r }))
  };
  assert.deepStrictEqual(actualSubset, expected, 'buildPlaneSeeds canonical subset must match locked output');

  console.log('[test] buildPlaneSeeds determinism checks passed');
}

function runApiShapeChecks(){
  const enc = new RomanCodeWheel();
  const dec = new RomanDecoderWheel('xy', 432, 600);
  // basic methods should exist
  assert.strictEqual(typeof enc.encodeOctaStructure, 'function', 'RomanCodeWheel.encodeOctaStructure should exist');
  assert.strictEqual(typeof dec.decodeData, 'function', 'RomanDecoderWheel.decodeData should exist');

  // Exercise encode/decode API shapes (not cryptographic verification)
  const a = buildPlaneSeeds(job, extranonce1, {});
  const encoded = enc.encodeOctaStructure({ hello: 'world' });
  const decoded = dec.decodeData((a.planeSeeds && a.planeSeeds[0]) || '');
  assert.ok(encoded, 'encodeOctaStructure returned falsy');
  assert.ok(typeof decoded === 'string', 'decodeData should return a string');
  console.log('[test] API shape checks passed');
}

// Run tests
try{
  runDeterminismChecks();
  runApiShapeChecks();
  console.log('[test] All roman-wheel tests passed');
  process.exit(0);
}catch(e){
  console.error('[test] roman-wheel tests failed:', e && e.stack ? e.stack : e);
  process.exit(2);
}
