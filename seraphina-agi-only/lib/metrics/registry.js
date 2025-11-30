// registry.js - centralized Prometheus metrics creation
let promClient=null; try { promClient=require('prom-client'); } catch(_){}

function createKawpowMetrics(){
  if(!promClient) return null;
  return {
    nonces: new promClient.Counter({ name:'aurrelia_kawpow_nonces_total', help:'Total KawPow nonces hashed (batched)' }),
    shares: new promClient.Counter({ name:'aurrelia_kawpow_shares_total', help:'Share candidates meeting local target prefix' }),
    mismatches: new promClient.Counter({ name:'aurrelia_kawpow_parity_mismatches_total', help:'Parity mismatches (native vs JS)' }),
    batches: new promClient.Counter({ name:'aurrelia_kawpow_batches_total', help:'Nonce batches executed' }),
    lastBatch: new promClient.Gauge({ name:'aurrelia_kawpow_last_batch_size', help:'Size of last nonce batch' }),
    parityInterval: new promClient.Gauge({ name:'aurrelia_kawpow_parity_interval', help:'Parity interval (batches)' }),
    rashbaGain: new promClient.Gauge({ name:'aurrelia_rashba_gain_current', help:'Current Rashba gain used in JS mix modulation' }),
    memReads: new promClient.Counter({ name:'aurrelia_kawpow_mem_reads_total', help:'Pseudo light-cache memory line reads inside JS KawPow loop' }),
    memParityChecks: new promClient.Counter({ name:'aurrelia_kawpow_mem_parity_checks_total', help:'Dual JS (mem vs no-mem) effect checks' }),
    memParityDeterminismFails: new promClient.Counter({ name:'aurrelia_kawpow_mem_determinism_fails_total', help:'Recomputed mem variant mismatch (non-deterministic)' }),
    memEffectRatio: new promClient.Gauge({ name:'aurrelia_kawpow_mem_effect_ratio', help:'Clamped numeric hash ratio noMem/mem (<=10)' }),
    memEffectDeltaBits: new promClient.Gauge({ name:'aurrelia_kawpow_mem_effect_delta_bits', help:'Leading zero bits difference (noMem - mem)' }),
    memDeterminismFailRatio: new promClient.Gauge({ name:'aurrelia_kawpow_mem_determinism_fail_ratio', help:'mem determinism fails / checks ratio' }),
    nativeDisableEvents: new promClient.Counter({ name:'aurrelia_kawpow_native_disable_events_total', help:'Times native hashing disabled by native-gate' }),
    nativeEnabled: new promClient.Gauge({ name:'aurrelia_kawpow_native_enabled', help:'1 if native hashing path enabled, else 0' }),
  cacheBuildMs: new promClient.Gauge({ name:'aurrelia_kawpow_cache_build_ms', help:'Milliseconds to (re)build KawPow light cache' }),
  cacheSizeMB: new promClient.Gauge({ name:'aurrelia_kawpow_light_cache_mb', help:'Configured / realized light cache size in MB' }),
  cacheItems: new promClient.Gauge({ name:'aurrelia_kawpow_light_cache_items', help:'Number of items (lines) in light cache' }),
  hashLatencyNs: new promClient.Histogram({ name:'aurrelia_kawpow_hash_latency_ns_hist', help:'Native KawPow hash latency (nanoseconds)', buckets:[100,500,1000,5000,10000,20000,50000] }),
    // Swarm metrics (optional)
    swarmPeers: new promClient.Gauge({ name:'aurrelia_swarm_peers', help:'Current discovered swarm peers (UDP + mDNS)' }),
    swarmHeartbeatsSent: new promClient.Counter({ name:'aurrelia_swarm_heartbeats_sent_total', help:'Heartbeats sent (UDP broadcast/multicast)' }),
    swarmLastHeartbeatAgeMs: new promClient.Gauge({ name:'aurrelia_swarm_last_hb_age_ms', help:'Age ms of last local heartbeat emission' }),
    swarmHashrateTotal: new promClient.Gauge({ name:'aurrelia_swarm_hashrate_total', help:'Aggregated peer reported hash rate (H/s approx)' }),
    swarmHashratePeersAvg: new promClient.Gauge({ name:'aurrelia_swarm_hashrate_peers_avg', help:'Average peer reported hash rate' }),
    swarmHashrateLocal: new promClient.Gauge({ name:'aurrelia_swarm_hashrate_local', help:'Local estimated hash rate (H/s)' }),
    swarmInvalidSig: new promClient.Counter({ name:'aurrelia_swarm_invalid_sig_total', help:'Rejected heartbeats due to invalid or missing signature when required' }),
    swarmPeerDeterminismVotes: new promClient.Gauge({ name:'aurrelia_swarm_peer_determinism_votes', help:'Peers exceeding mem determinism fail ratio threshold' })
    ,sharesSubmitted: new promClient.Counter({ name:'aurrelia_kawpow_shares_submitted_total', help:'Total shares submitted to pool (attempted)' })
    ,sharesAccepted: new promClient.Counter({ name:'aurrelia_kawpow_shares_accepted_total', help:'Shares accepted by pool' })
    ,sharesRejected: new promClient.Counter({ name:'aurrelia_kawpow_shares_rejected_total', help:'Shares rejected by pool' })
    ,shareAcceptRatio: new promClient.Gauge({ name:'aurrelia_kawpow_share_accept_ratio', help:'Accepted / Submitted ratio (0..1)' })
  };
}

module.exports = { createKawpowMetrics, promClient };
