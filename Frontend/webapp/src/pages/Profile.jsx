import React from 'react';
import { User, Briefcase, Activity, Settings2, Shield, Eye, Lock, Edit3 } from 'lucide-react';

const Profile = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '3rem', height: '100%', paddingBottom: '3rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="newsreader" style={{ fontSize: '2rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <User size={24} style={{ color: 'var(--primary)' }}/> Identity Profile
        </h2>
        <button className="btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}><Edit3 size={16}/> Edit Profile</button>
      </div>

      <div style={{ display: 'flex', gap: '2rem' }}>
        {/* Left Column - User Info */}
        <div style={{ flex: '0 0 320px', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          <div className="insight-card" style={{ backgroundColor: 'var(--surface-container-highest)', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '3rem 2rem' }}>
            <div style={{ width: '80px', height: '80px', borderRadius: '50%', backgroundColor: 'var(--primary-container)', color: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2rem', fontWeight: 700, marginBottom: '1rem', border: '2px solid var(--secondary)' }}>
              JS
            </div>
            <h3 className="newsreader" style={{ fontSize: '1.5rem', marginBottom: '0.25rem' }}>Julia Stephens</h3>
            <div style={{ color: 'var(--on-surface-variant)', fontSize: '0.875rem', marginBottom: '1rem' }}>Principal Researcher</div>
            
            <span className="chip" style={{ backgroundColor: 'rgba(59, 130, 246, 0.1)', color: 'var(--tertiary)', border: '1px solid var(--outline-variant-ghost)' }}>
               <Shield size={12} style={{ display: 'inline', marginRight: '4px' }}/> Admin Privileges
            </span>
          </div>

          <div className="insight-card" style={{ backgroundColor: 'var(--surface-container)' }}>
            <h4 style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em', marginBottom: '1rem' }}>BASIC INFORMATION</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <div style={{ fontSize: '0.65rem', color: 'var(--tertiary)' }}>EMAIL</div>
                <div style={{ fontSize: '0.875rem' }}>julia.stephens@lex.hub</div>
              </div>
              <div>
                <div style={{ fontSize: '0.65rem', color: 'var(--tertiary)' }}>ORGANIZATION</div>
                <div style={{ fontSize: '0.875rem' }}>Apex Legal Technologies</div>
              </div>
              <div>
                <div style={{ fontSize: '0.65rem', color: 'var(--tertiary)' }}>ROLE DESIGNATION</div>
                <div style={{ fontSize: '0.875rem' }}>Researcher / Admin</div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column - Usage & Preferences */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* Activity Overviews */}
          <div style={{ display: 'flex', gap: '1rem' }}>
            <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container-low)', padding: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <div style={{ padding: '0.75rem', backgroundColor: 'var(--primary-container)', borderRadius: '8px' }}>
                <Activity size={24} style={{ color: 'var(--primary)' }}/>
              </div>
              <div>
                <div style={{ fontSize: '2rem', fontFamily: 'monospace', fontWeight: 700, color: 'var(--secondary)' }}>142</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>TOTAL PREDICTIONS</div>
              </div>
            </div>
            
            <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container-low)', padding: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <div style={{ padding: '0.75rem', backgroundColor: 'var(--primary-container)', borderRadius: '8px' }}>
                <Briefcase size={24} style={{ color: 'var(--tertiary)' }}/>
              </div>
              <div>
                <div style={{ fontSize: '2rem', fontFamily: 'monospace', fontWeight: 700, color: 'var(--on-surface)' }}>92%</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>AVG CONFIDENCE SCORE</div>
              </div>
            </div>
          </div>

          <div className="insight-card" style={{ backgroundColor: 'var(--surface-container)', flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', borderBottom: '1px solid var(--outline-variant-ghost)', paddingBottom: '1rem' }}>
              <h4 className="newsreader" style={{ fontSize: '1.25rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Settings2 size={18} style={{ color: 'var(--primary)' }}/> Global Preferences
              </h4>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--on-surface-variant)', marginBottom: '0.5rem' }}>DEFAULT JURISDICTION</label>
                <select className="docket-input" style={{ width: '100%', marginBottom: '1.5rem', background: 'transparent' }}>
                  <option>US Federal Circuit</option>
                  <option>2nd Circuit</option>
                  <option>9th Circuit</option>
                  <option>Supreme Court</option>
                </select>

                <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--on-surface-variant)', marginBottom: '0.5rem' }}>PREFERRED EXPORT FORMAT</label>
                <select className="docket-input" style={{ width: '100%', background: 'transparent' }}>
                  <option>PDF Report</option>
                  <option>DOCX Brief</option>
                  <option>Raw JSON</option>
                </select>
              </div>

              <div>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', padding: '1rem 0', borderBottom: '1px solid var(--outline-variant-ghost)' }}>
                  <div>
                    <span style={{ fontSize: '0.875rem', fontWeight: 600, display: 'block', color: 'var(--on-surface)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Eye size={14} style={{ color: 'var(--secondary)' }}/> Advanced Features Visiblity
                    </span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>Show scheduler logic and debate explorers in UI</span>
                  </div>
                  <div style={{ width: '40px', height: '20px', backgroundColor: 'var(--secondary)', borderRadius: '10px', position: 'relative', cursor: 'pointer' }}>
                    <div style={{ position: 'absolute', right: '2px', top: '2px', width: '16px', height: '16px', backgroundColor: 'var(--background)', borderRadius: '50%' }}></div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', padding: '1rem 0', opacity: 0.6 }}>
                  <div>
                    <span style={{ fontSize: '0.875rem', fontWeight: 600, display: 'block', color: 'var(--on-surface)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Lock size={14} style={{ color: 'var(--tertiary)' }}/> API Access (Integration)
                    </span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>Generate keys for external client integration</span>
                  </div>
                  <button className="icon-btn" style={{ fontSize: '0.75rem' }}>Generate</button>
                </div>
              </div>
            </div>
            
            <div style={{ marginTop: '2rem', display: 'flex', justifyContent: 'flex-end' }}>
               <button className="btn-primary" style={{ marginTop: 0 }}>Save Changes</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
