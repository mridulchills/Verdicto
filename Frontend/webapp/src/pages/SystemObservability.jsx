import React, { useState } from 'react';
import { Server, Activity, Terminal, BrainCircuit, RefreshCw, BarChart2, ShieldAlert } from 'lucide-react';

const SystemObservability = () => {
  const [activeTab, setActiveTab] = useState('agents');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', height: '100%', paddingBottom: '3rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--outline-variant-ghost)', paddingBottom: '1.5rem' }}>
        <div>
          <h2 className="newsreader" style={{ fontSize: '2rem', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.5rem' }}>
            <Server size={24} style={{ color: 'var(--primary)' }}/> System Observability
          </h2>
          <p className="body-md">Advanced analytics, scheduler decisions, and worker health logs.</p>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button className="icon-btn"><RefreshCw size={16}/> Sync Data</button>
          <button className="btn-secondary">Export All Logs</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '1rem' }}>
        <button className={`nav-link ${activeTab === 'agents' ? 'active' : ''}`} style={{ flex: 1, justifyContent: 'center', border: 'none', background: activeTab === 'agents' ? 'var(--surface-container-high)' : 'transparent', color: activeTab === 'agents' ? 'var(--primary)' : 'var(--on-surface-variant)' }} onClick={() => setActiveTab('agents')}>
          <Activity size={18}/> Agent Performance
        </button>
        <button className={`nav-link ${activeTab === 'scheduler' ? 'active' : ''}`} style={{ flex: 1, justifyContent: 'center', border: 'none', background: activeTab === 'scheduler' ? 'var(--surface-container-high)' : 'transparent', color: activeTab === 'scheduler' ? 'var(--primary)' : 'var(--on-surface-variant)' }} onClick={() => setActiveTab('scheduler')}>
          <BrainCircuit size={18}/> Scheduler Logs
        </button>
        <button className={`nav-link ${activeTab === 'iteration' ? 'active' : ''}`} style={{ flex: 1, justifyContent: 'center', border: 'none', background: activeTab === 'iteration' ? 'var(--surface-container-high)' : 'transparent', color: activeTab === 'iteration' ? 'var(--primary)' : 'var(--on-surface-variant)' }} onClick={() => setActiveTab('iteration')}>
          <BarChart2 size={18}/> Iteration Analytics
        </button>
      </div>

      <div style={{ flex: 1, display: 'flex', gap: '2rem' }}>
        {activeTab === 'agents' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', width: '100%' }}>
            {[
              { name: 'Fact Extractor', success: '99%', avgTime: '2.4s', errors: '12' },
              { name: 'Retrieval Engine', success: '97%', avgTime: '5.1s', errors: '34' },
              { name: 'Debater 1 (Pro)', success: '94%', avgTime: '12.8s', errors: '8' },
              { name: 'Debater 2 (Con)', success: '93%', avgTime: '13.1s', errors: '9' }
            ].map((agent, i) => (
              <div key={i} className="insight-card" style={{ backgroundColor: 'var(--surface-container)' }}>
                <h4 style={{ fontSize: '1rem', color: 'var(--on-surface)', marginBottom: '1.5rem', fontWeight: 600 }}>{agent.name}</h4>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem', fontSize: '0.875rem' }}>
                  <span style={{ color: 'var(--on-surface-variant)' }}>Success Rate</span>
                  <span style={{ color: 'var(--primary)', fontFamily: 'monospace' }}>{agent.success}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem', fontSize: '0.875rem' }}>
                  <span style={{ color: 'var(--on-surface-variant)' }}>Avg Exec Time</span>
                  <span style={{ color: 'var(--secondary)', fontFamily: 'monospace' }}>{agent.avgTime}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.875rem' }}>
                  <span style={{ color: 'var(--on-surface-variant)' }}>Error Volume</span>
                  <span style={{ color: 'var(--error)', fontFamily: 'monospace' }}>{agent.errors} (7-day)</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'scheduler' && (
          <div className="insight-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: 'var(--surface-container-lowest)', padding: 0 }}>
            <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)', display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <Terminal size={18} style={{ color: 'var(--tertiary)' }}/> <span className="newsreader" style={{ fontSize: '1.25rem' }}>Orchestrator Decision Trace</span>
            </div>
            <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto', fontFamily: 'monospace', fontSize: '0.875rem', color: 'var(--on-surface-variant)', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div><span style={{ color: 'var(--tertiary)' }}>[10:14:02.111 UTC]</span> SCHEDULER: Initiating Pipeline Job #91B.</div>
              <div><span style={{ color: 'var(--tertiary)' }}>[10:14:03.402 UTC]</span> PLANNER: Step 1 (Extract Constraints). Output length=420.</div>
              <div><span style={{ color: 'var(--tertiary)' }}>[10:14:06.820 UTC]</span> RETRIEVER: Searched corpus `sdny_employment_10y`. Found 14 matches.</div>
              <div><span style={{ color: 'var(--tertiary)' }}>[10:14:09.110 UTC]</span> EVALUATOR: Similarity variance measured at 0.512. Threshold &gt; 0.3. Triggering DEBATER.</div>
              <div style={{ backgroundColor: 'rgba(255, 180, 171, 0.1)', padding: '0.5rem', borderLeft: '2px solid var(--error)' }}><ShieldAlert size={14} style={{ display: 'inline', color: 'var(--error)' }}/> [10:14:15.002 UTC] DEBATER_2: Received 429 TooManyRequests from LLM Node. Waiting 5000ms.</div>
              <div><span style={{ color: 'var(--tertiary)' }}>[10:14:21.050 UTC]</span> DEBATER_2: Resumed. Rebuttal payload generated.</div>
              <div><span style={{ color: 'var(--tertiary)' }}>[10:14:25.990 UTC]</span> EVALUATOR: Similarity variance updated to 0.121. Convergence achieved. Halting Iterations.</div>
            </div>
          </div>
        )}

        {activeTab === 'iteration' && (
          <div className="insight-card" style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column', color: 'var(--on-surface-variant)', backgroundColor: 'var(--surface-container-low)' }}>
             <Activity size={32} style={{ marginBottom: '1rem', opacity: 0.5 }}/>
             <p className="newsreader" style={{ fontSize: '1.25rem' }}>Score Improvement Trend</p>
             <div style={{ height: '300px', width: '100%', maxWidth: '600px', borderBottom: '2px solid var(--outline-variant-ghost)', borderLeft: '2px solid var(--outline-variant-ghost)', position: 'relative', marginTop: '2rem' }}>
                {/* Mock Chart Trend */}
                <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
                  <path d="M 0 80 Q 20 60, 40 40 T 80 20 T 100 10" fill="transparent" stroke="var(--primary)" strokeWidth="2" />
                  <circle cx="0" cy="80" r="2" fill="var(--secondary)" />
                  <circle cx="40" cy="40" r="2" fill="var(--secondary)" />
                  <circle cx="80" cy="20" r="2" fill="var(--secondary)" />
                  <circle cx="100" cy="10" r="2" fill="var(--secondary)" />
                </svg>
                <div style={{ position: 'absolute', bottom: '-20px', left: '0', fontSize: '0.65rem' }}>Start</div>
                <div style={{ position: 'absolute', bottom: '-20px', right: '0', fontSize: '0.65rem' }}>Convergence</div>
             </div>
             <p style={{ marginTop: '3rem', fontSize: '0.875rem', maxWidth: '500px', textAlign: 'center' }}>Convergence trends indicate that across 1,400 runs, the system reaches a stable similarity score by Iteration 4, showing decreasing returns on depth scaling beyond 7 cycles.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default SystemObservability;
