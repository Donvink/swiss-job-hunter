import { useState } from "react";
import { API } from "./api.js";

const inp = {
  width:"100%",padding:"6px 9px",borderRadius:4,
  background:"#faf7f2",border:"1px solid #c8c2b4",
  color:"#4a4238",fontSize:11,
};

export default function QuestionSearch({ onSelectJob }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const search = async () => {
    if (!q.trim()) return;
    setLoading(true);
    try {
      const r = await fetch(`${API}/interview-questions/search?q=${encodeURIComponent(q.trim())}`);
      if (r.ok) setResults(await r.json());
    } finally {
      setLoading(false);
      setSearched(true);
    }
  };

  return (
    <div>
      <div style={{display:"flex",gap:6,marginBottom:14}}>
        <input value={q} onChange={e=>setQ(e.target.value)}
          onKeyDown={e=>{ if (e.key==="Enter") search(); }}
          placeholder="Search past interview questions & answers..." style={{...inp,flex:1}}/>
        <button onClick={search} disabled={loading} style={{
          display:"flex",alignItems:"center",gap:6,padding:"7px 14px",
          borderRadius:5,border:"1px solid #4d7ab550",background:"#4d7ab510",
          color:"#4d7ab5",fontSize:11,fontWeight:700,letterSpacing:"0.05em",
          cursor:loading?"not-allowed":"pointer",fontFamily:"monospace",
          opacity:loading?0.6:1,whiteSpace:"nowrap",
        }}>{loading?"⟳":"🔍"} SEARCH</button>
      </div>

      {!searched
        ? <div style={{color:"#a8a098",fontSize:11,padding:"8px 0"}}>Search across every question and answer logged in past interview rounds</div>
        : results.length===0
        ? <div style={{color:"#a8a098",fontSize:11,padding:"8px 0"}}>No matches for "{q}"</div>
        : (
          <div style={{display:"flex",flexDirection:"column",gap:8}}>
            {results.map(r => (
              <div key={r.id} onClick={()=>onSelectJob?.(r.job.id)} style={{
                background:"#e8e3d8",border:"1px solid #c8c2b4",borderRadius:6,
                padding:"10px 12px",cursor:"pointer",transition:"border-color 0.12s",
              }}
                onMouseEnter={e=>e.currentTarget.style.borderColor="#4d7ab550"}
                onMouseLeave={e=>e.currentTarget.style.borderColor="#c8c2b4"}
              >
                <div style={{fontSize:10,color:"#7a7268",marginBottom:4}}>
                  {r.job.title} · {r.job.company} · Round {r.interview.round_number}
                </div>
                <div style={{fontSize:11,fontWeight:700,color:"#2c2820",marginBottom:3}}>{r.question}</div>
                {r.my_answer && (
                  <div style={{fontSize:10,color:"#5e5850",lineHeight:1.5}}>
                    {r.my_answer.length > 200 ? r.my_answer.slice(0,200)+"…" : r.my_answer}
                  </div>
                )}
              </div>
            ))}
          </div>
        )
      }
    </div>
  );
}
