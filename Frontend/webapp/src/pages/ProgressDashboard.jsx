import React, { useState, useEffect, useRef } from 'react';
import { Activity, Terminal, BrainCircuit, RefreshCw, Compass, Search, Combine, Scale, MessageSquare, Network, ShieldCheck, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const ProgressDashboard = () => {
  const navigate = useNavigate();
  const [stage, setStage] = useState(0); 
  const bottomRef = useRef(null);

  // Dynamic simulation timeline with a loop
  useEffect(() => {
    const sequence = [
      { t: 0, s: 0 },         // 0: Planner
      { t: 6500, s: 1 },      // 1: Retriever (Pass 1)
      { t: 13000, s: 2 },     // 2: Similarity (Pass 1: insufficient)
      { t: 19500, s: 3 },     // 3: Evaluator catches issue
      { t: 26000, s: 4 },     // 4: Scheduler identifies loop -> requests broader search
      { t: 32500, s: 5 },     // 5: Retriever (Pass 2)
      { t: 39000, s: 6 },     // 6: Similarity (Pass 2)
      { t: 45500, s: 7 },     // 7: Weighting 
      { t: 52000, s: 8 },     // 8: Evaluator logs variance -> triggered
      { t: 58500, s: 9 },     // 9: Debater
      { t: 65000, s: 10 },    // 10: Scheduler resolves
      { t: 71500, s: 11 },    // 11: End (push to Results)
    ];
    
    let timeouts = sequence.map(event => {
       return setTimeout(() => {
          if (event.s === 11) navigate('/results');
          else setStage(event.s);
       }, event.t);
    });
    
    return () => timeouts.forEach(clearTimeout);
  }, [navigate]);
  
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
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {stage >= 0 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-planner)' }}>[PLANNER] Execution Start...</div>
            <div>&gt; Decomposing arbitration & stamp act vectors...</div>
            <div>&gt; Identifying target statute: Arbitration Act 1996 Sec 11...</div>
          </div>
        )}
        {stage >= 1 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-retriever)' }}>[RETRIEVER] Scanning High Court Corpus...</div>
            <div>&gt; Query: `Section 11 unstamped arbitration clause validity`</div>
            <div>&gt; Found 12 relevant High Court cases. Extracting Top-3.</div>
          </div>
        )}
        {stage >= 2 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-similarity)' }}>[SIMILARITY] Factual Node Mapping...</div>
            <div>&gt; HC Precedents mapped. Confidence score: 0.42...</div>
          </div>
        )}
        {stage >= 3 && (
          <div className="log-block" style={{ borderLeft: '2px solid var(--error)', paddingLeft: '8px' }}>
            <div style={{ color: 'var(--agent-evaluator)' }}>[EVALUATOR] Structural Integrity Check...</div>
            <div style={{ color: 'var(--error)' }}>&gt; ERROR: Crucial jurisdictional mismatch detected.</div>
            <div>&gt; Input requires Indian Supreme Court precedents, only High Court data fetched.</div>
            <div>&gt; Raising fatal flag. Haulting linear pipeline.</div>
          </div>
        )}
        {stage >= 4 && (
          <div className="log-block" style={{ borderLeft: '2px solid var(--agent-scheduler)', paddingLeft: '8px', background: 'rgba(157, 126, 219, 0.05)' }}>
             <div style={{ color: 'var(--agent-scheduler)' }}>[SCHEDULER] Self-Correction Triggered...</div>
             <div>&gt; Rerouting task explicitly to Retriever Agent.</div>
             <div style={{ color: 'var(--agent-scheduler)' }}>&gt; UPDATED COMMAND: "Expand vector limits to strictly enforce Supreme Court registry."</div>
             <div>&gt; Iteration Cycle 2 Initialized.</div>
          </div>
        )}
        {stage >= 5 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-retriever)' }}>[RETRIEVER] Scanning Supreme Court Corpus (Pass 2)...</div>
            <div>&gt; Query: `Supreme Court Section 11 Stamp Act invalidity -HC`</div>
            <div>&gt; Found 32 strictly matching cases. Extracting Top-K (K=5).</div>
            <div>&gt; Ranked matches: NN Global (2023), SMS Tea (2011), In Re: Interplay (2023).</div>
          </div>
        )}
        {stage >= 6 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-similarity)' }}>[SIMILARITY] Factual Node Mapping (Pass 2)...</div>
            <div>&gt; NN Global (2023) - 98% factual match.</div>
            <div>&gt; In Re: Interplay (2023) - 97% factual match.</div>
          </div>
        )}
        {stage >= 7 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-weighting)' }}>[WEIGHTING] Hierarchical Graph Traversal...</div>
            <div style={{ color: 'var(--error)' }}>[WARNING] Conflicting precedent chains detected.</div>
            <div>&gt; NN Global (5-Judge Bench) vs In Re: Interplay (7-Judge Bench).</div>
          </div>
        )}
        {stage >= 8 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-evaluator)' }}>[EVALUATOR] Variance Inspection...</div>
            <div>&gt; Similarity Variance = 0.81 (Threshold &gt; 0.3)</div>
            <div>&gt; Direct contradiction in Top-2 precedents. Routing to Debate.</div>
          </div>
        )}
        {stage >= 9 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-debate)' }}>[DEBATER] Constructive vs Adversarial Instantiation...</div>
            <div>&gt; [Agent A] Claim: Rely on NN Global — uncurable defect.</div>
            <div>&gt; [Agent B] Rebuttal: In Re: Interplay is larger bench. Separability rule.</div>
            <div>&gt; Running Synthesis Round...</div>
          </div>
        )}
        {stage >= 10 && (
          <div className="log-block">
            <div style={{ color: 'var(--agent-scheduler)' }}>[SCHEDULER] Convergence Achieved.</div>
            <div>&gt; Debate resolved in favor of In Re: Interplay.</div>
            <div>&gt; Evaluator Variance drops to 0.12. Finalizing output.</div>
          </div>
        )}
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
