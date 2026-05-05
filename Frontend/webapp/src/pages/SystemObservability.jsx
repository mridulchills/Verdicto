import React, { useState, useEffect } from 'react';
import { Server, Activity, Terminal, BrainCircuit, RefreshCw, BarChart2, ShieldAlert, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import { getHealthStatus, getSystemStats } from '../lib/apiClient';

const SystemObservability = () => {
  const [activeTab, setActiveTab] = useState('health');
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, s] = await Promise.allSettled([getHealthStatus(), getSystemStats()]);
      if (h.status === 'fulfilled') setHealth(h.value);
      if (s.status === 'fulfilled') setStats(s.value);
      if (h.status === 'rejected' && s.status === 'rejected') {
        setError('Cannot reach backend. Is uvicorn running on port 8000?');
      }
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, []);

  const statusIcon = (val) => {
    if (!val || val === 'unknown') return <AlertTriangle size={16} style={{ color: 'var(--on-surface-variant)' }} />;
    if (val.startsWith('error') || val === 'not_available' || val === 'not_configured' || val === 'not_loaded')
      return <XCircle size={16} style={{ color: 'var(--error)' }} />;
    return <CheckCircle2 size={16} style={{ color: '#4ade80' }} />;
  };

  const statusColor = (val) => {
    if (!val || val === 'unknown') return 'var(--on-surface-variant)';
    if (val.startsWith('error') || val === 'not_available' || val === 'not_configured' || val === 'not_loaded') return 'var(--error)';
    return '#4ade80';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', height: '100%', paddingBottom: '3rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--outline-variant-ghost)', paddingBottom: '1.5rem' }}>
        <div>
          <h2 className="newsreader" style={{ fontSize: '2rem', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.5rem' }}>
            <Server size={24} style={{ color: 'var(--primary)' }}/> System Observability
          </h2>
          <p className="body-md">Live system health, infrastructure metrics, and pipeline statistics.</p>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button className="icon-btn" onClick={fetchData} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin-slow' : ''}/> {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '1rem', backgroundColor: 'rgba(255,180,171,0.1)', border: '1px solid var(--error)', borderRadius: '4px', color: 'var(--error)', fontSize: '0.875rem' }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', gap: '1rem' }}>
        {['health', 'stats', 'agents'].map((tab) => (
          <button key={tab}
            className={`nav-link ${activeTab === tab ? 'active' : ''}`}
            style={{ flex: 1, justifyContent: 'center', border: 'none', background: activeTab === tab ? 'var(--surface-container-high)' : 'transparent', color: activeTab === tab ? 'var(--primary)' : 'var(--on-surface-variant)' }}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'health' && <><Activity size={18}/> Service Health</>}
            {tab === 'stats' && <><BarChart2 size={18}/> Data Stats</>}
            {tab === 'agents' && <><BrainCircuit size={18}/> Pipeline Info</>}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, display: 'flex', gap: '2rem' }}>
        {activeTab === 'health' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', width: '100%', alignContent: 'start' }}>
            {[
              { name: 'PostgreSQL Database', key: 'database', desc: 'Stores case metadata, query history, and full-text search indexes.' },
              { name: 'FAISS Vector Index', key: 'faiss', desc: 'In-memory index for semantic similarity search across 782+ case embeddings.' },
              { name: 'Redis Cache', key: 'redis', desc: 'Task queue and session caching for async pipeline jobs.' },
              { name: 'Gemini LLM', key: 'gemini', desc: 'Google Gemini 1.5 Flash/Pro for multi-agent reasoning.' }
            ].map((svc) => {
              const val = health?.[svc.key] || 'unknown';
              return (
                <div key={svc.key} className="insight-card" style={{ backgroundColor: 'var(--surface-container)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem' }}>
                    {statusIcon(val)}
                    <h4 style={{ fontSize: '1rem', color: 'var(--on-surface)', fontWeight: 600 }}>{svc.name}</h4>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem', fontSize: '0.875rem' }}>
                    <span style={{ color: 'var(--on-surface-variant)' }}>Status</span>
                    <span style={{ color: statusColor(val), fontFamily: 'monospace', fontWeight: 600, textTransform: 'uppercase' }}>{val}</span>
                  </div>
                  <p style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', lineHeight: 1.5, marginTop: '0.5rem' }}>{svc.desc}</p>
                </div>
              );
            })}

            {/* Overall status banner */}
            <div className="insight-card" style={{ gridColumn: '1 / -1', backgroundColor: health?.status === 'healthy' ? 'rgba(74, 222, 128, 0.05)' : 'rgba(255, 180, 171, 0.05)', border: `1px solid ${health?.status === 'healthy' ? 'rgba(74, 222, 128, 0.3)' : 'rgba(255, 180, 171, 0.3)'}`, display: 'flex', alignItems: 'center', gap: '1rem', padding: '1.5rem' }}>
              {health?.status === 'healthy'
                ? <CheckCircle2 size={24} style={{ color: '#4ade80' }} />
                : <AlertTriangle size={24} style={{ color: 'var(--error)' }} />
              }
              <div>
                <div style={{ fontWeight: 700, fontSize: '1.125rem', color: health?.status === 'healthy' ? '#4ade80' : 'var(--error)' }}>
                  System Status: {health?.status?.toUpperCase() || 'UNKNOWN'}
                </div>
                <div style={{ fontSize: '0.875rem', color: 'var(--on-surface-variant)' }}>
                  {health?.status === 'healthy' ? 'All core services are operational.' : 'One or more services are degraded. Check individual statuses above.'}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'stats' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem', width: '100%', alignContent: 'start' }}>
            <div className="insight-card" style={{ backgroundColor: 'var(--surface-container)', textAlign: 'center', padding: '2rem' }}>
              <div style={{ fontSize: '3rem', fontFamily: 'monospace', fontWeight: 700, color: 'var(--primary)' }}>{stats?.total_cases ?? '—'}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em', marginTop: '0.5rem' }}>INDEXED CASES</div>
            </div>
            <div className="insight-card" style={{ backgroundColor: 'var(--surface-container)', textAlign: 'center', padding: '2rem' }}>
              <div style={{ fontSize: '3rem', fontFamily: 'monospace', fontWeight: 700, color: 'var(--secondary)' }}>{stats?.faiss_index_size ?? '—'}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em', marginTop: '0.5rem' }}>FAISS VECTORS</div>
            </div>
            <div className="insight-card" style={{ backgroundColor: 'var(--surface-container)', textAlign: 'center', padding: '2rem' }}>
              <div style={{ fontSize: '3rem', fontFamily: 'monospace', fontWeight: 700, color: 'var(--tertiary)' }}>{stats?.total_queries ?? '—'}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em', marginTop: '0.5rem' }}>QUERIES RUN</div>
            </div>

            <div className="insight-card" style={{ backgroundColor: 'var(--surface-container)', padding: '1.5rem', gridColumn: '1 / -1' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em', marginBottom: '1rem' }}>YEARS COVERED IN INDEX</div>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {(stats?.years_covered || []).length > 0 ? stats.years_covered.map(y => (
                  <span key={y} className="chip" style={{ backgroundColor: 'rgba(190, 198, 224, 0.1)', color: 'var(--primary)', border: '1px solid rgba(190, 198, 224, 0.3)' }}>{y}</span>
                )) : <span style={{ color: 'var(--on-surface-variant)', fontSize: '0.875rem' }}>No years indexed yet. Run the ingestion pipeline.</span>}
              </div>
            </div>

            <div className="insight-card" style={{ backgroundColor: 'var(--surface-container)', padding: '1.5rem', gridColumn: '1 / -1' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em', marginBottom: '0.5rem' }}>EMBEDDING DIMENSION</div>
              <div style={{ fontSize: '1.5rem', fontFamily: 'monospace', color: 'var(--on-surface)' }}>{stats?.embedding_dimension ?? '—'} <span style={{ fontSize: '0.875rem', color: 'var(--on-surface-variant)' }}>dimensions (Sentence Transformer: all-MiniLM-L6-v2)</span></div>
            </div>
          </div>
        )}

        {activeTab === 'agents' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', width: '100%', alignContent: 'start' }}>
            {[
              { name: 'Query Planner', desc: 'Decomposes legal queries into sub-tasks and identifies target statutes.', color: 'var(--agent-planner)' },
              { name: 'Retriever', desc: 'Hybrid FAISS + BM25 search with Reciprocal Rank Fusion.', color: 'var(--agent-retriever)' },
              { name: 'Precedent Weighter', desc: 'Scores precedents by bench strength, recency, and factual similarity.', color: 'var(--agent-weighting)' },
              { name: 'Debate Agent', desc: 'Constructive vs adversarial argument generation for conflicting precedents.', color: 'var(--agent-debate)' },
              { name: 'Evaluator', desc: 'Measures similarity variance and determines if debate convergence is achieved.', color: 'var(--agent-evaluator)' },
              { name: 'Scheduler', desc: 'Orchestrates the pipeline, handles error recovery and iteration loops.', color: 'var(--agent-scheduler)' },
            ].map((agent, i) => (
              <div key={i} className="insight-card" style={{ backgroundColor: 'var(--surface-container)', borderLeft: `3px solid ${agent.color}` }}>
                <h4 style={{ fontSize: '1rem', color: agent.color, marginBottom: '0.75rem', fontWeight: 600 }}>{agent.name}</h4>
                <p style={{ fontSize: '0.8rem', color: 'var(--on-surface-variant)', lineHeight: 1.6 }}>{agent.desc}</p>
              </div>
            ))}
          </div>
        )}
      </div>
      <style>{`
        @keyframes spin-slow { 100% { transform: rotate(360deg); } }
        .spin-slow { animation: spin-slow 1s linear infinite; }
      `}</style>
    </div>
  );
};

export default SystemObservability;
