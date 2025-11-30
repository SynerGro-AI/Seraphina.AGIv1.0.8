// rvn-header.js - header assembly helpers for Ravencoin-like stratum jobs
const crypto = require('crypto');

function doubleSha256Buf(buf){
  const h1 = crypto.createHash('sha256').update(buf).digest();
  return crypto.createHash('sha256').update(h1).digest();
}

function decodeCompactTarget(nBitsHex){
  try {
    const hex = nBitsHex.replace(/^0x/,'');
    const buf = Buffer.from(hex,'hex'); if (buf.length!==4) return null;
    const exp = buf[0];
    const mant = buf.readUIntBE(1,3);
    let target = BigInt(mant) * (BigInt(2)**(BigInt(8)*(BigInt(exp)-BigInt(3))));
    const max256=(BigInt(1)<<BigInt(256))-1n; if (target>max256) target=max256;
    return { targetBig: target, targetHex: target.toString(16).padStart(64,'0') };
  } catch { return null; }
}

function buildCoinbase(job, extranonce1, extranonce2){
  const p1 = job.part1 || job.coinb1 || '';
  const p2 = job.part2 || job.coinb2 || '';
  return p1 + (extranonce1||'') + (extranonce2||'') + p2;
}

function computeMerkleRoot(coinbaseHex, branches){
  let hash = doubleSha256Buf(Buffer.from(coinbaseHex,'hex'));
  for (const br of (branches||[])){
    const brBuf = Buffer.from(br,'hex');
    hash = doubleSha256Buf(Buffer.concat([hash, brBuf]));
  }
  return hash.reverse().toString('hex');
}

function assembleHeader(job, extranonce1, extranonce2){
  const coinbaseHex = buildCoinbase(job, extranonce1, extranonce2);
  const merkleRootBig = computeMerkleRoot(coinbaseHex, job.merkleBranches);
  const merkleLE = Buffer.from(merkleRootBig,'hex').reverse();
  const prevhashLE = Buffer.from((job.prevhash||'').padEnd(64,'0'),'hex');
  const versionLE = Buffer.from((job.version||'20000000').padEnd(8,'0'),'hex');
  const ntimeLE = Buffer.from((job.ntime||'00000000').padEnd(8,'0'),'hex');
  const nbitsLE = Buffer.from((job.nbits||'00000000').padEnd(8,'0'),'hex');
  const base = Buffer.concat([versionLE, prevhashLE, merkleLE, ntimeLE, nbitsLE]);
  const targetDecoded = job.nbits ? decodeCompactTarget(job.nbits) : null;
  return { headerBaseHex: base.toString('hex'), targetDecoded, merkleRootLE: merkleLE.toString('hex') };
}

module.exports = { assembleHeader, decodeCompactTarget };
