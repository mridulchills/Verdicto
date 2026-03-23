import React, { useState } from 'react';
import { Microscope, SplitSquareHorizontal, ToggleLeft } from 'lucide-react';

const ExperimentMode = () => {
  const [activeTab, setActiveTab] = useState('ablation');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--outline-variant-ghost)', paddingBottom: '1.5rem' }}>
        <div>
          <h2 className="newsreader" style={{ fontSize: '2rem', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.5rem' }}>
            <Microscope size={24} style={{ color: 'var(--tertiary)' }}/> Experimentation Suite
          </h2>
          <p className="body-md">Advanced research features for testing multi-agent capabilities and paper publication ablation studies.</p>
        </div>
        <div style={{ display: 'flex', gap: '1rem', backgroundColor: 'var(--surface-container-low)', padding: '0.5rem', borderRadius: '4px' }}>
          <button className={`nav-link ${activeTab === 'ablation' ? 'active' : ''}`} style={{ border: 'none', background: activeTab === 'ablation' ? 'var(--primary-container)' : 'transparent', color: activeTab === 'ablation' ? 'var(--primary)' : 'var(--on-surface-variant)' }} onClick={() => setActiveTab('ablation')}>
            <ToggleLeft size={16}/> Ablation Module
          </button>
          <button className={`nav-link ${activeTab === 'comparison' ? 'active' : ''}`} style={{ border: 'none', background: activeTab === 'comparison' ? 'var(--primary-container)' : 'transparent', color: activeTab === 'comparison' ? 'var(--primary)' : 'var(--on-surface-variant)' }} onClick={() => setActiveTab('comparison')}>
            <SplitSquareHorizontal size={16}/> Side-by-Side Comparison
          </button>
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', gap: '2rem' }}>
        {activeTab === 'ablation' && (
          <>
            <div style={{ flex: '0 0 350px', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <div className="insight-card" style={{ backgroundColor: 'var(--surface-container)', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <h3 className="newsreader" style={{ fontSize: '1.25rem' }}>Algorithm Capabilities</h3>
                
                {[
                  { name: 'Debater Subsystem', desc: 'Disables constructive/adversarial rounds. Uses flat similarity ranking only.', checked: true },
                  { name: 'Structural Similarity', desc: 'Discards vector structural overlap, relies purely on TF-IDF semantic matching.', checked: false },
                  { name: 'Dynamic Scheduler', desc: 'Forces static 1-pass execution instead of letting the evaluator loop until variance convergence.', checked: true }
                ].map((ablation, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid var(--outline-variant-ghost)', paddingBottom: '1rem' }}>
                    <div>
                      <div style={{ fontSize: '0.875rem', fontWeight: 600, color: ablation.checked ? 'var(--on-surface)' : 'var(--on-surface-variant)', marginBottom: '4px' }}>
                        {ablation.name}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', maxWidth: '240px' }}>
                        {ablation.desc}
                      </div>
                    </div>
                    {ablation.checked ? (
                      <div style={{ width: '36px', height: '18px', backgroundColor: 'var(--primary)', borderRadius: '9px', position: 'relative', cursor: 'pointer' }}>
                        <div style={{ position: 'absolute', right: '2px', top: '2px', width: '14px', height: '14px', backgroundColor: 'var(--primary-container)', borderRadius: '50%' }}></div>
                      </div>
                    ) : (
                      <div style={{ width: '36px', height: '18px', backgroundColor: 'var(--surface-container-high)', borderRadius: '9px', position: 'relative', cursor: 'pointer' }}>
                        <div style={{ position: 'absolute', left: '2px', top: '2px', width: '14px', height: '14px', backgroundColor: 'var(--on-surface-variant)', borderRadius: '50%' }}></div>
                      </div>
                    )}
                  </div>
                ))}
                
                <button className="btn-primary" style={{ marginTop: 'auto' }}>Run Ablation Test</button>
              </div>
            </div>

            <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container-lowest)', border: '1px dashed var(--outline-variant-ghost)', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column', textAlign: 'center' }}>
              <Microscope size={40} style={{ color: 'var(--tertiary)', marginBottom: '1.5rem', opacity: 0.5 }}/>
              <div className="newsreader" style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>Select constraints & execute to view delta</div>
              <p className="body-md" style={{ maxWidth: '400px' }}>The system will run a parallel analysis using the identical benchmark set but omitting the selected cognitive modules. You can then measure accuracy loss for paper data.</p>
            </div>
          </>
        )}

        {activeTab === 'comparison' && (
          <div style={{ display: 'flex', gap: '2rem', width: '100%' }}>
            <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container)', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <h3 className="newsreader" style={{ fontSize: '1.5rem', color: 'var(--secondary)' }}>Standard Run (10 Iters)</h3>
              <ul style={{ paddingLeft: '1.25rem', fontSize: '0.875rem', color: 'var(--on-surface)', lineHeight: '1.8' }}>
                <li>Evaluator Threshold: 0.10</li>
                <li>Outcome Confidence: <strong style={{ color: 'var(--primary)' }}>92.4%</strong></li>
                <li>Debate Triggered: Round 2 & 3</li>
                <li>Precedents: <em>Smith (98%)</em>, <em>Torres (94%)</em></li>
              </ul>
            </div>
            <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container-low)', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <h3 className="newsreader" style={{ fontSize: '1.5rem', color: 'var(--error)' }}>Ablated Run (No Scheduler)</h3>
              <ul style={{ paddingLeft: '1.25rem', fontSize: '0.875rem', color: 'var(--on-surface)', lineHeight: '1.8' }}>
                <li>Evaluator Threshold: N/A</li>
                <li>Outcome Confidence: <strong style={{ opacity: 0.6 }}>68.1%</strong></li>
                <li>Debate Triggered: None (Flat Vector)</li>
                <li>Precedents: <em>Doe (82%)</em>, <em>Smith (79%)</em></li>
              </ul>
              
              <div style={{ padding: '1rem', backgroundColor: 'rgba(255, 180, 171, 0.1)', borderLeft: '2px solid var(--error)', fontSize: '0.875rem', marginTop: 'auto' }}>
                <strong style={{ display: 'block', color: 'var(--error)', marginBottom: '4px' }}>ANALYSIS DELTA</strong>
                Confidence drops 24 points. Precedent retrieval hallucinates context due to lack of Debate error-correction.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ExperimentMode;
