import React, { useState, useEffect, useRef } from 'react';
import { Activity, Terminal, BrainCircuit, RefreshCw, Compass, Search, Combine, Scale, MessageSquare, Network, ShieldCheck, ChevronRight, Cpu, Database, Layers, Hash } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { queryLegalCases } from '../lib/apiClient';

const ProgressDashboard = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const queryResult = location?.state?.queryResult;
  const queryText = location?.state?.queryText || '';
  
  // Restore from localStorage if navigating back without state
  const [apiResult, setApiResult] = useState(() => {
    if (queryResult) return queryResult;
    try {
      const saved = localStorage.getItem('verdicto_active_query');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });
  const [activeQueryText, setActiveQueryText] = useState(() => {
    if (queryText) return queryText;
    return localStorage.getItem('verdicto_active_query_text') || '';
  });
  const [apiError, setApiError] = useState(null);

  // Persist active query to localStorage whenever it changes
  useEffect(() => {
    if (apiResult?.query_id) {
      localStorage.setItem('verdicto_active_query', JSON.stringify(apiResult));
    }
  }, [apiResult]);
  useEffect(() => {
    if (queryText) {
      setActiveQueryText(queryText);
      localStorage.setItem('verdicto_active_query_text', queryText);
    }
  }, [queryText]);

  // If we already have results (e.g. from a completed query), redirect immediately
  useEffect(() => {
    if (apiResult?.status === 'complete') {
      const timer = setTimeout(async () => {
        // Fetch the final results using getQuery just in case
        try {
            const { getQuery } = await import('../lib/apiClient');
            const finalResult = await getQuery(apiResult.query_id);
            localStorage.removeItem('verdicto_active_query');
            navigate('/results', { state: { queryResult: finalResult, queryText: activeQueryText } });
        } catch (e) {
            localStorage.removeItem('verdicto_active_query');
            navigate('/results', { state: { queryResult: apiResult, queryText: activeQueryText } });
        }
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [apiResult?.status, apiResult?.query_id, activeQueryText, navigate]);

  useEffect(() => {
    if (!apiResult && activeQueryText) {
      queryLegalCases({ query: activeQueryText })
        .then(res => setApiResult(res))
        .catch(err => setApiError(err.message));
    }
  }, [activeQueryText, apiResult]);

  const [stage, setStage] = useState(0);
  const [centerTab, setCenterTab] = useState('logs');
  const [metaPage, setMetaPage] = useState(0);
  const META_PAGE_SIZE = 8;
  const bottomRef = useRef(null);

  // Poll backend status every 1.5 seconds
  useEffect(() => {
    if (!apiResult?.query_id || apiResult.status === 'complete') return;
    
    const interval = setInterval(async () => {
      try {
        const { getQueryStatus } = await import('../lib/apiClient');
        const statusData = await getQueryStatus(apiResult.query_id);
        
        // Merge trace updates into the component state
        setApiResult(prev => ({
          ...prev,
          status: statusData.status,
          processing_time_ms: statusData.processing_time_ms,
          agent_trace: statusData.agent_trace || prev?.agent_trace
        }));

        if (statusData.status === 'complete' || statusData.status === 'failed') {
          clearInterval(interval);
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 1500);
    
    return () => clearInterval(interval);
  }, [apiResult?.query_id, apiResult?.status]);

  // Determine stage dynamically from live trace
  useEffect(() => {
    if (!apiResult?.agent_trace) return;
    const trace = apiResult.agent_trace;
    const isDone = (key) => trace[key] && trace[key].status === 'complete';
    const isRunning = (key) => trace[key] && trace[key].status === 'in_progress';
    if (isDone('scheduler')) setStage(10);
    else if (isDone('debate') || isRunning('evaluator')) setStage(9);
    else if (isRunning('debate')) setStage(8);
    else if (isDone('precedent_weighting')) setStage(7);
    else if (isDone('retriever')) setStage(2);
    else if (isDone('query_planner')) setStage(1);
    else setStage(0);
  }, [apiResult?.agent_trace]);

  // auto scroll logs
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [stage, apiResult?.agent_trace]);

  const agents = {
    PLANNER: { color: 'var(--agent-planner)', icon: Compass, name: 'Planner' },
    RETRIEVER: { color: 'var(--agent-retriever)', icon: Search, name: 'Retriever' },
    SIMILARITY: { color: 'var(--agent-similarity)', icon: Combine, name: 'Similarity Engine' },
    WEIGHTING: { color: 'var(--agent-weighting)', icon: Scale, name: 'Precedent Weighting' },
    EVALUATOR: { color: 'var(--agent-evaluator)', icon: ShieldCheck, name: 'Evaluator' },
    DEBATER: { color: 'var(--agent-debate)', icon: MessageSquare, name: 'Debate Agent' },
    SCHEDULER: { color: 'var(--agent-scheduler)', icon: Network, name: 'Scheduler' }
  };

  // Map trace keys to agent tags for the timeline
  const traceKeyToTag = {
    query_planner: 'PLANNER',
    retriever: 'RETRIEVER',
    precedent_weighting: 'WEIGHTING',
    debate: 'DEBATER',
    evaluator: 'EVALUATOR',
    scheduler: 'SCHEDULER',
  };

  // Build real latency labels from live trace
  const getAgentTime = (traceKey) => {
    const entry = apiResult?.agent_trace?.[traceKey];
    if (!entry?.latency_ms) return null;
    const ms = entry.latency_ms;
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
  };

  const steps = [
    { tag: "PLANNER",   traceKey: "query_planner",       sIdx: 0 },
    { tag: "RETRIEVER", traceKey: "retriever",            sIdx: stage >= 5 ? 5 : 1 },
    { tag: "WEIGHTING", traceKey: "precedent_weighting",  sIdx: 7 },
    { tag: "DEBATER",   traceKey: "debate",               sIdx: 9 },
    { tag: "EVALUATOR", traceKey: "evaluator",            sIdx: 8 },
    { tag: "SCHEDULER", traceKey: "scheduler",            sIdx: 10 },
  ];
  
  // Determine current active agent from live trace (last incomplete step)
  // liveTrace is derived below — define it here first
  const liveTrace = apiResult?.agent_trace || {};

  let currentAgentTag = "PLANNER";
  const isDone = (key) => liveTrace[key]?.status === 'complete';
  const isRunning = (key) => liveTrace[key]?.status === 'in_progress';
  if (isDone('scheduler')) currentAgentTag = "SCHEDULER";
  else if (isRunning('scheduler')) currentAgentTag = "SCHEDULER";
  else if (isDone('evaluator')) currentAgentTag = "SCHEDULER";
  else if (isRunning('evaluator')) currentAgentTag = "EVALUATOR";
  else if (isDone('debate')) currentAgentTag = "EVALUATOR";
  else if (isRunning('debate')) currentAgentTag = "DEBATER";
  else if (isDone('precedent_weighting')) currentAgentTag = "DEBATER";
  else if (isDone('retriever')) currentAgentTag = "WEIGHTING";
  else if (isDone('query_planner')) currentAgentTag = "RETRIEVER";

  const renderLog = () => {
    const trace = apiResult?.agent_trace;

    // Always render from live trace when available
    if (trace && Object.keys(trace).length > 0) {
      // Ordered display sequence
      const displayOrder = ['query_planner', 'retriever', 'precedent_weighting', 'debate', 'evaluator', 'scheduler'];
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div className="log-block">
            <div style={{ color: 'var(--agent-planner)' }}>[INITIALIZING] Establishing pipeline...</div>
            <div>&gt; Query received: "{apiResult?.query_text || activeQueryText || '...'}"</div>
          </div>
          {displayOrder.map((traceKey) => {
            const entry = trace[traceKey];
            if (!entry) return null;
            const tag = traceKeyToTag[traceKey] || traceKey.toUpperCase();
            const agent = agents[tag] || { color: 'var(--primary)', name: traceKey };
            const isInProgress = entry.status === 'in_progress';
            const latencyLabel = isInProgress ? '...' : (
              entry.latency_ms >= 1000
                ? `${(entry.latency_ms / 1000).toFixed(2)}s`
                : `${Math.round(entry.latency_ms)}ms`
            );
            return (
              <div key={traceKey} className="log-block">
                <div style={{ color: agent.color }}>
                  [{agent.name.toUpperCase()}] {isInProgress ? 'RUNNING — LLM CALLS IN PROGRESS...' : (entry.status || 'complete').toUpperCase()}
                </div>
                {isInProgress
                  ? <div style={{ color: 'var(--on-surface-variant)' }}>&gt; Processing... (this may take 1-3 minutes per agent)</div>
                  : <div>&gt; Latency: {latencyLabel}</div>
                }
                {!isInProgress && entry.details && Object.entries(entry.details).map(([k, v], i) => {
                  if (typeof v === 'object' && v !== null && !Array.isArray(v)) return null; // skip nested objects
                  if (Array.isArray(v)) return null;
                  return <div key={i}>&gt; {k}: {String(v)}</div>;
                })}
              </div>
            );
          })}
          {apiResult?.status === 'complete' && (
            <div style={{ color: 'var(--secondary)', marginTop: '0.5rem' }}>
              &gt; Pipeline complete. Total time: {apiResult.processing_time_ms != null
                ? (apiResult.processing_time_ms >= 1000
                    ? `${(apiResult.processing_time_ms / 1000).toFixed(2)}s`
                    : `${apiResult.processing_time_ms}ms`)
                : '—'}.
            </div>
          )}
          {apiError && (
            <div style={{ color: 'var(--error)', padding: '1rem', border: '1px solid var(--error)', borderRadius: '4px' }}>
              <strong>BACKEND ERROR:</strong> {apiError}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      );
    }

    // No trace yet — show initializing state
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <div className="log-block">
          <div style={{ color: 'var(--agent-planner)' }}>[INITIALIZING] Establishing pipeline...</div>
          <div>&gt; Query received, orchestrating multi-agent system.</div>
          <div>&gt; Waiting for first agent response...</div>
        </div>
        {apiError && (
          <div style={{ color: 'var(--error)', padding: '1rem', border: '1px solid var(--error)', borderRadius: '4px' }}>
            <strong>BACKEND ERROR:</strong> {apiError}
            <div style={{ marginTop: '0.5rem', fontSize: '0.75rem' }}>Please ensure the FastAPI server is running on port 8000.</div>
          </div>
        )}
        <div style={{ color: agents[currentAgentTag]?.color || 'var(--primary)', marginTop: 'auto' }}>
          &gt; [EXECUTING: {currentAgentTag}]
        </div>
        <div ref={bottomRef} />
      </div>
    );
  };

  // Derive live orchestration values from trace instead of hardcoded stage math
  const liveEvalScore = liveTrace.evaluator?.details?.confidence != null
    ? liveTrace.evaluator.details.confidence.toFixed(3)
    : (stage < 2 ? '0.420' : stage < 4 ? '0.240' : stage < 7 ? '0.680' : stage < 10 ? '0.810' : '0.940');
  const liveIterations = liveTrace.scheduler?.details?.iterations ?? (stage < 4 ? 1 : stage < 9 ? 2 : 3);
  const liveMaxIter = 5;
  const liveNeedsRefinement = liveTrace.evaluator?.details?.needs_refinement ?? false;
  const liveDebateEnabled = liveTrace.scheduler?.details?.debate_enabled ?? true;
  const loopActive = liveNeedsRefinement && liveIterations > 1;
  const debateInProgress = liveTrace.debate?.status === 'in_progress';

  const nextNodeStrategy = () => {
    if (!liveTrace.query_planner) return 'Waiting for pipeline to start...';
    if (!liveTrace.retriever) return 'Query planned. Dispatching retriever to scan legal corpus.';
    if (!liveTrace.precedent_weighting) return 'Retrieval complete. Applying precedent authority weighting.';
    if (debateInProgress) return 'Adversarial debate in progress — LLM generating advocate & opposing arguments (may take 2-5 min).';
    if (!liveTrace.debate || liveTrace.debate.status !== 'complete') return liveDebateEnabled ? 'Weighting complete. Routing to adversarial debate node.' : 'Weighting complete. Debate disabled — routing to evaluator.';
    if (!liveTrace.evaluator || liveTrace.evaluator.status !== 'complete') return 'Debate concluded. Running evaluator for confidence scoring.';
    if (liveNeedsRefinement) return 'Low confidence detected. Scheduler re-routing for refinement pass.';
    if (!liveTrace.scheduler || liveTrace.scheduler.status !== 'complete') return 'Evaluation passed. Finalising consensus output.';
    return 'Pipeline complete. Consensus vector matrix ready for presentation.';
  };

  return (
    <div style={{ display: 'flex', gap: '2rem', height: '100%' }}>
      {/* Left Panel — Execution Timeline */}
      <div style={{ flex: '0 0 300px', display: 'flex', flexDirection: 'column' }}>
        <h3 className="newsreader" style={{ fontSize: '1.5rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={20} style={{ color: 'var(--secondary)' }}/> Execution Timeline
        </h3>
        
        <div style={{ position: 'relative', borderLeft: '1px solid var(--outline-variant-ghost)', marginLeft: '1.5rem', paddingLeft: '2rem', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          {steps.map((step, i) => {
             const IconComponent = agents[step.tag].icon;
             const traceEntry = apiResult?.agent_trace?.[step.traceKey];
             const isComplete = traceEntry?.status === 'complete';
             const isActive = traceEntry?.status === 'in_progress' || (!traceEntry && stage === step.sIdx);
             const isPending = !isComplete && !isActive;
             const realTime = traceEntry?.latency_ms != null
               ? (traceEntry.latency_ms >= 1000
                   ? `${(traceEntry.latency_ms / 1000).toFixed(1)}s`
                   : `${Math.round(traceEntry.latency_ms)}ms`)
               : null;

             let dynamicColor = agents[step.tag].color;

             return (
              <div key={i} style={{ position: 'relative', opacity: isPending ? 0.5 : 1 }}>
                <div style={{
                  position: 'absolute', left: '-44px', top: '-4px', width: '24px', height: '24px', backgroundColor: 'var(--surface)', color: isPending ? 'var(--on-surface-variant)' : dynamicColor, border: isActive ? `2px solid ${dynamicColor}` : `1px solid var(--outline-variant-ghost)`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: isActive ? `0 0 10px ${dynamicColor}` : (isComplete ? `0 0 4px ${dynamicColor}40` : 'none'), zIndex: 2
                }}>
                  <IconComponent size={14} />
                </div>
                <div style={{ fontSize: '0.75rem', color: isPending ? 'var(--on-surface-variant)' : dynamicColor, fontWeight: 700, letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {agents[step.tag].name}
                  {isComplete && realTime && <span style={{ fontSize: '0.65rem', color: 'var(--on-surface-variant)' }}>({realTime})</span>}
                </div>
                <div style={{ fontSize: '0.875rem', color: isPending ? 'var(--on-surface-variant)' : 'var(--on-surface)' }}>{isActive ? 'Processing...' : (isComplete ? 'Complete' : 'Pending')}</div>
              </div>
             );
          })}
        </div>
      </div>

      {/* Center Panel — Agent Activity Viewer */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem', position: 'relative' }}>
        <div style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid var(--outline-variant-ghost)', position: 'relative', zIndex: 10 }}>
          {[{ label: 'Execution Logs', key: 'logs' }, { label: 'Metadata Vectors', key: 'vectors' }].map((tab) => {
            const isActive = centerTab === tab.key;
            return (
              <div key={tab.key} onClick={() => setCenterTab(tab.key)} style={{ 
                padding: '0.75rem 1rem', fontSize: '0.875rem',
                color: isActive ? agents[currentAgentTag].color : 'var(--on-surface-variant)',
                borderBottom: isActive ? `2px solid ${agents[currentAgentTag].color}` : '2px solid transparent',
                cursor: 'pointer', fontWeight: isActive ? 600 : 400,
                transition: 'color 0.2s, border-color 0.2s',
              }}>
                {tab.label}
              </div>
            );
          })}
        </div>

        {/* Dynamic faint color bleed */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          background: `radial-gradient(circle at 50% 30%, ${agents[currentAgentTag].color}20, transparent 70%)`,
          pointerEvents: 'none', zIndex: 0, transition: 'background 0.5s ease'
        }} />

        {centerTab === 'logs' ? (
          <div className="insight-card scrollbar-hide" style={{ flex: 1, backgroundColor: 'var(--surface-container-lowest)', border: `1px solid ${agents[currentAgentTag].color}40`, borderRadius: '4px', padding: '1.5rem', fontFamily: 'monospace', fontSize: '0.875rem', lineHeight: 1.8, zIndex: 1, position: 'relative', color: 'var(--on-surface-variant)', display: 'flex', flexDirection: 'column', gap: '0.5rem', overflowY: 'auto' }}>
            {renderLog()}
            <div style={{ color: agents[currentAgentTag].color, marginTop: 'auto' }}>&gt; Executing neural trace... [RUNNING]</div>
          </div>
        ) : (
          /* ── Metadata Vectors Tab ── */
          <div className="insight-card scrollbar-hide" style={{ flex: 1, backgroundColor: 'var(--surface-container-lowest)', border: `1px solid ${agents[currentAgentTag].color}40`, borderRadius: '4px', padding: '1.5rem', zIndex: 1, position: 'relative', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {(() => {
              const retriever = liveTrace.retriever?.details;
              const candidates = retriever?.candidates || liveTrace.retriever?.candidates || [];
              const faissHits = retriever?.faiss_hits ?? liveTrace.retriever?.faiss_hits ?? null;
              const bm25Hits  = retriever?.bm25_hits  ?? liveTrace.retriever?.bm25_hits  ?? null;
              const afterRrf  = retriever?.after_rrf  ?? liveTrace.retriever?.after_rrf  ?? null;

              if (!liveTrace.retriever) {
                return (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, gap: '0.75rem', color: 'var(--on-surface-variant)', opacity: 0.6 }}>
                    <Layers size={32} />
                    <span style={{ fontSize: '0.875rem' }}>Waiting for retriever to populate vector data…</span>
                  </div>
                );
              }

              const totalPages = Math.ceil(candidates.length / META_PAGE_SIZE);
              const pageSlice  = candidates.slice(metaPage * META_PAGE_SIZE, (metaPage + 1) * META_PAGE_SIZE);

              // Normalise scores to [0,1] for bar widths
              const maxRrf   = candidates.length ? Math.max(...candidates.map(c => c.rrf_score   || 0)) : 1;
              const maxFaiss = candidates.length ? Math.max(...candidates.map(c => c.faiss_score || 0)) : 1;
              const maxBm25  = candidates.length ? Math.max(...candidates.map(c => c.bm25_score  || 0)) : 1;

              return (
                <>
                  {/* Summary row */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
                    {[
                      { label: 'FAISS HITS',    value: faissHits ?? '—', icon: <Cpu size={14}/>,      color: 'var(--agent-retriever)' },
                      { label: 'BM25 HITS',     value: bm25Hits  ?? '—', icon: <Hash size={14}/>,     color: 'var(--agent-planner)'   },
                      { label: 'AFTER RRF',     value: afterRrf ?? (candidates.length || '—'), icon: <Layers size={14}/>, color: 'var(--secondary)' },
                    ].map(({ label, value, icon, color }) => (
                      <div key={label} style={{ backgroundColor: 'var(--surface-container)', borderRadius: '4px', padding: '0.75rem 1rem', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <span style={{ fontSize: '0.65rem', color: 'var(--on-surface-variant)', letterSpacing: '0.08em', display: 'flex', alignItems: 'center', gap: '4px' }}>{icon} {label}</span>
                        <span style={{ fontSize: '1.25rem', fontFamily: 'monospace', fontWeight: 700, color }}>{value}</span>
                      </div>
                    ))}
                  </div>

                  {/* Candidate table */}
                  {candidates.length > 0 ? (
                    <>
                      <div style={{ fontSize: '0.7rem', color: 'var(--on-surface-variant)', letterSpacing: '0.06em', marginTop: '0.25rem' }}>
                        CANDIDATE VECTORS — {candidates.length} total, showing {metaPage * META_PAGE_SIZE + 1}–{Math.min((metaPage + 1) * META_PAGE_SIZE, candidates.length)}
                      </div>

                      {/* Column headers */}
                      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: '0.5rem', fontSize: '0.65rem', color: 'var(--on-surface-variant)', letterSpacing: '0.06em', padding: '0 0.25rem' }}>
                        <span>CASE ID</span><span>RRF</span><span>FAISS</span><span>BM25</span>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                        {pageSlice.map((c, idx) => {
                          const rank = metaPage * META_PAGE_SIZE + idx + 1;
                          const rrfPct   = maxRrf   > 0 ? (c.rrf_score   || 0) / maxRrf   * 100 : 0;
                          const faissPct = maxFaiss > 0 ? (c.faiss_score || 0) / maxFaiss * 100 : 0;
                          const bm25Pct  = maxBm25  > 0 ? (c.bm25_score  || 0) / maxBm25  * 100 : 0;
                          return (
                            <div key={c.case_id} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: '0.5rem', alignItems: 'center', padding: '0.4rem 0.25rem', borderBottom: '1px solid var(--surface-container)', fontSize: '0.8rem' }}>
                              <span style={{ fontFamily: 'monospace', color: 'var(--on-surface)', fontSize: '0.75rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.case_id}>
                                <span style={{ color: 'var(--on-surface-variant)', marginRight: '6px' }}>#{rank}</span>{c.case_id}
                              </span>
                              {[
                                { val: c.rrf_score,   pct: rrfPct,   color: 'var(--secondary)'         },
                                { val: c.faiss_score, pct: faissPct, color: 'var(--agent-retriever)'   },
                                { val: c.bm25_score,  pct: bm25Pct,  color: 'var(--agent-planner)'     },
                              ].map(({ val, pct, color }, si) => (
                                <div key={si} style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                  <span style={{ fontFamily: 'monospace', fontSize: '0.7rem', color }}>{val != null ? val.toFixed(4) : '—'}</span>
                                  <div style={{ height: '3px', backgroundColor: 'var(--surface-container)', borderRadius: '2px', overflow: 'hidden' }}>
                                    <div style={{ height: '100%', width: `${pct}%`, backgroundColor: color, borderRadius: '2px', transition: 'width 0.4s ease' }} />
                                  </div>
                                </div>
                              ))}
                            </div>
                          );
                        })}
                      </div>

                      {/* Pagination */}
                      {totalPages > 1 && (
                        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
                          <button onClick={() => setMetaPage(p => Math.max(0, p - 1))} disabled={metaPage === 0}
                            style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem', backgroundColor: 'var(--surface-container)', border: '1px solid var(--outline-variant-ghost)', borderRadius: '4px', color: 'var(--on-surface)', cursor: metaPage === 0 ? 'not-allowed' : 'pointer', opacity: metaPage === 0 ? 0.4 : 1 }}>
                            ← Prev
                          </button>
                          <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', alignSelf: 'center' }}>{metaPage + 1} / {totalPages}</span>
                          <button onClick={() => setMetaPage(p => Math.min(totalPages - 1, p + 1))} disabled={metaPage === totalPages - 1}
                            style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem', backgroundColor: 'var(--surface-container)', border: '1px solid var(--outline-variant-ghost)', borderRadius: '4px', color: 'var(--on-surface)', cursor: metaPage === totalPages - 1 ? 'not-allowed' : 'pointer', opacity: metaPage === totalPages - 1 ? 0.4 : 1 }}>
                            Next →
                          </button>
                        </div>
                      )}
                    </>
                  ) : (
                    <div style={{ color: 'var(--on-surface-variant)', fontSize: '0.875rem', opacity: 0.7, textAlign: 'center', marginTop: '1rem' }}>
                      Retriever ran but returned no candidate vectors.
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        )}
      </div>

      {/* Right Panel — Scheduler State Visualization */}
      <div style={{ flex: '0 0 350px', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
        <div className="insight-card" style={{ padding: '1.5rem', backgroundColor: 'var(--surface-container)', border: loopActive ? '1px solid var(--agent-scheduler)' : '1px solid transparent', transition: 'border 0.3s ease' }}>
          <h3 className="newsreader" style={{ fontSize: '1.5rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
             <Network size={20} style={{ color: 'var(--agent-scheduler)' }}/> Orchestration Logic
          </h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--surface-container-lowest)', paddingBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>EVALUATOR SCORE</span>
              <span style={{ fontSize: '1.125rem', fontFamily: 'monospace', color: liveNeedsRefinement ? 'var(--error)' : 'var(--agent-evaluator)', fontWeight: 700, transition: 'color 0.3s' }}>{liveEvalScore}</span>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--surface-container-lowest)', paddingBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>DEBATE ENABLED</span>
              <span style={{ fontSize: '1rem', fontFamily: 'monospace', color: 'var(--on-surface)', transition: 'color 0.3s' }}>{liveDebateEnabled ? 'Yes' : 'No'}</span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--surface-container-lowest)', paddingBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>SYSTEM FLAG</span>
              <span style={{ fontSize: '0.875rem', color: liveNeedsRefinement ? 'var(--error)' : 'var(--on-surface-variant)', fontWeight: liveNeedsRefinement ? 700 : 400 }}>
                {liveNeedsRefinement ? 'Refinement Required' : (liveTrace.scheduler ? 'Converged' : 'Dormant')}
              </span>
            </div>
            
            <div style={{ backgroundColor: 'var(--surface-container-lowest)', padding: '1rem', marginTop: '1rem', borderLeft: `3px solid ${agents[currentAgentTag].color}`, transition: 'border-color 0.3s' }}>
              <span style={{ fontSize: '0.65rem', color: agents[currentAgentTag].color, fontWeight: 700, display: 'block', marginBottom: '4px' }}>NEXT NODE STRATEGY</span>
              <span style={{ fontSize: '0.875rem', color: 'var(--on-surface)' }}>{nextNodeStrategy()}</span>
            </div>
          </div>
        </div>

        <div className="insight-card" style={{ padding: '1.5rem', backgroundColor: 'var(--surface-container-low)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>Iteration Progress</span>
            <RefreshCw size={16} className={apiResult?.status !== 'complete' ? "spin-slow" : ""} style={{ color: 'var(--secondary)' }}/>
          </div>
          <div style={{ height: '6px', width: '100%', backgroundColor: 'var(--surface-container-lowest)', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${Math.min(100, (liveIterations / liveMaxIter) * 100)}%`, backgroundColor: 'var(--primary)', transition: 'width 2s ease' }}></div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--primary)' }}>Cycle: {liveIterations}</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>Limit: {liveMaxIter}</span>
          </div>
        </div>
      </div>
      <style>{`
        @keyframes spin-slow { 100% { transform: rotate(360deg); } }
        .spin-slow { animation: spin-slow 2s linear infinite; }
        .scrollbar-hide::-webkit-scrollbar { display: none; }
        .scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }
      `}</style>
    </div>
  );
};

export default ProgressDashboard;
