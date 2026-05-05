import React, { useState, useEffect } from 'react';
import { Search, Filter, FolderArchive, ArrowRight, Loader2, RefreshCw } from 'lucide-react';
import { listQueries } from '../lib/apiClient';
import { useNavigate } from 'react-router-dom';

const PastCases = () => {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [total, setTotal] = useState(0);

  const fetchCases = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listQueries({ limit: 50 });
      setCases(data.queries || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError(e.message);
      setCases([]);
    }
    setLoading(false);
  };

  useEffect(() => { fetchCases(); }, []);

  const filtered = cases.filter(cs =>
    cs.query_text.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatDate = (isoStr) => {
    if (!isoStr) return '—';
    try {
      return new Date(isoStr).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return isoStr; }
  };

  const statusChip = (status) => {
    if (status === 'complete') return (
      <span className="chip" style={{ backgroundColor: 'rgba(74, 222, 128, 0.1)', color: '#4ade80', border: '1px solid rgba(74, 222, 128, 0.2)' }}>Complete</span>
    );
    if (status === 'failed') return (
      <span className="chip" style={{ backgroundColor: 'rgba(255, 180, 171, 0.1)', color: 'var(--error)', border: '1px solid rgba(255, 180, 171, 0.2)' }}>Failed</span>
    );
    if (status === 'processing') return (
      <span className="chip" style={{ backgroundColor: 'rgba(233, 195, 73, 0.1)', color: 'var(--secondary)', border: '1px solid rgba(233, 195, 73, 0.2)' }}>Processing</span>
    );
    return (
      <span className="chip" style={{ backgroundColor: 'rgba(190, 198, 224, 0.1)', color: 'var(--on-surface-variant)', border: '1px solid rgba(190, 198, 224, 0.2)' }}>{status}</span>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h2 className="newsreader" style={{ fontSize: '2rem', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.5rem' }}>
            <FolderArchive size={24} style={{ color: 'var(--primary)' }}/> Past Queries
          </h2>
          <p className="body-md">Search and review your previous multi-agent analysis runs. {total > 0 && <span style={{ color: 'var(--secondary)' }}>{total} total queries.</span>}</p>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <div style={{ position: 'relative', width: '300px' }}>
            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--on-surface-variant)' }} />
            <input 
              className="docket-input" 
              placeholder="Search query text..." 
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              style={{ paddingLeft: '2.5rem', backgroundColor: 'var(--surface-container-lowest)', border: '1px solid var(--outline-variant-ghost)', borderRadius: '4px' }}
            />
          </div>
          <button className="icon-btn" style={{ padding: '0.5rem 1rem' }} onClick={fetchCases} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin-slow' : ''}/> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '1rem', backgroundColor: 'rgba(255,180,171,0.1)', border: '1px solid var(--error)', borderRadius: '4px', color: 'var(--error)', fontSize: '0.875rem' }}>
          {error}
        </div>
      )}

      <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container)', padding: '0', overflow: 'hidden' }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '300px', flexDirection: 'column', gap: '1rem' }}>
            <Loader2 size={32} className="spin-slow" style={{ color: 'var(--primary)' }} />
            <span style={{ color: 'var(--on-surface-variant)' }}>Loading query history...</span>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '300px', flexDirection: 'column', gap: '1rem', color: 'var(--on-surface-variant)' }}>
            <FolderArchive size={40} style={{ opacity: 0.4 }}/>
            <p>No past queries found. {searchQuery ? 'Try a different search.' : 'Submit a query from the New Case page to see results here.'}</p>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead style={{ backgroundColor: 'var(--surface-container-low)', color: 'var(--on-surface-variant)', fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.05em' }}>
              <tr>
                <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>QUERY</th>
                <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>DATE</th>
                <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>STATUS</th>
                <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>TIME</th>
                <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((cs) => (
                <tr key={cs.query_id} style={{ borderBottom: '1px solid var(--outline-variant-ghost)', transition: 'background 0.2s', cursor: 'pointer' }}
                  onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-container-high)'}
                  onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                  onClick={() => navigate(`/results`, { state: { queryId: cs.query_id } })}
                >
                  <td style={{ padding: '1.5rem', maxWidth: '400px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--on-surface)', marginBottom: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cs.query_text}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--tertiary)' }}>#{cs.query_id.slice(0, 8)}</div>
                  </td>
                  <td style={{ padding: '1.5rem', color: 'var(--on-surface-variant)', fontSize: '0.875rem' }}>{formatDate(cs.created_at)}</td>
                  <td style={{ padding: '1.5rem' }}>{statusChip(cs.status)}</td>
                  <td style={{ padding: '1.5rem', fontFamily: 'monospace', color: 'var(--primary)' }}>
                    {cs.processing_time_ms != null ? `${(cs.processing_time_ms / 1000).toFixed(1)}s` : '—'}
                  </td>
                  <td style={{ padding: '1.5rem', textAlign: 'right' }}>
                    <button className="icon-btn" style={{ border: 'none' }}><ArrowRight size={18} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <style>{`
        @keyframes spin-slow { 100% { transform: rotate(360deg); } }
        .spin-slow { animation: spin-slow 1s linear infinite; }
      `}</style>
    </div>
  );
};

export default PastCases;
