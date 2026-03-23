import React, { useState, useRef } from 'react';
import { Upload, FileText, CheckCircle2, Zap, Play, Trash2, File as FileIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const NewCasePage = () => {
  const navigate = useNavigate();
  const [modalOpen, setModalOpen] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('idle'); // idle, dragging, scanning, complete
  const [extractedFacts, setExtractedFacts] = useState(false);
  const [files, setFiles] = useState([]);
  
  const fileInputRef = useRef(null);

  // Fake scanning delay effect
  const simulateProcessing = () => {
    setUploadStatus('scanning');
    setTimeout(() => {
      setUploadStatus('complete');
      setTimeout(() => {
        setModalOpen(false);
        setExtractedFacts(true);
      }, 1500);
    }, 2000);
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files).map(f => ({ name: f.name, size: (f.size / 1024).toFixed(1) + ' KB' }));
      setFiles([...files, ...newFiles]);
      simulateProcessing();
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setUploadStatus('scanning');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const newFiles = Array.from(e.dataTransfer.files).map(f => ({ name: f.name, size: (f.size / 1024).toFixed(1) + ' KB' }));
      setFiles([...files, ...newFiles]);
      simulateProcessing();
    }
  };

  const removeFile = (idx, e) => {
    e.stopPropagation();
    const newF = [...files];
    newF.splice(idx, 1);
    setFiles(newF);
    if (newF.length === 0) setUploadStatus('idle');
  };

  return (
    <div style={{ display: 'flex', gap: '2rem', height: '100%' }}>
      {/* Upload Modal Overlay */}
      {modalOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(11, 19, 38, 0.8)', backdropFilter: 'blur(8px)', zIndex: 1000, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <div className="insight-card" style={{ width: '600px', backgroundColor: 'var(--surface-container-high)', border: '1px solid var(--outline-variant-ghost)', padding: '2rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
               <h3 className="newsreader" style={{ fontSize: '1.5rem' }}>Upload Case Files</h3>
               <button className="icon-btn" style={{ border: 'none' }} onClick={() => setModalOpen(false)}>&times;</button>
            </div>
            
            <input 
               type="file" 
               multiple 
               ref={fileInputRef} 
               style={{ display: 'none' }} 
               onChange={handleFileChange}
               accept=".pdf,.docx,.txt"
            />
            
            <div 
               onDragOver={(e) => { e.preventDefault(); setUploadStatus('dragging'); }}
               onDragLeave={() => setUploadStatus(files.length > 0 ? 'complete' : 'idle')}
               onDrop={handleDrop}
               style={{ border: `2px dashed ${uploadStatus === 'dragging' ? 'var(--primary)' : 'var(--outline-variant-ghost)'}`, borderRadius: '8px', padding: '3rem 2rem', textAlign: 'center', backgroundColor: uploadStatus === 'dragging' ? 'rgba(190, 198, 224, 0.05)' : 'var(--surface-container-lowest)', transition: 'all 0.2s', cursor: 'pointer' }}
               onClick={() => uploadStatus !== 'scanning' && fileInputRef.current?.click()}
            >
              {(uploadStatus === 'idle' || uploadStatus === 'dragging') && files.length === 0 ? (
                <>
                  <Upload size={32} style={{ color: 'var(--tertiary)', marginBottom: '1rem', opacity: 0.8, alignSelf: 'center', margin: '0 auto 1rem' }}/>
                  <p className="body-md" style={{ color: 'var(--on-surface)', marginBottom: '0.25rem', fontWeight: 600 }}>Drag and drop files here</p>
                  <p style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', marginBottom: '1.5rem' }}>Supports PDF, DOCX, TXT (Multiple Files Allowed)</p>
                  <button className="btn-secondary" onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}>Browse Files</button>
                </>
              ) : uploadStatus === 'scanning' ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
                   <div style={{ width: '40px', height: '40px', border: '3px solid var(--surface)', borderTop: '3px solid var(--primary)', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                   <p className="body-md" style={{ color: 'var(--primary)', fontWeight: 600 }}>Scanning & Parsing Documents...</p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem', width: '100%' }}>
                   <CheckCircle2 size={40} style={{ color: '#4ade80' }}/>
                   <p className="body-md" style={{ color: '#4ade80', fontWeight: 600, marginBottom: '0.25rem' }}>Successfully Extracted {files.length} Document{files.length > 1 ? 's' : ''}</p>
                   
                   <div style={{ width: '100%', marginTop: '1rem', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {files.map((f, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--surface-container)', padding: '0.75rem 1rem', borderRadius: '4px' }}>
                           <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                             <FileIcon size={16} style={{ color: 'var(--tertiary)' }}/>
                             <span style={{ fontSize: '0.875rem', color: 'var(--on-surface)' }}>{f.name}</span>
                             <span style={{ fontSize: '0.7rem', color: 'var(--on-surface-variant)' }}>({f.size})</span>
                           </div>
                           <Trash2 size={16} style={{ color: 'var(--error)', cursor: 'pointer' }} onClick={(e) => removeFile(i, e)} />
                        </div>
                      ))}
                   </div>
                   
                   <button className="btn-secondary" style={{ marginTop: '1.5rem' }} onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}>+ Add More Files</button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Left Panel — Editor */}
      <div style={{ flex: '0 0 65%', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <h2 className="newsreader" style={{ fontSize: '2.5rem', display: 'flex', alignItems: 'center', gap: '12px', color: 'var(--on-surface)' }}>
          <FileText size={28} style={{ color: 'var(--primary)' }}/> Initialize Analysis
        </h2>
        <div style={{ flex: 1, backgroundColor: 'var(--surface-container-lowest)', borderRadius: '4px', border: '1px solid var(--surface-container)', display: 'flex', flexDirection: 'column', position: 'relative' }}>
          
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 1.5rem', borderBottom: '1px solid var(--surface-container-high)', backgroundColor: 'var(--surface-container-low)' }}>
             <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em' }}>CASE INPUT WORKSPACE</span>
             <button className="btn-secondary" style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '8px' }} onClick={() => setModalOpen(true)}>
               <Upload size={14}/> {files.length > 0 ? `Manage ${files.length} Files` : 'Upload Documents'}
             </button>
          </div>
          
          <textarea 
            className="docket-input"
            readOnly={extractedFacts}
            value={extractedFacts ? `FACTUAL MATRIX:\n\n1. The Petitioner and Respondent entered into a Sub-Contract for executing specialized construction works.\n2. The underlying Sub-Contract contained an arbitration clause (Clause 32) providing for a three-member arbitral tribunal.\n3. A dispute arose regarding delayed payments.\n4. The Petitioner invoked arbitration. The Respondent challenged the invocation, citing that the overarching Sub-Contract was unstamped under the Indian Stamp Act, 1899, rendering the arbitration clause void ab initio and unenforceable.\n5. The Petitioner seeks the appointment of an arbitrator under Section 11 of the Arbitration and Conciliation Act, 1996.\n\nKey Question: Does the non-stamping of the main commercial agreement render the embedded arbitration agreement invalid at the pre-arbitral Section 11 stage?` : ''}
            placeholder="Type or paste case facts, legal queries, or constraints here. Alternatively, upload documents to auto-extract the factual matrix."
            style={{ flex: 1, border: 'none', backgroundColor: 'transparent', resize: 'none', padding: '1.5rem', fontSize: '0.875rem', lineHeight: '1.8' }}
            onChange={() => {}} // dummy onChange for react
          />
        </div>
      </div>

      {/* Right Panel — AI Assist */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div className="insight-card" style={{ flex: 1, padding: '0', overflow: 'hidden', display: 'flex', flexDirection: 'column', border: '1px solid var(--surface-container-highest)' }}>
          <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--surface-container)', backgroundColor: 'var(--primary-container)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Zap size={18} style={{ color: 'var(--primary)' }}/>
            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--primary)' }}>Initial Intelligence Extraction</span>
          </div>
          
          {extractedFacts ? (
            <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', overflowY: 'auto' }}>
              <div>
                <div style={{ fontSize: '0.65rem', color: 'var(--on-surface-variant)', letterSpacing: '0.05em', marginBottom: '8px', fontWeight: 700 }}>IDENTIFIED LEGAL DOMAIN</div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <span className="chip" style={{ backgroundColor: 'rgba(233, 195, 73, 0.1)', color: 'var(--secondary)', border: '1px solid rgba(233, 195, 73, 0.3)' }}>Arbitration Law</span>
                  <span className="chip">Indian Stamp Act</span>
                  <span className="chip">Contract Validity</span>
                </div>
              </div>
              
              <div>
                <div style={{ fontSize: '0.65rem', color: 'var(--on-surface-variant)', letterSpacing: '0.05em', marginBottom: '8px', fontWeight: 700 }}>KEY ISSUES EXTRACTED</div>
                <ul style={{ margin: 0, paddingLeft: '1rem', fontSize: '0.875rem', color: 'var(--on-surface)', lineHeight: 1.6 }}>
                  <li>Separability of the arbitration agreement from the unstamped mother contract.</li>
                  <li>Jurisdiction of courts under Section 11 of the Arbitration & Conciliation Act regarding stamping defects.</li>
                </ul>
              </div>

              <div>
                <div style={{ fontSize: '0.65rem', color: 'var(--on-surface-variant)', letterSpacing: '0.05em', marginBottom: '8px', fontWeight: 700 }}>COMPLEXITY ESTIMATE</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ flex: 1, height: '4px', background: 'var(--surface-container-lowest)', borderRadius: '2px' }}>
                     <div style={{ width: '85%', height: '100%', background: 'var(--error)', borderRadius: '2px' }}></div>
                  </div>
                  <span style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--error)' }}>High (Constitutional Bench Conflict)</span>
                </div>
                <p style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', marginTop: '8px' }}>Detected conflicting precedent lineages (NN Global vs. SMA). Debate agents highly likely to trigger.</p>
              </div>
            </div>
          ) : (
             <div style={{ padding: '3rem', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', opacity: 0.5 }}>
               <DatabaseIcon />
               <p className="body-md" style={{ marginTop: '1rem' }}>Enter text or upload a document on the left to activate pre-analysis heuristics.</p>
             </div>
          )}
        </div>

        <button 
           className="btn-primary" 
           style={{ margin: 0, padding: '1.25rem', fontSize: '1.125rem', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '12px', opacity: extractedFacts ? 1 : 0.5, cursor: extractedFacts ? 'pointer' : 'not-allowed' }}
           onClick={() => extractedFacts && navigate('/progress')}
        >
          Begin Multi-Agent Analysis <Play fill="currentColor" size={16}/>
        </button>
      </div>
      <style>{`
        @keyframes spin { 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
};

const DatabaseIcon = () => (
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--tertiary)' }}>
    <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
  </svg>
)

export default NewCasePage;
