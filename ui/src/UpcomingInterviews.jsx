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

function OutcomeBadge({ outcome }) {
  const m = INTERVIEW_OUTCOME_META[outcome] || INTERVIEW_OUTCOME_META.pending;
  return (
    <span style={{
      fontSize:9,fontWeight:700,letterSpacing:"0.08em",
      color:m.color,background:m.bg,padding:"2px 7px",borderRadius:3,
      border:`1px solid ${m.color}35`,fontFamily:"monospace",whiteSpace:"nowrap",
    }}>{m.label}</span>
  );
}

// ── New-interview form (job picker + round details) ─────────────────────────

function NewInterviewForm({ onDone, onCancel }) {
  const [jobQuery, setJobQuery] = useState("");
  const [jobResults, setJobResults] = useState([]);
  const [searchingJobs, setSearchingJobs] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);

  const [roundNumber, setRoundNumber] = useState(1);
  const [type, setType] = useState("phone_screen");
  const [format, setFormat] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [interviewer, setInterviewer] = useState("");
  const [duration, setDuration] = useState("");
  const [prepNotes, setPrepNotes] = useState("");
  const [loading, setLoading] = useState(false);

  const searchJobs = async () => {
    if (!jobQuery.trim()) return;
    setSearchingJobs(true);
    try {
      const r = await fetch(`${API}/jobs?q=${encodeURIComponent(jobQuery.trim())}`);
      if (r.ok) setJobResults(await r.json());
    } finally { setSearchingJobs(false); }
  };

  const pickJob = async (job) => {
    setSelectedJob(job);
    setJobResults([]);
    const r = await fetch(`${API}/jobs/${job.id}/interviews`);
    setRoundNumber(r.ok ? (await r.json()).length + 1 : 1);
  };

  const submit = async () => {
    if (!selectedJob) return;
    setLoading(true);
    try {
      await fetch(`${API}/jobs/${selectedJob.id}/interviews`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          round_number: roundNumber,
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
      {!selectedJob ? (
        <>
          <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:6}}>SELECT JOB</div>
          <div style={{display:"flex",gap:6,marginBottom:8}}>
            <input value={jobQuery} onChange={e=>setJobQuery(e.target.value)}
              onKeyDown={e=>{ if (e.key==="Enter") searchJobs(); }}
              placeholder="Search jobs by title or company..." style={{...inp,flex:1}}/>
            <ActionBtn onClick={searchJobs} loading={searchingJobs} label="Search" icon="🔍" small/>
          </div>
          {jobResults.length>0 && (
            <div style={{display:"flex",flexDirection:"column",gap:4,marginBottom:8,maxHeight:180,overflowY:"auto"}}>
              {jobResults.map(j => (
                <div key={j.id} onClick={()=>pickJob(j)} style={{
                  background:"#f5f0e8",border:"1px solid #d4cfc4",borderRadius:4,
                  padding:"6px 9px",cursor:"pointer",fontSize:10,
                }}>
                  <span style={{fontWeight:700,color:"#2c2820"}}>{j.title}</span>
                  <span style={{color:"#8a8278"}}> · {j.company}</span>
                </div>
              ))}
            </div>
          )}
          <div style={{display:"flex",gap:6,justifyContent:"flex-end"}}>
            <ActionBtn onClick={onCancel} label="Cancel" icon="✕" color="#8a8278" small/>
          </div>
        </>
      ) : (
        <>
          <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:6,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <span>{selectedJob.title} · {selectedJob.company} — ROUND {roundNumber}</span>
            <button onClick={()=>setSelectedJob(null)} style={{
              border:"none",background:"none",color:"#4d7ab5",cursor:"pointer",
              fontSize:9,fontFamily:"monospace",fontWeight:700,
            }}>CHANGE JOB</button>
          </div>
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
        </>
      )}
    </div>
  );
}

export default function UpcomingInterviews({ onSelectJob }) {
  const [items, setItems] = useState([]);
  const [includePast, setIncludePast] = useState(false);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/interviews/upcoming?include_past=${includePast}`);
      if (r.ok) setItems(await r.json());
    } finally { setLoading(false); }
  }, [includePast]);

  useEffect(() => { load(); }, [load]);

  const fmt = iso => {
    if (!iso) return "no date set";
    const d = new Date(iso);
    return d.toLocaleDateString("de-CH",{day:"2-digit",month:"2-digit",year:"numeric"}) + " " +
           d.toLocaleTimeString("de-CH",{hour:"2-digit",minute:"2-digit"});
  };

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <div style={{fontSize:10,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700}}>
          {includePast ? "ALL INTERVIEWS" : "UPCOMING INTERVIEWS"}
        </div>
        <div style={{display:"flex",gap:6}}>
          <button onClick={()=>setAdding(p=>!p)} style={{
            fontSize:9,padding:"3px 9px",borderRadius:3,border:"1px solid #4d7ab550",
            background:"#4d7ab510",color:"#4d7ab5",cursor:"pointer",fontFamily:"monospace",fontWeight:700,
          }}>+ NEW INTERVIEW</button>
          <button onClick={()=>setIncludePast(p=>!p)} style={{
            fontSize:9,padding:"3px 9px",borderRadius:3,border:"1px solid #4d7ab550",
            background:"#4d7ab510",color:"#4d7ab5",cursor:"pointer",fontFamily:"monospace",fontWeight:700,
          }}>{includePast ? "HIDE PAST" : "SHOW PAST"}</button>
        </div>
      </div>

      {adding && (
        <NewInterviewForm
          onDone={async ()=>{ setAdding(false); await load(); }}
          onCancel={()=>setAdding(false)}/>
      )}

      {loading && items.length===0
        ? <div style={{color:"#a8a098",fontSize:11,padding:"8px 0"}}>Loading…</div>
        : items.length===0
        ? <div style={{color:"#a8a098",fontSize:11,padding:"8px 0"}}>No {includePast ? "" : "upcoming "}interviews yet</div>
        : (
          <div style={{display:"flex",flexDirection:"column",gap:8}}>
            {items.map(iv => {
              const tm = INTERVIEW_TYPE_META[iv.interview_type] || {icon:"•",label:iv.interview_type,color:"#8a8278"};
              const fm = INTERVIEW_FORMAT_META[iv.format];
              return (
                <div key={iv.id} onClick={()=>onSelectJob?.(iv.job.id)} style={{
                  background:"#e8e3d8",border:"1px solid #c8c2b4",borderRadius:6,
                  padding:"10px 12px",cursor:"pointer",transition:"border-color 0.12s",
                }}
                  onMouseEnter={e=>e.currentTarget.style.borderColor=tm.color+"50"}
                  onMouseLeave={e=>e.currentTarget.style.borderColor="#c8c2b4"}
                >
                  <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:10}}>
                    <div>
                      <div style={{fontSize:12,fontWeight:700,color:"#2c2820"}}>{iv.job.title}</div>
                      <div style={{fontSize:10,color:"#7a7268",marginTop:1}}>{iv.job.company} · Round {iv.round_number}</div>
                    </div>
                    <OutcomeBadge outcome={iv.outcome}/>
                  </div>
                  <div style={{display:"flex",alignItems:"center",gap:10,marginTop:8,flexWrap:"wrap"}}>
                    <span style={{fontSize:10,color:tm.color}}>{tm.icon} {tm.label}</span>
                    {fm && <span style={{fontSize:10,color:fm.color}}>{fm.icon} {fm.label}</span>}
                    {iv.interviewer_name && <span style={{fontSize:10,color:"#8a8278"}}>with {iv.interviewer_name}</span>}
                    <span style={{flex:1}}/>
                    <span style={{fontSize:9,color:"#a8a098",fontFamily:"monospace"}}>{fmt(iv.scheduled_at)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )
      }
    </div>
  );
}
