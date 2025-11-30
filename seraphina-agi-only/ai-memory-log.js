// ai-memory-log.js
// Append-only hashed memory log for AI agent suggestions (deterministic chain).
// Environment:
//   AI_MEMORY_ENABLE=1                Enable logging
//   AI_MEMORY_FILE=ai-memory.jsonl    Target file path
//   AI_MEMORY_MAX_SIZE=5242880        Rotate when exceeding size (bytes)
//   AI_MEMORY_MAX_FILES=5             Keep last N rotated gzip archives
//   AI_MEMORY_SCHEMA=agent_mem/v1     Schema tag
// Chain: Each entry includes prev_hash (SHA256 of previous entry JSON) and entry_hash (new chain head)
// Rotation preserves continuity by writing a marker entry at start of new file referencing last hash.

const fs = require('fs');
const crypto = require('crypto');

const ENABLE = process.env.AI_MEMORY_ENABLE === '1';
const FILE = process.env.AI_MEMORY_FILE || 'ai-memory.jsonl';
const MAX_SIZE = parseInt(process.env.AI_MEMORY_MAX_SIZE || (5*1024*1024).toString(),10);
const MAX_FILES = parseInt(process.env.AI_MEMORY_MAX_FILES || '5',10);
const SCHEMA = process.env.AI_MEMORY_SCHEMA || 'agent_mem/v1';

let lastHash = null;
let initialized = false;

function rotateIfNeeded(){
  if (!fs.existsSync(FILE)) return;
  try {
    const st = fs.statSync(FILE);
    if (st.size < MAX_SIZE) return;
    const ts = Date.now();
    const gzName = FILE + '.' + ts + '.gz';
    const zlib = require('zlib');
    const inp = fs.createReadStream(FILE); const out = fs.createWriteStream(gzName); const gz = zlib.createGzip();
    return new Promise((resolve)=>{
      inp.pipe(gz).pipe(out).on('finish', ()=>{
        try { fs.unlinkSync(FILE); } catch(_){ }
        // prune old
        try {
          const list = fs.readdirSync('.').filter(f=> f.startsWith(FILE+'.') && f.endsWith('.gz')).sort();
          const excess = list.length - MAX_FILES;
          if (excess>0){ for (let i=0;i<excess;i++){ try { fs.unlinkSync(list[i]); } catch(_){} } }
        } catch(_prune){}
        resolve();
      });
    });
  } catch(e){ /* ignore */ }
}

function initLoad(){
  if (initialized) return;
  initialized = true;
  if (!fs.existsSync(FILE)) return;
  try {
    const lines = fs.readFileSync(FILE,'utf8').trim().split(/\r?\n/).filter(Boolean);
    if (lines.length){
      const last = JSON.parse(lines[lines.length-1]);
      lastHash = last.entry_hash || null;
    }
  } catch(e){ /* ignore */ }
}

function appendMemory(entry){
  if (!ENABLE) return;
  initLoad();
  const base = {
    ts: Date.now(),
    schema: SCHEMA,
    prev_hash: lastHash || 'GENESIS',
    action: entry.action || null,
    delta: entry.delta != null ? entry.delta : null,
    confidence: entry.confidence != null ? entry.confidence : null,
    note: entry.note || entry.text || null
  };
  const payload = JSON.stringify(base);
  const h = crypto.createHash('sha256').update(payload).digest('hex');
  const rec = { ...base, entry_hash: h };
  try { fs.appendFileSync(FILE, JSON.stringify(rec)+'\n'); lastHash = h; } catch(e){ /* ignore */ }
  // Expose chain head for system reproducibility harness
  try { global.__AI_MEMORY_CHAIN_HASH__ = lastHash; } catch(_){ }
  rotateIfNeeded();
}

module.exports = { appendMemory, enabled: ENABLE };
