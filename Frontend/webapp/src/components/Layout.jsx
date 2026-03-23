import React, { useState, useEffect } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import { Search, Map, Cpu, FileText } from 'lucide-react';
import '../index.css';

const CommandPalette = ({ isOpen, onClose }) => {
  if (!isOpen) return null;
  const navigate = useNavigate();

  return (
    <div className="cmd-k-overlay" onClick={onClose}>
      <div className="cmd-k-palette" onClick={e => e.stopPropagation()}>
        <input 
          autoFocus
          className="cmd-k-input" 
          placeholder="Search cases, agents, logs, actions..." 
        />
        <div style={{ paddingBottom: '1rem', maxHeight: '300px', overflowY: 'auto' }}>
          <div className="cmd-k-category">Actions</div>
          <div className="cmd-k-item" onClick={() => { navigate('/'); onClose(); }}><FileText size={16} style={{ color: 'var(--tertiary)' }}/> New Analysis</div>
          <div className="cmd-k-item"><Search size={16} style={{ color: 'var(--tertiary)' }}/> Search corpus across SDNY</div>
          
          <div className="cmd-k-category">Logs & Agents</div>
          <div className="cmd-k-item" onClick={() => { navigate('/system'); onClose(); }}><Cpu size={16} style={{ color: 'var(--agent-debate)' }}/> Debate Agent Logs</div>
          <div className="cmd-k-item" onClick={() => { navigate('/system'); onClose(); }}><Cpu size={16} style={{ color: 'var(--agent-scheduler)' }}/> Scheduler Decision Trace</div>

          <div className="cmd-k-category">Recent Cases</div>
          <div className="cmd-k-item selected" onClick={() => { navigate('/results'); onClose(); }}><Map size={16} style={{ color: 'var(--agent-weighting)' }}/> Case #91B (Torts vs Logistics) - 88% Confidence</div>
        </div>
      </div>
    </div>
  );
};

const Layout = () => {
  const [cmdKAux, setCmdKAux] = useState(false);

  useEffect(() => {
    const down = (e) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setCmdKAux((open) => !open);
      }
      if (e.key === 'Escape') setCmdKAux(false);
    };

    document.addEventListener('keydown', down);
    return () => document.removeEventListener('keydown', down);
  }, []);

  return (
    <div className="app-layout" style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--background)' }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100vh' }}>
        <Topbar />
        <main style={{ flex: 1, overflowY: 'auto', padding: '2rem 3rem' }}>
          <Outlet />
        </main>
      </div>
      <CommandPalette isOpen={cmdKAux} onClose={() => setCmdKAux(false)} />
    </div>
  );
};

export default Layout;
