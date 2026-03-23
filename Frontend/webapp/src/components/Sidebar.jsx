import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  FileText, Activity, Clock, MessageSquare, 
  Settings, Server, Navigation, FolderArchive, Microscope, User
} from 'lucide-react';

const Sidebar = () => {
  return (
    <aside className="sidebar" style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '280px', backgroundColor: 'var(--surface-container-lowest)', borderRight: '1px solid var(--outline-variant-ghost)', padding: '1.5rem', flexShrink: 0 }}>
      {/* Product Logo / Name */}
      <div style={{ paddingBottom: '2rem', borderBottom: '1px solid var(--outline-variant-ghost)', marginBottom: '1.5rem' }}>
        <h1 className="newsreader" style={{ fontSize: '1.5rem', color: 'var(--primary)', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Navigation size={24} style={{ color: 'var(--secondary)' }}/>
          Verdicto
        </h1>
        <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', marginTop: '4px' }}>Multi-Agent Strategy Engine</div>
      </div>

      {/* Navigation */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flex: 1 }}>
        <div style={{ fontSize: '0.65rem', color: 'var(--on-surface-variant)', fontWeight: 700, margin: '0.5rem 0 0.25rem 0.5rem', letterSpacing: '0.05em' }}>MAIN WORKSPACE</div>
        <NavLink to="/" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
          <FileText size={18} /> New Case Analysis
        </NavLink>
        <NavLink to="/progress" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
          <Activity size={18} /> Active Jobs
        </NavLink>
        <NavLink to="/results" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
          <Clock size={18} /> Results Dashboard
        </NavLink>
        <NavLink to="/debate" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
          <MessageSquare size={18} /> Debate Explorer
        </NavLink>
        <NavLink to="/past-cases" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
          <FolderArchive size={18} /> Past Cases
        </NavLink>
        
        <div style={{ fontSize: '0.65rem', color: 'var(--on-surface-variant)', fontWeight: 700, margin: '1rem 0 0.25rem 0.5rem', letterSpacing: '0.05em' }}>ADVANCED / SETTINGS</div>
        <NavLink to="/system" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
          <Server size={18} /> System Observability
        </NavLink>
        <NavLink to="/experiments" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
          <Microscope size={18} /> Experiment Mode
        </NavLink>
        <NavLink to="/profile" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
          <User size={18} /> Identity & Settings
        </NavLink>
      </nav>

      {/* Footer System Health */}
      <div className="system-health shimmer" style={{ padding: '1rem', background: 'var(--surface-container-low)', borderRadius: '4px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--tertiary)' }}>SYSTEM STATUS</div>
        <div className="health-stat">
          <span>LLM Node</span>
          <span style={{ color: 'var(--secondary)' }}>Stable (12ms)</span>
        </div>
        <div className="health-stat">
          <span>Retrieval Index</span>
          <span style={{ color: 'var(--secondary)' }}>Syncing (99%)</span>
        </div>
        <div className="health-stat">
          <span>Agents Active</span>
          <span style={{ color: 'var(--primary)' }}>4</span>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
