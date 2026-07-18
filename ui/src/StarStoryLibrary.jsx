import { useState, useEffect, useCallback } from "react";
import { API } from "./api.js";

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

function tagList(tags) {
  return (tags || "").split(",").map(t => t.trim()).filter(Boolean);
}

// ── New-story form ───────────────────────────────────────────────────────────

function NewStoryForm({ addLog, onDone, onCancel }) {
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [situation, setSituation] = useState("");
  const [task, setTask] = useState("");
  const [action, setAction] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);

  const valid = title.trim() && situation.trim() && task.trim() && action.trim() && result.trim();

  const submit = async () => {
    if (!valid) return;
    setLoading(true);
    try {
      const r = await fetch(`${API}/star-stories`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ title, tags: tags.trim() || null, situation, task, action, result }),
      });
      if (r.ok) { addLog(`✓ Story "${title}" added`); onDone(); }
      else { const err = await r.text(); addLog(`✗ Add story failed: ${err.slice(0,150)}`); }
    } catch (e) { addLog(`✗ ${e.message}`); }
    finally { setLoading(false); }
  };

  return (
    <div style={{background:"#e8e3d8",border:"1px solid #c8c2b4",borderRadius:6,padding:12,marginBottom:12,gridColumn:"1 / -1"}}>
      <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:6}}>NEW STORY</div>
      <input value={title} onChange={e=>setTitle(e.target.value)}
        placeholder="Title..." style={{...inp,marginBottom:6,fontSize:10}}/>
      <input value={tags} onChange={e=>setTags(e.target.value)}
        placeholder="Tags (comma-separated, optional)..." style={{...inp,marginBottom:6,fontSize:10}}/>
      <textarea value={situation} onChange={e=>setSituation(e.target.value)}
        placeholder="Situation..." style={{...inp,minHeight:44,resize:"vertical",marginBottom:6,fontFamily:"inherit",fontSize:10}}/>
      <textarea value={task} onChange={e=>setTask(e.target.value)}
        placeholder="Task..." style={{...inp,minHeight:44,resize:"vertical",marginBottom:6,fontFamily:"inherit",fontSize:10}}/>
      <textarea value={action} onChange={e=>setAction(e.target.value)}
        placeholder="Action..." style={{...inp,minHeight:44,resize:"vertical",marginBottom:6,fontFamily:"inherit",fontSize:10}}/>
      <textarea value={result} onChange={e=>setResult(e.target.value)}
        placeholder="Result..." style={{...inp,minHeight:44,resize:"vertical",marginBottom:8,fontFamily:"inherit",fontSize:10}}/>
      <div style={{display:"flex",gap:6,justifyContent:"flex-end"}}>
        <ActionBtn onClick={onCancel} label="Cancel" icon="✕" color="#8a8278" small/>
        <ActionBtn onClick={submit} loading={loading} disabled={!valid} label="Add" icon="+" color="#4d7ab5" small/>
      </div>
    </div>
  );
}

// ── Story card ───────────────────────────────────────────────────────────────

function StoryCard({ story, expanded, onToggle, addLog, onChanged, onDeleted }) {
  const [title, setTitle] = useState(story.title);
  const [tags, setTags] = useState(story.tags || "");
  const [situation, setSituation] = useState(story.situation);
  const [task, setTask] = useState(story.task);
  const [action, setAction] = useState(story.action);
  const [result, setResult] = useState(story.result);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setTitle(story.title);
    setTags(story.tags || "");
    setSituation(story.situation);
    setTask(story.task);
    setAction(story.action);
    setResult(story.result);
  }, [story.id, story.updated_at]);

  const save = async () => {
    if (!title.trim() || !situation.trim() || !task.trim() || !action.trim() || !result.trim()) return;
    setSaving(true);
    try {
      const r = await fetch(`${API}/star-stories/${story.id}`, {
        method:"PATCH", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ title, tags: tags.trim() || null, situation, task, action, result }),
      });
      if (r.ok) { addLog(`✓ Story "${title}" saved`); onChanged(); }
      else addLog(`✗ Save failed`);
    } finally { setSaving(false); }
  };

  const del = async () => {
    const r = await fetch(`${API}/star-stories/${story.id}`, { method:"DELETE" });
    if (r.ok) { addLog(`✓ Story "${story.title}" deleted`); onDeleted(); }
    else addLog(`✗ Delete failed`);
  };

  return (
    <div style={{
      background:"#e8e3d8",border:"1px solid #c8c2b4",borderRadius:6,overflow:"hidden",
      gridColumn: expanded ? "1 / -1" : undefined,
    }}>
      <div onClick={onToggle} style={{
        padding:"10px 12px",cursor:"pointer",display:"flex",alignItems:"center",gap:10,
      }}>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontSize:11,fontWeight:700,color:"#2c2820",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
            {story.title}
          </div>
          {tagList(story.tags).length > 0 && (
            <div style={{display:"flex",flexWrap:"wrap",gap:4,marginTop:5}}>
              {tagList(story.tags).map(t => (
                <span key={t} style={{
                  fontSize:9,padding:"1px 6px",borderRadius:3,
                  border:"1px solid #4d7ab535",background:"#4d7ab510",
                  color:"#4d7ab5",fontFamily:"monospace",fontWeight:600,
                }}>{t}</span>
              ))}
            </div>
          )}
        </div>
        <button onClick={e=>{e.stopPropagation();del();}} title="Delete story" style={{
          border:"none",background:"none",color:"#d4cfc4",cursor:"pointer",fontSize:13,lineHeight:1,flexShrink:0,
        }}>✕</button>
        <span style={{color:"#8a8278",fontSize:10,flexShrink:0}}>{expanded?"▲":"▼"}</span>
      </div>

      {expanded && (
        <div style={{padding:"0 12px 14px",borderTop:"1px solid #d4cfc4"}}>
          <input value={title} onChange={e=>setTitle(e.target.value)}
            placeholder="Title..." style={{...inp,marginTop:10,marginBottom:6,fontWeight:700}}/>
          <input value={tags} onChange={e=>setTags(e.target.value)}
            placeholder="Tags (comma-separated)..." style={{...inp,marginBottom:10,fontSize:10}}/>

          <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:4}}>SITUATION</div>
          <textarea value={situation} onChange={e=>setSituation(e.target.value)}
            style={{...inp,minHeight:50,resize:"vertical",marginBottom:8,fontFamily:"inherit"}}/>

          <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:4}}>TASK</div>
          <textarea value={task} onChange={e=>setTask(e.target.value)}
            style={{...inp,minHeight:50,resize:"vertical",marginBottom:8,fontFamily:"inherit"}}/>

          <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:4}}>ACTION</div>
          <textarea value={action} onChange={e=>setAction(e.target.value)}
            style={{...inp,minHeight:50,resize:"vertical",marginBottom:8,fontFamily:"inherit"}}/>

          <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:4}}>RESULT</div>
          <textarea value={result} onChange={e=>setResult(e.target.value)}
            style={{...inp,minHeight:50,resize:"vertical",marginBottom:10,fontFamily:"inherit"}}/>

          <div style={{display:"flex",justifyContent:"flex-end"}}>
            <ActionBtn onClick={save} loading={saving} label="Save Story" icon="✓" color="#4d8a68" small/>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function StarStoryLibrary({ addLog }) {
  const [stories, setStories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/star-stories`);
      if (r.ok) setStories(await r.json());
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <div style={{fontSize:10,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700}}>STAR STORIES</div>
        <button onClick={()=>setAdding(p=>!p)} style={{
          fontSize:9,padding:"3px 9px",borderRadius:3,border:"1px solid #4d7ab550",
          background:"#4d7ab510",color:"#4d7ab5",cursor:"pointer",fontFamily:"monospace",fontWeight:700,
        }}>+ NEW STORY</button>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(280px,1fr))",gap:10}}>
        {adding && (
          <NewStoryForm addLog={addLog}
            onDone={()=>{ setAdding(false); load(); }}
            onCancel={()=>setAdding(false)}/>
        )}

        {loading && stories.length===0
          ? <div style={{color:"#a8a098",fontSize:11,padding:"8px 0",gridColumn:"1 / -1"}}>Loading…</div>
          : stories.length===0 && !adding
          ? <div style={{color:"#a8a098",fontSize:11,padding:"8px 0",gridColumn:"1 / -1"}}>No STAR stories yet</div>
          : stories.map(s => (
            <StoryCard key={s.id} story={s} addLog={addLog}
              expanded={expandedId===s.id}
              onToggle={()=>setExpandedId(p=>p===s.id?null:s.id)}
              onChanged={load}
              onDeleted={async ()=>{ if(expandedId===s.id) setExpandedId(null); await load(); }}/>
          ))
        }
      </div>
    </div>
  );
}
