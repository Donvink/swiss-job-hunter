import { useState, useEffect, useCallback } from "react";
import { API } from "./api.js";
import { INTERVIEW_TYPE_META, INTERVIEW_FORMAT_META, INTERVIEW_OUTCOME_META } from "./interviewMeta.js";

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

export default function UpcomingInterviews({ onSelectJob }) {
  const [items, setItems] = useState([]);
  const [includePast, setIncludePast] = useState(false);
  const [loading, setLoading] = useState(false);

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
        <button onClick={()=>setIncludePast(p=>!p)} style={{
          fontSize:9,padding:"3px 9px",borderRadius:3,border:"1px solid #4d7ab550",
          background:"#4d7ab510",color:"#4d7ab5",cursor:"pointer",fontFamily:"monospace",fontWeight:700,
        }}>{includePast ? "HIDE PAST" : "SHOW PAST"}</button>
      </div>

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
