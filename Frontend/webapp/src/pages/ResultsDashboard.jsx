import React, { useState, useEffect, useRef } from 'react';
import { FileSearch, BarChart, FileJson, Network, Flag, Send, ChevronDown, ChevronUp, Star, ShieldCheck, X, AlertTriangle, Scale, Target, BookOpen, Layers, Users, Hash, FileText, CheckCircle2, XCircle } from 'lucide-react';
import ForceGraph2D from 'react-force-graph-2d';

// Tooltip component for legal terms
const LegalTerm = ({ term, definition }) => (
  <span className="legal-term-tooltip" style={{ cursor: 'help', borderBottom: '1px dashed currentColor', position: 'relative', display: 'inline-block' }}>
    {term}
    <span className="tooltip-text" style={{ visibility: 'hidden', width: '250px', backgroundColor: 'var(--surface-container-highest)', color: 'var(--on-surface)', textAlign: 'left', borderRadius: '4px', padding: '0.75rem', position: 'absolute', zIndex: 1, bottom: '125%', left: '50%', transform: 'translateX(-50%)', opacity: 0, transition: 'opacity 0.2s', fontSize: '0.75rem', fontWeight: 'normal', fontFamily: 'sans-serif', border: '1px solid var(--outline-variant-ghost)', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}>
      <strong>{term}</strong>: {definition}
    </span>
    <style>{`
      .legal-term-tooltip:hover .tooltip-text {
        visibility: visible;
        opacity: 1;
      }
    `}</style>
  </span>
);

const ResultsDashboard = () => {
  const [activeTab, setActiveTab] = useState('summary');
  const [expandedId, setExpandedId] = useState(null);
  const [challengeOpen, setChallengeOpen] = useState(null);
  const graphRef = useRef();

  const inputCaseFacts = [
    "The Petitioner and Respondent entered into a Sub-Contract.",
    "The sub-contract contains an arbitration clause (Clause 32).",
    "The overarching Sub-Contract is completely unstamped.",
    "Petitioner invoked Section 11 of the Arbitration & Conciliation Act."
  ];

  const inputCaseIssues = [
    "Does the non-stamping of the main commercial agreement render the embedded arbitration agreement invalid?",
    "Should the Section 11 court impound the document or leave it to the arbitral tribunal?"
  ];

  const precedentData = [
    { 
      id: 1, 
      title: "In Re: Interplay Between Arbitration Agreements", 
      court: "Supreme Court (7-Judge)", year: 2023, score: "81.4%", 
      jurisdiction: "Supreme Court of India",
      judges: "D.Y. Chandrachud, S.K. Kaul, Sanjiv Khanna, B.R. Gavai, Surya Kant, J.B. Pardiwala, Manoj Misra",
      outcome: "Arbitration Valid", relief: "Section 11 motion granted. Arbitral Tribunal can be constituted.", stars: 5, 
      strength: "Binding", recommendation: "Highly Applicable Precedent",
      ratioDecidendi: "Non-stamping or insufficient stamping of an underlying contract is merely a curable defect under the Stamp Act. It does not render the arbitration agreement void ab initio. Under the doctrine of Kompetenz-Kompetenz, the arbitral tribunal, not the Section 11 referral court, must adjudicate the document's validity.",
      obiterDicta: "The Stamp Act is a fiscal statute intent on protecting revenue, not a tool to arm a litigating party with weapons of technicality to defeat the arbitration process.",
      precedentFacts: [
        "Unstamped commercial contract with an arbitration clause.",
        "Section 11 application filed in Supreme Court/High Court.",
        "Curative petition challenging previous precedents (NN Global)."
      ],
      factsComparison: {
        matching: ["Underlying commercial contract contains arbitration clause", "Application filed under Section 11", "Parent contract is entirely unstamped"],
        missing: ["Specifics of construction delay damages"],
        contradicting: []
      },
      precedentIssues: [
        "Whether an unstamped arbitration agreement is admissible in law.",
        "Whether the doctrine of separability applies to unstamped contracts."
      ],
      issuesComparison: {
        matching: ["Admissibility of unstamped arbitration agreements", "Scope of judicial interference at pre-arbitral stage"],
        additional: ["Harmonious construction of Stamp Act Section 33 and Arbitration Act Section 11(6A)"]
      },
      differences: "Negligible differences. This is a recent 7-judge curative decision matching the input structural matrix perfectly. The jurisdiction is identical. It explicitly resolves the exact legal question you are facing.",
      cites: ["Vidya Drolia (2020)", "SMS Tea Estates (Overruled)"],
      citedBy: 142,
      desc: "Curative petition reversing NN Global. Held that non-stamping of an underlying contract is a curable defect and does not render the arbitration agreement void.",
      metrics: [98, 92, 100, 95] 
    },
    { 
      id: 2, 
      title: "NN Global Mercantile Pvt. Ltd. v. Indo Unique Flame", 
      court: "Supreme Court (5-Judge)", year: 2023, score: "68.2%", 
      jurisdiction: "Supreme Court of India",
      judges: "K.M. Joseph, Ajay Rastogi, Aniruddha Bose, Hrishikesh Roy, C.T. Ravikumar",
      outcome: "Arbitration Invalid", relief: "Section 11 application dismissed pending stamp duty payment.", stars: 4, challenged: true,
      strength: "Overruled", recommendation: "Weak Precedent (Overruled)",
      ratioDecidendi: "An unstamped instrument containing an arbitration agreement is legally non-est (does not exist in law) under Section 33 of the Stamp Act, inherently rendering the arbitration clause unenforceable until the defect is cured.",
      obiterDicta: "The court cannot turn a blind eye to the mandate of the Stamp Act, which is a substantive law regarding admissibility.",
      precedentFacts: [
        "Work order containing an arbitration clause.",
        "Invocation of bank guarantee leading to dispute.",
        "Work order was entirely unstamped."
      ],
      factsComparison: {
        matching: ["Unstamped commercial contract", "Sub-contract dispute", "Section 11 invocation"],
        missing: ["None"],
        contradicting: ["Outcome explicitly overridden by subsequent jurisprudence"]
      },
      precedentIssues: [
        "Whether a court can appoint an arbitrator if the underlying document is unstamped."
      ],
      issuesComparison: {
        matching: ["Admissibility of unstamped arbitration agreements"],
        additional: ["Bank guarantee invocation nuances"]
      },
      differences: "This case has been formally overruled by a larger bench (In Re: Interplay). Do not rely on it for your core argument. Opposing counsel may try to distinguish In Re Interplay and resurrect this, but as a smaller bench (5 vs 7), it is no longer Binding.",
      cites: ["Garware Wall Ropes (2019)", "SMS Tea Estates (2011)"],
      citedBy: 86,
      desc: "Overruled by In Re: Interplay. Previously held that an unstamped instrument containing an arbitration agreement cannot be acted upon by the Court.",
      metrics: [95, 80, 85, 40] 
    },
    { 
      id: 3, 
      title: "Garware Wall Ropes Ltd. v. Coastal Marine", 
      court: "Supreme Court", year: 2019, score: "54.7%", 
      jurisdiction: "Supreme Court of India",
      judges: "R.F. Nariman, Vineet Saran",
      outcome: "Arbitration Invalid", relief: "Contract impounded; arbitration paused.", stars: 3,
      strength: "Overruled", recommendation: "Weak Precedent",
      ratioDecidendi: "The arbitration clause cannot be bifurcated from the main contract for the purpose of avoiding stamp duty. The court must impound the document before considering Section 11.",
      obiterDicta: "An agreement only becomes a contract if it is enforceable by law; without stamping, it is not enforceable.",
      precedentFacts: [
        "Sub-contract agreement containing arbitration clause.",
        "Complete failure to pay stamp duty."
      ],
      factsComparison: {
        matching: ["Unstamped sub-contract", "Section 11 litigation initiation"],
        missing: ["Corporate veil circumstances"],
        contradicting: ["Modern precedent negates this court's interpretation of separability"]
      },
      precedentIssues: [
        "Effect of non-stamping on Section 11 applications."
      ],
      issuesComparison: {
        matching: ["Duty of the court to impound unstamped documents"],
        additional: ["None"]
      },
      differences: "Strictly follows the outdated reasoning that judges cannot separate the arbitration clause from the fiscal defect of the main contract. Heavily distinguished and overruled in modern courts.",
      cites: ["SMS Tea Estates (2011)"],
      citedBy: 112,
      desc: "Affirmed the position that an arbitration clause in an unstamped commercial agreement cannot be invoked until duty is paid.",
      metrics: [85, 75, 80, 50] 
    },
    { 
      id: 4, 
      title: "SMS Tea Estates Pvt. Ltd. v. Chandmari Tea", 
      court: "Supreme Court", year: 2011, score: "49.1%", 
      jurisdiction: "Supreme Court of India",
      judges: "R.V. Raveendran, A.K. Patnaik",
      outcome: "Arbitration Invalid", relief: "Lease deed impounded.", stars: 3,
      strength: "Persuasive", recommendation: "Partially Applicable",
      ratioDecidendi: "Where an arbitration clause is contained in an unregistered but compulsorily registrable document, it can be acted upon, but if it is unstamped, it cannot be acted upon at all.",
      obiterDicta: "The court must first impound the document and ensure duty and penalty are paid before proceeding.",
      precedentFacts: [
        "Lease deed concerning tea estates.",
        "Document was both unregistered and unstamped.",
        "Contained an arbitration clause."
      ],
      factsComparison: {
        matching: ["Section 11 application", "Unstamped underlying document"],
        missing: ["Construction/Sub-contract context"],
        contradicting: ["Underlying document was a Lease Deed, not a commercial service contract"]
      },
      precedentIssues: [
        "Validity of arbitration clause in unstamped and unregistered lease deeds."
      ],
      issuesComparison: {
        matching: ["Severability of arbitrary clauses in defective contracts"],
        additional: ["Registration Act vs Stamp Act implications"]
      },
      differences: "Dealt specifically with unregistered lease deeds (property law), introducing nuances related to the Registration Act not present in standard commercial supply contracts.",
      cites: [],
      citedBy: 245,
      desc: "The genesis of the strict interpretation regarding unstamped documents.",
      metrics: [70, 80, 90, 45] 
    },
    { 
      id: 5, 
      title: "M/s Weatherford Oil Tool v. Tesac", 
      court: "Supreme Court", year: 2020, score: "32.6%", 
      jurisdiction: "Supreme Court of India",
      judges: "Indu Malhotra, Ajay Rastogi",
      outcome: "Distinguished", relief: "Arbitrator appointed conditionally.", stars: 2,
      strength: "Persuasive", recommendation: "Weak Precedent",
      ratioDecidendi: "In cases of insufficient stamping (rather than complete non-stamping), the court may appoint an arbitrator subject to the document being impounded and the deficit paid.",
      obiterDicta: "The court should facilitate arbitration rather than frustrate it at the threshold.",
      precedentFacts: [
        "Commercial contract with an arbitration clause.",
        "Contract was insufficiently stamped, not wholly unstamped."
      ],
      factsComparison: {
        matching: ["Section 11 Arbitration"],
        missing: ["Complete absence of stamping"],
        contradicting: ["Contract was partially stamped, whereas input case implies zero stamp duty paid"]
      },
      precedentIssues: [
        "Difference between insufficient stamping vs no stamping."
      ],
      issuesComparison: {
        matching: ["Impact of stamp duty on arbitration"],
        additional: ["Distinction between insufficiently stamped vs unstamped instruments"]
      },
      differences: "Crucial factual difference: The precedent dealt with 'insufficient' stamping (some duty paid), whereas the input facts state the contract was completely 'unstamped'. This differentiates the initial admissibility threshold.",
      cites: ["Garware Wall Ropes (2019)"],
      citedBy: 45,
      desc: "Dealt with insufficient stamping where reliance could be placed subject to conditional impounding.",
      metrics: [65, 60, 75, 60] 
    }
  ];

  const graphData = {
    nodes: [
      { id: "INPUT", name: "Your Input Case", val: 8, color: "#d97706", textColor: "#ffffff", type: 'input' },
      { id: "INTERPLAY", name: "In Re Interplay (2023)", val: 15, color: "#16a34a", textColor: "#ffffff", type: 'valid' },
      { id: "NNGLOBAL", name: "NN Global (2023)", val: 12, color: "#dc2626", textColor: "#ffffff", type: 'invalid' },
      { id: "GARWARE", name: "Garware Wall Ropes (2019)", val: 8, color: "#dc2626", textColor: "#ffffff", type: 'invalid' },
      { id: "SMSTEA", name: "SMS Tea Estates (2011)", val: 6, color: "#dc2626", textColor: "#ffffff", type: 'invalid' },
      { id: "WEATHERFORD", name: "Weatherford Oil (2020)", val: 5, color: "#b45309", textColor: "#ffffff", type: 'neutral' },
      { id: "VIDYA", name: "Vidya Drolia (2020)", val: 6, color: "#16a34a", textColor: "#ffffff", type: 'valid' }
    ],
    links: [
      { source: "INPUT", target: "INTERPLAY", color: "var(--secondary)" },
      { source: "INPUT", target: "NNGLOBAL", color: "var(--outline-variant-ghost)" },
      { source: "INTERPLAY", target: "NNGLOBAL", color: "#4ade80", isOverride: true },
      { source: "NNGLOBAL", target: "GARWARE", color: "var(--error)" },
      { source: "GARWARE", target: "SMSTEA", color: "var(--error)" },
      { source: "INPUT", target: "WEATHERFORD", color: "var(--outline-variant-ghost)", dashed: true },
      { source: "INTERPLAY", target: "VIDYA", color: "#4ade80" }
    ]
  };

  useEffect(() => {
    if (activeTab === 'graph' && graphRef.current) {
      setTimeout(() => {
         graphRef.current.zoomToFit(400, 50);
      }, 500);
    }
  }, [activeTab]);

  const handleExpand = (id, e) => {
    e.stopPropagation(); 
    if (challengeOpen === id) return;
    setExpandedId(id);
  };
  
  const expandedCase = precedentData.find(p => p.id === expandedId);

  return (
    <div style={{ display: 'flex', gap: '2rem', height: '100%', position: 'relative' }}>
      
      {/* Full Screen Precedent Modal */}
      {expandedCase && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(11, 19, 38, 0.95)', backdropFilter: 'blur(10px)', zIndex: 1000, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <div className="insight-card" style={{ width: '95vw', height: '95vh', backgroundColor: 'var(--surface-container-high)', border: '1px solid var(--outline-variant-ghost)', padding: '0', display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)' }}>
            
            {/* Modal Header — Section A: Case Metadata */}
            <div style={{ padding: '1.5rem 2rem', borderBottom: '1px solid var(--surface-container)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', background: 'var(--surface-container-lowest)' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.25rem' }}>
                  <h2 className="newsreader" style={{ fontSize: '2rem', color: 'var(--on-surface)' }}>{expandedCase.title}</h2>
                  <span className="chip" style={{ backgroundColor: expandedCase.outcome === 'Arbitration Valid' ? 'rgba(74, 222, 128, 0.1)' : 'rgba(239, 68, 68, 0.1)', color: expandedCase.outcome === 'Arbitration Valid' ? '#4ade80' : '#ef4444', border: expandedCase.outcome === 'Arbitration Valid' ? '1px solid rgba(74, 222, 128, 0.3)' : '1px solid rgba(239, 68, 68, 0.3)', fontSize: '0.875rem' }}>
                    {expandedCase.outcome}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
                  <span style={{ fontSize: '0.875rem', color: 'var(--on-surface-variant)', display: 'flex', alignItems: 'center', gap: '6px' }}><Scale size={14}/> {expandedCase.jurisdiction} ({expandedCase.year})</span>
                  <span style={{ fontSize: '0.875rem', color: 'var(--on-surface-variant)', display: 'flex', alignItems: 'center', gap: '6px' }}><Users size={14}/> {expandedCase.judges}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                     {[...Array(5)].map((_, idx) => (
                       <Star key={idx} size={14} fill={idx < expandedCase.stars ? "var(--secondary)" : "transparent"} stroke={idx < expandedCase.stars ? "var(--secondary)" : "var(--on-surface-variant)"} />
                     ))}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '2rem' }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '2.5rem', color: 'var(--primary)', fontWeight: 700, fontFamily: 'monospace', lineHeight: 1 }}>
                    {expandedCase.score}
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', letterSpacing: '0.1em' }}>MATCH SCORE</span>
                </div>
                <button className="icon-btn" style={{ border: 'none', background: 'var(--surface-container)', padding: '0.75rem' }} onClick={() => setExpandedId(null)}>
                  <X size={24} />
                </button>
              </div>
            </div>
            
            {/* Modal Body — Multi-Column Layout */}
            <div style={{ padding: '2rem', flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
              
              {/* Row 1: Ratio Decidendi (D), Outcome (E), Strength (G), Citation Graph Info (H) */}
              <div style={{ display: 'flex', gap: '2rem' }}>
                 
                 <div style={{ flex: '1.5', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    <div style={{ background: 'var(--primary-container)', padding: '1.5rem', borderRadius: '8px', borderLeft: '4px solid var(--primary)' }}>
                       <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem', color: 'var(--primary)', fontWeight: 700, marginBottom: '0.5rem', letterSpacing: '0.05em' }}>
                         <BookOpen size={18}/> 
                         <LegalTerm term="RATIO DECIDENDI" definition="The core legal reasoning behind the judgment. The principle that forms the precedent." /> 
                         (CORE REASONING)
                       </span>
                       <p className="newsreader" style={{ fontSize: '1.125rem', color: 'var(--on-surface)', lineHeight: 1.8 }}>
                         "{expandedCase.ratioDecidendi}"
                       </p>
                    </div>

                    <div style={{ display: 'flex', gap: '1.5rem' }}>
                       <div style={{ flex: 1, background: 'var(--surface-container)', padding: '1.25rem', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                         <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em' }}>FINAL OUTCOME / RELIEF GRANTED</span>
                         <span style={{ fontSize: '1rem', color: 'var(--on-surface)', fontWeight: 600 }}>{expandedCase.relief}</span>
                       </div>

                       <div style={{ flex: 1, background: 'var(--surface-container)', padding: '1.25rem', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                         <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em' }}>
                            <LegalTerm term="OBITER DICTA" definition="Extra comments by the judge. Not binding, but can be persuasive in arguments." /> (OPTIONAL)
                         </span>
                         <span style={{ fontSize: '0.875rem', color: 'var(--on-surface)' }}>"{expandedCase.obiterDicta}"</span>
                       </div>
                    </div>
                 </div>

                 {/* Precedential Stats and Recommendation Mini-Dash */}
                 <div style={{ flex: '0.7', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div style={{ background: 'var(--surface-container)', padding: '1.25rem', borderRadius: '8px', borderTop: `4px solid ${expandedCase.strength === 'Binding' ? '#4ade80' : 'var(--agent-similarity)'}` }}>
                       <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, marginBottom: '0.5rem', letterSpacing: '0.05em' }}>PRECEDENTIAL STRENGTH</div>
                       <div style={{ fontSize: '1.25rem', color: 'var(--on-surface)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                         {expandedCase.strength}
                         <span style={{ fontSize: '0.75rem', fontWeight: 'normal', color: 'var(--on-surface-variant)' }}>
                           (<LegalTerm term={expandedCase.strength === 'Binding' ? 'Binding' : 'Persuasive'} definition={expandedCase.strength === 'Binding' ? 'Must be followed by lower courts.' : 'Optional to follow, based on authority.'} />)
                         </span>
                       </div>
                    </div>
                    
                    <div style={{ background: 'var(--surface-container)', padding: '1.25rem', borderRadius: '8px' }}>
                       <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, marginBottom: '0.5rem', letterSpacing: '0.05em' }}>CITATION GRAPH STATS</div>
                       <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                         <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                           <span style={{ fontSize: '0.875rem', color: 'var(--on-surface)' }}>Cited By (Impact):</span>
                           <span style={{ fontSize: '0.875rem', color: 'var(--secondary)', fontWeight: 700 }}>{expandedCase.citedBy} Cases</span>
                         </div>
                         <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                           <span style={{ fontSize: '0.875rem', color: 'var(--on-surface)' }}>Key Cases Cited:</span>
                           <span style={{ fontSize: '0.875rem', color: 'var(--on-surface-variant)' }}>{expandedCase.cites.join(', ') || 'None prominent'}</span>
                         </div>
                       </div>
                    </div>

                    <div style={{ background: 'var(--surface-container-low)', padding: '1.25rem', borderRadius: '8px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                       <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, marginBottom: '0.5rem' }}>AGENT RECOMMENDATION</span>
                       <span style={{ background: 'var(--secondary)', color: 'var(--surface)', padding: '0.5rem 1rem', borderRadius: '4px', fontWeight: 700, fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Layers size={16}/> {expandedCase.recommendation}
                       </span>
                    </div>
                 </div>
              </div>

              {/* Row 2: Facts & Issues Comparison (B & C) */}
              <div style={{ display: 'flex', gap: '2rem' }}>
                 
                 {/* Section B: Facts Differential */}
                 <div style={{ flex: 1, background: 'var(--surface-container)', borderRadius: '8px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                   <div style={{ padding: '1rem 1.5rem', background: 'var(--surface-container-low)', borderBottom: '1px solid var(--surface-container-lowest)', fontSize: '0.875rem', fontWeight: 700, color: 'var(--on-surface)', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '8px' }}>
                     <FileText size={16} color="var(--primary)" /> 
                     <LegalTerm term="FACTS" definition="Actual events of the case (Who did what, when, how). Law is applied based on facts." /> ALIGNMENT
                   </div>
                   
                   {/* Facts Breakdown */}
                   <div style={{ padding: '1.5rem', display: 'flex', gap: '1rem', borderBottom: '1px solid var(--surface-container-high)' }}>
                      <div style={{ flex: 1, paddingRight: '1rem', borderRight: '1px solid var(--surface-container-high)' }}>
                         <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, display: 'block', marginBottom: '8px' }}>KEY FACTS (INPUT CASE)</span>
                         <ul style={{ margin: 0, paddingLeft: '1rem', color: 'var(--on-surface)', fontSize: '0.875rem', lineHeight: 1.5 }}>
                           {inputCaseFacts.map((f, i) => <li key={i} style={{ marginBottom: '4px' }}>{f}</li>)}
                         </ul>
                      </div>
                      <div style={{ flex: 1 }}>
                         <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, display: 'block', marginBottom: '8px' }}>KEY FACTS (PRECEDENT)</span>
                         <ul style={{ margin: 0, paddingLeft: '1rem', color: 'var(--on-surface)', fontSize: '0.875rem', lineHeight: 1.5 }}>
                           {expandedCase.precedentFacts.map((f, i) => <li key={i} style={{ marginBottom: '4px' }}>{f}</li>)}
                         </ul>
                      </div>
                   </div>

                   <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', flex: 1 }}>
                     <div>
                       <span style={{ fontSize: '0.75rem', color: '#4ade80', fontWeight: 700, letterSpacing: '0.05em', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                         <CheckCircle2 size={14} /> MATCHING FACTS
                       </span>
                       <ul style={{ margin: 0, paddingLeft: '1.2rem', gap: '0.5rem', display: 'flex', flexDirection: 'column', color: 'var(--on-surface)', fontSize: '0.875rem', lineHeight: 1.6 }}>
                         {expandedCase.factsComparison.matching.map((f, i) => <li key={i}>{f}</li>)}
                       </ul>
                     </div>

                     <div style={{ display: 'flex', gap: '1rem' }}>
                       <div style={{ flex: 1 }}>
                         <span style={{ fontSize: '0.75rem', color: 'var(--agent-similarity)', fontWeight: 700, letterSpacing: '0.05em', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                           <AlertTriangle size={14} /> MISSING FACTS
                         </span>
                         <ul style={{ margin: 0, paddingLeft: '1.2rem', gap: '0.5rem', display: 'flex', flexDirection: 'column', color: 'var(--on-surface-variant)', fontSize: '0.875rem', lineHeight: 1.6 }}>
                           {expandedCase.factsComparison.missing.length > 0 ? expandedCase.factsComparison.missing.map((f, i) => <li key={i}>{f}</li>) : <li>None</li>}
                         </ul>
                       </div>
                       <div style={{ flex: 1 }}>
                         <span style={{ fontSize: '0.75rem', color: 'var(--error)', fontWeight: 700, letterSpacing: '0.05em', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                           <XCircle size={14} /> CONTRADICTING FACTS
                         </span>
                         <ul style={{ margin: 0, paddingLeft: '1.2rem', gap: '0.5rem', display: 'flex', flexDirection: 'column', color: 'var(--on-surface-variant)', fontSize: '0.875rem', lineHeight: 1.6 }}>
                           {expandedCase.factsComparison.contradicting.length > 0 ? expandedCase.factsComparison.contradicting.map((f, i) => <li key={i}>{f}</li>) : <li>None</li>}
                         </ul>
                       </div>
                     </div>
                   </div>
                </div>

                {/* Section C: Issues Differential */}
                <div style={{ flex: 1, background: 'var(--surface-container)', borderRadius: '8px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                   <div style={{ padding: '1rem 1.5rem', background: 'var(--surface-container-low)', borderBottom: '1px solid var(--surface-container-lowest)', fontSize: '0.875rem', fontWeight: 700, color: 'var(--on-surface)', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '8px' }}>
                     <Hash size={16} color="var(--secondary)" /> 
                     <LegalTerm term="ISSUES" definition="Legal questions the court must answer (e.g. Was contract valid?)." /> COMPARISON
                   </div>
                   
                   <div style={{ padding: '1.5rem', display: 'flex', gap: '1rem', borderBottom: '1px solid var(--surface-container-high)' }}>
                      <div style={{ flex: 1, paddingRight: '1rem', borderRight: '1px solid var(--surface-container-high)' }}>
                         <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, display: 'block', marginBottom: '8px' }}>LEGAL QUESTIONS (INPUT CASE)</span>
                         <ul style={{ margin: 0, paddingLeft: '1rem', color: 'var(--on-surface)', fontSize: '0.875rem', lineHeight: 1.5 }}>
                           {inputCaseIssues.map((f, i) => <li key={i} style={{ marginBottom: '4px' }}>{f}</li>)}
                         </ul>
                      </div>
                      <div style={{ flex: 1 }}>
                         <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, display: 'block', marginBottom: '8px' }}>LEGAL QUESTIONS (PRECEDENT)</span>
                         <ul style={{ margin: 0, paddingLeft: '1rem', color: 'var(--on-surface)', fontSize: '0.875rem', lineHeight: 1.5 }}>
                           {expandedCase.precedentIssues.map((f, i) => <li key={i} style={{ marginBottom: '4px' }}>{f}</li>)}
                         </ul>
                      </div>
                   </div>

                   <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', flex: 1 }}>
                     <div>
                       <span style={{ fontSize: '0.75rem', color: 'var(--secondary)', fontWeight: 700, letterSpacing: '0.05em', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                         <CheckCircle2 size={14} /> MATCHING ISSUES
                       </span>
                       <ul style={{ margin: 0, paddingLeft: '1.2rem', gap: '0.5rem', display: 'flex', flexDirection: 'column', color: 'var(--on-surface)', fontSize: '0.875rem', lineHeight: 1.6 }}>
                         {expandedCase.issuesComparison.matching.map((f, i) => <li key={i}>{f}</li>)}
                       </ul>
                     </div>

                     <div>
                       <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                         <Hash size={14} /> ADDITIONAL ISSUES IN PRECEDENT
                       </span>
                       <ul style={{ margin: 0, paddingLeft: '1.2rem', gap: '0.5rem', display: 'flex', flexDirection: 'column', color: 'var(--on-surface-variant)', fontSize: '0.875rem', lineHeight: 1.6 }}>
                         {expandedCase.issuesComparison.additional.length > 0 ? expandedCase.issuesComparison.additional.map((f, i) => <li key={i}>{f}</li>) : <li>None</li>}
                       </ul>
                     </div>
                   </div>
                </div>

              </div>

              {/* Row 3: Similarity Breakdown (F) and Differences/Vulnerability Warning (I) */}
              <div style={{ display: 'flex', gap: '2rem' }}>
                 
                 {/* Section F: Similarity Feature Matrix */}
                 <div style={{ flex: '0.6', background: 'var(--surface-container)', padding: '2rem', borderRadius: '8px' }}>
                   <div style={{ fontSize: '0.875rem', color: 'var(--tertiary)', fontWeight: 700, marginBottom: '2rem', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '8px' }}>
                     <Target size={18}/> AI SIMILARITY BREAKDOWN
                   </div>
                   
                   <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', alignItems: 'center' }}>
                     {/* Radar */}
                     <div style={{ width: '150px', height: '150px', marginBottom: '1rem' }}>
                       <svg width="150" height="150" viewBox="0 0 100 100">
                         <polygon points="50,10 90,50 50,90 10,50" fill="none" stroke="var(--outline-variant-ghost)" />
                         <polygon points="50,30 70,50 50,70 30,50" fill="none" stroke="var(--outline-variant-ghost)" />
                         <line x1="50" y1="10" x2="50" y2="90" stroke="var(--outline-variant-ghost)"/>
                         <line x1="10" y1="50" x2="90" y2="50" stroke="var(--outline-variant-ghost)"/>
                         
                         <text x="50" y="5" fontSize="4" fill="var(--on-surface-variant)" textAnchor="middle">Semantic</text>
                         <text x="95" y="52" fontSize="4" fill="var(--on-surface-variant)">Structural</text>
                         <text x="50" y="98" fontSize="4" fill="var(--on-surface-variant)" textAnchor="middle">Weight</text>
                         <text x="5" y="52" fontSize="4" fill="var(--on-surface-variant)" textAnchor="end">Outcome</text>
                         
                         <polygon 
                           points={`
                             50,${50 - (expandedCase.metrics[0]*0.4)} 
                             ${50 + (expandedCase.metrics[1]*0.4)},50 
                             50,${50 + (expandedCase.metrics[2]*0.4)} 
                             ${50 - (expandedCase.metrics[3]*0.4)},50
                           `} 
                           fill={`rgba(233, 195, 73, 0.3)`}
                           stroke={"var(--secondary)"} strokeWidth="1.5"
                         />
                       </svg>
                     </div>
                     
                     <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        {['Semantic Similarity', 'Structural (Facts/Issues)', 'Precedential Weight', 'Outcome Similarity'].map((label, idx) => (
                          <div key={idx}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '0.75rem' }}>
                              <span style={{ color: 'var(--on-surface-variant)' }}>{label}</span>
                              <span style={{ color: 'var(--on-surface)', fontWeight: 600 }}>{expandedCase.metrics[idx]}%</span>
                            </div>
                            <div style={{ height: '4px', background: 'var(--surface-container-lowest)', borderRadius: '2px' }}>
                              <div style={{ height: '100%', width: `${expandedCase.metrics[idx]}%`, background: 'var(--primary)', borderRadius: '2px' }}></div>
                            </div>
                          </div>
                        ))}
                     </div>
                   </div>
                 </div>

                 {/* Section I: Why this might not apply */}
                 <div style={{ flex: '1.4', background: expandedCase.outcome === 'Distinguished' || expandedCase.strength === 'Overruled' ? 'rgba(239, 68, 68, 0.1)' : 'var(--surface-container-low)', padding: '2rem', borderRadius: '8px', borderLeft: expandedCase.outcome === 'Distinguished' || expandedCase.strength === 'Overruled' ? '4px solid var(--error)' : '4px solid var(--agent-similarity)', display: 'flex', flexDirection: 'column' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '1rem', color: expandedCase.outcome === 'Distinguished' || expandedCase.strength === 'Overruled' ? 'var(--error)' : 'var(--agent-similarity)', fontWeight: 700, marginBottom: '1.5rem', letterSpacing: '0.05em' }}>
                      <AlertTriangle size={20}/> DIFFERENCES & VULNERABILITY (WHY THIS MIGHT NOT APPLY)
                    </span>
                    <p className="body-md" style={{ color: 'var(--on-surface)', lineHeight: 1.8, fontSize: '1rem' }}>
                      {expandedCase.differences}
                    </p>
                    
                    <div style={{ marginTop: 'auto', background: 'var(--surface-container)', padding: '1rem', borderRadius: '4px', borderLeft: '2px solid var(--primary)' }}>
                      <span style={{ fontSize: '0.75rem', fontWeight: 'bold', color: 'var(--primary)', display: 'block', marginBottom: '4px' }}>EXPERT INSIGHT</span>
                      <span style={{ fontSize: '0.875rem', color: 'var(--on-surface-variant)' }}>
                        Lawyers distinguish cases to prove why a past ruling shouldn't apply to their facts. Anticipate opposing counsel exploiting the "Contradicting Facts" or "Missing Facts" outlined above.
                      </span>
                    </div>
                 </div>

              </div>

            </div>
          </div>
        </div>
      )}

      {/* Main Page Content - Left Panel (Precedent List) */}
      <div style={{ flex: '0 0 540px', display: 'flex', flexDirection: 'column', gap: '1.5rem', position: 'relative' }}>
        <h3 className="newsreader" style={{ fontSize: '1.5rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <FileSearch size={20} style={{ color: 'var(--primary)' }}/> Ranked 
          <LegalTerm term="Precedents" definition="A previous court decision used to decide a new case. Guides future rulings." />
        </h3>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', overflowY: 'auto', paddingRight: '0.5rem', paddingBottom: '2rem' }}>
          {precedentData.map((p, i) => (
            <div key={p.id} className="insight-card" style={{ padding: '1.5rem', backgroundColor: expandedId === p.id ? 'var(--surface-container-highest)' : (i === 0 ? 'var(--surface-container-high)' : 'var(--surface-container)'), border: i === 0 ? '1px solid var(--secondary)' : '1px solid transparent', position: 'relative', overflow: 'hidden', flexShrink: 0 }}>
              
              <div 
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', cursor: 'pointer' }}
                onClick={(e) => handleExpand(p.id, e)}
              >
                <div style={{ flex: 1, paddingRight: '1rem' }}>
                  <h4 className="newsreader" style={{ fontSize: '1.125rem', color: 'var(--on-surface)', marginBottom: '0.25rem' }}>{p.title}</h4>
                  
                  <div className="jurisdiction-timeline" style={{ marginBottom: '8px' }}>
                    <div className="court-node" style={{ opacity: 0.6 }} title="High Court"></div>
                    <div className="court-line"></div>
                    <div className="court-node active" title={`${p.court} (${p.year})`}></div>
                    <span style={{ fontSize: '0.7rem', color: 'var(--on-surface-variant)', marginLeft: '8px' }}>{p.court} ({p.year})</span>
                  </div>
                  
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                     {[...Array(5)].map((_, idx) => (
                       <Star key={idx} size={12} fill={idx < p.stars ? "var(--secondary)" : "transparent"} stroke={idx < p.stars ? "var(--secondary)" : "var(--on-surface-variant)"} />
                     ))}
                  </div>
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '12px' }}>
                  <div style={{ fontSize: '1.125rem', color: i === 0 ? 'var(--secondary)' : 'var(--primary)', fontWeight: 700, fontFamily: 'monospace' }}>
                    {p.score}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <Flag 
                      size={14} 
                      style={{ color: p.challenged ? 'var(--agent-similarity)' : 'var(--on-surface-variant)', cursor: 'pointer' }} 
                      onClick={(e) => { e.stopPropagation(); setChallengeOpen(p.id === challengeOpen ? null : p.id); setExpandedId(null); }}
                    />
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '1rem' }}>
                <span className="chip" style={{ backgroundColor: p.outcome === 'Arbitration Valid' ? 'rgba(74, 222, 128, 0.1)' : 'var(--surface-bright)', color: p.outcome === 'Arbitration Valid' ? '#4ade80' : 'inherit', border: p.outcome === 'Arbitration Valid' ? '1px solid rgba(74, 222, 128, 0.3)' : 'none' }}>
                  {p.outcome}
                </span>
                {i === 0 && !p.challenged && <span style={{ fontSize: '0.7rem', color: 'var(--secondary)', fontWeight: 600 }}>Dominant Precedent</span>}
                {p.challenged && <span style={{ fontSize: '0.7rem', color: 'var(--agent-similarity)', fontWeight: 700 }}>Challenged by User</span>}
              </div>

              <div className={`challenge-drawer ${challengeOpen === p.id ? 'open' : ''}`}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--agent-similarity)' }}>ANNOTATE PRECEDENT</span>
                  <span style={{ cursor: 'pointer', fontSize: '1rem' }} onClick={(e) => { e.stopPropagation(); setChallengeOpen(null); }}>&times;</span>
                </div>
                <select className="docket-input" style={{ fontSize: '0.75rem', marginBottom: '1rem', background: 'transparent' }} onClick={e => e.stopPropagation()}>
                  <option>Wrongly Included</option>
                  <option>Wrong Outcome Classification</option>
                  <option>Missing Key Case</option>
                </select>
                <textarea className="docket-input" rows="3" placeholder="Explain the reasoning (e.g., this case was factually distinguished later)..." style={{ fontSize: '0.75rem', marginBottom: '1rem', resize: 'none' }} onClick={e => e.stopPropagation()}></textarea>
                <button className="btn-secondary" style={{ marginTop: 'auto', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', padding: '0.5rem' }} onClick={e => e.stopPropagation()}>
                  <Send size={14}/> Submit Annotation
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Main Page Content - Right Panel (Summary / Graph Tabs) */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem', minWidth: 0 }}>
        
        {/* Dynamic Context Tabs */}
        <div style={{ display: 'flex', gap: '1rem', flexShrink: 0 }}>
          <button className={`nav-link ${activeTab === 'summary' ? 'active' : ''}`} style={{ flex: 1, justifyContent: 'center', border: 'none', background: activeTab === 'summary' ? 'var(--surface-container-high)' : 'transparent', color: activeTab === 'summary' ? 'var(--primary)' : 'var(--on-surface-variant)' }} onClick={() => setActiveTab('summary')}>
            <BarChart size={18}/> Summary Breakdown
          </button>
          <button className={`nav-link ${activeTab === 'graph' ? 'active' : ''}`} style={{ flex: 1, justifyContent: 'center', border: 'none', background: activeTab === 'graph' ? 'var(--surface-container-high)' : 'transparent', color: activeTab === 'graph' ? 'var(--primary)' : 'var(--on-surface-variant)' }} onClick={() => setActiveTab('graph')}>
            <Network size={18}/> Citation / Case Authority Graph
          </button>
        </div>

        {activeTab === 'summary' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', overflowY: 'auto', flex: 1 }}>
            <div className="hero-section" style={{ margin: 0, padding: '2.5rem', height: 'auto', display: 'flex', flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', overflow: 'visible' }}>
              <div className="hero-content" style={{ zIndex: 2 }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--primary-fixed-dim)', letterSpacing: '0.1em', marginBottom: '0.5rem' }}>FINAL PREDICTED OUTCOME</div>
                <h2 className="newsreader" style={{ fontSize: '2.5rem', color: 'var(--on-background)', marginBottom: '1rem' }}>Arbitration Will Proceed</h2>
                <p className="body-md" style={{ maxWidth: '600px', lineHeight: '1.8' }}>
                  The 7-Judge Constitutional Bench ruling in <em>In Re: Interplay (2023)</em> supersedes all historical precedent limiting Section 11 invocation due to unstamped parent documents. Defendant's objection is procedurally void under current binding <LegalTerm term="Case Law" definition="Law created by previous judicial decisions. Guides future interpretations." />.
                </p>
              </div>
              
              <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.5rem', background: 'var(--surface-container-highest)', padding: '1.5rem', borderRadius: '8px', border: '1px solid var(--secondary)' }}>
                {/* VERDICTO SEAL */}
                <div className="verdicto-seal">
                   <div className="verdicto-seal-tooltip">
                     <strong>VERDICTO SEAL AWARDED</strong><br/>
                     System consensus highly stable (Variance 0.12). Supreme Court constitutional authority directly superimposes input matrix.
                   </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
                  <span className="playfair" style={{ fontSize: '4rem', fontWeight: 700, color: '#4ade80', lineHeight: 1 }}>94</span>
                  <span style={{ fontSize: '1rem', color: 'var(--on-surface-variant)' }}>/ 100</span>
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', fontWeight: 700, letterSpacing: '0.05em' }}>VERDICTO COMPOSITE PREDICTION</span>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '2rem' }}>
              <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container)' }}>
                <h4 className="newsreader" style={{ fontSize: '1.25rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <BarChart size={18} style={{ color: 'var(--primary)' }}/> Structural Similarity
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  {[
                    { label: 'Separability Doctrine', fill: 98 },
                    { label: 'Section 11 Invocation', fill: 95 },
                    { label: 'Fiscal vs Void Defect', fill: 99 },
                    { label: 'Corporate Veil/Entity', fill: 12 }
                  ].map((metric, i) => (
                    <div key={i}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.875rem' }}>
                        <span style={{ color: 'var(--on-surface-variant)' }}>{metric.label}</span>
                        <span style={{ color: 'var(--on-surface)', fontFamily: 'monospace' }}>{metric.fill}%</span>
                      </div>
                      <div style={{ height: '6px', width: '100%', backgroundColor: 'var(--surface-container-lowest)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${metric.fill}%`, backgroundColor: metric.fill > 50 ? 'var(--primary)' : 'var(--error)' }}></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--surface-container-low)' }}>
                <h4 className="newsreader" style={{ fontSize: '1.25rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <FileJson size={18} style={{ color: 'var(--tertiary)' }}/> Deep Explainability
                </h4>
                <p className="body-md" style={{ marginBottom: '1rem' }}>
                  The <strong>Scheduler Agent</strong> actively routed a pipeline repair. In pass 2, it detected a collision between <em>NN Global (2023)</em> and <em>In Re: Interplay (2023)</em>. 
                </p>
                <div style={{ padding: '1rem', backgroundColor: 'var(--surface-container-lowest)', borderRadius: '0.25rem', borderLeft: `3px solid var(--agent-evaluator)` }}>
                  <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--agent-evaluator)', fontWeight: 700, marginBottom: '0.25rem' }}>EVALUATOR NODE RESOLUTION</span>
                  <span style={{ fontSize: '0.875rem', color: 'var(--on-surface)', lineHeight: 1.6 }}>By routing through the Debate Agent, the model strictly followed the <LegalTerm term="Doctrine of Precedent" definition="Courts follow previous decisions for consistency." />, successfully ranking the 7-Bench Curative decision higher in authoritative hierarchy over the 5-Bench NN Global ruling.</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Cinematic Force Graph View contained beautifully */}
        {activeTab === 'graph' && (
          <div className="insight-card" style={{ flex: 1, backgroundColor: 'var(--background)', padding: 0, position: 'relative', overflow: 'hidden', border: '1px solid var(--surface-container-high)', borderRadius: '8px', cursor: 'grab', minHeight: '500px', display: 'flex', flexDirection: 'column' }}>
            <div style={{ position: 'absolute', top: '1rem', left: '1rem', right: '1rem', display: 'flex', justifyContent: 'space-between', zIndex: 10, pointerEvents: 'none' }}>
              <div style={{ background: 'rgba(11, 19, 38, 0.8)', padding: '0.5rem 1rem', borderRadius: '4px', fontSize: '0.75rem', color: 'var(--on-surface-variant)', display: 'flex', gap: '1rem', alignItems: 'center', backdropFilter: 'blur(4px)', pointerEvents: 'auto' }}>
                <strong>CITATION DEPTH:</strong>
                <input type="range" min="1" max="4" defaultValue="3" style={{ cursor: 'pointer' }} />
                <span>3 Hops</span>
              </div>
              <div style={{ background: 'rgba(11, 19, 38, 0.8)', padding: '0.5rem 1rem', borderRadius: '4px', fontSize: '0.75rem', color: 'var(--on-surface-variant)', display: 'flex', gap: '1rem', backdropFilter: 'blur(4px)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#4ade80' }}></div> Validates / Relies On</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--error)' }}></div> Overrules / Distinguishes</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--secondary)' }}></div> Input Focus Node</span>
              </div>
            </div>

            <div style={{ flex: 1 }}>
              <ForceGraph2D
                ref={graphRef}
                graphData={graphData}
                backgroundColor="var(--background)"
                nodeRelSize={1}
                nodeColor={node => node.color}
                linkColor={link => link.color}
                linkWidth={link => link.isOverride ? 4 : 2}
                linkLineDash={link => link.dashed ? [5, 5] : []}
                linkDirectionalParticles={2}
                linkDirectionalParticleSpeed={0.01}
                width={800} // Force explicit dimensions to prevent CSS flexbox blowouts
                height={600}
                nodeCanvasObject={(node, ctx, globalScale) => {
                  const label = node.name;
                  const fontSize = 12/globalScale;
                  ctx.font = `bold ${fontSize}px Sans-Serif`;
                  
                  ctx.beginPath();
                  ctx.arc(node.x, node.y, node.val, 0, 2 * Math.PI, false);
                  ctx.fillStyle = node.color;
                  ctx.fill();
                  ctx.shadowColor = node.color;
                  ctx.shadowBlur = 10;
                  
                  const textWidth = ctx.measureText(label).width;
                  const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2);
                  
                  ctx.textAlign = 'center';
                  ctx.textBaseline = 'middle';
                  ctx.shadowBlur = 0; 
                  ctx.fillStyle = node.textColor;
                  ctx.fillText(label, node.x, node.y);
                }}
                onNodeClick={node => {
                  graphRef.current.centerAt(node.x, node.y, 1000);
                  graphRef.current.zoom(8, 2000);
                }}
              />
            </div>
          </div>
        )}
      </div>
      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  );
};

export default ResultsDashboard;
