// keccak.js - extracted Keccak-f[1600] + keccak256 used by miner
const crypto = require('crypto'); // fallback only (not used directly here except if extended)

const KECCAK_R = 1088;
const RC = [
  0x0000000000000001n,0x0000000000008082n,0x800000000000808an,0x8000000080008000n,
  0x000000000000808bn,0x0000000080000001n,0x8000000080008081n,0x8000000000008009n,
  0x000000000000008an,0x0000000000000088n,0x0000000080008009n,0x000000008000000an,
  0x000000008000808bn,0x800000000000008bn,0x8000000000008089n,0x8000000000008003n,
  0x8000000000008002n,0x8000000000000080n,0x000000000000800an,0x800000008000000an,
  0x8000000080008081n,0x8000000000008080n,0x0000000080000001n,0x8000000080008008n];

function keccakF1600(s){
  for (let r=0;r<24;r++){
    const C=new Array(5); for(let x=0;x<5;x++) C[x]=s[x]^s[x+5]^s[x+10]^s[x+15]^s[x+20];
    const D=new Array(5); for(let x=0;x<5;x++) D[x]=C[(x+4)%5]^((C[(x+1)%5] << 1n) | (C[(x+1)%5] >> 63n));
    for(let x=0;x<5;x++) for(let y=0;y<5;y++) s[x+5*y] ^= D[x];
    let [x,y]=[1,0]; let cur=s[1];
    for(let t=0;t<24;t++){ const X=y; y=(2*x+3*y)%5; x=X; const idx=x+5*y; const shift=BigInt((t+1)*(t+2)/2 % 64); const tmp=s[idx]; s[idx]=(cur << shift)|(cur>>(64n-shift)); cur=tmp; }
    for(let y0=0;y0<5;y0++){ const row=[]; for(let x0=0;x0<5;x0++) row[x0]=s[x0+5*y0]; for(let x0=0;x0<5;x0++) s[x0+5*y0]= row[x0] ^ ((~row[(x0+1)%5]) & row[(x0+2)%5]); }
    s[0] ^= RC[r];
  }
}

function keccak256(buf){
  const rateBytes=KECCAK_R/8; const state=new Array(25).fill(0n);
  const b=Buffer.from(buf); let offset=0;
  while(offset<b.length){
    const block=Math.min(rateBytes,b.length-offset);
    for(let i=0;i<block;i++){ const bi=b[offset+i]; const lane=Math.floor(i/8); const shift=BigInt((i%8)*8); state[lane]^=BigInt(bi)<<shift; }
    offset+=block; if(block===rateBytes) keccakF1600(state);
  }
  const pad=Buffer.alloc(rateBytes,0); pad[0]=0x01; pad[rateBytes-1]|=0x80;
  for(let i=0;i<rateBytes;i++){ const lane=Math.floor(i/8); const shift=BigInt((i%8)*8); state[lane]^=BigInt(pad[i])<<shift; }
  keccakF1600(state);
  const out=Buffer.alloc(32); let outOff=0; let i=0; while(outOff<32){ const lane=state[i]; for(let j=0;j<8 && outOff<32;j++){ out[outOff++]=Number((lane>>BigInt(8*j))&0xffn);} i++; }
  return out;
}

module.exports = { keccakF1600, keccak256, KECCAK_R };
