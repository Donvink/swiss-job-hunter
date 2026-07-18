import { useState, useEffect, useCallback } from "react";
import { API } from "./api.js";
import { INTERVIEW_TYPE_META, INTERVIEW_FORMAT_META, INTERVIEW_OUTCOME_META } from "./interviewMeta.js";

const inp = {
  width:"100%",padding:"6px 9px",borderRadius:4,
  background:"#faf7f2",border:"1px solid #c8c2b4",
  color:"#4a4238",fontSize:11,
};

function ActionBtn({ onClick, label, icon, color="#4d7ab5", disabled, small, loading }) {
  return (
    <button onClick={onClick} disabled={disabled||loading} style={{
      display:"flex",alignItems:"center",gap:6,
      padding: small ? "4px 8px" : "7px 12px",
      borderRadius:5,border:`1px solid ${color}50`,
      background:`${color}10`,color:disabled?"#b0a898":color,
      fontSize: small?10:11,fontWeight:700,letterSpacing:"0.05em",
      cursor:disabled||loading?"not-allowed":"pointer",
      fontFamily:"monospace",opacity:disabled?0.45:1,
      whiteSpace:"nowrap",
    }}>
      <span>{loading?"⟳":icon}</span>{loading?"…":label}
    </button>
  );
}

function RoundStars({ rating, onRate }) {
  const [hovered, setHovered] = useState(null);
  const current = hovered ?? rating ?? 0;
  return (
    <span style={{display:"inline-flex",gap:1,lineHeight:1}}>
      {[1,2,3,4,5].map(n => (
        <span key={n}
          onClick={()=>onRate(n === rating ? 0 : n)}
          onMouseEnter={() => setHovered(n)}
          onMouseLeave={() => setHovered(null)}
          style={{cursor:"pointer", fontSize:14, color: n <= current ? "#c09030" : "#d4cfc4"}}>★</span>
      ))}
    </span>
  );
}

function fmtDt(iso) {
  if (!iso) return "no date set";
  const d = new Date(iso);
  return d.toLocaleDateString("de-CH",{day:"2-digit",month:"2-digit",year:"numeric"}) + " " +
         d.toLocaleTimeString("de-CH",{hour:"2-digit",minute:"2-digit"});
}

function toInputDt(iso) {
  return iso ? iso.slice(0,16) : "";
}

// ── Add-round form ───────────────────────────────────────────────────────────

function AddRoundForm({ jobId, nextRound, onDone, onCancel }) {
  const [type, setType] = useState("phone_screen");
  const [format, setFormat] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [interviewer, setInterviewer] = useState("");
  const [duration, setDuration] = useState("");
  const [prepNotes, setPrepNotes] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      await fetch(`${API}/jobs/${jobId}/interviews`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          round_number: nextRound,
          interview_type: type,
          format: format || null,
          scheduled_at: scheduledAt || null,
          interviewer_name: interviewer || null,
          duration_minutes: duration ? parseInt(duration) : null,
          prep_notes: prepNotes || null,
        }),
      });
      onDone();
    } finally { setLoading(false); }
  };

  return (
    <div style={{background:"#e8e3d8",border:"1px solid #c8c2b4",borderRadius:6,padding:12,marginBottom:12}}>
      <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:6}}>ROUND {nextRound}</div>
      <div style={{display:"flex",flexWrap:"wrap",gap:4,marginBottom:6}}>
        {Object.keys(INTERVIEW_TYPE_META).map(t=>{
          const m = INTERVIEW_TYPE_META[t];
          return (
            <button key={t} onClick={()=>setType(t)} style={{
              fontSize:9,padding:"2px 7px",borderRadius:3,
              border:`1px solid ${type===t?m.color+"50":"#c8c2b4"}`,
              background:type===t?`${m.color}12`:"transparent",
              color:type===t?m.color:"#8a8278",
              cursor:"pointer",fontFamily:"monospace",fontWeight:600,
            }}>{m.icon} {m.label}</button>
          );
        })}
      </div>
      <div style={{display:"flex",flexWrap:"wrap",gap:4,marginBottom:8}}>
        <button onClick={()=>setFormat("")} style={{
          fontSize:9,padding:"2px 7px",borderRadius:3,
          border:`1px solid ${format===""?"#8a827850":"#c8c2b4"}`,
          background:format===""?"#8a827812":"transparent",
          color:format===""?"#8a8278":"#a8a098",
          cursor:"pointer",fontFamily:"monospace",fontWeight:600,
        }}>— no format —</button>
        {Object.keys(INTERVIEW_FORMAT_META).map(f=>{
          const m = INTERVIEW_FORMAT_META[f];
          return (
            <button key={f} onClick={()=>setFormat(f)} style={{
              fontSize:9,padding:"2px 7px",borderRadius:3,
              border:`1px solid ${format===f?m.color+"50":"#c8c2b4"}`,
              background:format===f?`${m.color}12`:"transparent",
              color:format===f?m.color:"#8a8278",
              cursor:"pointer",fontFamily:"monospace",fontWeight:600,
            }}>{m.icon} {m.label}</button>
          );
        })}
      </div>
      <input type="datetime-local" value={scheduledAt} onChange={e=>setScheduledAt(e.target.value)}
        style={{...inp,marginBottom:6,fontSize:10}}/>
      <div style={{display:"flex",gap:6,marginBottom:6}}>
        <input value={interviewer} onChange={e=>setInterviewer(e.target.value)}
          placeholder="Interviewer (optional)" style={{...inp,flex:1,fontSize:10}}/>
        <input type="number" min={0} value={duration} onChange={e=>setDuration(e.target.value)}
          placeholder="min" style={{...inp,width:60,fontSize:10,textAlign:"center"}}/>
      </div>
      <textarea value={prepNotes} onChange={e=>setPrepNotes(e.target.value)}
        placeholder="Prep notes (optional)..." style={{...inp,minHeight:50,resize:"vertical",marginBottom:8,fontFamily:"inherit",fontSize:10}}/>
      <div style={{display:"flex",gap:6,justifyContent:"flex-end"}}>
        <ActionBtn onClick={onCancel} label="Cancel" icon="✕" color="#8a8278" small/>
        <ActionBtn onClick={submit} loading={loading} label="Add" icon="+" color="#4d7ab5" small/>
      </div>
    </div>
  );
}

// ── Question row ──────────────────────────────────────────────────────────────

function QuestionRow({ question, onSaved, onDeleted }) {
  const [q, setQ] = useState(question.question);
  const [answer, setAnswer] = useState(question.my_answer || "");
  const [optimizing, setOptimizing] = useState(false);

  const save = async (patch) => {
    await fetch(`${API}/interview-questions/${question.id}`, {
      method:"PATCH", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(patch),
    });
    onSaved();
  };

  const optimize = async () => {
    setOptimizing(true);
    try {
      await fetch(`${API}/interview-questions/${question.id}/optimize-answer`, { method:"POST" });
      onSaved();
    } finally { setOptimizing(false); }
  };

  const del = async () => {
    await fetch(`${API}/interview-questions/${question.id}`, { method:"DELETE" });
    onDeleted();
  };

  return (
    <div style={{background:"#f5f0e8",border:"1px solid #d4cfc4",borderRadius:5,padding:"9px 11px",marginBottom:8}}>
      <div style={{display:"flex",gap:6,alignItems:"flex-start"}}>
        <textarea value={q} onChange={e=>setQ(e.target.value)}
          onBlur={()=>{ if (q.trim() && q!==question.question) save({question:q}); }}
          placeholder="Question..." style={{...inp,flex:1,fontWeight:700,fontFamily:"inherit",resize:"vertical",minHeight:32}}/>
        <button onClick={del} title="Delete question" style={{
          border:"none",background:"none",color:"#d4cfc4",cursor:"pointer",
          fontSize:12,lineHeight:1,flexShrink:0,padding:"4px 2px",
        }}>✕</button>
      </div>
      <textarea value={answer} onChange={e=>setAnswer(e.target.value)}
        onBlur={()=>{ if (answer!==(question.my_answer||"")) save({my_answer:answer}); }}
        placeholder="My answer..." style={{...inp,marginTop:6,minHeight:50,resize:"vertical",fontFamily:"inherit"}}/>

      <div style={{marginTop:6,display:"flex",justifyContent:"flex-end"}}>
        <ActionBtn onClick={optimize} loading={optimizing} disabled={!answer.trim()}
          label="AI 优化" icon="✨" color="#9070c8" small/>
      </div>

      {question.optimized_answer && (
        <div style={{background:"#e4dfd4",borderRadius:5,padding:"9px 11px",
          border:"1px solid #d4cfc4",fontSize:10,marginTop:8}}>
          {question.llm_feedback && (
            <div style={{color:"#a87c2e",fontStyle:"italic",marginBottom:6,lineHeight:1.5}}>
              {question.llm_feedback}
            </div>
          )}
          <div style={{fontWeight:700,color:"#9070c8",marginBottom:4,fontSize:9,letterSpacing:"0.05em"}}>
            OPTIMIZED ANSWER
          </div>
          <div style={{color:"#2c2820",lineHeight:1.6,whiteSpace:"pre-wrap"}}>
            {question.optimized_answer}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Add-question form ────────────────────────────────────────────────────────

function AddQuestionForm({ interviewId, onDone, onCancel }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!question.trim()) return;
    setLoading(true);
    try {
      await fetch(`${API}/interviews/${interviewId}/questions`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ question, my_answer: answer || null }),
      });
      onDone();
    } finally { setLoading(false); }
  };

  return (
    <div style={{background:"#e8e3d8",border:"1px solid #c8c2b4",borderRadius:6,padding:10,marginBottom:8}}>
      <input value={question} onChange={e=>setQuestion(e.target.value)}
        placeholder="Question..." style={{...inp,marginBottom:6,fontSize:10}}/>
      <textarea value={answer} onChange={e=>setAnswer(e.target.value)}
        placeholder="My answer (optional)..." style={{...inp,minHeight:44,resize:"vertical",marginBottom:8,fontFamily:"inherit",fontSize:10}}/>
      <div style={{display:"flex",gap:6,justifyContent:"flex-end"}}>
        <ActionBtn onClick={onCancel} label="Cancel" icon="✕" color="#8a8278" small/>
        <ActionBtn onClick={submit} loading={loading} disabled={!question.trim()} label="Add" icon="+" color="#4d7ab5" small/>
      </div>
    </div>
  );
}

// ── Round card ────────────────────────────────────────────────────────────────

function RoundCard({ interview, expanded, onToggle, onChanged, onDeleted }) {
  const [wentWell, setWentWell] = useState(interview.went_well || "");
  const [toImprove, setToImprove] = useState(interview.to_improve || "");
  const [notes, setNotes] = useState(interview.notes || "");
  const [savingRetro, setSavingRetro] = useState(false);
  const [addingQuestion, setAddingQuestion] = useState(false);

  useEffect(() => {
    setWentWell(interview.went_well || "");
    setToImprove(interview.to_improve || "");
    setNotes(interview.notes || "");
  }, [interview.id, interview.updated_at]);

  const patch = async (body) => {
    await fetch(`${API}/interviews/${interview.id}`, {
      method:"PATCH", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(body),
    });
    onChanged();
  };

  const saveRetro = async () => {
    setSavingRetro(true);
    try { await patch({ went_well: wentWell, to_improve: toImprove, notes }); }
    finally { setSavingRetro(false); }
  };

  const del = async () => {
    await fetch(`${API}/interviews/${interview.id}`, { method:"DELETE" });
    onDeleted();
  };

  const tm = INTERVIEW_TYPE_META[interview.interview_type] || {icon:"•",label:interview.interview_type,color:"#8a8278"};
  const fm = INTERVIEW_FORMAT_META[interview.format];
  const om = INTERVIEW_OUTCOME_META[interview.outcome] || INTERVIEW_OUTCOME_META.pending;

  return (
    <div style={{background:"#e8e3d8",border:"1px solid #c8c2b4",borderRadius:6,marginBottom:10,overflow:"hidden"}}>
      <div onClick={onToggle} style={{
        padding:"10px 12px",cursor:"pointer",display:"flex",alignItems:"center",gap:10,
      }}>
        <div style={{flex:1,minWidth:0}}>
          <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
            <span style={{fontSize:11,fontWeight:700,color:"#2c2820"}}>Round {interview.round_number}</span>
            <span style={{fontSize:10,color:tm.color}}>{tm.icon} {tm.label}</span>
            {fm && <span style={{fontSize:10,color:fm.color}}>{fm.icon} {fm.label}</span>}
            {interview.interviewer_name && <span style={{fontSize:10,color:"#8a8278"}}>with {interview.interviewer_name}</span>}
          </div>
          <div style={{fontSize:9,color:"#a8a098",fontFamily:"monospace",marginTop:3}}>{fmtDt(interview.scheduled_at)}</div>
        </div>
        <span style={{
          fontSize:9,fontWeight:700,letterSpacing:"0.08em",
          color:om.color,background:om.bg,padding:"2px 7px",borderRadius:3,
          border:`1px solid ${om.color}35`,fontFamily:"monospace",whiteSpace:"nowrap",
        }}>{om.label}</span>
        <button onClick={e=>{e.stopPropagation();del();}} title="Delete round" style={{
          border:"none",background:"none",color:"#d4cfc4",cursor:"pointer",fontSize:13,lineHeight:1,flexShrink:0,
        }}>✕</button>
        <span style={{color:"#8a8278",fontSize:10,flexShrink:0}}>{expanded?"▲":"▼"}</span>
      </div>

      {expanded && (
        <div style={{padding:"0 12px 14px",borderTop:"1px solid #d4cfc4"}}>
          {interview.prep_notes && (
            <div style={{fontSize:10,color:"#5e5850",lineHeight:1.5,marginTop:10,marginBottom:4}}>
              <span style={{color:"#8a8278",fontWeight:700}}>PREP: </span>{interview.prep_notes}
            </div>
          )}

          {/* Outcome */}
          <div style={{marginTop:12,marginBottom:10}}>
            <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:6}}>OUTCOME</div>
            <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>
              {Object.keys(INTERVIEW_OUTCOME_META).map(o=>{
                const m = INTERVIEW_OUTCOME_META[o];
                return (
                  <button key={o} onClick={()=>patch({outcome:o})} style={{
                    fontSize:8,padding:"4px 8px",borderRadius:3,
                    border:`1px solid ${m.color}35`,
                    background:interview.outcome===o?`${m.color}18`:"transparent",
                    color:m.color,cursor:"pointer",fontFamily:"monospace",fontWeight:700,letterSpacing:"0.05em",
                  }}>{m.label}</button>
                );
              })}
            </div>
          </div>

          {/* Retrospective */}
          <div style={{marginBottom:12}}>
            <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:6,
              display:"flex",alignItems:"center",gap:8}}>
              RETROSPECTIVE
              <RoundStars rating={interview.self_rating} onRate={n=>patch({self_rating:n})}/>
            </div>
            <textarea value={wentWell} onChange={e=>setWentWell(e.target.value)}
              placeholder="What went well..." style={{...inp,minHeight:44,resize:"vertical",marginBottom:6,fontFamily:"inherit"}}/>
            <textarea value={toImprove} onChange={e=>setToImprove(e.target.value)}
              placeholder="What to improve..." style={{...inp,minHeight:44,resize:"vertical",marginBottom:6,fontFamily:"inherit"}}/>
            <textarea value={notes} onChange={e=>setNotes(e.target.value)}
              placeholder="Other notes..." style={{...inp,minHeight:44,resize:"vertical",marginBottom:8,fontFamily:"inherit"}}/>
            <ActionBtn onClick={saveRetro} loading={savingRetro} label="Save Retrospective" icon="✓" color="#4d8a68" small/>
          </div>

          {/* Questions */}
          <div>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
              <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700}}>QUESTIONS</div>
              <button onClick={()=>setAddingQuestion(p=>!p)} style={{
                fontSize:9,padding:"3px 9px",borderRadius:3,border:"1px solid #4d7ab550",
                background:"#4d7ab510",color:"#4d7ab5",cursor:"pointer",fontFamily:"monospace",fontWeight:700,
              }}>+ ADD QUESTION</button>
            </div>

            {addingQuestion && (
              <AddQuestionForm interviewId={interview.id}
                onDone={()=>{ setAddingQuestion(false); onChanged(); }}
                onCancel={()=>setAddingQuestion(false)}/>
            )}

            {interview.questions.length===0
              ? <div style={{color:"#a8a098",fontSize:11,padding:"8px 0"}}>No questions logged yet</div>
              : interview.questions.map(q => (
                <QuestionRow key={q.id} question={q} onSaved={onChanged} onDeleted={onChanged}/>
              ))
            }
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main tab ──────────────────────────────────────────────────────────────────

export default function JobInterviewsTab({ jobId, onRefresh }) {
  const [interviews, setInterviews] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/jobs/${jobId}/interviews`);
    if (r.ok) setInterviews(await r.json());
  }, [jobId]);

  useEffect(() => { load(); }, [load]);

  const refreshAll = async () => { await load(); onRefresh?.(); };

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <div style={{fontSize:10,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700}}>INTERVIEW ROUNDS</div>
        <button onClick={()=>setAdding(p=>!p)} style={{
          fontSize:9,padding:"3px 9px",borderRadius:3,border:"1px solid #4d7ab550",
          background:"#4d7ab510",color:"#4d7ab5",cursor:"pointer",fontFamily:"monospace",fontWeight:700,
        }}>+ ADD ROUND</button>
      </div>

      {adding && (
        <AddRoundForm jobId={jobId} nextRound={interviews.length+1}
          onDone={async ()=>{ setAdding(false); await refreshAll(); }}
          onCancel={()=>setAdding(false)}/>
      )}

      {interviews.length===0
        ? <div style={{color:"#a8a098",fontSize:11,padding:"8px 0"}}>No interview rounds yet</div>
        : interviews.map(iv => (
          <RoundCard key={iv.id} interview={iv}
            expanded={expandedId===iv.id}
            onToggle={()=>setExpandedId(p=>p===iv.id?null:iv.id)}
            onChanged={refreshAll}
            onDeleted={async ()=>{ if(expandedId===iv.id) setExpandedId(null); await refreshAll(); }}/>
        ))
      }
    </div>
  );
}
