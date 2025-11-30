// kawpow.js - extracted JS KawPow-like hashing (simplified, NOT consensus)
const { keccak256 } = require('./keccak');

const _lightCacheStore = new Map();
function buildLightCache(epoch){
  const sizeMB = parseInt(process.env.KAWPOW_LIGHT_CACHE_MB || '2',10);
  const lineSize = 64; const totalBytes = sizeMB*1024*1024;
  const linesCount = Math.max(8, Math.floor(totalBytes/lineSize));
  const seed = keccak256(Buffer.from('epoch:'+epoch));
  const lines = new Array(linesCount); let prev=seed;
  for (let i=0;i<linesCount;i++){
    const idxBuf = Buffer.alloc(4); idxBuf.writeUInt32LE(i,0);
    const base = keccak256(Buffer.concat([prev, idxBuf]));
    let chunk=base; const acc=[];
    while(Buffer.concat(acc).length<lineSize){ chunk=keccak256(chunk); acc.push(chunk.slice(0, Math.min(chunk.length, lineSize-Buffer.concat(acc).length))); }
    const line = Buffer.concat(acc).slice(0,lineSize);
    for(let b=0;b<line.length;b++) line[b]^=seed[(b+i)%seed.length];
    lines[i]=line; prev=line.slice(0,32);
  }
  const obj={lines,lineSize}; _lightCacheStore.set(epoch,obj); return obj;
}
function getLightCache(epoch){ return _lightCacheStore.get(epoch) || buildLightCache(epoch); }

function kawpowJs(headerBuf,height,seedBuf,nonce){
  const epoch = Math.floor(height / parseInt(process.env.KAWPOW_EPOCH_LEN||'7500',10));
  const nonceBuf=Buffer.alloc(8); nonceBuf.writeUInt32LE(nonce>>>0,0); nonceBuf.writeUInt32LE(epoch>>>0,4);
  const base=Buffer.concat([headerBuf, seedBuf||Buffer.alloc(32,0), nonceBuf]);
  const digest=keccak256(base);
  const mixWords=32; const mix=new Uint32Array(mixWords); for(let i=0;i<mixWords;i++) mix[i]=digest[i%32];
  const progOps=['xor','add','rot','mul','sub'];
  function randWord(i){ const h=keccak256(Buffer.concat([digest, Buffer.from([i & 0xff]) ])); return h.readUInt32LE(0); }
  const rashbaGain=Math.min(0.60, Math.max(0.01, parseFloat(process.env.RASHBA_GAIN||'0.15')));
  const rounds=parseInt(process.env.KAWPOW_JS_ROUNDS||'64',10);
  const light=getLightCache(epoch); let memReads=0;
  for (let r=0;r<rounds;r++){
    const sel=randWord(r)%progOps.length; const a=randWord(r+37)%mixWords; const b=randWord(r+73)%mixWords;
    const lineIndex=((mix[a]^randWord(r+91)^a^r)>>>0)%light.lines.length; const line=light.lines[lineIndex]; memReads++;
    const w0=line.readUInt32LE(0), w1=line.readUInt32LE(4); mix[a]=(mix[a]+w0)>>>0; mix[b]=(mix[b]^w1)>>>0;
    switch(progOps[sel]){
      case 'xor': mix[a]=(mix[a]^mix[b])>>>0; break;
      case 'add': mix[a]= (mix[a]+mix[b]+Math.floor(rashbaGain*1024)) & 0xffffffff; break;
      case 'rot': { const rot=(randWord(r+111)%31)+1; const v=mix[a]; mix[a]=((v<<rot)|(v>>> (32-rot)))>>>0; break; }
      case 'mul': mix[a]=Math.imul(mix[a]|1, (mix[b]|1))>>>0; break;
      case 'sub': mix[a]=(mix[a]-mix[b])>>>0; break;
    }
    if (r%8===0){ const theta=(r*0.125)*Math.PI; const amp=1+rashbaGain*Math.cos(theta); mix[a]=(mix[a]+((amp*65535)&0xffff))>>>0; }
  }
  const mixBuf=Buffer.alloc(mixWords*4); for(let i=0;i<mixWords;i++) mixBuf.writeUInt32LE(mix[i],i*4);
  const mixHash=keccak256(mixBuf); const finalHash=keccak256(Buffer.concat([digest,mixHash]));
  return { finalHash: finalHash.toString('hex'), mixHash: mixHash.toString('hex'), memReads };
}

function kawpowJsNoMem(headerBuf,height,seedBuf,nonce){
  const epoch=Math.floor(height / parseInt(process.env.KAWPOW_EPOCH_LEN||'7500',10));
  const nonceBuf=Buffer.alloc(8); nonceBuf.writeUInt32LE(nonce>>>0,0); nonceBuf.writeUInt32LE(epoch>>>0,4);
  const base=Buffer.concat([headerBuf, seedBuf||Buffer.alloc(32,0), nonceBuf]);
  const digest=keccak256(base); const mixWords=32; const mix=new Uint32Array(mixWords); for(let i=0;i<mixWords;i++) mix[i]=digest[i%32];
  const progOps=['xor','add','rot','mul','sub'];
  function randWord(i){ const h=keccak256(Buffer.concat([digest, Buffer.from([i & 0xff]) ])); return h.readUInt32LE(0); }
  const rashbaGain=Math.min(0.60, Math.max(0.01, parseFloat(process.env.RASHBA_GAIN||'0.15')));
  const rounds=parseInt(process.env.KAWPOW_JS_ROUNDS||'64',10);
  for(let r=0;r<rounds;r++){
    const sel=randWord(r)%progOps.length; const a=randWord(r+37)%mixWords; const b=randWord(r+73)%mixWords;
    switch(progOps[sel]){
      case 'xor': mix[a]=(mix[a]^mix[b])>>>0; break;
      case 'add': mix[a]=(mix[a]+mix[b]+Math.floor(rashbaGain*1024)) & 0xffffffff; break;
      case 'rot': { const rot=(randWord(r+111)%31)+1; const v=mix[a]; mix[a]=((v<<rot)|(v>>>(32-rot)))>>>0; break; }
      case 'mul': mix[a]=Math.imul(mix[a]|1,(mix[b]|1))>>>0; break;
      case 'sub': mix[a]=(mix[a]-mix[b])>>>0; break;
    }
    if(r%8===0){ const theta=(r*0.125)*Math.PI; const amp=1+rashbaGain*Math.cos(theta); mix[a]=(mix[a]+((amp*65535)&0xffff))>>>0; }
  }
  const mixBuf=Buffer.alloc(mixWords*4); for(let i=0;i<mixWords;i++) mixBuf.writeUInt32LE(mix[i],i*4);
  const mixHash=keccak256(mixBuf); const finalHash=keccak256(Buffer.concat([digest,mixHash]));
  return { finalHash: finalHash.toString('hex'), mixHash: mixHash.toString('hex'), memReads:0 };
}

module.exports = { kawpowJs, kawpowJsNoMem, getLightCache };
