import React, { useState, useEffect } from 'react';
import { Network, Users, CheckCircle2, Loader2, Scale } from 'lucide-react';
import { listQueries, getQuery, getQueryStatus } from '../lib/apiClient';

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Pull debate payload out of an agent_trace.
 *  Backend stores it at trace.debate.details (scheduler wraps it) OR trace.debate directly.
 *  Must have debate_rounds with at least one entry to be considered valid. */
function extractDebate(trace) {
  if (!trace?.debate) return null;
  const d = trace.debate.details ?? trace.debate;
  if (d?.debate_rounds?.length) return d;
  return null;
}

function pct(val) {
  return Math.round((val ?? 0.5) * 100) + '%';
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ConfBadge({ value, color }) {
  return (
    <span style={{
      display: 'inline-block', fontSize: '0.65rem', fontWeight: 700,
      letterSpacing: '0.05em', padding: '2px 7px', borderRadius: '999px',
      backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
      color, border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`,
    }}>
      {pct(value)} conf.
    </span>
  );
}

function AdvocateCard({ entry, index }) {
  return (
    <div style={{ marginBottom: '1.25rem', paddingBottom: '1.25rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--on-surface-variant)', letterSpacing: '0.05em' }}>
          CASE {index + 1} · {entry.case_id}
        </span>
        <ConfBadge value={entry.advocate?.confidence} color="var(--agent-planner)" />
      </div>
      <p className="body-md" style={{ marginBottom: '0.5rem', lineHeight: 1.6 }}>
        {entry.advocate?.relevance_argument || 'No argument recorded.'}
      </p>
      {entry.advocate?.key_principles?.length > 0 && (
        <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.25rem', fontSize: '0.8rem', color: 'var(--on-surface-variant)', lineHeight: 1.7 }}>
          {entry.advocate.key_principles.map((p, i) => <li key={i}>{p}</li>)}
        </ul>
      )}
    </div>
  );
}

function OpposingCard({ entry, index }) {
  return (
    <div style={{ marginBottom: '1.25rem', paddingBottom: '1.25rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--on-surface-variant)', letterSpacing: '0.05em' }}>
          CASE {index + 1} · {entry.case_id}
        </span>
        <ConfBadge value={entry.opposing?.confidence} color="var(--agent-debate)" />
      </div>
      <p className="body-md" style={{ marginBottom: '0.5rem', lineHeight: 1.6 }}>
        {entry.opposing?.counterargument || 'No counterargument recorded.'}
      </p>
      {entry.opposing?.weaknesses?.length > 0 && (
        <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.25rem', fontSize: '0.8rem', color: 'var(--error)', lineHeight: 1.7 }}>
          {entry.opposing.weaknesses.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
      {entry.opposing?.overruled_by && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--error)', fontStyle: 'italic' }}>
          Overruled by: {entry.opposing.overruled_by}
        </div>
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

const DebateVisualization = () => {
  const [activeTab, setActiveTab] = useState('round1');
  const [debateData, setDebateData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [noData, setNoData] = useState(false);
  const [isLive, setIsLive] = useState(false);
  const [activeQueryId, setActiveQueryId] = useState(null);

  // ── Initial data fetch ──────────────────────────────────────────────────
  useEffect(() => {
    async function fetchData() {
      try {
        let debate = null;
        let qid = null;

        // 1. Check localStorage for an active/in-progress query
        try {
          const saved = localStorage.getItem('verdicto_active_query');
          if (saved) {
            const active = JSON.parse(saved);
            qid = active?.query_id;
            debate = extractDebate(active?.agent_trace);
            if (qid && active?.status !== 'complete') {
              setIsLive(true);
              setActiveQueryId(qid);
            }
          }
        } catch { /* ignore */ }

        // 2. Fall back to most recent completed query
        if (!debate) {
          const { queries } = await listQueries({ limit: 10 });
          const completed = queries?.find(q => q.status === 'complete');
          if (completed) {
            const res = await getQuery(completed.query_id);
            debate = extractDebate(res?.agent_trace);
          }
        }

        if (debate) {
          setDebateData(debate);
        } else {
          setNoData(true);
        }
      } catch (err) {
        console.error('DebateVisualization fetch error:', err);
        setNoData(true);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  // ── Live polling every 2 s ──────────────────────────────────────────────
  useEffect(() => {
    if (!isLive || !activeQueryId) return;
    const interval = setInterval(async () => {
      try {
        const statusRes = await getQueryStatus(activeQueryId);
        const debate = extractDebate(statusRes?.agent_trace);
        if (debate) {
          setDebateData(debate);
          setNoData(false);
        }
        if (statusRes?.status === 'complete' || statusRes?.status === 'failed') {
          setIsLive(false);
          clearInterval(interval);
          // If complete, fetch full result to get final debate data
          if (statusRes?.status === 'complete') {
            try {
              const full = await getQuery(activeQueryId);
              const fullDebate = extractDebate(full?.agent_trace);
              if (fullDebate) setDebateData(fullDebate);
            } catch { /* ignore */ }
          }
        }
      } catch (err) {
        console.error('Debate poll error:', err);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [isLive, activeQueryId]);

  // ── Derived data ────────────────────────────────────────────────────────
  const advocateRound = debateData?.debate_rounds?.find(r => r.round_number === 1);
  const synthesisRound = debateData?.debate_rounds?.find(r => r.round_number === 2);
  const entries = advocateRound?.entries ?? [];
  const synthesisResult = synthesisRound?.result ?? {};
  const synthesisText = synthesisResult.rationale || debateData?.consensus_rationale || 'Synthesis not yet available.';
  const finalRanking = synthesisResult.final_ranking ?? debateData?.final_ranking ?? [];
  const disputes = synthesisResult.disputes ?? debateData?.disagreement_flags ?? [];

  const avgAdvConf = entries.length
    ? entries.reduce((s, e) => s + (e.advocate?.confidence ?? 0.5), 0) / entries.length
    : null;
  const avgOppConf = entries.length
    ? entries.reduce((s, e) => s + (e.opposing?.confidence ?? 0.5), 0) / entries.length
    : null;

  // ── Loading ─────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '1rem' }}>
        <Loader2 size={36} className="spin-slow" style={{ color: 'var(--agent-debate)' }} />
        <p className="body-md" style={{ color: 'var(--on-surface-variant)' }}>Loading debate data…</p>
        <style>{`@keyframes spin-slow{100%{transform:rotate(360deg)}}.spin-slow{animation:spin-slow 1.5s linear infinite}`}</style>
      </div>
    );
  }

  // ── Live but debate not started yet ────────────────────────────────────
  if (isLive && !debateData) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '1rem' }}>
        <Loader2 size={36} className="spin-slow" style={{ color: 'var(--agent-debate)' }} />
        <h3 className="newsreader" style={{ fontSize: '1.5rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          Debate agent is running…
          <LiveBadge />
        </h3>
        <p className="body-md" style={{ color: 'var(--on-surface-variant)', textAlign: 'center', maxWidth: '420px' }}>
          The multi-agent pipeline is deliberating. This typically takes 2–5 minutes with a local LLM. Results will appear automatically.
        </p>
        <style>{`@keyframes spin-slow{100%{transform:rotate(360deg)}}.spin-slow{animation:spin-slow 1.5s linear infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}`}</style>
      </div>
    );
  }

  // ── No data ─────────────────────────────────────────────────────────────
  if (noData || !debateData) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '1rem', opacity: 0.65 }}>
        <Scale size={48} style={{ color: 'var(--agent-scheduler)' }} />
        <h3 className="newsreader" style={{ fontSize: '1.5rem' }}>No debate data yet</h3>
        <p className="body-md" style={{ color: 'var(--on-surface-variant)', textAlign: 'center', maxWidth: '400px' }}>
          Run a legal query first. Once the multi-agent pipeline completes its debate rounds, the results will appear here.
        </p>
      </div>
    );
  }

  // ── Full render ─────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%', position: 'relative' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <h2 className="newsreader" style={{ fontSize: '2rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Network size={24} style={{ color: 'var(--agent-scheduler)' }} />
          Multi-Agent Debate Simulation
          {isLive && <LiveBadge />}
        </h2>

        <div style={{ display: 'flex', gap: '0.5rem', backgroundColor: 'var(--surface-container)', padding: '0.5rem', borderRadius: '0.5rem' }}>
          {[
            { key: 'round1', label: 'Round I: Claims' },
            { key: 'round2', label: 'Round II: Rebuttals' },
            { key: 'round3', label: 'Round III: Synthesis' },
          ].map(({ key, label }) => (
            <button key={key}
              onClick={() => setActiveTab(key)}
              className={activeTab === key ? 'btn-primary' : 'btn-secondary'}
              style={{ padding: '0.5rem 1rem', border: 'none', margin: 0 }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Confidence bars — live data from Ollama */}
      <div className="insight-card" style={{ padding: '1.25rem', backgroundColor: 'var(--surface-container)' }}>
        <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--on-surface-variant)', marginBottom: '0.75rem', letterSpacing: '0.06em' }}>
          DEBATE CONFIDENCE — PER CASE (Advocate vs Opposing)
        </div>
        {entries.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {entries.map((entry, i) => {
              const advConf = (entry.advocate?.confidence ?? 0.5) * 100;
              const oppConf = (entry.opposing?.confidence ?? 0.5) * 100;
              const label = entry.case_id?.replace(/_/g, ' ') ?? `Case ${i + 1}`;
              return (
                <div key={entry.case_id || i}>
                  <div style={{ fontSize: '0.65rem', color: 'var(--on-surface-variant)', marginBottom: '3px' }}>{label}</div>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '2px' }}>
                    <span style={{ width: '60px', fontSize: '0.6rem', color: 'var(--agent-planner)', textAlign: 'right', flexShrink: 0 }}>Advocate</span>
                    <div style={{ flex: 1, height: '8px', backgroundColor: 'var(--surface-container-highest)', borderRadius: '4px', overflow: 'hidden' }}>
                      <div style={{ width: `${advConf}%`, height: '100%', backgroundColor: 'var(--agent-planner)', borderRadius: '4px', transition: 'width 0.6s ease' }} />
                    </div>
                    <span style={{ width: '28px', fontSize: '0.6rem', color: 'var(--agent-planner)' }}>{Math.round(advConf)}%</span>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <span style={{ width: '60px', fontSize: '0.6rem', color: 'var(--agent-debate)', textAlign: 'right', flexShrink: 0 }}>Opposing</span>
                    <div style={{ flex: 1, height: '8px', backgroundColor: 'var(--surface-container-highest)', borderRadius: '4px', overflow: 'hidden' }}>
                      <div style={{ width: `${oppConf}%`, height: '100%', backgroundColor: 'var(--agent-debate)', borderRadius: '4px', transition: 'width 0.6s ease' }} />
                    </div>
                    <span style={{ width: '28px', fontSize: '0.6rem', color: 'var(--agent-debate)' }}>{Math.round(oppConf)}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p style={{ fontSize: '0.8rem', color: 'var(--on-surface-variant)', opacity: 0.7 }}>Confidence data will appear once debate rounds complete.</p>
        )}
      </div>

      {/* Three-column debate cards */}
      <div style={{ flex: 1, display: 'flex', gap: '1.5rem', minHeight: 0 }}>

        {/* Left — Advocate (A1) */}
        <div className="insight-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', borderLeft: '4px solid var(--agent-planner)', overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--outline-variant-ghost)', flexShrink: 0 }}>
            <div style={{ width: '36px', height: '36px', borderRadius: '50%', backgroundColor: 'rgba(70,130,180,0.15)', display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'var(--agent-planner)', fontWeight: 'bold', border: '1px solid var(--agent-planner)', fontSize: '0.875rem' }}>A1</div>
            <div>
              <div style={{ fontSize: '1rem', fontFamily: 'Newsreader', color: 'var(--on-surface)' }}>Respondent Agent</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--agent-planner)' }}>
                Avg confidence: {avgAdvConf !== null ? pct(avgAdvConf) : '—'}
              </div>
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', paddingRight: '0.5rem' }}>
            {activeTab === 'round1' && (
              entries.length === 0
                ? <p className="body-md" style={{ color: 'var(--on-surface-variant)' }}>No advocate arguments yet.</p>
                : entries.map((entry, idx) => <AdvocateCard key={entry.case_id || idx} entry={entry} index={idx} />)
            )}
            {activeTab === 'round2' && (
              <div style={{ opacity: 0.6 }}>
                <p className="body-md" style={{ fontStyle: 'italic', color: 'var(--on-surface-variant)' }}>
                  Advocate reviews opposing counterarguments and prepares rebuttal. See Round II on the right panel.
                </p>
              </div>
            )}
            {activeTab === 'round3' && (
              <div style={{ opacity: 0.7 }}>
                <p className="body-md"><strong>CONCEDING STANCE:</strong> Agent A1 recalculates jurisprudential hierarchy based on Chief Justice synthesis.</p>
                {finalRanking.length > 0 && (
                  <div style={{ marginTop: '1rem' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--on-surface-variant)', marginBottom: '0.5rem', letterSpacing: '0.05em' }}>ACCEPTED FINAL RANKING</div>
                    {finalRanking.map((cid, i) => (
                      <div key={cid} style={{ fontSize: '0.8rem', color: 'var(--on-surface)', padding: '4px 0', borderBottom: '1px solid var(--outline-variant-ghost)' }}>
                        <span style={{ color: 'var(--agent-planner)', marginRight: '8px' }}>#{i + 1}</span>{cid.replace(/_/g, ' ')}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Center divider */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <div style={{ height: '30%', width: '1px', backgroundColor: 'var(--outline-variant-ghost)' }} />
          <Users size={28} style={{ margin: '0.75rem 0', color: 'var(--agent-debate)' }} />
          {activeTab === 'round3' && (
            <CheckCircle2 size={28} style={{ color: 'var(--agent-evaluator)', filter: 'drop-shadow(0 0 8px #98FF98)', margin: '0.5rem 0' }} />
          )}
          <div style={{ height: '30%', width: '1px', backgroundColor: 'var(--outline-variant-ghost)' }} />
        </div>

        {/* Right — Opposing (A2) / Synthesis */}
        <div className="insight-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', borderRight: '4px solid var(--agent-debate)', overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--outline-variant-ghost)', flexShrink: 0 }}>
            <div style={{ width: '36px', height: '36px', borderRadius: '50%', backgroundColor: 'rgba(255,127,80,0.15)', display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'var(--agent-debate)', fontWeight: 'bold', border: '1px solid var(--agent-debate)', fontSize: '0.875rem' }}>A2</div>
            <div>
              <div style={{ fontSize: '1rem', fontFamily: 'Newsreader', color: 'var(--on-surface)' }}>Petitioner Agent</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--agent-debate)' }}>
                Avg confidence: {avgOppConf !== null ? pct(avgOppConf) : '—'}
              </div>
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', paddingRight: '0.5rem' }}>
            {activeTab === 'round1' && (
              entries.length === 0
                ? <p className="body-md" style={{ color: 'var(--on-surface-variant)' }}>No opposing arguments yet.</p>
                : entries.map((entry, idx) => (
                    <div key={entry.case_id || idx} style={{ marginBottom: '1.25rem', paddingBottom: '1.25rem', borderBottom: '1px solid var(--outline-variant-ghost)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                        <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--on-surface-variant)', letterSpacing: '0.05em' }}>
                          CASE {idx + 1} · {entry.case_id}
                        </span>
                        <ConfBadge value={entry.opposing?.confidence} color="var(--agent-debate)" />
                      </div>
                      <p className="body-md" style={{ color: 'var(--on-surface-variant)', fontStyle: 'italic', fontSize: '0.8rem' }}>
                        Awaiting Round II rebuttal — see Rebuttals tab.
                      </p>
                    </div>
                  ))
            )}
            {activeTab === 'round2' && (
              entries.length === 0
                ? <p className="body-md" style={{ color: 'var(--on-surface-variant)' }}>No rebuttal data yet.</p>
                : entries.map((entry, idx) => <OpposingCard key={entry.case_id || idx} entry={entry} index={idx} />)
            )}
            {activeTab === 'round3' && (
              <div>
                <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--on-surface-variant)', letterSpacing: '0.06em', marginBottom: '0.75rem' }}>
                  CHIEF JUSTICE SYNTHESIS
                </div>
                <p className="body-md" style={{ lineHeight: 1.8, marginBottom: '1rem' }}>
                  {synthesisText}
                </p>
                {disputes.length > 0 && (
                  <div style={{ marginTop: '1rem' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--error)', fontWeight: 700, marginBottom: '0.5rem', letterSpacing: '0.05em' }}>UNRESOLVED DISPUTES</div>
                    {disputes.map((d, i) => (
                      <div key={i} style={{ fontSize: '0.8rem', color: 'var(--error)', padding: '4px 0', borderBottom: '1px solid var(--outline-variant-ghost)' }}>• {d}</div>
                    ))}
                  </div>
                )}
                {finalRanking.length > 0 && (
                  <div style={{ marginTop: '1rem' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--agent-evaluator)', fontWeight: 700, marginBottom: '0.5rem', letterSpacing: '0.05em' }}>CONSENSUS FINAL RANKING</div>
                    {finalRanking.map((cid, i) => (
                      <div key={cid} style={{ fontSize: '0.8rem', color: 'var(--on-surface)', padding: '4px 0', borderBottom: '1px solid var(--outline-variant-ghost)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ color: 'var(--agent-evaluator)', fontWeight: 700, minWidth: '20px' }}>#{i + 1}</span>
                        <span>{cid.replace(/_/g, ' ')}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin-slow { 100% { transform: rotate(360deg); } }
        .spin-slow { animation: spin-slow 1.5s linear infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
      `}</style>
    </div>
  );
};

function LiveBadge() {
  return (
    <span style={{
      fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em',
      backgroundColor: 'rgba(255,127,80,0.15)', color: 'var(--agent-debate)',
      border: '1px solid var(--agent-debate)', borderRadius: '4px',
      padding: '2px 8px', display: 'inline-flex', alignItems: 'center', gap: '4px',
    }}>
      <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--agent-debate)', display: 'inline-block', animation: 'pulse 1.2s ease-in-out infinite' }} />
      LIVE
    </span>
  );
}

export default DebateVisualization;
