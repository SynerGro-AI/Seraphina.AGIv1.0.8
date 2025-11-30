// Structured agent response schema & validator.
// Provides normalization and validation for advisory actions returned by __AUR_AGENT_INVOKE__.
// Future enhancement: integrate with governance proposal auto-sanitizer.
const ACTION_TYPES = new Set([
  'adjust_prune',
  'adjust_growth',
  'rotate_geometry',
  'tune_plane_weights',
  'latency_mitigate',
  'noop'
]);

function validateAgentResponse(resp){
  if(!resp || typeof resp !== 'object') return { ok:false, reason:'not_object' };
  const out = { action: 'noop', delta: 0, confidence: 0, note: '' };
  if(resp.action){
    if(!ACTION_TYPES.has(resp.action)) return { ok:false, reason:'invalid_action' };
    out.action = resp.action;
  }
  if(resp.delta != null){
    if(typeof resp.delta !== 'number' || !isFinite(resp.delta) || Math.abs(resp.delta) > 1){
      return { ok:false, reason:'bad_delta' };
    }
    out.delta = resp.delta;
  }
  if(resp.confidence != null){
    if(typeof resp.confidence !== 'number' || resp.confidence < 0 || resp.confidence > 1){
      return { ok:false, reason:'bad_confidence' };
    }
    out.confidence = resp.confidence;
  }
  if(resp.note){
    if(typeof resp.note !== 'string' || resp.note.length > 400){
      return { ok:false, reason:'bad_note' };
    }
    out.note = resp.note;
  }
  return { ok:true, normalized: out };
}

module.exports = { validateAgentResponse, ACTION_TYPES };
