"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"

const messages = [
  'Received: "Summarize Q3 performance for stakeholder report..."',
  "Chunking input → 847 tokens → 6 embeddings generated",
  "Vector search complete: 5 chunks, avg cosine sim 0.89",
  "Injecting context into prompt template (1,204 tokens)",
  "LLM inference: 3 tool calls dispatched in parallel",
  "Tool: send_email → draft created, pending approval",
  "Tool: update_crm → record Q3_2024 flagged as reviewed",
  "Tool: generate_report → PDF queued for dispatch",
  "Workflow complete. 3 actions dispatched in 342ms.",
]

const nodes = [
  ["TRIGGER", "User Query", "node-01"],
  ["VECTOR DB", "Semantic Search", "pinecone"],
  ["LLM AGENT", "Processing", "claude"],
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
