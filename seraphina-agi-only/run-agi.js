#!/usr/bin/env node
/*
  Minimal AGI-only runner.
  Commands:
    help           Show usage
    serve [port]   Start simple HTTP API for language processing
    train          Run ai-learning-orchestrator.orchestrate() (if available)
    optimize       Run AGI self-optimizer with a safe mock cube

  This runner intentionally avoids any mining or wallet modules.
*/
const http = require('http');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const ENGINE_PATH = path.join(__dirname, '..', 'advanced-language-engine.js');
const ORCH_PATH = path.join(__dirname, '..', 'ai-learning-orchestrator.js');
const AGI_OPT_PATH = path.join(__dirname, '..', 'agi-self-optimizer.js');

function safeRequire(p){ try { return require(p); } catch(e){ return null; } }

async function serve(port = 8080){
  const Engine = safeRequire(ENGINE_PATH);
  if(!Engine){ console.error('Advanced language engine not found in expected location.'); process.exit(2); }
  const engine = new Engine();

  const srv = http.createServer((req,res)=>{
    if(req.method==='POST' && req.url === '/process'){
      let b=''; req.on('data',c=>b+=c); req.on('end', ()=>{
        try{
          const body = JSON.parse(b||'{}');
          const input = body.input || body.prompt || '';
          const opts = body.options || {};
          const out = engine.processLanguage(input, opts);
          res.writeHead(200, {'Content-Type':'application/json'});
          res.end(JSON.stringify(out));
        }catch(e){ res.writeHead(400); res.end(JSON.stringify({ error: String(e) })); }
      });
    } else {
      res.writeHead(404); res.end('Not Found');
    }
  });
  srv.listen(port, ()=> console.log(`[Seraphina AGI] HTTP API listening on ${port} (POST /process)`));
}

async function runTrain(){
  const mod = safeRequire(ORCH_PATH);
  if(!mod || typeof mod.orchestrate !== 'function'){
    console.error('ai-learning-orchestrator.orchestrate() unavailable in this workspace.');
    return process.exit(3);
  }
  try{
    const result = mod.orchestrate();
    console.log('Orchestrator result (truncated):', JSON.stringify(result && Object.keys(result).slice(0,10))); // concise
  }catch(e){ console.error('Orchestrator error:', e.message); process.exit(4); }
}

async function runOptimize(){
  const mod = safeRequire(AGI_OPT_PATH);
  if(!mod || !mod.AGISelfOptimizer){ console.error('AGI self-optimizer module not found.'); process.exit(5); }
  // Provide a safe mock cube (no real device IO)
  const mockCube = {
    transferOut: (ep, buf, cb)=> { if(cb) cb(null); else return Promise.resolve(); },
    transferIn: (ep, size, cb)=> { const buf = Buffer.alloc(size,0); if(cb) cb(null, buf); else return Promise.resolve(buf); }
  };
  try{
    const inst = new mod.AGISelfOptimizer(mockCube);
    console.log('[Seraphina AGI] AGISelfOptimizer started (mock cube).');
  }catch(e){ console.error('AGI optimizer error:', e.message); process.exit(6); }
}

async function main(argv){
  const cmd = argv[2] || 'help';
  if(cmd === 'help'){
    console.log('Usage: seraphina-agi-core <command>');
    console.log('  serve [port]   Start HTTP API (POST /process)');
    console.log('  train          Run ai-learning-orchestrator.orchestrate() (if present)');
    console.log('  optimize       Run AGI self-optimizer (safe mock cube)');
    return;
  }
  if(cmd === 'serve'){
    const port = Number(argv[3] || process.env.SERAPHINA_AGI_PORT || 8080);
    await serve(port);
    return;
  }
  if(cmd === 'train'){
    await runTrain(); return;
  }
  if(cmd === 'optimize'){
    await runOptimize(); return;
  }
  console.error('Unknown command:', cmd); process.exit(1);
}

if(require.main === module){ main(process.argv).catch(e=>{ console.error(e); process.exit(1); }); }

module.exports = { serve, runTrain, runOptimize };
