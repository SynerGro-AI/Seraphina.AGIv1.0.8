// ai-learning-orchestrator.js
// Deterministic orchestrator: loads config + builds manifest, invokes training harness(es),
// evaluates improvement, conditionally updates weights (bounded), appends summary ledger.
// No randomness; ordering strictly defined.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = __dirname;
const CONFIG_PATH = path.join(ROOT,'ai-learning-config.json');
const MANIFEST_SCRIPT = path.join(ROOT,'ai-dataset-manifest.js');
const ML_TRAIN_SCRIPT = path.join(ROOT,'ml-train-deterministic.js');
const WEIGHTS_PATH = path.join(ROOT,'ml-advisor-weights.json');
const SUMMARY_LEDGER = path.join(ROOT,'ai-learning-summary-ledger.jsonl');
const IMAGINATION_ADAPTER = path.join(ROOT,'seraphina-3d-imagination-adapter.js');
const SERAPHINA_TRAIN_SCRIPT = path.join(ROOT,'seraphina-train-deterministic.js');
const SANDBOX_ENV_SCRIPT = path.join(ROOT,'seraphina-sandbox-env.js');
const PARETO_OPT_SCRIPT = path.join(ROOT,'pareto-multi-metric-optimizer.js');
const DIM_ESC_SCRIPT = path.join(ROOT,'dimension-escalator.js');
const DIM_STATE_FILE = path.join(ROOT,'dimension-state.json');
const DIM_ESC_LEDGER = path.join(ROOT,'dimension-escalation-ledger.js');
const COLOR_EMOTION_MAP = path.join(ROOT,'color-emotion-map.js');
const EMPOWERMENT_STABILITY_MOD = path.join(ROOT,'empowerment-stability.js');
const AUTONOMY_ENGINE = path.join(ROOT,'autonomy-decision-engine.js');
const REGRESSION_DIFF_MOD = path.join(ROOT,'regression-diff.js');

function sha256(data){
  return crypto.createHash('sha256').update(data).digest('hex');
}

function readJSON(p){ return JSON.parse(fs.readFileSync(p,'utf8')); }

function safeRequire(p){ try { return require(p); } catch(e){ return null; } }

function loadConfig(){ return readJSON(CONFIG_PATH); }

function buildManifest(){
  // require manifest script and invoke builder for in-process determinism.
  const mod = safeRequire(MANIFEST_SCRIPT);
  if(!mod || !mod.buildManifest) throw new Error('Manifest builder missing');
  return mod.buildManifest();
}

function loadWeights(){
  try { return readJSON(WEIGHTS_PATH); } catch(e){ return { version:'unknown', weights:{} }; }
}

function invokeMlTraining(){
  // Deterministic training harness should append to its ledger & update scoreboard.
  // We run in-process by requiring (if it exports a function) else spawnless via node child disabled for simplicity.
  try {
    const mod = safeRequire(ML_TRAIN_SCRIPT);
    if(mod && typeof mod.runDeterministicTraining === 'function'){
      return mod.runDeterministicTraining();
    }
  } catch(e){ /* ignore; fallback scoreboard read */ }
  // Fallback: read scoreboard after external invocation expectation.
  const sbPath = path.join(ROOT,'ml-train-scoreboard.json');
  if(fs.existsSync(sbPath)) return readJSON(sbPath); else return { status:'no-scoreboard' };
}

function evaluateImprovement(scoreboard){
  // Expect scoreboard with maybe fields bestCandidateDelta / improvementAccepted
  const improv = {
    accepted: !!scoreboard?.improvementAccepted,
    bestDelta: scoreboard?.bestCandidateDelta ?? 0,
    baselineScore: scoreboard?.baselineScore ?? null,
    bestScore: scoreboard?.bestScore ?? null
  };
  return improv;
}

function maybeUpdateWeights(improv){
  if(!improv.accepted) return { updated:false };
  // Load current weights then compute digest; assume training harness updated file already if accepted.
  const newWeights = loadWeights();
  return { updated:true, newVersion:newWeights.version, weightsDigest:sha256(JSON.stringify(newWeights)) };
}

function appendSummaryLedger(entry){
  const line = JSON.stringify(entry);
  fs.appendFileSync(SUMMARY_LEDGER, line+'\n');
}

function orchestrate(){
  const start = Date.now();
  const cfg = loadConfig();
  const cfgDigest = sha256(JSON.stringify(cfg));
  const manifest = buildManifest();
  const beforeWeights = loadWeights();
  const beforeDigest = sha256(JSON.stringify(beforeWeights));

  // Optional imagination session
  let imagination = null;
  try {
    const imagCfg = cfg.modules?.imagination;
    if(imagCfg){
      const enabledEnv = process.env[imagCfg.enableParam] || '0';
      const enabled = enabledEnv === '1';
      if(enabled){
        const maxScenariosBound = parseInt(process.env[imagCfg.maxScenariosParam]|| imagCfg.defaultMaxScenarios,10);
        let scenarios = [];
        if(fs.existsSync(path.join(ROOT, imagCfg.scenariosFile))){
          try{ scenarios = JSON.parse(fs.readFileSync(path.join(ROOT, imagCfg.scenariosFile),'utf8')); }catch(_){ scenarios=[]; }
        }
        if(Array.isArray(scenarios)){
          scenarios = scenarios.slice(0, maxScenariosBound);
        } else { scenarios = []; }
        const adapter = safeRequire(IMAGINATION_ADAPTER);
        if(adapter && typeof adapter.runImaginationSession === 'function'){
          imagination = adapter.runImaginationSession({
            lattice: imagCfg.latticeDefaults || {},
            scenarios
          });
        }
      }
    }
  } catch(e){ imagination = { error: 'imagination_failed', message: e.message }; }

  const trainingScoreboard = invokeMlTraining();
  // Seraphina training (optional; runs if script exists)
  let seraphinaScoreboard = null;
  // Sandbox intrinsic motivation session (optional)
  let sandboxSession = null;
  try {
    if(fs.existsSync(SERAPHINA_TRAIN_SCRIPT)){
      const seraph = safeRequire(SERAPHINA_TRAIN_SCRIPT);
      if(seraph && typeof seraph.runSeraphinaTraining === 'function'){
        seraphinaScoreboard = seraph.runSeraphinaTraining();
      }
    }
  } catch(e){ seraphinaScoreboard = { error:'seraphina_training_failed', message:e.message }; }
  try {
    if(process.env.SANDBOX_ENABLED === '1' && fs.existsSync(SANDBOX_ENV_SCRIPT)){
      const sandbox = safeRequire(SANDBOX_ENV_SCRIPT);
      if(sandbox && typeof sandbox.runSandboxSession === 'function'){
        sandboxSession = sandbox.runSandboxSession();
      }
    }
  } catch(e){ sandboxSession = { error:'sandbox_failed', message:e.message }; }
  const improv = evaluateImprovement(trainingScoreboard);
  // Effective improvement policy: base improvement plus weighted imagination contribution.
  const imaginationGain = imagination?.aggregateGain || 0;
  const imagWeight = parseFloat(process.env.IMAGINATION_GAIN_WEIGHT || '0');
  const curiosityWeight = parseFloat(process.env.CURIOSITY_GAIN_WEIGHT || '0');
  const integrationWeight = parseFloat(process.env.INTEGRATION_GAIN_WEIGHT || '0');
  const baseImprovementPct = trainingScoreboard?.improvementPct || 0;
  const curiosityGain = sandboxSession ? sandboxSession.avgCuriosity : 0;
  const integrationNorm = sandboxSession ? sandboxSession.avgIntegration : 0;
  const empowermentGain = sandboxSession ? sandboxSession.avgEmpowerment : 0;
  const noveltyGain = sandboxSession ? sandboxSession.avgNovelty : 0;
  // Empowerment stability tracking & dynamic weight adaptation (bounded by governance)
  let empowermentStabilityState = null;
  try {
    const est = safeRequire(EMPOWERMENT_STABILITY_MOD);
    if(est && typeof est.recordEmpowerment === 'function'){
      empowermentStabilityState = est.recordEmpowerment(empowermentGain);
      // Dynamic adjustment heuristic: if stability > 0.85 increase weight modestly; if <0.3 decrease.
      const currentWeight = parseFloat(process.env.EMPOWERMENT_GAIN_WEIGHT || '0');
      const minW = 0; const maxW = 5; // future: read from governance bounds directly
      let target = currentWeight;
      if(empowermentStabilityState.stability > 0.85) target = Math.min(maxW, currentWeight + 0.1);
      else if(empowermentStabilityState.stability < 0.3) target = Math.max(minW, currentWeight * 0.8);
      if(Math.abs(target - currentWeight) >= 0.05){
        // Emit draft proposal instead of direct env mutation for operator confirmation
        const draftFile = path.join(ROOT,'governance-proposal-drafts.jsonl');
        const draft = { id:'auto-empowerment-weight-'+Date.now(), params:{ EMPOWERMENT_GAIN_WEIGHT: Number(target.toFixed(4)) }, rationale:{ stability: empowermentStabilityState.stability } };
        try { fs.appendFileSync(draftFile, JSON.stringify(draft)+'\n'); } catch(_){ }
      }
    }
  } catch(_){ }
  // Color-emotion tier mapping (deterministic) using sandbox metrics + imagination gain
  let colorEmotionTier = null;
  try {
    const cem = safeRequire(COLOR_EMOTION_MAP);
    if(cem && typeof cem.computeColorEmotionTier === 'function'){
      colorEmotionTier = cem.computeColorEmotionTier({
        curiosity: curiosityGain,
        novelty: sandboxSession ? sandboxSession.avgNovelty : 0,
        empowerment: empowermentGain,
        integration: sandboxSession ? sandboxSession.avgIntegration : 0,
        imaginationGain
      });
    }
  } catch(_){ }
  let paretoRepresentative = null, paretoFrontSize = 0;
  // Dimension escalation history tracking
  let dimState = { currentDim: parseInt(process.env.IMAGINATION_DIM||'3',10), history: [] };
  if(fs.existsSync(DIM_STATE_FILE)){
    try { dimState = JSON.parse(fs.readFileSync(DIM_STATE_FILE,'utf8')); } catch(_){ }
  }
  // Append latest effectiveImprovement from previous run if present (loaded before recompute) using a small side file
  // We only escalate AFTER computing current effectiveImprovement; so push previous improvement stored in state.
  if(typeof dimState.lastEffective === 'number'){
    dimState.history.push(dimState.lastEffective);
    if(dimState.history.length > 200) dimState.history = dimState.history.slice(-200);
  }
  // Bootstrap option: treat current run as first history element if enabled and history empty
  const bootstrapEnabled = process.env.IMAGINATION_DIM_BOOTSTRAP === '1';
  if(bootstrapEnabled && dimState.history.length === 0){
    // we will add current run's effective improvement after computation; mark placeholder
    dimState.bootstrapPending = true;
  }
  if(process.env.PARETO_ENABLED === '1'){
    try {
      if(fs.existsSync(PARETO_OPT_SCRIPT)){
        const pareto = safeRequire(PARETO_OPT_SCRIPT);
        if(pareto && typeof pareto.runPareto === 'function'){
          const res = pareto.runPareto({ imaginationGain, curiosityGain, integrationNorm, empowermentGain, noveltyGain });
          paretoRepresentative = res.representative;
          paretoFrontSize = res.frontSize;
        }
      }
    } catch(_){ }
  }
  const empowermentWeight = parseFloat(process.env.EMPOWERMENT_GAIN_WEIGHT || '0');
  const noveltyWeight = parseFloat(process.env.NOVELTY_GAIN_WEIGHT || '0');
  let effectiveImprovement = baseImprovementPct + (imaginationGain * imagWeight) + (curiosityGain * curiosityWeight) + (integrationNorm * integrationWeight) + (empowermentGain * empowermentWeight) + (noveltyGain * noveltyWeight);
  if(paretoRepresentative){
    // Override dynamic weighting proportionally using pareto representative weights
    const dims = paretoRepresentative.length;
    const wImag = paretoRepresentative[0];
    const wCurio = paretoRepresentative[1];
    const wInt = paretoRepresentative[2];
    const wEmp = (process.env.PARETO_INCLUDE_EMPOWERMENT === '1') ? paretoRepresentative[3] : 0;
    const wNov = (process.env.PARETO_INCLUDE_NOVELTY === '1') ? paretoRepresentative[dims-1] : 0;
    effectiveImprovement = baseImprovementPct + (imaginationGain * wImag) + (curiosityGain * wCurio) + (integrationNorm * wInt) + (empowermentGain * wEmp) + (noveltyGain * wNov);
  }
  // Dimension escalation check (post effectiveImprovement compute to record this run for next cycle)
  try {
    const targetDim = parseInt(process.env.IMAGINATION_DIM_TARGET || process.env.IMAGINATION_DIM || '3',10);
    const stepMax = parseInt(process.env.IMAGINATION_DIM_STEP_MAX || '8',10);
    const varianceThreshold = parseFloat(process.env.IMAGINATION_DIM_VARIANCE_THRESHOLD || '0.2');
    const plateauRuns = parseInt(process.env.IMAGINATION_DIM_PLATEAU_RUNS || '5',10);
    const rollbackRuns = parseInt(process.env.IMAGINATION_DIM_ROLLBACK_RUNS || '5',10);
  const rampStep = parseInt(process.env.IMAGINATION_DIM_RAMP_STEP || String(stepMax),10);
    const minIntegration = parseFloat(process.env.IMAGINATION_DIM_MIN_INTEGRATION || '0');
    const minEmpowerment = parseFloat(process.env.IMAGINATION_DIM_MIN_EMPOWERMENT || '0');
  const cooldownRuns = parseInt(process.env.IMAGINATION_DIM_ESC_COOLDOWN_RUNS || '0',10);
  const costLimit = parseFloat(process.env.IMAGINATION_DIM_COST_LIMIT || '0');
  // Compute dimension cost heuristic: dim^2 * (paretoFrontSize+1)
  const dimensionCost = dimState.currentDim * dimState.currentDim * (paretoFrontSize || 1);
  const dimensionCostAlt = dimState.currentDim * (paretoFrontSize || 1) * (imagination?.scenarioCount || 1);
  summary.dimensionCost = dimensionCost;
  summary.dimensionCostAlt = dimensionCostAlt;
    if(targetDim > dimState.currentDim && fs.existsSync(DIM_ESC_SCRIPT)){
      const esc = safeRequire(DIM_ESC_SCRIPT);
      if(esc && typeof esc.decideDimensionEscalation === 'function'){
        // If bootstrap pending, inject current effectiveImprovement into a temp history slice
        let histSlice = dimState.history.slice(-plateauRuns);
        if(dimState.bootstrapPending){ histSlice = histSlice.concat([effectiveImprovement]); }
        // Gating by sandbox metrics if available
        const sandboxIntegrationOk = (sandboxSession ? (sandboxSession.avgIntegration || 0) : 0) >= minIntegration;
        const sandboxEmpowermentOk = (sandboxSession ? (sandboxSession.avgEmpowerment || 0) : 0) >= minEmpowerment;
        const cooldownOk = !dimState.escalatedAt || (dimState.history.length - (dimState.escalationIndex||0)) >= cooldownRuns;
        const costOk = costLimit === 0 || dimensionCost <= costLimit;
        if(sandboxIntegrationOk && sandboxEmpowermentOk && cooldownOk && costOk){
          let decision = esc.decideDimensionEscalation({ history: histSlice, currentDim: dimState.currentDim, targetDim, stepMax, varianceThreshold, plateauRuns });
          if(decision.escalate){
            // Apply ramping: limit nextDim to currentDim + rampStep and not exceed targetDim
            const cappedNext = Math.min(dimState.currentDim + rampStep, decision.nextDim, targetDim);
            const prevDim = dimState.currentDim;
            dimState.previousDim = prevDim;
            dimState.currentDim = cappedNext;
            process.env.IMAGINATION_DIM = String(dimState.currentDim);
            summary.dimensionEscalation = { from: prevDim, to: dimState.currentDim, reason: decision.reason, rampApplied: cappedNext !== decision.nextDim || cappedNext !== targetDim };
            dimState.escalatedAt = Date.now();
            dimState.escalatedEffective = effectiveImprovement;
            dimState.escalationIndex = dimState.history.length;
            // Ledger event
            try {
              if(fs.existsSync(DIM_ESC_LEDGER)){
                const ledgerMod = safeRequire(DIM_ESC_LEDGER);
                ledgerMod && ledgerMod.appendDimensionEvent && ledgerMod.appendDimensionEvent({ t:Date.now(), type:'escalate', from:prevDim, to:dimState.currentDim, reason:decision.reason, rampStep:rampStep, preMetrics:{ imaginationGain, curiosityGain, integrationNorm, empowermentGain, effectiveImprovementBefore: effectiveImprovement } });
              }
            } catch(_){}
          }
        } else {
          const altCostLimit = parseFloat(process.env.IMAGINATION_DIM_COST_ALT_LIMIT || '0');
          const costAltOk = altCostLimit === 0 || dimensionCostAlt <= altCostLimit;
          summary.dimensionEscalationBlocked = { integrationOk: sandboxIntegrationOk, empowermentOk: sandboxEmpowermentOk, cooldownOk, costOk, costAltOk };
        }
      }
    }
    // Rollback safeguard: if escalated and last N effective improvements (< rollbackRuns) all fall below minRequired
    if(dimState.escalatedAt && dimState.history.length >= rollbackRuns){
      const recent = dimState.history.slice(-rollbackRuns);
      const allUnder = recent.every(v=> v < minRequired);
      if(allUnder && dimState.currentDim > 3){
        const previousDim = dimState.previousDim || 3;
        const proposalMode = process.env.DIMENSION_ROLLBACK_PROPOSAL_MODE === '1';
        if(proposalMode){
          // Emit governance draft instead of immediate revert
          const draftFile = path.join(ROOT,'governance-proposal-drafts.jsonl');
          const draft = { id:'auto-dim-rollback-'+Date.now(), params:{ IMAGINATION_DIM_TARGET: previousDim }, rationale:{ window:rollbackRuns, reason:'underperformance' } };
          try { fs.appendFileSync(draftFile, JSON.stringify(draft)+'\n'); } catch(_){}
          summary.dimensionRollbackProposal = { from: dimState.currentDim, proposed: previousDim, window: rollbackRuns };
          try {
            if(fs.existsSync(DIM_ESC_LEDGER)){
              const ledgerMod = safeRequire(DIM_ESC_LEDGER);
              ledgerMod && ledgerMod.appendDimensionEvent && ledgerMod.appendDimensionEvent({ t:Date.now(), type:'rollback-proposal', from:dimState.currentDim, to:previousDim, window:rollbackRuns });
            }
          } catch(_){}
        } else {
          dimState.rollbackAt = Date.now();
          dimState.rollbackFrom = dimState.currentDim;
          dimState.currentDim = previousDim;
          process.env.IMAGINATION_DIM = String(previousDim);
          summary.dimensionRollback = { from: dimState.rollbackFrom, to: previousDim, reason:'underperformance', window: rollbackRuns };
          try {
            if(fs.existsSync(DIM_ESC_LEDGER)){
              const ledgerMod = safeRequire(DIM_ESC_LEDGER);
              ledgerMod && ledgerMod.appendDimensionEvent && ledgerMod.appendDimensionEvent({ t:Date.now(), type:'rollback', from:dimState.rollbackFrom, to:previousDim, window:rollbackRuns });
            }
          } catch(_){}
        }
      }
    }
  } catch(_){ }
  const minRequired = parseFloat(process.env.GLOBAL_MIN_IMPROVEMENT || '0');
  // Force acceptance flag based on effectiveImprovement
  const acceptance = effectiveImprovement >= minRequired && trainingScoreboard?.improvementAccepted;
  const updateResult = acceptance ? maybeUpdateWeights({ accepted:true }) : { updated:false };
  const afterWeights = loadWeights();
  const afterDigest = sha256(JSON.stringify(afterWeights));

  // Seraphina effective improvement (base seraphina improvement plus imagination weighting)
  let seraphinaEffectiveImprovement = 0;
  if (seraphinaScoreboard && typeof seraphinaScoreboard.improvementPct === 'number') {
    seraphinaEffectiveImprovement = seraphinaScoreboard.improvementPct + (imaginationGain * imagWeight) + (curiosityGain * curiosityWeight);
  }

  // Rollback logic: maintain snapshot of previous weights after successful update; if a future run's effectiveImprovement
  // drops below minRequired, revert to snapshot deterministically.
  const rollbackSnapshotPath = path.join(ROOT,'ml-advisor-weights-rollback-snapshot.json');
  let rollbackConsidered = false, rollbackPerformed = false, previousSnapshotDigest = null;
  if (fs.existsSync(rollbackSnapshotPath)){
    try {
      const snapRaw = fs.readFileSync(rollbackSnapshotPath,'utf8');
      const snap = JSON.parse(snapRaw);
      previousSnapshotDigest = sha256(JSON.stringify(snap));
      if (effectiveImprovement < minRequired){
        rollbackConsidered = true;
        // Compare digests to ensure we only rollback if current differs from snapshot
        const currentDigest = sha256(JSON.stringify(afterWeights));
        if (currentDigest !== previousSnapshotDigest){
          fs.writeFileSync(WEIGHTS_PATH, JSON.stringify(snap,null,2));
          rollbackPerformed = true;
        }
      }
    } catch(_){ /* ignore parse errors */ }
  }
  // If we just successfully updated and acceptance true, capture beforeWeights snapshot for potential rollback.
  if (updateResult.updated && !rollbackPerformed){
    try { fs.writeFileSync(rollbackSnapshotPath, JSON.stringify(beforeWeights,null,2)); previousSnapshotDigest = sha256(JSON.stringify(beforeWeights)); } catch(_){ }
  }

  const summary = {
    ts: new Date().toISOString(),
    durationMs: Date.now()-start,
    cfgDigest,
    manifestChainDigest: manifest.aggregateChainDigest,
    training: trainingScoreboard,
    seraphinaTraining: seraphinaScoreboard ? {
      improvementPct: seraphinaScoreboard.improvementPct,
      candidateCount: seraphinaScoreboard.candidateCount,
      baseScore: seraphinaScoreboard.base?.score,
      bestScore: seraphinaScoreboard.best?.score,
      signalsDigest: seraphinaScoreboard.signalsDigest,
      imaginationDigest: seraphinaScoreboard.imaginationDigest,
      effectiveImprovement: seraphinaEffectiveImprovement
    } : null,
  improvement: { ...improv, effectiveImprovement, minRequired },
    weightsBefore: beforeDigest,
    weightsAfter: afterDigest,
    updated: updateResult.updated,
    newVersion: updateResult.newVersion || beforeWeights.version,
    weightsDigest: updateResult.weightsDigest || beforeDigest,
    imagination: imagination ? {
      sessionDigest: imagination.sessionDigest,
      aggregateGain: imagination.aggregateGain,
      scenarioCount: imagination.scenarioCount
    } : null,
    sandbox: sandboxSession ? {
      steps: sandboxSession.steps,
      avgCuriosity: sandboxSession.avgCuriosity,
      avgNovelty: sandboxSession.avgNovelty,
      avgEmpowerment: sandboxSession.avgEmpowerment,
      avgIntegration: sandboxSession.avgIntegration,
      diversityHash: sandboxSession.diversityHash
    } : null,
    empowermentStability: empowermentStabilityState ? { stability: empowermentStabilityState.stability, mean: empowermentStabilityState.mean, stdev: empowermentStabilityState.stdev } : null,
  pareto: paretoRepresentative ? { representative: paretoRepresentative, frontSize: paretoFrontSize } : null,
  emotionTier: colorEmotionTier,
  virtue: colorEmotionTier ? { index: colorEmotionTier.tierIndex, name: colorEmotionTier.virtue } : null,
  regressionDiff: null,
  autonomyDraft: null,
  dimension: { current: dimState.currentDim },
    rollbackConsidered,
    rollbackPerformed,
    previousSnapshotDigest
  };
  // Deterministic ledger chain by including previous line sha in new line if exists.
  let prevHash = null;
  if(fs.existsSync(SUMMARY_LEDGER)){
    const lines = fs.readFileSync(SUMMARY_LEDGER,'utf8').trim().split(/\n+/).filter(Boolean);
    if(lines.length){
      const last = lines[lines.length-1];
      prevHash = sha256(last);
    }
  }
  summary.prevHash = prevHash;
  summary.entryHash = sha256(JSON.stringify(summary));
  appendSummaryLedger(summary);
  // Persist dimension state (record this run's effectiveImprovement for next evaluation cycle)
  try {
    dimState.lastEffective = effectiveImprovement;
    if(dimState.bootstrapPending){
      // finalize bootstrap by adding current run effectiveImprovement to history immediately
      dimState.history.push(effectiveImprovement);
      delete dimState.bootstrapPending;
    }
    fs.writeFileSync(DIM_STATE_FILE, JSON.stringify(dimState,null,2));
  } catch(_){ }
  // Prometheus gauges (lazy registration)
  try {
    if (global.__AUR_METRICS_REG__ && global.__AUR_METRICS_REG__.gauges){
      const prom = require('prom-client');
      const g = global.__AUR_METRICS_REG__.gauges;
      if (!g.learningMlImprovement){ g.learningMlImprovement = new prom.Gauge({ name:'aurrelia_learning_ml_improvement_pct', help:'ML advisor raw improvementPct' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.learningMlImprovement); }
      if (!g.learningSeraphinaImprovement){ g.learningSeraphinaImprovement = new prom.Gauge({ name:'aurrelia_learning_seraphina_improvement_pct', help:'Seraphina training improvementPct' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.learningSeraphinaImprovement); }
      if (!g.learningImaginationGain){ g.learningImaginationGain = new prom.Gauge({ name:'aurrelia_learning_imagination_gain', help:'Imagination aggregateGain for latest session' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.learningImaginationGain); }
      if (!g.learningEffectiveImprovement){ g.learningEffectiveImprovement = new prom.Gauge({ name:'aurrelia_learning_effective_improvement', help:'Effective improvement after imagination weighting' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.learningEffectiveImprovement); }
  if (!g.learningSeraphinaEffectiveImprovement){ g.learningSeraphinaEffectiveImprovement = new prom.Gauge({ name:'aurrelia_learning_seraphina_effective_improvement', help:'Seraphina effective improvement after imagination weighting' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.learningSeraphinaEffectiveImprovement); }
      if (!g.sandboxCuriosity){ g.sandboxCuriosity = new prom.Gauge({ name:'aurrelia_sandbox_avg_curiosity', help:'Average sandbox curiosity score' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.sandboxCuriosity); }
      if (!g.sandboxNovelty){ g.sandboxNovelty = new prom.Gauge({ name:'aurrelia_sandbox_avg_novelty', help:'Average sandbox novelty score' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.sandboxNovelty); }
      if (!g.sandboxEmpowerment){ g.sandboxEmpowerment = new prom.Gauge({ name:'aurrelia_sandbox_avg_empowerment', help:'Average sandbox empowerment score' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.sandboxEmpowerment); }
  if (!g.sandboxIntegration){ g.sandboxIntegration = new prom.Gauge({ name:'aurrelia_sandbox_avg_integration', help:'Average sandbox integration score' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.sandboxIntegration); }
  if (!g.paretoFrontSize){ g.paretoFrontSize = new prom.Gauge({ name:'aurrelia_pareto_front_size', help:'Current Pareto front size (multi-metric optimizer)' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.paretoFrontSize); }
  if (!g.paretoRepresentativeImag){ g.paretoRepresentativeImag = new prom.Gauge({ name:'aurrelia_pareto_rep_imagination_weight', help:'Pareto representative imagination weight' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.paretoRepresentativeImag); }
  if (!g.paretoRepresentativeCurio){ g.paretoRepresentativeCurio = new prom.Gauge({ name:'aurrelia_pareto_rep_curiosity_weight', help:'Pareto representative curiosity weight' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.paretoRepresentativeCurio); }
  if (!g.paretoRepresentativeInt){ g.paretoRepresentativeInt = new prom.Gauge({ name:'aurrelia_pareto_rep_integration_weight', help:'Pareto representative integration weight' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.paretoRepresentativeInt); }
  if (!g.paretoRepresentativeEmp){ g.paretoRepresentativeEmp = new prom.Gauge({ name:'aurrelia_pareto_rep_empowerment_weight', help:'Pareto representative empowerment weight (if included)' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.paretoRepresentativeEmp); }
  if (!g.learningEmpowermentGain){ g.learningEmpowermentGain = new prom.Gauge({ name:'aurrelia_learning_empowerment_gain', help:'Sandbox empowerment gain' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.learningEmpowermentGain); }
  if (!g.imaginationDim){ g.imaginationDim = new prom.Gauge({ name:'aurrelia_imagination_dimension', help:'Current imagination lattice dimensionality' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.imaginationDim); }
  if (!g.emotionTierIndex){ g.emotionTierIndex = new prom.Gauge({ name:'aurrelia_emotion_tier_index', help:'Color-emotion tier index (0..6)' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.emotionTierIndex); }
  if (!g.empowermentStability){ g.empowermentStability = new prom.Gauge({ name:'aurrelia_empowerment_stability', help:'Empowerment stability score (0..1)' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.empowermentStability); }
  if (!g.dimensionCostAlt){ g.dimensionCostAlt = new prom.Gauge({ name:'aurrelia_dimension_cost_alt', help:'Alternate dimension cost function' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.dimensionCostAlt); }
  if (!g.regressionDiffPct){ g.regressionDiffPct = new prom.Gauge({ name:'aurrelia_regression_diff_pct', help:'Regression diff percent vs baseline' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.regressionDiffPct); }
  if (!g.autonomyDecisionApplied){ g.autonomyDecisionApplied = new prom.Gauge({ name:'aurrelia_autonomy_decision_applied', help:'Autonomy draft emitted this run (1/0)' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.autonomyDecisionApplied); }
      g.learningMlImprovement.set(trainingScoreboard?.improvementPct || 0);
      g.learningSeraphinaImprovement.set(seraphinaScoreboard?.improvementPct || 0);
      g.learningImaginationGain.set(imaginationGain);
      g.learningEffectiveImprovement.set(summary.improvement?.effectiveImprovement || 0);
  g.learningSeraphinaEffectiveImprovement.set(seraphinaEffectiveImprovement || 0);
      if (sandboxSession){
        g.sandboxCuriosity.set(sandboxSession.avgCuriosity || 0);
        g.sandboxNovelty.set(sandboxSession.avgNovelty || 0);
        g.sandboxEmpowerment.set(sandboxSession.avgEmpowerment || 0);
        g.sandboxIntegration.set(sandboxSession.avgIntegration || 0);
        g.learningEmpowermentGain.set(sandboxSession.avgEmpowerment || 0);
      }
      if (paretoRepresentative){
        g.paretoFrontSize.set(paretoFrontSize);
        g.paretoRepresentativeImag.set(paretoRepresentative[0]||0);
        g.paretoRepresentativeCurio.set(paretoRepresentative[1]||0);
        g.paretoRepresentativeInt.set(paretoRepresentative[2]||0);
        if(process.env.PARETO_INCLUDE_EMPOWERMENT === '1'){ g.paretoRepresentativeEmp.set(paretoRepresentative[3]||0); }
      }
      // Imagination dimension gauge derives from environment or session
      const imaginationDim = parseInt(process.env.IMAGINATION_DIM || summary.imagination?.dim || '3',10);
  g.imaginationDim.set(imaginationDim);
  if(colorEmotionTier){ g.emotionTierIndex.set(colorEmotionTier.tierIndex); }
  if(colorEmotionTier){
        if(!g.virtueTierIndex){ g.virtueTierIndex = new prom.Gauge({ name:'aurrelia_emotion_virtue_index', help:'Virtue index (0..6) mapped from emotion tier' }); global.__AUR_METRICS_REG__.registry.registerMetric(g.virtueTierIndex); }
        g.virtueTierIndex.set(colorEmotionTier.tierIndex);
      }
  if(empowermentStabilityState){ g.empowermentStability.set(empowermentStabilityState.stability||0); }
  g.dimensionCostAlt.set(summary.dimensionCostAlt||0);
  if(summary.regressionDiff){ g.regressionDiffPct.set(summary.regressionDiff.pct||0); }
  g.autonomyDecisionApplied.set(summary.autonomyDraft?1:0);
    }
  } catch(_){ }

  // Adaptive curiosity weight tuner (governance-driven proposal emission stub):
  // If curiosity weight >0 but marginal contribution very small for several runs OR
  // if curiosityGain is consistently high vs imaginationGain, propose adjustment.
  try {
    const tunerLog = path.join(ROOT,'curiosity-weight-tuner.log');
    const record = {
      ts: summary.ts,
      curiosityGain: curiosityGain,
      curiosityWeight,
      imaginationGain,
      imagWeight,
      effectiveImprovement: summary.improvement.effectiveImprovement
    };
    fs.appendFileSync(tunerLog, JSON.stringify(record)+'\n');
    // Simple heuristic using last 5 records
  const linesRaw = fs.readFileSync(tunerLog,'utf8').trim().split(/\n+/);
  const lines = linesRaw.slice(-5);
    const recent = lines.map(l=>{ try{return JSON.parse(l);}catch(_){return null;} }).filter(Boolean);
    if(recent.length >= 3){
      const avgCuriosity = recent.reduce((a,b)=>a+b.curiosityGain,0)/recent.length;
      const avgImag = recent.reduce((a,b)=>a+b.imaginationGain,0)/recent.length;
      const currentWeight = curiosityWeight;
      let target = null;
      if(currentWeight > 0 && avgCuriosity < 0.01){
        target = Math.max(0, currentWeight * 0.5);
      } else if(avgCuriosity > 0.3 && avgImag < 0.05){
        target = Math.min(5, currentWeight + 0.2);
      }
      // Safety valve: limit draft proposals over recent window
      const maxDrafts = parseInt(process.env.TUNER_MAX_DRAFTS_WINDOW || '10',10);
      let draftCount = 0;
      const draftFile = path.join(ROOT,'governance-proposal-drafts.jsonl');
      if(fs.existsSync(draftFile)){
        try {
          const dlines = fs.readFileSync(draftFile,'utf8').trim().split(/\n+/).slice(-maxDrafts);
          draftCount = dlines.length;
        } catch(_){ }
      }
      if(target !== null && Math.abs(target - currentWeight) >= 0.05 && draftCount < maxDrafts){
        // Emit governance proposal draft (dry-run) file for operator review instead of direct change.
        const draft = { id: 'auto-curiosity-weight-'+Date.now(), params:{ CURIOSITY_GAIN_WEIGHT: Number(target.toFixed(4)) }, rationale: { avgCuriosity: Number(avgCuriosity.toFixed(6)), avgImagination: Number(avgImag.toFixed(6)) } };
        fs.appendFileSync(draftFile, JSON.stringify(draft)+'\n');
      }
    }
  } catch(_){ }
  // Regression diff & autonomy cycle
  try {
    if(summary.dimensionEscalation && summary.improvement){
      const baseline = { t:Date.now(), effectiveImprovement: summary.improvement.effectiveImprovement, sandbox: summary.sandbox, dimension: summary.dimension.current };
      fs.writeFileSync(path.join(ROOT,'regression-baseline.json'), JSON.stringify(baseline,null,2));
    }
    const regMod = safeRequire(REGRESSION_DIFF_MOD);
    if(regMod && typeof regMod.computeDiff === 'function'){
      const diffEntry = regMod.computeDiff();
      if(diffEntry){ summary.regressionDiff = diffEntry; }
    }
    const autoMod = safeRequire(AUTONOMY_ENGINE);
    if(autoMod && typeof autoMod.autonomousCycle === 'function'){
      const draft = autoMod.autonomousCycle();
      if(draft){ summary.autonomyDraft = { id: draft.id }; }
    }
  } catch(_){ }
  return summary;
}

if(require.main === module){
  const result = orchestrate();
  process.stdout.write(JSON.stringify(result,null,2)+'\n');
}

module.exports = { orchestrate };
