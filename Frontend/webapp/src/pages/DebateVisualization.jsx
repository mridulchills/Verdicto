import React, { useState } from 'react';
import { Network, Users, CheckCircle2 } from 'lucide-react';

const DebateVisualization = () => {
  const [activeTab, setActiveTab] = useState('round1');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', height: '100%', position: 'relative' }}>
      
      {/* Header and Timeline Navigation */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="newsreader" style={{ fontSize: '2rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Network size={24} style={{ color: 'var(--agent-scheduler)' }}/> Multi-Agent Debate Simulation
        </h2>
        
        <div style={{ display: 'flex', gap: '0.5rem', backgroundColor: 'var(--surface-container)', padding: '0.5rem', borderRadius: '0.5rem' }}>
          {['round1', 'round2', 'round3'].map((tab, idx) => (
            <button key={tab} 
              onClick={() => setActiveTab(tab)}
              className={activeTab === tab ? 'btn-primary' : 'btn-secondary'} 
              style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '8px', border: 'none', margin: 0 }}
            >
              {idx === 0 && 'Round I: Claims'}
              {idx === 1 && 'Round II: Rebuttals'}
              {idx === 2 && 'Round III: Synthesis'}
            </button>
          ))}
        </div>
      </div>

      {/* Debate Confidence Flow Chart */}
      <div className="insight-card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--surface-container)' }}>
        <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--on-surface-variant)', marginBottom: '1rem', letterSpacing: '0.05em' }}>DEBATE CONFIDENCE FLOW</div>
        
        <div style={{ height: '80px', width: '100%', position: 'relative', borderLeft: '1px solid var(--outline-variant-ghost)', borderBottom: '1px solid var(--outline-variant-ghost)', display: 'flex' }}>
          
          <div style={{ flex: 1, position: 'relative' }}>
             <div style={{ position: 'absolute', bottom: '-20px', left: '0', fontSize: '0.65rem', color: 'var(--on-surface-variant)' }}>Round I</div>
             <div style={{ position: 'absolute', bottom: '-20px', left: '50%', transform: 'translateX(-50%)', fontSize: '0.65rem', color: 'var(--on-surface-variant)' }}>Round II</div>
             <div style={{ position: 'absolute', bottom: '-20px', right: '0', fontSize: '0.65rem', color: 'var(--on-surface-variant)' }}>Round III</div>
             
             {/* Chart Viewport */}
             <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none" style={{ overflow: 'visible' }}>
                {/* Agent Retriever (Teal) */}
                <path d="M 0 28 L 50 39 L 100 22" fill="none" stroke="var(--agent-retriever)" strokeWidth="2" strokeDasharray="4 2" />
                <circle cx="0" cy="28" r="3" fill="var(--agent-retriever)" />
                <circle cx="50" cy="39" r="3" fill="var(--agent-retriever)" />
                <circle cx="100" cy="22" r="3" fill="var(--agent-retriever)" />

                {/* Agent Similarity (Amber) - Dips heavily in Round 2, recovers in Round 3 */}
                <path d="M 0 50 L 50 80 L 100 30" fill="none" stroke="var(--agent-similarity)" strokeWidth="2" strokeDasharray="4 2" />
                <circle cx="0" cy="50" r="3" fill="var(--agent-similarity)" />
                <circle cx="50" cy="80" r="3" fill="var(--agent-similarity)" />
                <circle cx="100" cy="30" r="3" fill="var(--agent-similarity)" />

                {/* Precedent Weighting (Gold) - Rises steadily as Constitutional Bench is found */}
                <path d="M 0 40 L 50 15 L 100 5" fill="none" stroke="var(--agent-weighting)" strokeWidth="3" />
                <circle cx="0" cy="40" r="4" fill="var(--agent-weighting)" />
                <circle cx="50" cy="15" r="4" fill="var(--agent-weighting)" />
                <circle cx="100" cy="5" r="4" fill="var(--agent-weighting)" />
             </svg>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingLeft: '2rem', justifyContent: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', color: 'var(--on-surface)' }}>
               <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--agent-weighting)' }}></div> Precedent Weighting (Converged: 0.95)
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', color: 'var(--on-surface)' }}>
               <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--agent-retriever)' }}></div> Retriever Agent (0.78)
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', color: 'var(--on-surface)' }}>
               <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--agent-similarity)' }}></div> Similarity Engine (0.70)
            </div>
          </div>
        </div>
      </div>

      {/* Debate Flow Timeline Cards */}
      <div style={{ flex: 1, display: 'flex', gap: '2rem', marginTop: '1rem' }}>
        
        {/* Left Side — Agent 1 */}
        <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container-highest)', display: 'flex', flexDirection: 'column', borderLeft: '4px solid var(--agent-planner)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)', paddingBottom: '1rem' }}>
            <div style={{ width: '40px', height: '40px', borderRadius: '50%', backgroundColor: 'rgba(70, 130, 180, 0.2)', display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'var(--agent-planner)', fontWeight: 'bold', border: '1px solid var(--agent-planner)' }}>A1</div>
            <div>
              <div style={{ fontSize: '1.125rem', fontFamily: 'Newsreader', color: 'var(--on-surface)' }}>Respondent Agent (Adversarial)</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--agent-planner)' }}>Confidence: 94%</div>
            </div>
          </div>
          
          <div style={{ flex: 1, overflowY: 'auto', paddingRight: '1rem' }}>
            {activeTab === 'round1' && (
              <div className="shimmer">
                <p className="body-md"><strong>CLAIM:</strong> The underlying construction sub-contract is entirely unstamped under the Indian Stamp Act, 1899. Consequently, the embedded arbitration clause perishes with the main contract, and the Court cannot appoint an arbitrator under Section 11.</p>
                <div style={{ margin: '1rem 0', paddingLeft: '1rem', borderLeft: `2px solid var(--agent-planner)` }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', display: 'block' }}>RELIANCE ON PRECEDENT</span>
                  <span style={{ fontSize: '0.875rem' }}>NN Global Mercantile v. Indo Unique Flame (2023) 5-Judge</span>
                </div>
              </div>
            )}
            {activeTab === 'round2' && (
              <div>
                <p className="body-md"><strong>REBUTTAL:</strong> The doctrine of separability cannot insulate the arbitration provision from a fundamental fiscal deficiency that renders the contract legally non-est in the eyes of Section 33 of the Stamp Act.</p>
              </div>
            )}
            {activeTab === 'round3' && (
              <div style={{ opacity: 0.5 }}>
                <p className="body-md"><strong>CONCEDING STANCE:</strong> Agent A recalculates jurisprudential hierarchy. Acknowledging that a 7-Judge constitutional bench explicitly overruled NN Global. Curative petition prioritizes party autonomy over fiscal technicality at pre-arbitral reference stage.</p>
              </div>
            )}
          </div>
        </div>

        {/* Center — Conflict Marker */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--tertiary)' }}>
          <div style={{ height: '30%', width: '1px', backgroundColor: 'var(--outline-variant-ghost)' }}></div>
          <Users size={32} style={{ margin: '1rem 0', color: 'var(--agent-debate)' }} />
          {activeTab === 'round3' && <CheckCircle2 size={32} style={{ color: 'var(--agent-evaluator)', filter: 'drop-shadow(0 0 10px #98FF98)' }}/>}
          <div style={{ height: '30%', width: '1px', backgroundColor: 'var(--outline-variant-ghost)' }}></div>
        </div>

        {/* Right Side — Agent 2 */}
        <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container-low)', display: 'flex', flexDirection: 'column', borderRight: '4px solid var(--agent-debate)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)', paddingBottom: '1rem' }}>
            <div style={{ width: '40px', height: '40px', borderRadius: '50%', backgroundColor: 'rgba(255, 127, 80, 0.2)', display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'var(--agent-debate)', fontWeight: 'bold', border: '1px solid var(--agent-debate)' }}>A2</div>
            <div>
              <div style={{ fontSize: '1.125rem', fontFamily: 'Newsreader', color: 'var(--on-surface)' }}>Petitioner Agent (Constructive)</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--agent-debate)' }}>Confidence: 89%</div>
            </div>
          </div>
          
          <div style={{ flex: 1, overflowY: 'auto', paddingRight: '1rem' }}>
            {activeTab === 'round1' && (
              <div>
                <p className="body-md"><strong>CLAIM:</strong> While the document is unstamped, the doctrine of separability (Section 16(1) of the Act) implies that the arbitration agreement stands independent. Section 11 courts must minimize judicial interference and leave stamping issues to the arbitral tribunal.</p>
                <div style={{ margin: '1rem 0', paddingLeft: '1rem', borderLeft: `2px solid var(--agent-debate)` }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', display: 'block' }}>RELIANCE ON PRINCIPLE</span>
                  <span style={{ fontSize: '0.875rem' }}>Kompetenz-Kompetenz Doctrine</span>
                </div>
              </div>
            )}
            {activeTab === 'round2' && (
              <div className="shimmer">
                <p className="body-md"><strong>REBUTTAL:</strong> Precedent fetch error resolved! <i>NN Global</i> has been formally overruled. The Supreme Court in <i>In Re: Interplay Between Arbitration Agreements</i> definitively established that unstamped agreements are not void ab initio, just inadmissible as evidence — a curable defect.</p>
                 <div style={{ margin: '1rem 0', paddingLeft: '1rem', borderLeft: `2px solid var(--agent-weighting)` }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--agent-weighting)', display: 'block' }}>DEFENDING PRECEDENT OVERRIDE</span>
                  <span style={{ fontSize: '0.875rem' }}>In Re: Interplay (7-Judge Constitutional Bench, 2023)</span>
                </div>
              </div>
            )}
            {activeTab === 'round3' && (
              <div>
                <p className="body-md"><strong>FINAL SYNTHESIS:</strong> The 7-judge ruling acts as binding precedent. An arbitral tribunal has the authority to impound unstamped instruments. Non-stamping does not bar the appointment of an arbitrator under Section 11. Final output established: Motion to arbitrate is highly likely to be granted.</p>
              </div>
            )}
          </div>
        </div>
        
      </div>
    </div>
  );
};

export default DebateVisualization;
