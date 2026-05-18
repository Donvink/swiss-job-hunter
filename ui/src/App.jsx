import { useState, useEffect, useCallback, useRef } from "react";

const API = "http://localhost:8765";

// ── Constants ─────────────────────────────────────────────────────────────────

const STATUS_META = {
  new:          { label: "NEW",         color: "#4a7a60", bg: "rgba(100,116,139,0.12)" },
  analyzed:     { label: "ANALYZED",    color: "#2e7d52", bg: "rgba(56,189,248,0.12)" },
  shortlisted:  { label: "SHORTLISTED", color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
  viewed:       { label: "VIEWED",      color: "#7aa090", bg: "rgba(129,140,248,0.12)" },
  applied:      { label: "APPLIED",     color: "#34d399", bg: "rgba(52,211,153,0.12)" },
  interviewing: { label: "INTERVIEW",   color: "#a78bfa", bg: "rgba(167,139,250,0.12)" },
  offer:        { label: "OFFER 🎉",    color: "#fb923c", bg: "rgba(251,146,60,0.12)" },
  rejected:     { label: "REJECTED",    color: "#f87171", bg: "rgba(248,113,113,0.08)" },
  archived:     { label: "ARCHIVED",    color: "#6b8c7a", bg: "rgba(51,65,85,0.12)" },
};

const EVENT_META = {
  viewed:         { icon: "👁",  label: "Viewed",            color: "#7aa090" },
  applied:        { icon: "📤",  label: "Applied",           color: "#34d399" },
  confirmation:   { icon: "✉️",  label: "Confirmation",      color: "#2e7d52" },
  recruiter_call: { icon: "📞",  label: "Recruiter Call",    color: "#f59e0b" },
  interview_1:    { icon: "🤝",  label: "1st Interview",     color: "#a78bfa" },
  interview_2:    { icon: "🤝",  label: "2nd Interview",     color: "#a78bfa" },
  technical:      { icon: "💻",  label: "Technical Test",    color: "#f59e0b" },
  offer_received: { icon: "🎁",  label: "Offer Received",    color: "#fb923c" },
  offer_accepted: { icon: "✅",  label: "Offer Accepted",    color: "#34d399" },
  offer_declined: { icon: "🚫",  label: "Offer Declined",    color: "#f87171" },
  rejected:       { icon: "❌",  label: "Rejected",          color: "#f87171" },
  note:           { icon: "📝",  label: "Note",              color: "#4a7a60" },
};

const SOURCES = ["jobs.ch","swissdevjobs.ch","jobup.ch","züri.jobs","efinancialcareers.ch","linkedin.com"];

const APPLY_METHODS = [
  { id: "email",    label: "Email",    icon: "📧" },
  { id: "form",     label: "Web Form", icon: "🌐" },
  { id: "linkedin", label: "LinkedIn", icon: "💼" },
  { id: "manual",   label: "Manual",   icon: "✍️" },
];

const ADDABLE_EVENTS = [
  "confirmation","recruiter_call","interview_1","interview_2",
  "technical","offer_received","offer_accepted","offer_declined","rejected","note",
];

// ── Tiny components ───────────────────────────────────────────────────────────

function ScoreBar({ score }) {
  if (score == null) return <span style={{color:"#6b8c7a",fontSize:11}}>—</span>;
  const pct = Math.round(score * 100);
  const color = pct >= 70 ? "#34d399" : pct >= 40 ? "#f59e0b" : "#f87171";
  return (
    <div style={{display:"flex",alignItems:"center",gap:6}}>
      <div style={{width:44,height:3,background:"#d4dece",borderRadius:2,overflow:"hidden"}}>
        <div style={{width:`${pct}%`,height:"100%",background:color,transition:"width 0.6s"}}/>
      </div>
      <span style={{color,fontSize:11,fontFamily:"mono",fontWeight:700}}>{pct}%</span>
    </div>
  );
}

function Badge({ status }) {
  const m = STATUS_META[status] || STATUS_META.new;
  return (
    <span style={{
      fontSize:9,fontWeight:700,letterSpacing:"0.08em",
      color:m.color,background:m.bg,padding:"2px 7px",borderRadius:3,
      border:`1px solid ${m.color}30`,fontFamily:"monospace",whiteSpace:"nowrap",
    }}>{m.label}</span>
  );
}

function Btn({ onClick, label, icon, color="#2e7d52", disabled, small, loading }) {
  return (
    <button onClick={onClick} disabled={disabled||loading} style={{
      display:"flex",alignItems:"center",gap:6,
      padding: small ? "5px 10px" : "8px 14px",
      borderRadius:4,border:`1px solid ${color}35`,
      background:`${color}0d`,color:disabled?"#6b8c7a":color,
      fontSize: small?10:11,fontWeight:700,letterSpacing:"0.05em",
      cursor:disabled||loading?"not-allowed":"pointer",
      fontFamily:"monospace",opacity:disabled?0.45:1,
      transition:"background 0.12s",
    }}
      onMouseEnter={e=>{if(!disabled&&!loading)e.currentTarget.style.background=`${color}20`;}}
      onMouseLeave={e=>{if(!disabled&&!loading)e.currentTarget.style.background=`${color}0d`;}}
    >
      <span>{loading?"⟳":icon}</span>{loading?"…":label}
    </button>
  );
}

function LogPane({ lines }) {
  const ref = useRef();
  useEffect(()=>{ if(ref.current) ref.current.scrollTop=ref.current.scrollHeight; },[lines]);
  return (
    <div ref={ref} style={{
      flex:1,overflowY:"auto",background:"#e2e8dc",borderRadius:6,
      padding:"10px 12px",fontFamily:"monospace",fontSize:10,
      lineHeight:1.9,color:"#5a7a68",border:"1px solid #d4dece",
    }}>
      {lines.length===0
        ? <span style={{color:"#d4dece"}}>// output appears here</span>
        : lines.map((l,i)=>(
          <div key={i} style={{color:
            l.startsWith("✓")?"#34d399":
            l.startsWith("✗")||l.includes("error")?"#f87171":
            l.startsWith("→")?"#2e7d52":
            l.startsWith("[")?"#f59e0b":"#4a7a60"
          }}>{l}</div>
        ))
      }
    </div>
  );
}

function StatCard({ label, value, color="#2e7d52" }) {
  return (
    <div style={{background:"#e2e8dc",border:"1px solid #d4dece",borderRadius:7,padding:"14px 18px",minWidth:95}}>
      <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.1em",fontWeight:700,marginBottom:5,fontFamily:"monospace"}}>{label}</div>
      <div style={{fontSize:26,fontWeight:700,color,fontFamily:"monospace",lineHeight:1}}>{value??0}</div>
    </div>
  );
}

// ── Apply modal ───────────────────────────────────────────────────────────────

function ApplyModal({ job, coverLetter, onClose, onDone, addLog }) {
  const [method, setMethod] = useState("email");
  const [recipient, setRecipient] = useState("");
  const [contact, setContact] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      await fetch(`${API}/jobs/${job.id}/apply`, {
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ method, recipient_email:recipient, contact_name:contact, note, cover_letter:coverLetter }),
      });
      addLog(`✓ Job #${job.id} marked as APPLIED (${method})`);
      onDone();
    } catch(e) { addLog(`✗ ${e.message}`); }
    setLoading(false);
  };

  return (
    <div style={{
      position:"fixed",inset:0,background:"rgba(0,0,0,0.75)",
      display:"flex",alignItems:"center",justifyContent:"center",zIndex:100,
    }} onClick={onClose}>
      <div onClick={e=>e.stopPropagation()} style={{
        background:"#e2e8dc",border:"1px solid #d4dece",borderRadius:10,
        padding:28,width:460,boxShadow:"0 24px 64px rgba(0,0,0,0.6)",
      }}>
        <div style={{fontSize:14,fontWeight:700,color:"#1a2e20",marginBottom:4}}>{job.title}</div>
        <div style={{fontSize:11,color:"#5a7a68",marginBottom:20}}>{job.company} · {job.location}</div>

        <div style={{fontSize:10,color:"#5a7a68",letterSpacing:"0.1em",fontWeight:700,marginBottom:8}}>APPLICATION METHOD</div>
        <div style={{display:"flex",gap:8,marginBottom:18}}>
          {APPLY_METHODS.map(m=>(
            <button key={m.id} onClick={()=>setMethod(m.id)} style={{
              flex:1,padding:"8px 0",borderRadius:5,border:`1px solid ${method===m.id?"#34d39940":"#d4dece"}`,
              background:method===m.id?"#34d39915":"transparent",
              color:method===m.id?"#34d399":"#5a7a68",
              fontSize:10,cursor:"pointer",fontFamily:"monospace",fontWeight:600,
            }}>{m.icon} {m.label}</button>
          ))}
        </div>

        {method==="email" && (
          <>
            <input value={recipient} onChange={e=>setRecipient(e.target.value)}
              placeholder="recruiter@company.com" style={{...inp,marginBottom:8}}/>
            <input value={contact} onChange={e=>setContact(e.target.value)}
              placeholder="Contact name (optional)" style={{...inp,marginBottom:8}}/>
          </>
        )}

        <textarea value={note} onChange={e=>setNote(e.target.value)}
          placeholder="Notes (optional) — e.g. applied via company website, referral from..."
          style={{...inp,minHeight:70,resize:"vertical",marginBottom:16,fontFamily:"inherit"}}/>

        <div style={{display:"flex",gap:10,justifyContent:"flex-end"}}>
          <Btn onClick={onClose} label="Cancel" icon="✕" color="#5a7a68" small/>
          <Btn onClick={submit} loading={loading} label="Mark as Applied" icon="✓" color="#34d399" small/>
        </div>
      </div>
    </div>
  );
}

// ── Timeline ──────────────────────────────────────────────────────────────────

function Timeline({ jobId, onRefresh }) {
  const [events, setEvents] = useState([]);
  const [adding, setAdding] = useState(false);
  const [evType, setEvType] = useState("note");
  const [evNote, setEvNote] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/jobs/${jobId}/events`);
    if (r.ok) setEvents(await r.json());
  }, [jobId]);

  useEffect(() => { load(); }, [load]);

  const addEvent = async () => {
    setLoading(true);
    await fetch(`${API}/jobs/${jobId}/events`, {
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({ event_type:evType, note:evNote }),
    });
    setEvNote(""); setAdding(false);
    await load(); onRefresh?.();
    setLoading(false);
  };

  const fmt = iso => {
    const d = new Date(iso);
    return d.toLocaleDateString("de-CH",{day:"2-digit",month:"2-digit"}) + " " +
           d.toLocaleTimeString("de-CH",{hour:"2-digit",minute:"2-digit"});
  };

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <div style={{fontSize:10,color:"#5a7a68",letterSpacing:"0.1em",fontWeight:700}}>TIMELINE</div>
        <button onClick={()=>setAdding(p=>!p)} style={{
          fontSize:9,padding:"3px 9px",borderRadius:3,border:"1px solid #2e7d5230",
          background:"#2e7d5210",color:"#2e7d52",cursor:"pointer",fontFamily:"monospace",fontWeight:700,
        }}>+ ADD EVENT</button>
      </div>

      {adding && (
        <div style={{background:"#ffffff",border:"1px solid #c8d8c4",borderRadius:6,padding:12,marginBottom:12}}>
          <div style={{display:"flex",flexWrap:"wrap",gap:4,marginBottom:8}}>
            {ADDABLE_EVENTS.map(t=>(
              <button key={t} onClick={()=>setEvType(t)} style={{
                fontSize:9,padding:"2px 7px",borderRadius:3,
                border:`1px solid ${evType===t?(EVENT_META[t]?.color||"#2e7d52")+"40":"#d4dece"}`,
                background:evType===t?`${EVENT_META[t]?.color||"#2e7d52"}15`:"transparent",
                color:evType===t?(EVENT_META[t]?.color||"#2e7d52"):"#5a7a68",
                cursor:"pointer",fontFamily:"monospace",fontWeight:600,
              }}>{EVENT_META[t]?.icon} {EVENT_META[t]?.label}</button>
            ))}
          </div>
          <input value={evNote} onChange={e=>setEvNote(e.target.value)}
            placeholder="Note (optional)..." style={{...inp,marginBottom:8,fontSize:10}}/>
          <div style={{display:"flex",gap:6,justifyContent:"flex-end"}}>
            <Btn onClick={()=>setAdding(false)} label="Cancel" icon="✕" color="#5a7a68" small/>
            <Btn onClick={addEvent} loading={loading} label="Add" icon="+" color="#2e7d52" small/>
          </div>
        </div>
      )}

      {events.length===0
        ? <div style={{color:"#6b8c7a",fontSize:11,padding:"8px 0"}}>No events yet</div>
        : (
          <div style={{position:"relative",paddingLeft:20}}>
            <div style={{position:"absolute",left:7,top:6,bottom:6,width:1,background:"#d4dece"}}/>
            {events.map((e,i)=>{
              const m = EVENT_META[e.event_type] || {icon:"•",label:e.event_type,color:"#4a7a60"};
              return (
                <div key={e.id} style={{position:"relative",marginBottom:14}}>
                  <div style={{
                    position:"absolute",left:-20,top:1,width:14,height:14,
                    borderRadius:"50%",background:"#e2e8dc",border:`2px solid ${m.color}`,
                    display:"flex",alignItems:"center",justifyContent:"center",
                    fontSize:8,
                  }}>{m.icon}</div>
                  <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
                    <div style={{fontSize:11,fontWeight:700,color:m.color}}>{m.label}</div>
                    <div style={{fontSize:9,color:"#6b8c7a",fontFamily:"monospace"}}>{fmt(e.occurred_at)}</div>
                  </div>
                  {e.note && <div style={{fontSize:10,color:"#4a7a60",marginTop:2,lineHeight:1.5}}>{e.note}</div>}
                </div>
              );
            })}
          </div>
        )
      }
    </div>
  );
}

// ── Tracker board ─────────────────────────────────────────────────────────────

function TrackerBoard({ onSelectJob }) {
  const [items, setItems] = useState([]);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    const r = await fetch(`${API}/tracker`);
    if (r.ok) setItems(await r.json());
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 15000); return ()=>clearInterval(t); }, [load]);

  const cols = ["viewed","applied","interviewing","offer","rejected"];
  const byStatus = Object.fromEntries(cols.map(c => [c, items.filter(j=>j.status===c)]));

  const fmt = iso => iso ? new Date(iso).toLocaleDateString("de-CH",{day:"2-digit",month:"2-digit"}) : "—";

  return (
    <div style={{flex:1,overflow:"hidden",display:"flex",flexDirection:"column"}}>
      <div style={{
        padding:"10px 20px",borderBottom:"1px solid #d4dece",
        display:"flex",alignItems:"center",gap:12,
      }}>
        <span style={{fontSize:10,fontWeight:700,color:"#5a7a68",letterSpacing:"0.1em"}}>
          PROGRESS TRACKER
        </span>
        <span style={{fontSize:10,color:"#6b8c7a"}}>·</span>
        <span style={{fontSize:10,color:"#6b8c7a"}}>{items.length} active</span>
        <div style={{flex:1}}/>
        <button onClick={load} style={{background:"none",border:"none",color:"#5a7a68",cursor:"pointer",fontSize:12}}>↺</button>
      </div>

      <div style={{flex:1,overflow:"hidden",display:"flex"}}>
        {/* Kanban columns */}
        <div style={{flex:1,display:"flex",gap:0,overflowX:"auto",padding:16}}>
          {cols.map(col=>{
            const m = STATUS_META[col];
            const colJobs = byStatus[col] || [];
            return (
              <div key={col} style={{
                minWidth:220,flex:1,marginRight:12,
                background:"#e8ede4",border:`1px solid ${m.color}20`,
                borderTop:`2px solid ${m.color}`,borderRadius:6,
                display:"flex",flexDirection:"column",maxHeight:"100%",
              }}>
                <div style={{
                  padding:"10px 12px",display:"flex",
                  justifyContent:"space-between",alignItems:"center",
                  borderBottom:`1px solid ${m.color}15`,
                }}>
                  <span style={{fontSize:10,fontWeight:700,color:m.color,letterSpacing:"0.08em"}}>{m.label}</span>
                  <span style={{fontSize:10,color:m.color,background:m.bg,
                    padding:"1px 7px",borderRadius:10,fontFamily:"monospace"}}>{colJobs.length}</span>
                </div>
                <div style={{flex:1,overflowY:"auto",padding:8}}>
                  {colJobs.length===0
                    ? <div style={{color:"#d4dece",fontSize:10,textAlign:"center",padding:"20px 0"}}>empty</div>
                    : colJobs.map(j=>(
                      <div key={j.id}
                        onClick={()=>{ setExpanded(expanded===j.id?null:j.id); onSelectJob?.(j); }}
                        style={{
                          background: expanded===j.id?"#d4dece":"#e2e8dc",
                          border:`1px solid ${expanded===j.id?m.color+"40":"#d4dece"}`,
                          borderRadius:5,padding:"10px 11px",marginBottom:8,
                          cursor:"pointer",transition:"all 0.15s",
                        }}
                        onMouseEnter={e=>e.currentTarget.style.borderColor=m.color+"40"}
                        onMouseLeave={e=>e.currentTarget.style.borderColor=expanded===j.id?m.color+"40":"#d4dece"}
                      >
                        <div style={{fontSize:11,fontWeight:600,color:"#1a2e20",
                          marginBottom:3,lineHeight:1.3,
                          overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                          {j.title}
                        </div>
                        <div style={{fontSize:10,color:"#4a7a60",marginBottom:6}}>{j.company}</div>

                        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                          {j.match_score!=null
                            ? <ScoreBar score={j.match_score}/>
                            : <span style={{fontSize:9,color:"#6b8c7a"}}>no score</span>
                          }
                          <span style={{fontSize:9,color:"#6b8c7a",fontFamily:"monospace"}}>
                            {col==="applied"?fmt(j.applied_at):fmt(j.viewed_at)}
                          </span>
                        </div>

                        {expanded===j.id && (
                          <div style={{marginTop:10,borderTop:"1px solid #d4dece",paddingTop:10}}>
                            {j.apply_method && (
                              <div style={{fontSize:9,color:"#5a7a68",marginBottom:4}}>
                                via {j.apply_method}
                                {j.recipient_email && ` → ${j.recipient_email}`}
                              </div>
                            )}
                            {j.notes && (
                              <div style={{fontSize:9,color:"#4a7a60",marginBottom:8,lineHeight:1.5}}>{j.notes}</div>
                            )}
                            <Timeline jobId={j.id} onRefresh={load}/>
                            <div style={{marginTop:10}}>
                              <a href={j.url} target="_blank" rel="noreferrer" style={{
                                fontSize:9,color:"#2e7d52",textDecoration:"none",
                              }}>↗ open listing</a>
                            </div>
                          </div>
                        )}
                      </div>
                    ))
                  }
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Main app ──────────────────────────────────────────────────────────────────

export default function App() {
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState({});
  const [selected, setSelected] = useState(null);
  const [log, setLog] = useState([]);
  const [loading, setLoading] = useState({});
  const [searchKw, setSearchKw] = useState("ML engineer");
  const [searchLoc, setSearchLoc] = useState("Zürich");
  const [searchSrc, setSearchSrc] = useState(["jobs.ch"]);
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterText, setFilterText] = useState("");
  const [coverLetter, setCoverLetter] = useState("");
  const [coverLang, setCoverLang] = useState("en");
  const [mainTab, setMainTab] = useState("board");   // board | tracker
  const [rightTab, setRightTab] = useState("detail"); // detail | timeline | apply
  const [applyModal, setApplyModal] = useState(false);

  const addLog = useCallback(l => setLog(p=>[...p.slice(-300),l]),[]);

  const [backendOk, setBackendOk] = useState(true);

  const fetchJobs = useCallback(async () => {
    try {
      const r = await fetch(`${API}/jobs?status=${filterStatus}&q=${encodeURIComponent(filterText)}`);
      if (r.ok) { setJobs(await r.json()); setBackendOk(true); }
    } catch {
      if (backendOk) addLog("✗ Backend offline — run: python server.py");
      setBackendOk(false);
    }
  }, [filterStatus, filterText, addLog, backendOk]);

  const fetchStats = useCallback(async () => {
    try { const r=await fetch(`${API}/stats`); if(r.ok) setStats(await r.json()); } catch {}
  }, []);

  useEffect(() => { fetchJobs(); fetchStats(); }, [fetchJobs, fetchStats]);

  // Select job → auto-mark viewed
  const selectJob = useCallback(async (job) => {
    setSelected(job);
    setCoverLetter("");
    setRightTab("detail");
    if (!["viewed","applied","interviewing","offer","rejected"].includes(job.status)) {
      await fetch(`${API}/jobs/${job.id}/view`, { method:"POST" });
      fetchJobs(); fetchStats();
    }
  }, [fetchJobs, fetchStats]);

  const runStream = useCallback((endpoint, body, key) => {
    setLoading(p=>({...p,[key]:true}));
    addLog(`→ ${key} started`);

    // Use fetch with ReadableStream — more reliable than EventSource for POST
    const ctrl = new AbortController();

    fetch(`${API}/${endpoint}`, {
      method:"POST",
      headers:{"Content-Type":"application/json","Accept":"text/event-stream"},
      body:JSON.stringify(body),
      signal:ctrl.signal,
    }).then(async r => {
      if (!r.ok) {
        const err = await r.text();
        addLog(`✗ ${key} error: ${r.status} ${err.slice(0,100)}`);
        setLoading(p=>({...p,[key]:false}));
        return;
      }
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const {done,value} = await reader.read();
        if (done) break;
        buf += dec.decode(value, {stream:true});
        const lines = buf.split("\n");
        buf = lines.pop() || "";
        lines.forEach(line => {
          if (line.startsWith("data: ")) {
            const msg = line.slice(6).trim();
            if (msg && msg !== "[DONE]") addLog(msg);
          }
        });
      }
      addLog(`✓ ${key} done`);
    }).catch(e => {
      if (e.name !== "AbortError") addLog(`✗ ${key} failed: ${e.message}`);
    }).finally(() => {
      setLoading(p=>({...p,[key]:false}));
      fetchJobs(); fetchStats();
    });
  }, [addLog, fetchJobs, fetchStats]);

  const generateCover = async (job) => {
    setLoading(p=>({...p,cover:true}));
    try {
      const r = await fetch(`${API}/run/cover`,{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({job_id:job.id,language:coverLang}),
      });
      const d = await r.json();
      setCoverLetter(d.letter||"");
      setRightTab("apply");
      addLog(`✓ Cover letter generated`);
    } catch(e) { addLog(`✗ ${e.message}`); }
    setLoading(p=>({...p,cover:false}));
  };

  const updateStatus = async (jobId, status) => {
    await fetch(`${API}/jobs/${jobId}/status`,{
      method:"PATCH",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({status}),
    });
    fetchJobs(); fetchStats();
    addLog(`✓ #${jobId} → ${status}`);
    if (selected?.id===jobId) setSelected(p=>({...p,status}));
  };

  const visible = jobs.filter(j=>filterStatus==="all"||j.status===filterStatus);

  const Tab = ({id,label,active,onClick}) => (
    <button onClick={onClick} style={{
      padding:"7px 16px",border:"none",borderRadius:0,
      background:"transparent",
      color:active?"#1a2e20":"#5a7a68",
      fontSize:10,fontWeight:700,letterSpacing:"0.08em",
      cursor:"pointer",fontFamily:"monospace",
      borderBottom:active?"2px solid #2e7d52":"2px solid transparent",
    }}>{label}</button>
  );

  const RTab = ({id,label}) => (
    <Tab id={id} label={label} active={rightTab===id} onClick={()=>setRightTab(id)}/>
  );

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@700;800&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        body{background:#f5f7f2;font-family:'JetBrains Mono',monospace;}
        ::-webkit-scrollbar{width:3px;height:3px;}
        ::-webkit-scrollbar-track{background:#dde5d8;}
        ::-webkit-scrollbar-thumb{background:#b0c4b8;border-radius:2px;}
        .jr:hover{background:#e2e8dc!important;}
        .jr.sel{background:#e2e8dc!important;border-left-color:#2e7d52!important;}
        input,textarea{font-family:'JetBrains Mono',monospace;}
        input:focus,textarea:focus{outline:1px solid #2e7d5220;}
      `}</style>

      <div style={{height:"100vh",display:"flex",flexDirection:"column",background:"#f5f7f2",color:"#1a2e20"}}>

        {/* HEADER */}
        <div style={{height:48,borderBottom:"1px solid #d4dece",background:"#f0f3ed",
          display:"flex",alignItems:"center",padding:"0 20px",gap:16,flexShrink:0}}>
          <span style={{fontFamily:"'Syne',sans-serif",fontSize:15,fontWeight:800,color:"#2e7d52",letterSpacing:"0.05em"}}>
            🇨🇭 SWISS JOB HUNTER
          </span>
          <div style={{width:1,height:16,background:"#d4dece"}}/>
          {/* Main tabs */}
          <Tab id="board" label="BOARD" active={mainTab==="board"} onClick={()=>setMainTab("board")}/>
          <Tab id="tracker" label="TRACKER" active={mainTab==="tracker"} onClick={()=>setMainTab("tracker")}/>
          <div style={{flex:1}}/>
          <span style={{fontSize:9,color:stats.total>0?"#34d399":"#5a7a68",fontFamily:"monospace"}}>
            ● {stats.total??0} JOBS IN DB
          </span>
        </div>

        {/* STATS */}
        <div style={{
          display:"flex",gap:10,padding:"12px 20px",
          borderBottom:"1px solid #d4dece",overflowX:"auto",flexShrink:0,
          background:"#f0f3ed",
        }}>
          <StatCard label="TOTAL" value={stats.total??0} color="#4a7a60"/>
          <StatCard label="VIEWED" value={stats.by_status?.viewed??0} color="#7aa090"/>
          <StatCard label="APPLIED" value={stats.by_status?.applied??0} color="#34d399"/>
          <StatCard label="INTERVIEW" value={stats.by_status?.interviewing??0} color="#a78bfa"/>
          <StatCard label="OFFERS" value={stats.by_status?.offer??0} color="#fb923c"/>
          <StatCard label="SHORTLISTED" value={stats.by_status?.shortlisted??0} color="#f59e0b"/>
          <div style={{flex:1}}/>
          {stats.avg_score && <StatCard label="AVG MATCH" value={`${Math.round(stats.avg_score*100)}%`} color="#2e7d52"/>}
        </div>

        {/* BODY */}
        <div style={{flex:1,display:"flex",overflow:"hidden"}}>

          {mainTab==="tracker"
            ? <TrackerBoard onSelectJob={j=>{setSelected(j);setMainTab("board");}}/>
            : <>
              {/* LEFT PANEL */}
              <div style={{width:272,borderRight:"1px solid #d4dece",display:"flex",
                flexDirection:"column",background:"#f0f3ed",flexShrink:0}}>

                {/* Search */}
                <div style={{padding:14,borderBottom:"1px solid #d4dece"}}>
                  <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.12em",fontWeight:700,marginBottom:8}}>① SEARCH</div>
                  <input value={searchKw} onChange={e=>setSearchKw(e.target.value)}
                    placeholder="keyword" style={{...inp,marginBottom:6}}/>
                  <input value={searchLoc} onChange={e=>setSearchLoc(e.target.value)}
                    placeholder="location" style={{...inp,marginBottom:8}}/>
                  <div style={{display:"flex",flexWrap:"wrap",gap:3,marginBottom:10}}>
                    {SOURCES.map(s=>(
                      <button key={s} onClick={()=>setSearchSrc(p=>p.includes(s)?p.filter(x=>x!==s):[...p,s])} style={{
                        fontSize:8,padding:"2px 6px",borderRadius:3,border:"1px solid",
                        borderColor:searchSrc.includes(s)?"#2e7d5240":"#d4dece",
                        background:searchSrc.includes(s)?"#2e7d5215":"transparent",
                        color:searchSrc.includes(s)?"#2e7d52":"#6b8c7a",
                        cursor:"pointer",letterSpacing:"0.04em",fontFamily:"monospace",
                      }}>{s.replace(/\.(ch|com)/,"")}</button>
                    ))}
                  </div>
                  <Btn onClick={()=>runStream("run/search",{keyword:searchKw,location:searchLoc,sources:searchSrc,pages:3,semantic:false},"search")}
                    loading={loading.search} label="RUN SEARCH" icon="⬇" color="#2e7d52"/>
                </div>

                {/* Pipeline */}
                <div style={{padding:14,borderBottom:"1px solid #d4dece",display:"flex",flexDirection:"column",gap:7}}>
                  <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.12em",fontWeight:700,marginBottom:2}}>② PIPELINE</div>
                  <Btn onClick={()=>{
                    // Enrich each source separately
                    const sources = searchSrc.filter(s => ["jobs.ch","swissdevjobs.ch","jobup.ch","züri.jobs"].includes(s));
                    sources.forEach(src => runStream("run/enrich",{limit:50,source:src},`enrich-${src}`));
                    if(!sources.length) runStream("run/enrich",{limit:50,source:"jobs.ch"},"enrich");
                  }}
                    loading={loading.enrich} label="ENRICH DESCRIPTIONS" icon="📄"
                    color="#2e7d52" disabled={!stats.total}/>
                  <Btn onClick={()=>runStream("run/analyze",{limit:100,llm:false},"analyze")}
                    loading={loading.analyze} label="SCORE (KEYWORD)" icon="⚡"
                    color="#f59e0b" disabled={!stats.total}/>
                  <Btn onClick={()=>runStream("run/analyze",{limit:20,llm:true},"analyze-llm")}
                    loading={loading["analyze-llm"]} label="SCORE (LLM)" icon="🧠"
                    color="#a78bfa" disabled={!stats.total}/>
                </div>

                {/* Filter */}
                <div style={{padding:14,borderBottom:"1px solid #d4dece"}}>
                  <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.12em",fontWeight:700,marginBottom:8}}>FILTER</div>
                  <div style={{display:"flex",flexWrap:"wrap",gap:3,marginBottom:8}}>
                    {["all","new","shortlisted","viewed","applied","interviewing","offer","rejected"].map(s=>(
                      <button key={s} onClick={()=>setFilterStatus(s)} style={{
                        fontSize:8,padding:"2px 7px",borderRadius:3,border:"1px solid",
                        borderColor:filterStatus===s?(STATUS_META[s]?.color||"#2e7d52")+"40":"#d4dece",
                        background:filterStatus===s?(STATUS_META[s]?.color||"#2e7d52")+"15":"transparent",
                        color:filterStatus===s?(STATUS_META[s]?.color||"#2e7d52"):"#6b8c7a",
                        cursor:"pointer",fontFamily:"monospace",letterSpacing:"0.05em",fontWeight:700,
                      }}>{s.toUpperCase()}</button>
                    ))}
                  </div>
                  <input value={filterText} onChange={e=>setFilterText(e.target.value)}
                    placeholder="search title / company..." style={{...inp,fontSize:10}}/>
                </div>

                {/* Log */}
                <div style={{flex:1,padding:12,display:"flex",flexDirection:"column",gap:6,overflow:"hidden"}}>
                  <div style={{display:"flex",justifyContent:"space-between",
                    fontSize:9,color:"#5a7a68",letterSpacing:"0.12em",fontWeight:700}}>
                    <span>LOG</span>
                    <button onClick={()=>setLog([])} style={{background:"none",border:"none",color:"#6b8c7a",cursor:"pointer",fontSize:9}}>CLEAR</button>
                  </div>
                  <LogPane lines={log}/>
                </div>
              </div>

              {/* CENTER: Job list */}
              <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden",minWidth:0}}>
                <div style={{
                  padding:"8px 14px",borderBottom:"1px solid #d4dece",
                  display:"flex",alignItems:"center",gap:8,fontSize:9,color:"#5a7a68",flexShrink:0,
                }}>
                  <span style={{fontWeight:700,letterSpacing:"0.1em"}}>{visible.length} JOBS</span>
                  <span>· click to inspect · opens URL · auto-marks VIEWED</span>
                  <div style={{flex:1}}/>
                  <button onClick={fetchJobs} style={{background:"none",border:"none",color:"#5a7a68",cursor:"pointer"}}>↺</button>
                </div>
                <div style={{flex:1,overflowY:"auto"}}>
                  {visible.length===0
                    ? <div style={{padding:40,textAlign:"center",color:"#d4dece",fontSize:12}}>
                        no jobs — run a search first
                      </div>
                    : visible.map(j=>(
                      <div key={j.id}
                        className={`jr${selected?.id===j.id?" sel":""}`}
                        onClick={()=>selectJob(j)}
                        style={{
                          padding:"9px 14px",borderBottom:"1px solid #e8ede4",
                          borderLeft:"2px solid transparent",
                          display:"grid",gridTemplateColumns:"26px 1fr 100px 66px 52px",
                          alignItems:"center",gap:8,cursor:"pointer",transition:"background 0.1s",
                        }}>
                        <span style={{fontSize:9,color:"#6b8c7a",fontWeight:700}}>#{j.id}</span>
                        <div style={{minWidth:0}}>
                          <div style={{fontSize:11,fontWeight:600,color:"#1a2e20",marginBottom:2,
                            overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{j.title}</div>
                          <div style={{fontSize:9,color:"#5a7a68",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                            {j.company} · {j.location}
                          </div>
                        </div>
                        <Badge status={j.status}/>
                        <ScoreBar score={j.match_score}/>
                        <div style={{fontSize:8,color:"#6b8c7a",textAlign:"right",fontFamily:"monospace"}}>
                          {j.source?.replace(/\.(ch|com)/,"")}
                        </div>
                      </div>
                    ))
                  }
                </div>
              </div>

              {/* RIGHT PANEL */}
              <div style={{width:400,borderLeft:"1px solid #d4dece",display:"flex",
                flexDirection:"column",background:"#f0f3ed",flexShrink:0}}>
                <div style={{display:"flex",borderBottom:"1px solid #d4dece",flexShrink:0}}>
                  <RTab id="detail" label="DETAIL"/>
                  <RTab id="timeline" label="TIMELINE"/>
                  <RTab id="apply" label="APPLY"/>
                </div>

                {/* DETAIL TAB */}
                {rightTab==="detail" && (
                  <div style={{flex:1,overflowY:"auto",padding:18}}>
                    {!selected
                      ? <div style={{color:"#d4dece",fontSize:12,textAlign:"center",marginTop:50}}>
                          ← select a job
                        </div>
                      : <>
                        <div style={{marginBottom:14}}>
                          <div style={{fontSize:14,fontWeight:700,color:"#1a2e20",marginBottom:5,lineHeight:1.3}}>
                            {selected.title}
                          </div>
                          <div style={{fontSize:11,color:"#4a7a60",marginBottom:8}}>
                            {selected.company} · {selected.location}
                          </div>
                          <div style={{display:"flex",gap:7,flexWrap:"wrap",alignItems:"center"}}>
                            <Badge status={selected.status}/>
                            {selected.employment_type&&<span style={{fontSize:9,color:"#5a7a68",background:"#d4dece",padding:"2px 6px",borderRadius:3}}>{selected.employment_type}</span>}
                            {selected.match_score!=null&&<span style={{fontSize:9,color:"#2e7d52"}}>match {Math.round(selected.match_score*100)}%</span>}
                          </div>
                        </div>

                        {selected.match_explanation&&(
                          <div style={{background:"#e2e8dc",border:"1px solid #d4dece",borderRadius:5,
                            padding:"9px 11px",marginBottom:12,fontSize:10,color:"#4a7a60",lineHeight:1.6}}>
                            {selected.match_explanation}
                          </div>
                        )}

                        <div style={{marginBottom:12}}>
                          <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.1em",fontWeight:700,marginBottom:6}}>JD</div>
                          <div style={{fontSize:10,color:"#708878",lineHeight:1.7,maxHeight:200,overflowY:"auto",
                            background:"#e2e8dc",borderRadius:5,padding:"9px 11px",border:"1px solid #d4dece"}}>
                            {selected.description||<span style={{color:"#6b8c7a"}}>no description — run Enrich</span>}
                          </div>
                        </div>

                        <div style={{display:"flex",flexDirection:"column",gap:7,marginBottom:14}}>
                          <a href={selected.url} target="_blank" rel="noreferrer" style={{
                            display:"block",padding:"7px 12px",borderRadius:4,
                            background:"#d4dece",color:"#2e7d52",fontSize:10,
                            textDecoration:"none",textAlign:"center",border:"1px solid #2e7d5220",
                          }}>↗ OPEN ORIGINAL LISTING</a>
                          <Btn onClick={()=>generateCover(selected)} loading={loading.cover}
                            label="GENERATE COVER LETTER" icon="✍" color="#a78bfa"/>
                        </div>

                        <div>
                          <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.1em",fontWeight:700,marginBottom:7}}>UPDATE STATUS</div>
                          <div style={{display:"flex",flexWrap:"wrap",gap:5,marginBottom:10}}>
                            {["viewed","shortlisted","applied","interviewing","offer","rejected","archived"].map(s=>(
                              <button key={s} onClick={()=>{
                                if(s==="applied") setApplyModal(true);
                                else updateStatus(selected.id,s);
                              }} style={{
                                fontSize:8,padding:"4px 8px",borderRadius:3,
                                border:`1px solid ${STATUS_META[s]?.color||"#5a7a68"}30`,
                                background:selected.status===s?`${STATUS_META[s]?.color}20`:"transparent",
                                color:STATUS_META[s]?.color||"#5a7a68",
                                cursor:"pointer",fontFamily:"monospace",fontWeight:700,letterSpacing:"0.05em",
                              }}>{s.toUpperCase()}</button>
                            ))}
                          </div>
                        </div>
                      </>
                    }
                  </div>
                )}

                {/* TIMELINE TAB */}
                {rightTab==="timeline" && (
                  <div style={{flex:1,overflowY:"auto",padding:18}}>
                    {!selected
                      ? <div style={{color:"#d4dece",fontSize:12,textAlign:"center",marginTop:50}}>← select a job</div>
                      : <>
                        <div style={{fontSize:12,fontWeight:700,color:"#1a2e20",marginBottom:2}}>{selected.title}</div>
                        <div style={{fontSize:10,color:"#5a7a68",marginBottom:16}}>{selected.company}</div>
                        <Timeline jobId={selected.id} onRefresh={()=>{fetchJobs();fetchStats();}}/>
                      </>
                    }
                  </div>
                )}

                {/* APPLY TAB */}
                {rightTab==="apply" && (
                  <div style={{flex:1,overflowY:"auto",padding:18,display:"flex",flexDirection:"column",gap:12}}>
                    {!selected
                      ? <div style={{color:"#d4dece",fontSize:12,textAlign:"center",marginTop:50}}>← select a job first</div>
                      : <>
                        <div>
                          <div style={{fontSize:12,fontWeight:700,color:"#1a2e20",marginBottom:2}}>{selected.title}</div>
                          <div style={{fontSize:10,color:"#5a7a68"}}>{selected.company}</div>
                        </div>
                        <div style={{display:"flex",gap:5,alignItems:"center"}}>
                          <span style={{fontSize:9,color:"#5a7a68",fontWeight:700,letterSpacing:"0.08em"}}>LANG:</span>
                          {["en","de","fr"].map(l=>(
                            <button key={l} onClick={()=>setCoverLang(l)} style={{
                              fontSize:9,padding:"3px 8px",borderRadius:3,
                              border:`1px solid ${coverLang===l?"#2e7d5240":"#d4dece"}`,
                              background:coverLang===l?"#2e7d5215":"transparent",
                              color:coverLang===l?"#2e7d52":"#5a7a68",
                              cursor:"pointer",fontFamily:"monospace",fontWeight:700,
                            }}>{l.toUpperCase()}</button>
                          ))}
                          <button onClick={()=>generateCover(selected)} disabled={loading.cover} style={{
                            marginLeft:"auto",fontSize:9,padding:"3px 9px",borderRadius:3,
                            border:"1px solid #a78bfa30",background:"#a78bfa10",color:"#a78bfa",
                            cursor:"pointer",fontFamily:"monospace",fontWeight:700,
                          }}>{loading.cover?"⟳ ...":"↻ GENERATE"}</button>
                        </div>
                        <textarea value={coverLetter} onChange={e=>setCoverLetter(e.target.value)}
                          placeholder="cover letter appears here after generation..."
                          style={{flex:1,minHeight:260,background:"#e2e8dc",border:"1px solid #d4dece",
                            borderRadius:5,padding:"11px 13px",color:"#708878",fontSize:11,
                            lineHeight:1.8,fontFamily:"Georgia,serif"}}/>
                        <div style={{display:"flex",flexDirection:"column",gap:7}}>
                          <Btn onClick={()=>{navigator.clipboard.writeText(coverLetter);addLog("✓ Copied");}}
                            disabled={!coverLetter} label="COPY TO CLIPBOARD" icon="⎘" color="#2e7d52"/>
                          <Btn onClick={()=>setApplyModal(true)}
                            disabled={!coverLetter} label="MARK AS APPLIED" icon="✓" color="#34d399"/>
                        </div>
                      </>
                    }
                  </div>
                )}
              </div>
            </>
          }
        </div>
      </div>

      {/* Apply modal */}
      {applyModal && selected && (
        <ApplyModal
          job={selected}
          coverLetter={coverLetter}
          addLog={addLog}
          onClose={()=>setApplyModal(false)}
          onDone={()=>{ setApplyModal(false); updateStatus(selected.id,"applied"); setRightTab("timeline"); }}
        />
      )}
    </>
  );
}

const inp = {
  width:"100%",padding:"6px 9px",borderRadius:4,
  background:"#ffffff",border:"1px solid #c8d8c4",
  color:"#2c4a38",fontSize:11,
};
