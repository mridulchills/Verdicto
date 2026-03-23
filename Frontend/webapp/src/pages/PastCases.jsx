import React, { useState } from 'react';
import { Search, Filter, FolderArchive, ArrowRight } from 'lucide-react';

const PastCases = () => {
  const [searchQuery, setSearchQuery] = useState('');

  const cases = [
    { id: '91B', title: 'Torts vs Logistics (Smith v. Horizon)', date: 'Oct 12, 2023', status: 'Completed', score: '88%', jurisdiction: '2nd Cir.' },
    { id: '88A', title: 'IP Dispute (TechCorp v. Innovate)', date: 'Oct 10, 2023', status: 'Completed', score: '92%', jurisdiction: 'NDCA' },
    { id: '102C', title: 'Breach of Contract (Omega vs Delta)', date: 'Oct 08, 2023', status: 'Failed', score: '--', jurisdiction: 'SDNY' },
    { id: '77D', title: 'Employment Class Action (Jane Doe)', date: 'Sep 29, 2023', status: 'Completed', score: '76%', jurisdiction: '9th Cir.' }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h2 className="newsreader" style={{ fontSize: '2rem', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.5rem' }}>
            <FolderArchive size={24} style={{ color: 'var(--primary)' }}/> Past Cases Archive
          </h2>
          <p className="body-md">Search and filter historical multi-agent analyses and debate logs.</p>
        </div>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <div style={{ position: 'relative', width: '300px' }}>
            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--on-surface-variant)' }} />
            <input 
              className="docket-input" 
              placeholder="Search rulings, keywords, or inputs..." 
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              style={{ paddingLeft: '2.5rem', backgroundColor: 'var(--surface-container-lowest)', border: '1px solid var(--outline-variant-ghost)', borderRadius: '4px' }}
            />
          </div>
          <button className="icon-btn" style={{ padding: '0.5rem 1rem' }}><Filter size={16}/> Filters</button>
        </div>
      </div>

      <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container)', padding: '0', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead style={{ backgroundColor: 'var(--surface-container-low)', color: 'var(--on-surface-variant)', fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.05em' }}>
            <tr>
              <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>CASE IDENTIFIER</th>
              <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>DATE</th>
              <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>JURISDICTION</th>
              <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>STATUS</th>
              <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>EVAL SCORE</th>
              <th style={{ padding: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}></th>
            </tr>
          </thead>
          <tbody>
            {cases.map((cs, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--outline-variant-ghost)', transition: 'background 0.2s', cursor: 'pointer' }} onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-container-high)'} onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}>
                <td style={{ padding: '1.5rem' }}>
                  <div style={{ fontWeight: 600, color: 'var(--on-surface)', marginBottom: '4px' }}>{cs.title}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--tertiary)' }}>#{cs.id}</div>
                </td>
                <td style={{ padding: '1.5rem', color: 'var(--on-surface-variant)', fontSize: '0.875rem' }}>{cs.date}</td>
                <td style={{ padding: '1.5rem', fontSize: '0.875rem' }}>{cs.jurisdiction}</td>
                <td style={{ padding: '1.5rem' }}>
                  {cs.status === 'Completed' ? (
                     <span className="chip" style={{ backgroundColor: 'rgba(233, 195, 73, 0.1)', color: 'var(--secondary)', border: '1px solid rgba(233, 195, 73, 0.2)' }}>Completed</span>
                  ) : (
                     <span className="chip" style={{ backgroundColor: 'rgba(255, 180, 171, 0.1)', color: 'var(--error)', border: '1px solid rgba(255, 180, 171, 0.2)' }}>Failed</span>
                  )}
                </td>
                <td style={{ padding: '1.5rem', fontFamily: 'monospace', fontWeight: 600, color: cs.status === 'Completed' ? 'var(--primary)' : 'var(--on-surface-variant)' }}>{cs.score}</td>
                <td style={{ padding: '1.5rem', textAlign: 'right' }}>
                  <button className="icon-btn" style={{ border: 'none' }}><ArrowRight size={18} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default PastCases;
