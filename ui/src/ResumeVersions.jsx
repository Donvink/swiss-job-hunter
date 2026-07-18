import { useState, useEffect, useCallback } from "react";
import { API } from "./api.js";

const inp = {
  width:"100%",padding:"6px 9px",borderRadius:4,
  background:"#faf7f2",border:"1px solid #c8c2b4",
  color:"#4a4238",fontSize:11,
};

const FILE_FORMAT_META = {
  pdf:  { icon:"📄", color:"#c06838" },
  docx: { icon:"📝", color:"#4d7ab5" },
  txt:  { icon:"📃", color:"#8a8278" },
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

function fmtDt(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("de-CH",{day:"2-digit",month:"2-digit",year:"numeric"}) + " " +
         d.toLocaleTimeString("de-CH",{hour:"2-digit",minute:"2-digit"});
}

// ── Upload form ──────────────────────────────────────────────────────────────

function UploadForm({ direction, addLog, onDone, onCancel }) {
  const [file, setFile] = useState(null);
  const [label, setLabel] = useState("");
  const [changelog, setChangelog] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!file || !label.trim()) return;
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (direction) fd.append("direction", direction);
      fd.append("label", label);
      if (changelog.trim()) fd.append("changelog", changelog);
      const r = await fetch(`${API}/resume-versions`, { method:"POST", body: fd });
      if (r.ok) { addLog(`✓ Resume version "${label}" uploaded`); onDone(); }
      else { const err = await r.text(); addLog(`✗ Upload failed: ${err.slice(0,150)}`); }
    } catch (e) { addLog(`✗ ${e.message}`); }
    finally { setLoading(false); }
  };

  return (
    <div style={{background:"#e8e3d8",border:"1px solid #c8c2b4",borderRadius:6,padding:12,marginBottom:12}}>
      <div style={{fontSize:9,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:6}}>
        NEW VERSION — {direction ? direction.toUpperCase() : "NO DIRECTION"}
      </div>
      <input type="file" accept=".pdf,.docx,.txt" onChange={e=>setFile(e.target.files[0]||null)}
        style={{...inp,marginBottom:6,fontSize:10,padding:"5px 8px"}}/>
      <input value={label} onChange={e=>setLabel(e.target.value)}
        placeholder="Label (e.g. v2, tailored-for-fintech)..." style={{...inp,marginBottom:6,fontSize:10}}/>
      <textarea value={changelog} onChange={e=>setChangelog(e.target.value)}
        placeholder="Changelog (optional)..." style={{...inp,minHeight:44,resize:"vertical",marginBottom:8,fontFamily:"inherit",fontSize:10}}/>
      <div style={{display:"flex",gap:6,justifyContent:"flex-end"}}>
        <ActionBtn onClick={onCancel} label="Cancel" icon="✕" color="#8a8278" small/>
        <ActionBtn onClick={submit} loading={loading} disabled={!file||!label.trim()} label="Upload" icon="+" color="#4d7ab5" small/>
      </div>
    </div>
  );
}

// ── Version row ──────────────────────────────────────────────────────────────

function VersionRow({ version, addLog, onChanged }) {
  const [busy, setBusy] = useState(false);
  const fm = FILE_FORMAT_META[version.file_format] || { icon:"•", color:"#8a8278" };

  const activate = async () => {
    setBusy(true);
    try {
      const r = await fetch(`${API}/resume-versions/${version.id}/activate`, { method:"PATCH" });
      if (r.ok) { addLog(`✓ "${version.label}" activated`); onChanged(); }
      else addLog(`✗ Activate failed`);
    } finally { setBusy(false); }
  };

  const del = async () => {
    setBusy(true);
    try {
      const r = await fetch(`${API}/resume-versions/${version.id}`, { method:"DELETE" });
      if (r.ok) { addLog(`✓ "${version.label}" deleted`); onChanged(); }
      else { const err = await r.text(); addLog(`✗ Delete failed: ${err.slice(0,150)}`); }
    } finally { setBusy(false); }
  };

  return (
    <div style={{background:"#e8e3d8",border:"1px solid #c8c2b4",borderRadius:6,padding:"10px 12px",marginBottom:8}}>
      <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
        <span style={{fontSize:12,fontWeight:700,color:"#2c2820"}}>{version.label}</span>
        <span style={{fontSize:10,color:fm.color}}>{fm.icon} {(version.file_format||"").toUpperCase()}</span>
        {version.is_active && (
          <span style={{
            fontSize:9,fontWeight:700,letterSpacing:"0.08em",color:"#4d8a68",
            background:"rgba(77,138,104,0.10)",padding:"2px 7px",borderRadius:3,
            border:"1px solid #4d8a6835",fontFamily:"monospace",
          }}>ACTIVE</span>
        )}
      </div>
      <div style={{fontSize:10,color:"#7a7268",marginTop:2}}>{version.original_filename}</div>
      {version.changelog && (
        <div style={{fontSize:10,color:"#5e5850",marginTop:4,lineHeight:1.5}}>{version.changelog}</div>
      )}
      <div style={{fontSize:9,color:"#a8a098",fontFamily:"monospace",marginTop:4}}>{fmtDt(version.uploaded_at)}</div>

      <div style={{display:"flex",gap:6,marginTop:8,justifyContent:"flex-end"}}>
        <a href={`${API}/resume-versions/${version.id}/download`} style={{
          display:"flex",alignItems:"center",gap:6,padding:"4px 8px",
          borderRadius:5,border:"1px solid #4d7ab550",background:"#4d7ab510",
          color:"#4d7ab5",fontSize:10,fontWeight:700,letterSpacing:"0.05em",
          fontFamily:"monospace",textDecoration:"none",whiteSpace:"nowrap",
        }}>⬇ Download</a>
        {!version.is_active && (
          <ActionBtn onClick={activate} loading={busy} label="Activate" icon="✓" color="#4d8a68" small/>
        )}
        {!version.is_active && (
          <ActionBtn onClick={del} loading={busy} label="Delete" icon="✕" color="#b84848" small/>
        )}
      </div>
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function ResumeVersions({ addLog }) {
  const [directions, setDirections] = useState([]);
  const [selDirection, setSelDirection] = useState("");
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    fetch(`${API}/directions`).then(r=>r.ok?r.json():[]).then(setDirections).catch(()=>{});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/resume-versions`);
      if (r.ok) setVersions(await r.json());
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = versions
    .filter(v => (v.direction||"") === selDirection)
    .sort((a,b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));

  const pill = (active) => ({
    fontSize:9,padding:"3px 9px",borderRadius:3,
    border:`1px solid ${active?"#4d7ab555":"#c8c2b4"}`,
    background:active?"#4d7ab512":"transparent",
    color:active?"#4d7ab5":"#8a8278",
    cursor:"pointer",fontFamily:"monospace",fontWeight:700,letterSpacing:"0.05em",
  });

  return (
    <div>
      <div style={{fontSize:10,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700,marginBottom:8}}>DIRECTION</div>
      <div style={{display:"flex",flexWrap:"wrap",gap:4,marginBottom:16}}>
        <button onClick={()=>setSelDirection("")} style={pill(selDirection==="")}>— NO DIRECTION —</button>
        {directions.map(d => (
          <button key={d} onClick={()=>setSelDirection(d)} style={pill(selDirection===d)}>{d.toUpperCase()}</button>
        ))}
      </div>

      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
        <div style={{fontSize:10,color:"#8a8278",letterSpacing:"0.1em",fontWeight:700}}>
          {selDirection ? selDirection.toUpperCase() : "NO DIRECTION"} — VERSIONS
        </div>
        <button onClick={()=>setUploading(p=>!p)} style={{
          fontSize:9,padding:"3px 9px",borderRadius:3,border:"1px solid #4d7ab550",
          background:"#4d7ab510",color:"#4d7ab5",cursor:"pointer",fontFamily:"monospace",fontWeight:700,
        }}>+ UPLOAD VERSION</button>
      </div>

      {uploading && (
        <UploadForm direction={selDirection || null} addLog={addLog}
          onDone={()=>{ setUploading(false); load(); }}
          onCancel={()=>setUploading(false)}/>
      )}

      {loading && filtered.length===0
        ? <div style={{color:"#a8a098",fontSize:11,padding:"8px 0"}}>Loading…</div>
        : filtered.length===0
        ? <div style={{color:"#a8a098",fontSize:11,padding:"8px 0"}}>No resume versions yet</div>
        : filtered.map(v => (
          <VersionRow key={v.id} version={v} addLog={addLog} onChanged={load}/>
        ))
      }
    </div>
  );
}
