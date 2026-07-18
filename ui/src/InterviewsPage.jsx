import { useState } from "react";
import UpcomingInterviews from "./UpcomingInterviews.jsx";
import QuestionSearch from "./QuestionSearch.jsx";
import ResumeVersions from "./ResumeVersions.jsx";
import StarStoryLibrary from "./StarStoryLibrary.jsx";

const SUB_TABS = [
  { id: "upcoming", label: "UPCOMING" },
  { id: "search",   label: "SEARCH" },
  { id: "resumes",  label: "RESUMES" },
  { id: "stories",  label: "STORIES" },
];

export default function InterviewsPage({ onSelectJob, addLog }) {
  const [interviewSubTab, setInterviewSubTab] = useState("upcoming");

  return (
    <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden",background:"#f5f0e8"}}>
      <div style={{
        display:"flex",alignItems:"center",gap:2,padding:"0 20px",
        borderBottom:"1px solid #d4cfc4",background:"#ede8de",flexShrink:0,
      }}>
        {SUB_TABS.map(t => (
          <button key={t.id} onClick={()=>setInterviewSubTab(t.id)} style={{
            padding:"10px 16px",border:"none",background:"transparent",
            color:interviewSubTab===t.id?"#2c2820":"#8a8278",
            fontSize:10,fontWeight:700,letterSpacing:"0.08em",
            cursor:"pointer",fontFamily:"monospace",
            borderBottom:interviewSubTab===t.id?"2px solid #4d7ab5":"2px solid transparent",
            transition:"color 0.15s",
          }}>{t.label}</button>
        ))}
      </div>

      <div style={{flex:1,overflowY:"auto",padding:20}}>
        {interviewSubTab==="upcoming" && <UpcomingInterviews onSelectJob={onSelectJob}/>}
        {interviewSubTab==="search" && <QuestionSearch onSelectJob={onSelectJob}/>}
        {interviewSubTab==="resumes" && <ResumeVersions addLog={addLog}/>}
        {interviewSubTab==="stories" && <StarStoryLibrary addLog={addLog}/>}
      </div>
    </div>
  );
}
