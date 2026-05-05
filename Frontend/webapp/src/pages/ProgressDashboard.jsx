import React, { useState, useEffect, useRef } from 'react';
import { Activity, Terminal, BrainCircuit, RefreshCw, Compass, Search, Combine, Scale, MessageSquare, Network, ShieldCheck, ChevronRight } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { queryLegalCases } from '../lib/apiClient';

const ProgressDashboard = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const queryResult = location?.state?.queryResult;
  const queryText = location?.state?.queryText || '';
  const [apiResult, setApiResult] = useState(queryResult || null);
  const [apiError, setApiError] = useState(null);
  
  // If we already have results (e.g. from a completed query), redirect immediately
  useEffect(() => {
    if (apiResult) {
      const timer = setTimeout(() => {
        navigate('/results', { state: { queryResult: apiResult, queryText } });
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [apiResult, queryText, navigate]);

  useEffect(() => {
    if (!apiResult && queryText) {
      queryLegalCases({ query: queryText })
        .then(res => setApiResult(res))
        .catch(err => setApiError(err.message));
    }
  }, [queryText, apiResult]);

  const [stage, setStage] = useState(0); 
  const bottomRef = useRef(null);

  // Dynamic simulation timeline with a loop
  useEffect(() => {
    if (apiResult) return; // Don't start simulation if we already have results

    const sequence = [
      { t: 0, s: 0 },         // 0: Planner
      { t: 2500, s: 1 },      // 1: Retriever (Pass 1)
      { t: 5000, s: 2 },      // 2: Similarity (Pass 1)
      { t: 7500, s: 3 },      // 3: Evaluator catches issue
      { t: 10000, s: 4 },     // 4: Scheduler identifies loop
      { t: 12500, s: 5 },     // 5: Retriever (Pass 2)
      { t: 15000, s: 6 },     // 6: Similarity (Pass 2)
      { t: 17500, s: 7 },     // 7: Weighting 
      { t: 20000, s: 8 },     // 8: Evaluator
      { t: 22500, s: 9 },     // 9: Debater
      { t: 25000, s: 10 },    // 10: Scheduler resolves
    ];
    
    let timeouts = sequence.map(event => {
       return setTimeout(() => {
          if (!apiResult) {
            setStage(event.s);
          }
       }, event.t);
    });
    
    return () => timeouts.forEach(clearTimeout);
  }, [apiResult]);
  
  // auto scroll logs
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [stage]);

  const agents = {
    PLANNER: { color: 'var(--agent-planner)', icon: Compass, name: 'Planner' },
    RETRIEVER: { color: 'var(--agent-retriever)', icon: Search, name: 'Retriever' },
    SIMILARITY: { color: 'var(--agent-similarity)', icon: Combine, name: 'Similarity Engine' },
    WEIGHTING: { color: 'var(--agent-weighting)', icon: Scale, name: 'Precedent Weighting' },
    EVALUATOR: { color: 'var(--agent-evaluator)', icon: ShieldCheck, name: 'Evaluator' },
    DEBATER: { color: 'var(--agent-debate)', icon: MessageSquare, name: 'Debate Agent' },
    SCHEDULER: { color: 'var(--agent-scheduler)', icon: Network, name: 'Scheduler' }
  };

  const steps = [
    { tag: "PLANNER", time: "6.5s", sIdx: 0 },
    { tag: "RETRIEVER", time: "6.5s", sIdx: stage >= 5 ? 5 : 1 },
    { tag: "SIMILARITY", time: "6.5s", sIdx: stage >= 6 ? 6 : 2 },
    { tag: "WEIGHTING", time: "6.5s", sIdx: 7 },
    { tag: "EVALUATOR", time: "6.5s", sIdx: 8 },
    { tag: "DEBATER", time: "6.5s", sIdx: 9 },
    { tag: "SCHEDULER", time: "Current", sIdx: 10 }
  ];
  
  // Helper to determine what is currently running
  let currentAgentTag = "PLANNER";
  if (stage === 1 || stage === 5) currentAgentTag = "RETRIEVER";
  if (stage === 2 || stage === 6) currentAgentTag = "SIMILARITY";
  if (stage === 3 || stage === 8) currentAgentTag = "EVALUATOR";
  if (stage === 4 || stage === 10) currentAgentTag = "SCHEDULER";
  if (stage === 7) currentAgentTag = "WEIGHTING";
  if (stage === 9) currentAgentTag = "DEBATER";

  const renderLog = () => {
    if (apiResult?.agent_trace) {
      const trace = apiResult.agent_trace;
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {Object.entries(trace).map(([agentKey, entry], idx) => {
            if (!entry) return null;
            const agent = agents[agentKey.toUpperCase()] || { color: 'var(--primary)', name: agentKey };
            return (
              <div key={idx} className="log-block">
                <div style={{ color: agent.color }}>[{agent.name.toUpperCase()}] {entry.status.toUpperCase()}</div>
                <div>&gt; Latency: {entry.latency_ms.toFixed(0)}ms</div>
                {entry.details && Object.entries(entry.details).map(([k, v], i) => (
                  <div key={i}>&gt; {k}: {typeof v === 'object' ? JSON.stringify(v).substring(0, 100) : String(v)}</div>
                ))}
              </div>
            );
          })}
          <div style={{ color: 'var(--secondary)', marginTop: '1rem' }}>&gt; Final consensus reached in {apiResult.processing_time_ms}ms.</div>
          <div ref={bottomRef} />
        </div>
      );
    }

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {stage >= 0 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-planner)' }}>[PLANNER] Execution Start...</div>
            <div>&gt; Decomposing query vectors...</div>
            <div>&gt; Identifying target statutes: {queryText.toLowerCase().includes('stamp') ? 'Stamp Act, ' : ''} Arbitration Act...</div>
          </div>
        )}
        {stage >= 1 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-retriever)' }}>[RETRIEVER] Scanning Legal Corpus...</div>
            <div>&gt; Query: `{queryText.substring(0, 50)}...`</div>
            <div>&gt; Searching for relevant precedents...</div>
          </div>
        )}
        {stage >= 2 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-similarity)' }}>[SIMILARITY] Factual Node Mapping...</div>
            <div>&gt; Mapping input facts to vector space...</div>
          </div>
        )}
        {stage >= 7 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-weighting)' }}>[WEIGHTING] Hierarchical Graph Traversal...</div>
            <div>&gt; Calculating authoritative weights...</div>
          </div>
        )}
        {stage >= 8 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-evaluator)' }}>[EVALUATOR] Structural Integrity Check...</div>
            <div>&gt; Verifying jurisprudential consistency...</div>
          </div>
        )}
        {apiError && (
           <div style={{ color: 'var(--error)', padding: '1rem', border: '1px solid var(--error)', borderRadius: '4px' }}>
             <strong>BACKEND ERROR:</strong> {apiError}
             <div style={{ marginTop: '0.5rem', fontSize: '0.75rem' }}>Please ensure the FastAPI server is running on port 8000.</div>
           </div>
        )}
        <div style={{ color: agents[currentAgentTag]?.color || 'var(--primary)', marginTop: 'auto' }}>
          &gt; {apiResult ? '[ANALYSIS COMPLETE]' : `[EXECUTING: ${currentAgentTag}]`}
        </div>
        <div ref={bottomRef} />
      </div>
    );
  };

  const score = stage < 2 ? '0.420' : stage < 4 ? '0.240' : stage < 7 ? '0.680' : stage < 10 ? '0.810' : '0.940';
  const iter = stage < 4 ? 1 : stage < 9 ? 2 : 3;
  const loopActive = stage >= 4 && stage <= 6;

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
             const isComplete = stage > step.sIdx || (loopActive && i < 2); // visually messy but workable for demo
             const isActive = stage === step.sIdx || (stage === 1 && i===1) || (stage === 2 && i===2);
             const isPending = stage < step.sIdx && !isActive && !isComplete;
             
             let dynamicColor = agents[step.tag].color;
             if (loopActive && (i === 1 || i === 2)) dynamicColor = 'var(--agent-scheduler)'; // highlight the loop

             return (
              <div key={i} style={{ position: 'relative', opacity: isPending ? 0.5 : 1 }}>
                <div style={{
                  position: 'absolute', left: '-44px', top: '-4px', width: '24px', height: '24px', backgroundColor: 'var(--surface)', color: isPending ? 'var(--on-surface-variant)' : dynamicColor, border: isActive ? `2px solid ${dynamicColor}` : `1px solid var(--outline-variant-ghost)`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: isActive ? `0 0 10px ${dynamicColor}` : (isComplete ? `0 0 4px ${dynamicColor}40` : 'none'), zIndex: 2
                }}>
                  <IconComponent size={14} />
                </div>
                <div style={{ fontSize: '0.75rem', color: isPending ? 'var(--on-surface-variant)' : dynamicColor, fontWeight: 700, letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {agents[step.tag].name} {loopActive && (i===1||i===2) && "(Pass 2)"}
                  {isComplete && !isActive && <span style={{ fontSize: '0.65rem', color: 'var(--on-surface-variant)' }}>({step.time})</span>}
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
          {['Execution Logs', 'Metadata Vectors'].map((tab, i) => (
            <div key={i} style={{ 
              padding: '0.75rem 1rem', fontSize: '0.875rem', color: i === 0 ? agents[currentAgentTag].color : 'var(--on-surface-variant)', borderBottom: i === 0 ? `2px solid ${agents[currentAgentTag].color}` : '2px solid transparent', cursor: 'pointer', fontWeight: i === 0 ? 600 : 400
            }}>
              {tab}
            </div>
          ))}
        </div>

        {/* Dynamic faint color bleed */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          background: `radial-gradient(circle at 50% 30%, ${agents[currentAgentTag].color}20, transparent 70%)`,
          pointerEvents: 'none', zIndex: 0, transition: 'background 0.5s ease'
        }} />

        <div className="insight-card scrollbar-hide" style={{ flex: 1, backgroundColor: 'var(--surface-container-lowest)', border: `1px solid ${agents[currentAgentTag].color}40`, borderRadius: '4px', padding: '1.5rem', fontFamily: 'monospace', fontSize: '0.875rem', lineHeight: 1.8, zIndex: 1, position: 'relative', color: 'var(--on-surface-variant)', display: 'flex', flexDirection: 'column', gap: '0.5rem', overflowY: 'auto' }}>
          {renderLog()}
          <div style={{ color: agents[currentAgentTag].color, marginTop: 'auto' }}>&gt; Executing neural trace... [RUNNING]</div>
        </div>
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
              <span style={{ fontSize: '1.125rem', fontFamily: 'monospace', color: stage === 3 ? 'var(--error)' : 'var(--agent-evaluator)', fontWeight: 700, transition: 'color 0.3s' }}>{score}</span>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--surface-container-lowest)', paddingBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>SIMILARITY VARIANCE</span>
              <span style={{ fontSize: '1rem', fontFamily: 'monospace', color: stage >= 8 && stage <= 9 ? 'var(--error)' : 'var(--on-surface)', transition: 'color 0.3s' }}>{stage < 8 ? 'Low (0.12)' : stage >= 8 && stage <= 9 ? 'High (0.81)' : 'Stable (0.12)'}</span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--surface-container-lowest)', paddingBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>SYSTEM FLAG</span>
              <span style={{ fontSize: '0.875rem', color: stage === 3 ? 'var(--error)' : stage >= 8 && stage <= 9 ? 'var(--error)' : 'var(--on-surface-variant)', fontWeight: (stage === 3 || (stage >= 8 && stage <= 9)) ? 700 : 400 }}>{stage === 3 ? 'Context Miss' : stage >= 8 && stage <= 9 ? 'Debate Triggered' : 'Dormant'}</span>
            </div>
            
            <div style={{ backgroundColor: 'var(--surface-container-lowest)', padding: '1rem', marginTop: '1rem', borderLeft: `3px solid ${agents[currentAgentTag].color}`, transition: 'border-color 0.3s' }}>
              <span style={{ fontSize: '0.65rem', color: agents[currentAgentTag].color, fontWeight: 700, display: 'block', marginBottom: '4px' }}>NEXT NODE STRATEGY</span>
              <span style={{ fontSize: '0.875rem', color: 'var(--on-surface)' }}>
                 {stage < 3 ? "Linear pipeline execution under active progression." : stage === 3 ? "Pipeline haluted. Rerouting to Scheduler for explicit command generation." : stage < 7 ? "Self-corrected loop pass 2 running." : stage < 10 ? "Routing to Debate Node due to fatal jurisprudential conflict." : "Finalizing consensus vector matrix for output presentation."}
              </span>
            </div>
          </div>
        </div>

        <div className="insight-card" style={{ padding: '1.5rem', backgroundColor: 'var(--surface-container-low)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>Iteration Progress</span>
            <RefreshCw size={16} className={stage < 11 ? "spin-slow" : ""} style={{ color: 'var(--secondary)' }}/>
          </div>
          <div style={{ height: '6px', width: '100%', backgroundColor: 'var(--surface-container-lowest)', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: iter === 1 ? '10%' : iter === 2 ? '50%' : '100%', backgroundColor: 'var(--primary)', transition: 'width 2s ease' }}></div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--primary)' }}>Cycle: {iter}</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>Limit: 5</span>
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
