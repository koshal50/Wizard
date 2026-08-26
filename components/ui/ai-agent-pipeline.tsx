"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"

const messages = [
  'Task received: "Validate the latest Wizard change"',
  "Repository mapped → 42 files discovered → 8 relevant files selected",
  "Evidence gathered from app/page.tsx, hero.tsx, globals.css",
  "Browser check complete → wizardagents.vercel.app loaded successfully",
  "Agent replayed the path: inspect → execute → verify",
  "Finding: laptop scene and report render without blocking errors",
  "Finding: responsive layout verified at desktop and mobile widths",
  "Recommendation: ship the verified change with the captured evidence",
  "Verification complete. 8 checks passed · 0 blockers.",
]

const nodes = [
  ["SCOPE", "Inspect", "8 files"],
  ["ACTION", "Execute", "3 checks"],
  ["RESULT", "Verify", "0 blockers"],
]

export default function AIAgentPipeline() {
  const [message, setMessage] = useState(0)
  const [workflows, setWorkflows] = useState(1247)

  useEffect(() => {
    const messageTimer = window.setInterval(() => setMessage((value) => (value + 1) % messages.length), 2700)
    const workflowTimer = window.setInterval(() => setWorkflows((value) => value + 1), 7200)
    return () => { window.clearInterval(messageTimer); window.clearInterval(workflowTimer) }
  }, [])

  return (
    <div className="pipeline-report">
      <div className="pipeline-header">
        <span className="pipeline-live"><i /> AGENT PIPELINE · LIVE</span>
        <span>3 agents · 0 errors</span>
      </div>
      <div className="pipeline-graph" aria-label="Live agent pipeline">
        <div className="pipeline-flow pipeline-flow-one" />
        <div className="pipeline-flow pipeline-flow-two" />
        <div className="pipeline-flow pipeline-flow-three" />
        {nodes.map(([label, title, meta], index) => (
          <div key={label} className={`pipeline-node pipeline-node-${index}`}>
            <small>{label}</small><strong>{title}</strong><em>{meta}</em>
            {index === 2 && <span className="pipeline-dots"><b /><b /><b /></span>}
          </div>
        ))}
        <div className="pipeline-outputs">
          <span><b>●</b> Email Draft</span>
          <span><b>●</b> CRM Update</span>
          <span><b>●</b> Report Gen</span>
        </div>
      </div>
      <div className="pipeline-message"><span>›</span><motion.p key={message} initial={{ opacity: 0.35 }} animate={{ opacity: 1 }}>{messages[message]}</motion.p></div>
      <div className="pipeline-stats">
        <span><small>WORKFLOWS</small><b>{workflows.toLocaleString()}</b></span>
        <span><small>TOKENS</small><b>4.2M</b></span>
        <span><small>AVG LATENCY</small><b>342ms</b></span>
        <span className="pipeline-stack"><small>STACK</small><b>Claude · Pinecone</b></span>
      </div>
    </div>
  )
}
