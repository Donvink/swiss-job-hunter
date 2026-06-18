import { useState, useEffect, useCallback, useRef } from "react";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8765";

// ── Constants ─────────────────────────────────────────────────────────────────

const STATUS_META = {
  new:          { label: "NEW",         color: "#4a7a60", bg: "rgba(100,116,139,0.12)" },
  analyzed:     { label: "ANALYZED",    color: "#2e7d52", bg: "rgba(56,189,248,0.12)" },
  shortlisted:  { label: "SHORTLISTED", color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
  viewed:       { label: "VIEWED",      color: "#7aa090", bg: "rgba(129,140,248,0.12)" },
  considering:  { label: "CONSIDERING", color: "#38bdf8", bg: "rgba(56,189,248,0.12)" },
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

const SOURCES = ["jobs.ch","jobscout24.ch","swissdevjobs.ch","jobup.ch","züri.jobs","efinancialcareers.ch","linkedin.com","michael-page.ch"];

const DIRECTIONS_FALLBACK = ["agent", "perception"];

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

function Stars({ stars, jobId, onUpdate }) {
  const [hovered, setHovered] = useState(null);
  const current = hovered ?? stars ?? 0;
  return (
    <span style={{display:"inline-flex",gap:1,lineHeight:1}}>
      {[1,2,3,4,5].map(n => (
        <span key={n}
          onClick={async e => {
            e.stopPropagation();
            const next = n === stars ? 0 : n;
            await fetch(`${API}/jobs/${jobId}/stars`, {
              method:"PATCH", headers:{"Content-Type":"application/json"},
              body: JSON.stringify({stars: next}),
            });
            onUpdate();
          }}
          onMouseEnter={() => setHovered(n)}
          onMouseLeave={() => setHovered(null)}
          style={{cursor:"pointer", fontSize:14, color: n <= current ? "#f59e0b" : "#d4dece",
            transition:"color 0.1s"}}>★</span>
      ))}
    </span>
  );
}

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
      padding: small ? "4px 8px" : "6px 12px",
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

function LogPane({ lines, running }) {
  const ref = useRef();
  useEffect(()=>{ if(ref.current) ref.current.scrollTop=ref.current.scrollHeight; },[lines, running]);
  return (
    <div ref={ref} style={{
      flex:1,overflowY:"auto",background:"#e2e8dc",borderRadius:6,
      padding:"8px 10px",fontFamily:"monospace",fontSize:10,
      lineHeight:1.5,color:"#5a7a68",border:"1px solid #d4dece",
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
      {running && (
        <div style={{display:"flex",alignItems:"center",gap:5,marginTop:3,color:"#2e7d52"}}>
          <span style={{animation:"logpulse 1s ease-in-out infinite"}}>●</span>
          <span style={{fontSize:9,color:"#5a7a68"}}>running...</span>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, color="#2e7d52" }) {
  return (
    <div style={{background:"#e2e8dc",border:"1px solid #d4dece",borderRadius:7,padding:"8px 14px",minWidth:80}}>
      <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.1em",fontWeight:700,marginBottom:3,fontFamily:"monospace"}}>{label}</div>
      <div style={{fontSize:22,fontWeight:700,color,fontFamily:"monospace",lineHeight:1}}>{value??0}</div>
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

  const cols = ["viewed","considering","applied","interviewing","offer","rejected"];
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
  const pipelineRunning = useRef(false);
  const [searchKws, setSearchKws] = useState(["Agent"]);
  const [searchKwInput, setSearchKwInput] = useState("");
  const [searchLoc, setSearchLoc] = useState("Zürich");
  const [searchSrc, setSearchSrc] = useState(["jobs.ch"]);
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterText, setFilterText] = useState("");
  const [filterMinStars, setFilterMinStars] = useState(0);
  const [coverLetter, setCoverLetter] = useState("");
  const [coverLang, setCoverLang] = useState("en");
  const [threshold, setThreshold] = useState(10); // percent — shared by archive/purge/filter/lookup
  const [searchPages, setSearchPages] = useState(3);
  const [keywordPresets, setKeywordPresets] = useState({});
  const [linkedinTimeRange, setLinkedinTimeRange] = useState("r604800");
  const [linkedinExpLevel, setLinkedinExpLevel] = useState("3,4");
  const [direction, setDirection] = useState("all");
  const [directions, setDirections] = useState(DIRECTIONS_FALLBACK);
  const [mainTab, setMainTab] = useState("board");   // board | tracker
  const [rightTab, setRightTab] = useState("detail"); // detail | company | timeline | apply | tailor
  const [applyModal, setApplyModal] = useState(false);
  const [tailorResult, setTailorResult] = useState(null);
  const [translatedDesc, setTranslatedDesc] = useState("");
  const [translating, setTranslating] = useState(false);
  const [showOriginalDesc, setShowOriginalDesc] = useState(false);
  const [companyCache, setCompanyCache] = useState({});  // name → summary
  const [lookingUpCompany, setLookingUpCompany] = useState(false);

  const addLog = useCallback(l => setLog(p=>[...p.slice(-300),l]),[]);

  const [backendOk, setBackendOk] = useState(true);

  const fetchJobs = useCallback(async () => {
    try {
      const r = await fetch(`${API}/jobs?status=${filterStatus}&q=${encodeURIComponent(filterText)}&direction=${direction}&min_stars=${filterMinStars}`);
      if (r.ok) { setJobs(await r.json()); setBackendOk(true); }
    } catch {
      if (backendOk) addLog("✗ Backend offline — run: python server.py");
      setBackendOk(false);
    }
  }, [filterStatus, filterText, direction, filterMinStars, addLog, backendOk]);

  const fetchStats = useCallback(async () => {
    try { const r=await fetch(`${API}/stats?threshold=${threshold/100}`); if(r.ok) setStats(await r.json()); } catch {}
  }, [threshold]);

  useEffect(() => { fetchJobs(); fetchStats(); }, [fetchJobs, fetchStats]);

  useEffect(() => {
    fetch(`${API}/config`).then(r=>r.ok?r.json():null).then(cfg=>{
      if (!cfg) return;
      setSearchKws([cfg.default_keyword || "Agent"]);
      setSearchLoc(cfg.default_location || "Zürich");
      if (cfg.keyword_presets && typeof cfg.keyword_presets === "object") {
        setKeywordPresets(cfg.keyword_presets);
      }
    }).catch(()=>{});
    fetch(`${API}/presets`).then(r=>r.ok?r.json():null).then(presets=>{
      if (presets && typeof presets === "object") setKeywordPresets(presets);
    }).catch(()=>{});
    fetch(`${API}/directions`).then(r=>r.ok?r.json():null).then(dirs=>{
      if (dirs && dirs.length) setDirections(dirs);
    }).catch(()=>{});
  }, []);

  // Select job → auto-mark viewed
  const translateDesc = async (job, target) => {
    setTranslating(true);
    setTranslatedDesc("");
    setShowOriginalDesc(false);
    try {
      const r = await fetch(`${API}/run/translate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: job.id, target }),
      });
      const d = await r.json();
      if (d.translated) { setTranslatedDesc(d.translated); addLog(`✓ Translated to ${target === "en" ? "English" : "中文"}`); }
      else addLog("✗ Translation failed");
    } catch (e) { addLog(`✗ ${e.message}`); }
    setTranslating(false);
  };

  const lookupCompany = useCallback(async (name) => {
    if (!name || companyCache[name] !== undefined) return;
    // check cache first (GET)
    try {
      const r = await fetch(`${API}/companies/${encodeURIComponent(name)}`);
      if (r.ok) {
        const d = await r.json();
        if (d.summary) { setCompanyCache(p => ({...p, [name]: d.summary})); return; }
      }
    } catch {}
    setCompanyCache(p => ({...p, [name]: null})); // mark as checked, not cached
  }, [companyCache]);

  const triggerCompanyLookup = useCallback(async (name) => {
    setLookingUpCompany(true);
    try {
      const r = await fetch(`${API}/companies/lookup`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name}),
      });
      const d = await r.json();
      if (d.summary) {
        setCompanyCache(p => ({...p, [name]: d.summary}));
        addLog(`✓ Company info: ${name}`);
      }
    } catch (e) { addLog(`✗ ${e.message}`); }
    setLookingUpCompany(false);
  }, [addLog]);

  const selectJob = useCallback(async (job) => {
    setSelected(job);
    setCoverLetter("");
    setTranslatedDesc("");
    setShowOriginalDesc(false);
    setRightTab("detail");
    lookupCompany(job.company);
    if (!["viewed","considering","applied","interviewing","offer","rejected"].includes(job.status)) {
      await fetch(`${API}/jobs/${job.id}/view`, { method:"POST" });
      fetchJobs(); fetchStats();
    }
  }, [fetchJobs, fetchStats]);

  const runStream = useCallback((endpoint, body, key) => {
    setLoading(p=>({...p,[key]:true}));
    addLog(`→ ${key} started`);
    return fetch(`${API}/${endpoint}`, {
      method:"POST",
      headers:{"Content-Type":"application/json","Accept":"text/event-stream"},
      body:JSON.stringify(body),
    }).then(async r => {
      if (!r.ok) {
        const err = await r.text();
        addLog(`✗ ${key} error: ${r.status} ${err.slice(0,100)}`);
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
      addLog(`✗ ${key} failed: ${e.message}`);
    }).finally(() => {
      setLoading(p=>({...p,[key]:false}));
      fetchJobs(); fetchStats();
    });
  }, [addLog, fetchJobs, fetchStats]);

  const runPipeline = useCallback(async () => {
    if (pipelineRunning.current) { addLog("✗ Pipeline already running"); return; }
    const kws = searchKwInput.trim() ? [...searchKws, searchKwInput.trim()] : searchKws;
    if (!kws.length) { addLog("✗ No keywords set"); return; }
    const dir = direction === "all" ? null : direction;
    const enrichable = ["jobs.ch","jobscout24.ch","swissdevjobs.ch","züri.jobs","efinancialcareers.ch","jobup.ch","linkedin.com","michael-page.ch"];
    const enrichSources = searchSrc.filter(s => enrichable.includes(s));

    pipelineRunning.current = true;
    setLoading(p=>({...p, pipeline:true}));
    addLog("━━━ PIPELINE START ━━━");
    try {
      await runStream("run/search", {keywords:kws, keyword:kws[0]||"", location:searchLoc, sources:searchSrc, pages:searchPages, semantic:false, direction:dir, linkedin_time_range:linkedinTimeRange, linkedin_experience_level:linkedinExpLevel}, "search");
      for (const src of (enrichSources.length ? enrichSources : [searchSrc[0]||"jobs.ch"])) {
        await runStream("run/enrich", {limit:9999, source:src, rescore_llm:false, direction:dir}, `enrich-${src}`);
      }
      await runStream("run/analyze", {limit:9999, llm:true, archive_below:threshold/100, direction:dir}, "analyze-llm");
      addLog("━━━ PIPELINE DONE ━━━");
    } finally {
      pipelineRunning.current = false;
      setLoading(p=>({...p, pipeline:false}));
    }
  }, [searchKws, searchKwInput, searchSrc, searchLoc, searchPages, direction, linkedinTimeRange, linkedinExpLevel, threshold, runStream, addLog]);

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

  const tailorCv = async (job) => {
    setLoading(p=>({...p, tailor:true}));
    setTailorResult(null);
    try {
      const r = await fetch(`${API}/run/tailor-cv`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({job_id: job.id, direction: direction==="all"?null:direction}),
      });
      const d = await r.json();
      if (d.error) { addLog(`✗ Tailor CV: ${d.error}`); }
      else { setTailorResult(d); setRightTab("tailor"); addLog("✓ CV tailoring done"); }
    } catch(e) { addLog(`✗ ${e.message}`); }
    setLoading(p=>({...p, tailor:false}));
  };

  const deleteJob = async (jobId) => {
    await fetch(`${API}/jobs/${jobId}`, { method: "DELETE" });
    if (selected?.id === jobId) setSelected(null);
    fetchJobs(); fetchStats();
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

  const visible = jobs.filter(j=>
    (filterStatus==="all"||j.status===filterStatus) &&
    (threshold===0 || (j.match_score!=null && j.match_score*100 >= threshold))
  );

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
        @keyframes logpulse{0%,100%{opacity:1}50%{opacity:0.2}}
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
          display:"flex",gap:8,padding:"8px 16px",
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
          {stats.above_threshold!=null && <StatCard label={`≥${Math.round((stats.threshold??0.1)*100)}%`} value={stats.above_threshold} color="#2e7d52"/>}
          {stats.avg_score && <StatCard label="AVG MATCH" value={`${Math.round(stats.avg_score*100)}%`} color="#2e7d52"/>}
        </div>

        {/* BODY */}
        <div style={{flex:1,display:"flex",overflow:"hidden"}}>

          {mainTab==="tracker"
            ? <TrackerBoard onSelectJob={j=>{setSelected(j);setMainTab("board");}}/>
            : <>
              {/* LEFT PANEL */}
              <div style={{width:300,borderRight:"1px solid #d4dece",display:"flex",
                flexDirection:"column",background:"#f0f3ed",flexShrink:0,overflow:"hidden"}}>

                {/* Controls: scrollable, capped so Log stays visible */}
                <div style={{overflowY:"auto",flexShrink:0,maxHeight:"65%"}}>

                {/* Search */}
                <div style={{padding:"6px 10px",borderBottom:"1px solid #d4dece"}}>
                  <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.12em",fontWeight:700,marginBottom:4}}>① SEARCH</div>
                  <div style={{display:"flex",gap:3,marginBottom:4}}>
                    {["all",...directions].map(d=>(
                      <button key={d} onClick={()=>setDirection(d)} style={{
                        flex:1,fontSize:8,padding:"2px 0",borderRadius:3,border:"1px solid",
                        borderColor:direction===d?"#2e7d5240":"#d4dece",
                        background:direction===d?"#2e7d5215":"transparent",
                        color:direction===d?"#2e7d52":"#6b8c7a",
                        cursor:"pointer",fontFamily:"monospace",fontWeight:700,letterSpacing:"0.05em",
                      }}>{d.toUpperCase()}</button>
                    ))}
                  </div>
                  {/* keyword presets */}
                  <div style={{display:"flex",gap:3,marginBottom:4}}>
                    {Object.entries(keywordPresets).map(([dir, kws])=>(
                      <button key={dir} onClick={()=>{ setSearchKws(kws); setSearchKwInput(""); setDirection(dir); }} style={{
                        flex:1,fontSize:8,padding:"3px 0",borderRadius:3,border:"1px solid #2e7d5230",
                        background:"#2e7d5210",color:"#2e7d52",cursor:"pointer",
                        fontFamily:"monospace",fontWeight:700,letterSpacing:"0.04em",
                      }}>⚡ {dir.toUpperCase()}</button>
                    ))}
                  </div>
                  {/* keyword tags */}
                  <div style={{display:"flex",flexWrap:"wrap",gap:3,marginBottom:3}}>
                    {searchKws.map((kw,i)=>(
                      <span key={i} style={{
                        display:"inline-flex",alignItems:"center",gap:3,
                        fontSize:9,padding:"2px 6px",borderRadius:3,
                        background:"#2e7d5220",border:"1px solid #2e7d5240",color:"#2e7d52",
                        fontFamily:"monospace",fontWeight:700,
                      }}>
                        {kw}
                        <span onClick={()=>setSearchKws(p=>p.filter((_,j)=>j!==i))}
                          style={{cursor:"pointer",fontWeight:900,opacity:0.6,lineHeight:1}}>×</span>
                      </span>
                    ))}
                  </div>
                  <input value={searchKwInput}
                    onChange={e=>{
                      const v = e.target.value;
                      if (v.endsWith(",")) {
                        const kw = v.slice(0,-1).trim();
                        if (kw && !searchKws.includes(kw)) setSearchKws(p=>[...p,kw]);
                        setSearchKwInput("");
                      } else {
                        setSearchKwInput(v);
                      }
                    }}
                    onKeyDown={e=>{
                      if (e.key==="Enter") {
                        const kw = searchKwInput.trim();
                        if (kw && !searchKws.includes(kw)) setSearchKws(p=>[...p,kw]);
                        setSearchKwInput("");
                      } else if (e.key==="Backspace" && !searchKwInput && searchKws.length>0) {
                        setSearchKws(p=>p.slice(0,-1));
                      }
                    }}
                    placeholder={searchKws.length ? "add keyword (Enter/,)" : "keyword (Enter to add)"}
                    style={{...inp,marginBottom:4}}/>
                  <div style={{display:"flex",gap:5,marginBottom:4}}>
                    <input value={searchLoc} onChange={e=>setSearchLoc(e.target.value)}
                      placeholder="city (blank = all CH)" style={{...inp,flex:1}}/>
                    <button onClick={()=>setSearchLoc("")} title="Search all Switzerland" style={{
                      padding:"4px 7px",borderRadius:4,border:"1px solid",
                      borderColor:searchLoc===""?"#2e7d5240":"#d4dece",
                      background:searchLoc===""?"#2e7d5215":"transparent",
                      color:searchLoc===""?"#2e7d52":"#6b8c7a",
                      fontSize:9,fontWeight:700,fontFamily:"monospace",cursor:"pointer",whiteSpace:"nowrap",
                    }}>ALL CH</button>
                    <input type="number" min={1} max={40} value={searchPages}
                      onChange={e=>setSearchPages(Math.max(1,parseInt(e.target.value)||1))}
                      title="pages per source" style={{...inp,width:64,textAlign:"center"}}/>
                  </div>
                  <div style={{display:"flex",flexWrap:"wrap",gap:3,marginBottom:5}}>
                    <button onClick={()=>setSearchSrc(searchSrc.length===SOURCES.length?[]:SOURCES)} style={{
                      fontSize:8,padding:"2px 6px",borderRadius:3,border:"1px solid",
                      borderColor:searchSrc.length===SOURCES.length?"#2e7d5240":"#d4dece",
                      background:searchSrc.length===SOURCES.length?"#2e7d5215":"transparent",
                      color:searchSrc.length===SOURCES.length?"#2e7d52":"#6b8c7a",
                      cursor:"pointer",letterSpacing:"0.04em",fontFamily:"monospace",fontWeight:700,
                    }}>ALL</button>
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
                  {searchSrc.includes("linkedin.com") && (<>
                    <select value={linkedinTimeRange} onChange={e=>setLinkedinTimeRange(e.target.value)}
                      style={{...inp,marginBottom:0,fontSize:9,color:"#4a6a58"}}>
                      <option value="r86400">LinkedIn · 24h</option>
                      <option value="r604800">LinkedIn · 7 days</option>
                      <option value="r2592000">LinkedIn · 30 days</option>
                    </select>
                    <select value={linkedinExpLevel} onChange={e=>setLinkedinExpLevel(e.target.value)}
                      style={{...inp,marginBottom:0,fontSize:9,color:"#4a6a58"}}>
                      <option value="2,3,4">LinkedIn · Entry–Senior</option>
                      <option value="3,4">LinkedIn · Associate–Senior</option>
                      <option value="4">LinkedIn · Senior only</option>
                      <option value="4,5">LinkedIn · Senior–Director</option>
                    </select>
                  </>)}
                  <Btn onClick={()=>{
                    const kws = searchKwInput.trim()
                      ? [...searchKws, searchKwInput.trim()]
                      : searchKws;
                    runStream("run/search",{keywords:kws,keyword:kws[0]||"",location:searchLoc,sources:searchSrc,pages:searchPages,semantic:false,direction:direction==="all"?null:direction,linkedin_time_range:linkedinTimeRange,linkedin_experience_level:linkedinExpLevel},"search");
                  }} loading={loading.search} label="RUN SEARCH" icon="⬇" color="#2e7d52"/>
                  <Btn onClick={runPipeline}
                    loading={loading.pipeline}
                    disabled={loading.pipeline||loading.search||loading["analyze-llm"]||Object.keys(loading).some(k=>k.startsWith("enrich")&&loading[k])}
                    label="SEARCH + ENRICH + SCORE" icon="⚡" color="#a78bfa"/>
                </div>

                {/* Pipeline + Cleanup */}
                <div style={{padding:"6px 10px",borderBottom:"1px solid #d4dece",display:"flex",flexDirection:"column",gap:4}}>
                  <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.12em",fontWeight:700,marginBottom:0}}>② PIPELINE</div>
                  <Btn onClick={()=>{
                    const enrichable = ["jobs.ch","jobscout24.ch","swissdevjobs.ch","züri.jobs","efinancialcareers.ch","jobup.ch","linkedin.com","michael-page.ch"];
                    const sources = searchSrc.filter(s => enrichable.includes(s));
                    const dir = direction==="all"?null:direction;
                    if(sources.length) sources.forEach(src => runStream("run/enrich",{limit:9999,source:src,rescore_llm:false,direction:dir},`enrich-${src}`));
                    else runStream("run/enrich",{limit:9999,source:searchSrc[0]||"jobs.ch",rescore_llm:false,direction:dir},"enrich");
                  }}
                    loading={loading.enrich} label="ENRICH DESCRIPTIONS" icon="📄"
                    color="#2e7d52" disabled={!stats.total}/>
                  <Btn onClick={()=>{
                    const enrichable = ["jobs.ch","jobscout24.ch","swissdevjobs.ch","züri.jobs","efinancialcareers.ch","jobup.ch","linkedin.com","michael-page.ch"];
                    const sources = searchSrc.filter(s => enrichable.includes(s));
                    const dir = direction==="all"?null:direction;
                    if(sources.length) sources.forEach(src => runStream("run/enrich",{limit:9999,source:src,rescore_llm:true,direction:dir},`enrich-llm-${src}`));
                    else runStream("run/enrich",{limit:9999,source:searchSrc[0]||"jobs.ch",rescore_llm:true,direction:dir},"enrich-llm");
                  }}
                    loading={loading["enrich-llm"]} label="ENRICH + LLM SCORE" icon="🧠"
                    color="#a78bfa" disabled={!stats.total}/>
                  <Btn onClick={()=>runStream("run/analyze",{limit:9999,llm:false,direction:direction==="all"?null:direction},"analyze")}
                    loading={loading.analyze} label="SCORE (KEYWORD)" icon="⚡"
                    color="#f59e0b" disabled={!stats.total}/>
                  <div style={{display:"flex",alignItems:"center",gap:6}}>
                    <Btn onClick={()=>runStream("run/analyze",{limit:9999,llm:true,archive_below:threshold/100,direction:direction==="all"?null:direction},"analyze-llm")}
                      loading={loading["analyze-llm"]} label="SCORE (LLM)" icon="🧠"
                      color="#a78bfa" disabled={!stats.total}/>
                    <Btn onClick={()=>runStream("run/analyze",{llm:true,skip_scored:false,archive_below:threshold/100,concurrency:10,direction:direction==="all"?null:direction},"rescore-all")}
                      loading={loading["rescore-all"]} label="RESCORE ALL" icon="🔄"
                      color="#6366f1" disabled={!stats.total}/>
                  </div>
                  <Btn onClick={()=>runStream("run/company-lookup",{min_score:threshold/100},"company-lookup")}
                    loading={loading["company-lookup"]} label="LOOKUP COMPANIES" icon="🏢"
                    color="#2e7d52" disabled={!stats.total}/>
                  <div style={{height:1,background:"#d4dece",margin:"2px 0"}}/>
                  <div style={{display:"flex",alignItems:"center",gap:5}}>
                    <Btn onClick={()=>runStream("run/purge-archived",{max_score:threshold/100,dry_run:true},"purge-preview")}
                      loading={loading["purge-preview"]} label="PREVIEW" icon="🔍" small color="#6b8c7a"/>
                    <Btn onClick={()=>runStream("run/purge-archived",{max_score:threshold/100,dry_run:false},"purge")}
                      loading={loading["purge"]} label="PURGE" icon="🗑" small color="#f87171"/>
                  </div>
                </div>

                {/* Filter */}
                <div style={{padding:"6px 10px",borderBottom:"1px solid #d4dece"}}>
                  <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.12em",fontWeight:700,marginBottom:4}}>FILTER</div>
                  <div style={{display:"flex",flexWrap:"wrap",gap:3,marginBottom:5}}>
                    {["all","new","shortlisted","viewed","considering","applied","interviewing","offer","rejected"].map(s=>(
                      <button key={s} onClick={()=>setFilterStatus(s)} style={{
                        fontSize:8,padding:"2px 7px",borderRadius:3,border:"1px solid",
                        borderColor:filterStatus===s?(STATUS_META[s]?.color||"#2e7d52")+"40":"#d4dece",
                        background:filterStatus===s?(STATUS_META[s]?.color||"#2e7d52")+"15":"transparent",
                        color:filterStatus===s?(STATUS_META[s]?.color||"#2e7d52"):"#6b8c7a",
                        cursor:"pointer",fontFamily:"monospace",letterSpacing:"0.05em",fontWeight:700,
                      }}>{s.toUpperCase()}</button>
                    ))}
                  </div>
                  <div style={{display:"flex",gap:5,alignItems:"center",marginBottom:4}}>
                    <input value={filterText} onChange={e=>setFilterText(e.target.value)}
                      placeholder="search title / company..." style={{...inp,fontSize:10,flex:1}}/>
                    <div style={{display:"flex",alignItems:"center",gap:3,flexShrink:0}}>
                      <span style={{fontSize:9,color:"#5a7a68",fontFamily:"monospace",whiteSpace:"nowrap"}}>threshold ≥</span>
                      <input type="number" min={0} max={100} step={5} value={threshold}
                        onChange={e=>{const v=Math.max(0,Math.min(100,parseInt(e.target.value)||0));setThreshold(v);}}
                        title="score threshold % — used by filter, archive, purge, lookup" style={{...inp,width:52,textAlign:"center",fontSize:10}}/>
                      <span style={{fontSize:9,color:"#5a7a68",fontFamily:"monospace"}}>%</span>
                    </div>
                  </div>
                  <div style={{display:"flex",alignItems:"center",gap:4}}>
                    <span style={{fontSize:9,color:"#5a7a68",fontFamily:"monospace"}}>★≥</span>
                    {[0,1,2,3,4,5].map(n=>(
                      <button key={n} onClick={()=>setFilterMinStars(n)} style={{
                        fontSize:n===0?9:12, padding:"1px 5px", borderRadius:3, border:"1px solid",
                        borderColor:filterMinStars===n?"#f59e0b40":"#d4dece",
                        background:filterMinStars===n?"#f59e0b15":"transparent",
                        color:filterMinStars===n?"#f59e0b":"#6b8c7a",
                        cursor:"pointer", fontFamily:"monospace", fontWeight:700, lineHeight:1,
                      }}>{n===0?"ALL":"★".repeat(n)}</button>
                    ))}
                  </div>
                </div>
                </div>{/* end controls wrapper */}

                {/* Log */}
                <div style={{flex:1,minHeight:90,padding:"8px 10px",display:"flex",flexDirection:"column",gap:4,overflow:"hidden"}}>
                  <div style={{display:"flex",justifyContent:"space-between",
                    fontSize:9,color:"#5a7a68",letterSpacing:"0.12em",fontWeight:700}}>
                    <span>LOG</span>
                    <button onClick={()=>setLog([])} style={{background:"none",border:"none",color:"#6b8c7a",cursor:"pointer",fontSize:9}}>CLEAR</button>
                  </div>
                  <LogPane lines={log} running={Object.values(loading).some(Boolean)}/>
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
                          display:"grid",gridTemplateColumns:"26px 1fr 100px 66px 70px 52px 18px",
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
                        <div style={{display:"flex",flexDirection:"column",gap:2,alignItems:"flex-end"}}>
                          <ScoreBar score={j.match_score}/>
                          {j.user_stars && <Stars stars={j.user_stars} jobId={j.id} onUpdate={()=>{fetchJobs();fetchStats();}}/>}
                        </div>
                        <div style={{display:"flex",flexDirection:"column",alignItems:"flex-end",gap:2}}>
                          {j.direction&&<span style={{fontSize:7,fontFamily:"monospace",fontWeight:700,
                            color:"#fff",background:"#2e7d52",padding:"1px 4px",borderRadius:2,letterSpacing:"0.06em"}}>
                            {j.direction.toUpperCase()}</span>}
                          <div style={{fontSize:8,color:"#6b8c7a",fontFamily:"monospace"}}>
                            {j.source?.replace(/\.(ch|com)/,"")}
                          </div>
                        </div>
                        <button onClick={e=>{e.stopPropagation();deleteJob(j.id);}} title="Delete"
                          style={{border:"none",background:"none",color:"#b0c4b8",cursor:"pointer",
                            padding:0,fontSize:12,lineHeight:1,display:"flex",alignItems:"center",
                            justifyContent:"center",borderRadius:3,width:18,height:18,
                            transition:"color 0.15s, background 0.15s"}}
                          onMouseEnter={e=>{e.currentTarget.style.color="#c0392b";e.currentTarget.style.background="#fde8e4";}}
                          onMouseLeave={e=>{e.currentTarget.style.color="#b0c4b8";e.currentTarget.style.background="none";}}>
                          ✕
                        </button>
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
                  <RTab id="company" label="COMPANY"/>
                  <RTab id="timeline" label="TIMELINE"/>
                  <RTab id="apply" label="APPLY"/>
                  <RTab id="tailor" label="TAILOR"/>
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
                          <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:8}}>
                            <span style={{fontSize:11,color:"#4a7a60"}}>
                              {selected.company} · {selected.location}
                            </span>
                          </div>
                          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
                            <Stars stars={selected.user_stars} jobId={selected.id} onUpdate={()=>{fetchJobs();fetchStats();}}/>
                            <span style={{fontSize:9,color:"#6b8c7a",fontFamily:"monospace"}}>
                              {selected.user_stars ? `${selected.user_stars}/5` : "rate this job"}
                            </span>
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
                          <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:6}}>
                            <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.1em",fontWeight:700}}>JD</div>
                            {selected.description && (<>
                              {["en","zh"].map(lang=>(
                                <button key={lang} onClick={()=>translateDesc(selected,lang)} disabled={translating} style={{
                                  fontSize:8,padding:"1px 6px",borderRadius:3,
                                  border:"1px solid #2e7d5230",background:"#2e7d5210",
                                  color:translating?"#6b8c7a":"#2e7d52",
                                  cursor:translating?"not-allowed":"pointer",fontFamily:"monospace",fontWeight:700,
                                }}>{translating?"⟳":lang==="en"?"→EN":"→中文"}</button>
                              ))}
                              {translatedDesc && (
                                <button onClick={()=>setShowOriginalDesc(p=>!p)} style={{
                                  fontSize:8,padding:"1px 6px",borderRadius:3,
                                  border:"1px solid #f59e0b30",background:"#f59e0b10",
                                  color:"#f59e0b",cursor:"pointer",fontFamily:"monospace",fontWeight:700,
                                }}>{showOriginalDesc?"→译文":"→原文"}</button>
                              )}
                            </>)}
                          </div>
                          <div style={{fontSize:10,color:"#708878",lineHeight:1.7,maxHeight:200,overflowY:"auto",
                            background:"#e2e8dc",borderRadius:5,padding:"9px 11px",border:"1px solid #d4dece",
                            whiteSpace:"pre-wrap"}}>
                            {selected.description
                              ? (translatedDesc && !showOriginalDesc ? translatedDesc : selected.description)
                              : <span style={{color:"#6b8c7a"}}>no description — run Enrich</span>
                            }
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
                          <Btn onClick={()=>tailorCv(selected)} loading={loading.tailor}
                            disabled={!selected?.description} label="TAILOR CV FOR THIS JD" icon="📝" color="#f59e0b"/>
                        </div>

                        <div>
                          <div style={{fontSize:9,color:"#5a7a68",letterSpacing:"0.1em",fontWeight:700,marginBottom:7}}>UPDATE STATUS</div>
                          <div style={{display:"flex",flexWrap:"wrap",gap:5,marginBottom:10}}>
                            {["viewed","considering","shortlisted","applied","interviewing","offer","rejected","archived"].map(s=>(
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

                {/* COMPANY TAB */}
                {rightTab==="company" && (
                  <div style={{flex:1,overflowY:"auto",padding:18}}>
                    {!selected
                      ? <div style={{color:"#d4dece",fontSize:12,textAlign:"center",marginTop:50}}>← select a job</div>
                      : <>
                        <div style={{fontSize:14,fontWeight:700,color:"#1a2e20",marginBottom:3}}>
                          {selected.company}
                        </div>
                        <div style={{fontSize:10,color:"#6b8c7a",marginBottom:16}}>
                          {selected.location}
                        </div>
                        {companyCache[selected.company]
                          ? <div style={{
                              fontSize:11,color:"#2a3e2a",lineHeight:1.8,
                              whiteSpace:"pre-wrap",
                            }}>
                              {companyCache[selected.company]}
                            </div>
                          : <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:12,marginTop:40}}>
                              {companyCache[selected.company] === null
                                ? <>
                                    <span style={{fontSize:11,color:"#6b8c7a"}}>No info cached yet.</span>
                                    <button onClick={()=>triggerCompanyLookup(selected.company)}
                                      disabled={lookingUpCompany}
                                      style={{
                                        padding:"6px 14px",borderRadius:4,border:"1px solid #2e7d5235",
                                        background:"#2e7d520d",color:"#2e7d52",fontSize:11,
                                        fontWeight:700,fontFamily:"monospace",cursor:"pointer",
                                      }}>
                                      {lookingUpCompany ? "⟳ Looking up…" : "🔍 Lookup company"}
                                    </button>
                                  </>
                                : <span style={{fontSize:11,color:"#6b8c7a",fontFamily:"monospace"}}>⟳ loading…</span>
                              }
                            </div>
                        }
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

                {/* TAILOR TAB */}
                {rightTab==="tailor" && (
                  <div style={{flex:1,overflowY:"auto",padding:18,display:"flex",flexDirection:"column",gap:14}}>
                    {!selected
                      ? <div style={{color:"#d4dece",fontSize:12,textAlign:"center",marginTop:50}}>← select a job first</div>
                      : !tailorResult
                      ? <div style={{display:"flex",flexDirection:"column",gap:10,alignItems:"center",marginTop:40}}>
                          <div style={{fontSize:11,color:"#5a7a68",textAlign:"center"}}>
                            Generate tailored suggestions for<br/>
                            <strong style={{color:"#1a2e20"}}>{selected.title}</strong>
                          </div>
                          <Btn onClick={()=>tailorCv(selected)} loading={loading.tailor}
                            disabled={!selected.description} label="TAILOR CV FOR THIS JD" icon="📝" color="#f59e0b"/>
                          {!selected.description && <div style={{fontSize:9,color:"#f59e0b"}}>run Enrich first to get full JD</div>}
                        </div>
                      : <>
                        {/* Missing keywords */}
                        {tailorResult.missing_keywords?.length > 0 && (
                          <div>
                            <div style={{fontSize:9,fontWeight:700,color:"#5a7a68",letterSpacing:"0.1em",marginBottom:6}}>MISSING KEYWORDS TO ADD</div>
                            <div style={{display:"flex",flexWrap:"wrap",gap:5}}>
                              {tailorResult.missing_keywords.map((kw,i)=>(
                                <span key={i} style={{fontSize:9,padding:"2px 7px",borderRadius:10,
                                  background:"#fef3c7",color:"#92400e",border:"1px solid #f59e0b40"}}>
                                  {kw}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Suggestions */}
                        {tailorResult.suggestions?.length > 0 && (
                          <div>
                            <div style={{fontSize:9,fontWeight:700,color:"#5a7a68",letterSpacing:"0.1em",marginBottom:8}}>SUGGESTED REWRITES</div>
                            <div style={{display:"flex",flexDirection:"column",gap:10}}>
                              {tailorResult.suggestions.map((s,i)=>(
                                <div key={i} style={{background:"#e2e8dc",borderRadius:5,padding:"10px 12px",
                                  border:"1px solid #d4dece",fontSize:10}}>
                                  <div style={{fontWeight:700,color:"#2e7d52",marginBottom:5,fontSize:9,letterSpacing:"0.05em"}}>
                                    {s.section}
                                  </div>
                                  <div style={{color:"#708878",marginBottom:4,textDecoration:"line-through",opacity:0.7}}>
                                    {s.original}
                                  </div>
                                  <div style={{color:"#1a2e20",marginBottom:5,lineHeight:1.5}}>
                                    → {s.rewrite}
                                  </div>
                                  <div style={{fontSize:9,color:"#f59e0b",fontStyle:"italic"}}>
                                    {s.reason}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <Btn onClick={()=>tailorCv(selected)} loading={loading.tailor}
                          label="REGENERATE" icon="↻" color="#f59e0b"/>
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
