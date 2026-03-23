import React from 'react';
import { Download, Bookmark, Share2, HelpCircle, Bell, Search } from 'lucide-react';

const Topbar = () => {
  return (
    <header style={{ height: '72px', borderBottom: '1px solid var(--outline-variant-ghost)', padding: '0 2rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'var(--surface)', flexShrink: 0 }}>
      {/* Search and Context info */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '3rem' }}>
        
        {/* Global Search */}
        <div style={{ position: 'relative', width: '300px' }}>
          <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--on-surface-variant)' }} />
          <input 
            className="docket-input" 
            placeholder="Search cases, precedents, or logs..." 
            style={{ 
               paddingLeft: '2.5rem', 
               paddingRight: '1rem', 
               height: '36px', 
               backgroundColor: 'var(--surface-container-lowest)', 
               border: '1px solid var(--outline-variant-ghost)', 
               borderRadius: '4px',
               fontSize: '0.875rem'
            }}
          />
        </div>

        <div style={{ width: '1px', height: '32px', backgroundColor: 'var(--outline-variant-ghost)' }}></div>

        <div>
          <span style={{ color: 'var(--on-surface-variant)', fontSize: '0.75rem', fontWeight: 600 }}>CURRENT TASK</span>
          <div className="newsreader" style={{ fontSize: '1.25rem', marginTop: '2px', color: 'var(--on-surface)' }}>Case Analysis — #91B (Torts vs Logistics)</div>
        </div>
        
        <div style={{ display: 'flex', gap: '1rem' }}>
          <div className="chip status-chip running">
            <span className="dot"></span> RUNNING
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--tertiary)' }}>ITERATIONS</span>
            <span style={{ fontSize: '0.875rem', fontWeight: 700, fontFamily: 'monospace' }}>4 / 10</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '0.65rem', color: 'var(--tertiary)' }}>EVAL SCORE</span>
            <span style={{ fontSize: '0.875rem', fontWeight: 700, fontFamily: 'monospace', color: 'var(--secondary)' }}>88%</span>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <button className="icon-btn" style={{ position: 'relative' }}>
          <Bell size={18} /> 
          <span style={{ position: 'absolute', top: '-4px', right: '-4px', width: '8px', height: '8px', backgroundColor: 'var(--error)', borderRadius: '50%' }}></span>
          Alerts
        </button>
        <div style={{ width: '1px', height: '24px', backgroundColor: 'var(--outline-variant-ghost)' }}></div>
        <button className="icon-btn" title="Export to PDF/DOCX"><Download size={18} /> Export</button>
        <button className="icon-btn" title="Save Snapshot"><Bookmark size={18} /> Snapshot</button>
        <button className="icon-btn" title="Share Results"><Share2 size={18} /> Share</button>
      </div>
    </header>
  );
};

export default Topbar;
