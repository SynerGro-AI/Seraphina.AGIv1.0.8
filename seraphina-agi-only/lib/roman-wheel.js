const crypto = require('crypto');

// Minimal Octonion helper used by wheels (deterministic math only)
class SimpleOcto {
  constructor(coeffs){ this.coeffs = (coeffs||[]).slice(0,8).concat(new Array(8).fill(0)).slice(0,8); }
  norm(){ return Math.sqrt(this.coeffs.reduce((s,c)=> s + (Number(c)||0)*(Number(c)||0), 0)); }
  multiply(o){ const prod = new Array(8).fill(0); prod[0] = this.coeffs[0]*o.coeffs[0] - this.coeffs.slice(1).reduce((s,c,i)=> s + c*o.coeffs[i+1],0); for (let i=1;i<8;i++) prod[i] = this.coeffs[0]*o.coeffs[i] + o.coeffs[0]*this.coeffs[i]; return new SimpleOcto(prod); }
  power(d=2){ return d===2? this.multiply(this): this; }
}

// RomanDecoderWheel: deterministic spiral decode used across the project
class RomanDecoderWheel {
  constructor(plane='xy', freq=432, hue=600){ this.plane=plane; this.freq=freq; this.hue=hue; this.theta=0; this.r = hue/1000; }
  decodeData(hex){
    this.theta += 2*Math.PI*(this.freq/432)/8;
    const spiralR = this.r*(Math.cos(8*this.theta)+1.5)/2.5;
    const decoded = [];
    for (let i=0;i<hex.length;i+=8){
      const chunk = hex.slice(i,i+8);
      const oct = chunk.split('').reduce((a,c,j)=>{ a[j%8]+=parseInt(c,16)||0; return a; }, Array(8).fill(0));
      const n = new SimpleOcto(oct).norm()*spiralR;
      if (n <= 2) decoded.push(chunk);
    }
    return decoded.join('');
  }
}

// RomanCodeWheel: complementary encoder (octagramal spiral / golden-ratio)
class RomanCodeWheel {
  constructor(){ this.spiral_ratio = 1.618; this.octa_planes = 8; this.wheel_angles = Array.from({length:this.octa_planes},(_,i)=> (i*45)*Math.PI/180); this.octa_freq = 963; }
  generateHash(obj){ const s = typeof obj === 'string' ? obj : JSON.stringify(obj); let h=0; for (let i=0;i<s.length;i++){ h = (h<<5)-h + s.charCodeAt(i); h |= 0; } return h >>> 0; }
  rotateForElectrons(input, planes=this.octa_planes){ let rotated = (input>>>0); for (let plane=0; plane<planes; plane++){ const spiral_phase = Math.pow(this.spiral_ratio, plane) * this.wheel_angles[plane]; const freq_shift = Math.floor(this.octa_freq * spiral_phase) & 0xFF; rotated = ((rotated << (plane+1)) | (rotated >>> (32 - (plane+1)))) ^ freq_shift; } return rotated >>> 0; }
  encodeOctaStructure(structure, context_freq=this.octa_freq){ const baseHash = (typeof structure.hash === 'number') ? structure.hash : this.generateHash(structure); const encoded = this.rotateForElectrons(baseHash, this.octa_planes); return { ...structure, wheel_encoded: encoded.toString(16), spiral_phase: context_freq * this.spiral_ratio, electron_spin: 'entangled' }; }
}

// buildPlaneSeeds: deterministic plane seed derivation used by miner and engine
function buildPlaneSeeds(job, extranonce1, opts={}){
  if (!job) return { planeSeeds:[], aggregate:null };

  // Follow the requested deterministic derivation:
  // baseBytes = bytes(job.part1 + job.coinb1 + extranonce1) parsed from hex
  // baseHash = SHA256(baseBytes)
  // per-plane seed = SHA256(baseHash || planeName)
  // aggregate = SHA256(concat(per-plane-seeds))
  const hexConcat = (job.part1 || '') + (job.coinb1 || '') + (extranonce1 || '');
  let baseBuf;
  try {
    baseBuf = Buffer.from(hexConcat, 'hex');
  } catch (e) {
    baseBuf = Buffer.from('', 'hex');
  }
  const baseHashBuf = crypto.createHash('sha256').update(baseBuf).digest();

  const planeNames = ['xy','xz','yz','w4d'];
  const planeSeeds = planeNames.map(p => {
    const h = crypto.createHash('sha256').update(Buffer.concat([baseHashBuf, Buffer.from(p, 'utf8')])).digest('hex');
    return h.slice(0, 64);
  });

  const aggregate = crypto.createHash('sha256').update(planeSeeds.join('')).digest('hex').slice(0, 64);

  // For backwards compatibility, also construct the wheel objects (used elsewhere).
  const seedHex = baseHashBuf.toString('hex');
  const segs = [0,8,16,24].map(o=> parseInt(seedHex.slice(o,o+8),16));
  // golden-ratio folding for theta
  const PHI = 1.6180339887;
  function computeThetaFromSeedHex(hex){
    try{
      const buf = Buffer.from(hex, 'hex');
      let sum = 0; for (const b of buf) sum += b;
      const mod = sum % 1000;
      const theta = ((mod * PHI) % (2*Math.PI));
      // normalize to [0,1]
      const norm = theta / (2*Math.PI);
      return Number(norm.toFixed(9));
    }catch(e){ return 0; }
  }

  const mkWheel = (plane, idx)=>{
    const w = new RomanDecoderWheel(plane, 432 + ((segs[idx]%33)-16), 560 + (segs[idx]%120));
    // derive theta from the corresponding planeSeed (if available)
    const seedHexForPlane = planeSeeds[idx] || seedHex.slice(idx*16,(idx+1)*16);
    w.theta = computeThetaFromSeedHex(seedHexForPlane);
    return w;
  };
  const baseWheels = [ mkWheel('xy',0), mkWheel('xz',1), mkWheel('yz',2), mkWheel('w4d',3) ];
  let wheels = baseWheels;
  if (process.env.MULTI_PLANE_HYPER === '1'){
    for (let k=0;k<4;k++){ const off = 32 + k*8; const seg = parseInt(seedHex.slice(off, off+8) || seedHex.slice(0,8),16); wheels.push(new RomanDecoderWheel('h'+k, 432 + ((seg%45)-22), 520 + (seg%140))); }
  }

  return { planeSeeds, aggregate, wheels };
}

module.exports = { SimpleOcto, RomanDecoderWheel, RomanCodeWheel, buildPlaneSeeds };
