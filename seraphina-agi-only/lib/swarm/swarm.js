// swarm.js - mDNS + UDP heartbeat skeleton for Aurrelia miner swarm
// Goals:
// 1. Lightweight zero-config LAN peer discovery (mDNS / Bonjour style) advertising service TXT with instance stats.
// 2. Periodic UDP heartbeat broadcast (optionally multicast) carrying concise metrics snapshot.
// 3. Deterministic, no dynamic code exec; advisory only. Future: peer score sharing, hash/freq consensus.

const os = require('os');
const dgram = require('dgram');
const crypto = require('crypto');
let bonjour = null; try { bonjour = require('bonjour')(); } catch(_) { /* optional dependency */ }

const SWARM_SERVICE = process.env.SWARM_SERVICE || 'aurrelia-miner';
const HEARTBEAT_PORT = parseInt(process.env.SWARM_HEARTBEAT_PORT || process.env.HBUS_PORT || '49321',10);
const HEARTBEAT_INTERVAL = parseInt(process.env.SWARM_HEARTBEAT_INTERVAL || '5000',10); // ms
const HEARTBEAT_TTL_MS = parseInt(process.env.SWARM_HEARTBEAT_TTL || '15000',10); // expiry for peer listing
const MCAST_ADDR = process.env.SWARM_MCAST_ADDR || '239.192.0.13';
const USE_MDNS = process.env.SWARM_MDNS === '1';
const USE_UDP = process.env.SWARM_UDP !== '0';
const USE_MCAST = process.env.SWARM_MCAST === '1';
const INSTANCE_ID = (process.env.SWARM_INSTANCE_ID || os.hostname() + '-' + process.pid).slice(0,48);
const HMAC_KEY = process.env.SWARM_HMAC_KEY || process.env.SWARM_SIGN_KEY || '';
const REQUIRE_SIG = process.env.SWARM_REQUIRE_SIG === '1';
const EWMA_ALPHA = parseFloat(process.env.SWARM_EWMA_ALPHA || '0.3');

const peers = new Map(); // id -> { last, payload }
let socket = null; let mdnsService = null; let lastHeartbeatSent = 0;

function canonicalize(obj){
  const keys = Object.keys(obj).filter(k=> k !== 'sig').sort();
  const out={}; for (const k of keys) out[k]=obj[k]; return out;
}
function signPayload(obj){ if (!HMAC_KEY) return null; return crypto.createHmac('sha256', HMAC_KEY).update(JSON.stringify(canonicalize(obj))).digest('hex'); }
function encodeHeartbeat(data){ try { return Buffer.from(JSON.stringify(data)); } catch(_) { return Buffer.from('{}'); } }
function decodeHeartbeat(buf){ try { return JSON.parse(buf.toString('utf8')); } catch(_){ return null; } }

function currentSnapshot(extra){
  const base = Object.assign({
    id: INSTANCE_ID,
    t: Date.now(),
    v: 1,
    hn: os.hostname(),
    pid: process.pid,
    nonces: extra?.nonces || 0,
    shares: extra?.shares || 0,
    batches: extra?.batches || 0,
    native: extra?.nativeEnabled || 0,
    hps: extra?.hps || 0,
    memdf: typeof extra?.memdf === 'number' ? extra.memdf : 0,
    cfg: extra?.configHash || process.env.SWARM_CONFIG_HASH || process.env.TRIAD_CONFIG_HASH || ''
  }, extra||{});
  if (HMAC_KEY){ base.sig = signPayload(base); }
  return base;
}

function startUdpListener(onPeer){
  if (!USE_UDP) return;
  socket = dgram.createSocket({ type:'udp4', reuseAddr:true });
  socket.on('error', err => {
    console.warn('[Swarm][UDP][Error]', err.message);
  });
  socket.on('message', (msg, rinfo)=>{
    const hb = decodeHeartbeat(msg); if (!hb || !hb.id) return;
    if (hb.id === INSTANCE_ID) return; // self
    if ((HMAC_KEY || REQUIRE_SIG)){
      if (!hb.sig && REQUIRE_SIG){ if (metricsRef){ try { metricsRef.swarmInvalidSig.inc(); } catch(_){} } return; }
      if (hb.sig){ const clone = Object.assign({}, hb); delete clone.sig; const exp = signPayload(clone); if (exp !== hb.sig){ if (metricsRef){ try { metricsRef.swarmInvalidSig.inc(); } catch(_){} } return; } }
    }
    const now = Date.now();
    const hps = typeof hb.hps === 'number' ? hb.hps : 0;
    let rec = peers.get(hb.id);
    if (!rec){ rec = { last: now, payload: hb, emaHps: hps }; }
    else { rec.emaHps = rec.emaHps*(1-EWMA_ALPHA) + hps*EWMA_ALPHA; rec.last = now; rec.payload = hb; }
    peers.set(hb.id, rec);
    updateHashrateMetrics();
    if (onPeer) onPeer(hb, rinfo);
  });
  socket.bind(HEARTBEAT_PORT, ()=>{
    try {
      if (USE_MCAST){ socket.addMembership(MCAST_ADDR); console.log('[Swarm][UDP] Multicast joined', MCAST_ADDR, HEARTBEAT_PORT); }
      else { socket.setBroadcast(true); console.log('[Swarm][UDP] Broadcast listening port', HEARTBEAT_PORT); }
    } catch(e){ console.warn('[Swarm][UDP] membership/broadcast setup fail', e.message); }
  });
}

function sendHeartbeat(extra){
  if (!socket || !USE_UDP) return;
  const now = Date.now(); if (now - lastHeartbeatSent < HEARTBEAT_INTERVAL - 10) return; // rate guard
  lastHeartbeatSent = now;
  const snap = currentSnapshot(extra);
  const buf = encodeHeartbeat(snap);
  const targetAddr = USE_MCAST ? MCAST_ADDR : '255.255.255.255';
  socket.send(buf, 0, buf.length, HEARTBEAT_PORT, targetAddr, (err)=>{ if (err) console.warn('[Swarm][UDP][SendErr]', err.message); });
}

function startMdns(extraProvider){
  if (!USE_MDNS || !bonjour) return;
  try {
    mdnsService = bonjour.publish({ name: INSTANCE_ID, type: 'aurrelia', port: HEARTBEAT_PORT, txt: { id: INSTANCE_ID, v:'1' } });
    bonjour.find({ type:'aurrelia' }, (service)=>{
      if (!service?.txt?.id || service.txt.id === INSTANCE_ID) return;
      peers.set(service.txt.id, { last: Date.now(), payload: { id: service.txt.id, mdns: true, host: service.host } });
    });
    console.log('[Swarm][mDNS] Service published', INSTANCE_ID);
  } catch(e){ console.warn('[Swarm][mDNS] publish failed', e.message); }
}

function prunePeers(){
  const now = Date.now();
  for (const [id,info] of peers){
    if (now - info.last > HEARTBEAT_TTL_MS){ peers.delete(id); }
  }
}

let metricsRef = null; // will hold metrics object
let lastLocalNonceSample = 0; let lastLocalNonceTime = 0;

function integrateMetrics(metrics){ metricsRef = metrics; }

function metricsSnapshot(){
  if (!metricsRef) return {};
  const val = c=>{ try { const g=c.get(); return g.values && g.values[0]? g.values[0].value:0;} catch(_){ return 0; } };
  const nonces = metricsRef.nonces? val(metricsRef.nonces):0;
  const now = Date.now();
  if (!lastLocalNonceTime){ lastLocalNonceTime=now; lastLocalNonceSample=nonces; }
  let hps=0; const dt=(now-lastLocalNonceTime)/1000; if (dt>0.5){ const dn=nonces-lastLocalNonceSample; hps=dn/dt; lastLocalNonceSample=nonces; lastLocalNonceTime=now; if (metricsRef.swarmHashrateLocal){ try { metricsRef.swarmHashrateLocal.set(hps); } catch(_){} } }
  const memdf = metricsRef.memDeterminismFailRatio? val(metricsRef.memDeterminismFailRatio):0;
  return { nonces, shares: metricsRef.shares? val(metricsRef.shares):0, batches: metricsRef.batches? val(metricsRef.batches):0, nativeEnabled: metricsRef.nativeEnabled? val(metricsRef.nativeEnabled):0, hps, memdf };
}

function start(extraProvider, onPeer){
  startUdpListener(onPeer);
  startMdns(extraProvider);
  setInterval(()=>{ prunePeers(); sendHeartbeat(extraProvider? extraProvider(): {}); if (metricsRef && lastHeartbeatSent){ try { metricsRef.swarmLastHeartbeatAgeMs.set(Date.now()-lastHeartbeatSent); } catch(_){} } updateHashrateMetrics(); }, HEARTBEAT_INTERVAL).unref();
}

function updateHashrateMetrics(){
  if (!metricsRef) return;
  let total=0, count=0; let votes=0; const threshold=parseFloat(process.env.KAWPOW_MEM_DET_THRESHOLD||'0.05');
  for (const [,rec] of peers){ if (typeof rec.emaHps==='number'){ total+=rec.emaHps; count++; } if (rec.payload && typeof rec.payload.memdf==='number' && rec.payload.memdf>threshold) votes++; }
  if (metricsRef.swarmHashrateTotal){ try { metricsRef.swarmHashrateTotal.set(total); } catch(_){} }
  if (metricsRef.swarmHashratePeersAvg){ try { metricsRef.swarmHashratePeersAvg.set(count? total/count:0); } catch(_){} }
  if (metricsRef.swarmPeerDeterminismVotes){ try { metricsRef.swarmPeerDeterminismVotes.set(votes); } catch(_){} }
  if (metricsRef.swarmPeers){ try { metricsRef.swarmPeers.set(peers.size); } catch(_){} }
}

function listPeers(){
  const arr=[]; for (const [id,info] of peers){ arr.push({ id, age: Date.now()-info.last, payload: info.payload }); }
  return arr.sort((a,b)=> a.id.localeCompare(b.id));
}

module.exports = { start, listPeers, integrateMetrics };
