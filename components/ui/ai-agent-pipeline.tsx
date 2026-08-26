"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"

const events = [
  "Investigation created · intent: verify runtime",
  "Repository manifest generated · 42 files indexed",
  "Technology plan created · runtime, dependencies, deployment",
  "Observation obs_031 · package.json declares Node.js 18",
  "Claim created · runtime matches declared environment",
  "Observation obs_034 · install completed with exit code 0",
  "Claim created · dependencies are installable",
  "Trust recalculated · runtime evidence HIGH",
  "Checkpoint satisfied · verification complete",
  "Convergence reached · report generated",
]

const claims = [
  ["Runtime", "Node.js 18", "HIGH"],
  ["Dependencies", "Installable", "HIGH"],
  ["Application", "Executes", "HIGH"],
]

export default function AIAgentPipeline() {
  const [eventIndex, setEventIndex] = useState(0)
  const [visibleClaims, setVisibleClaims] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setEventIndex((value) => {
        const next = (value + 1) % events.length
        setVisibleClaims(Math.min(claims.length, Math.max(0, next - 6)))
        return next
      })
    }, 2700)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="pipeline-report" role="region" aria-label="Wizard verification report">
      <div className="pipeline-header">
        <span className="pipeline-live"><i /> WIZARD VERIFICATION · LIVE</span>
        <span>{visibleClaims} claims · 0 contradictions</span>
      </div>
      <div className="pipeline-graph">
        <div className="pipeline-flow pipeline-flow-one" />
        <div className="pipeline-flow pipeline-flow-two" />
        <div className="pipeline-flow pipeline-flow-three" />
        {[
          ["INVESTIGATION", "What we did", "node_014"],
          ["OBSERVATION", "What happened", "obs_031"],
          ["KNOWLEDGE", "What we know", "claim_007"],
        ].map(([label, title, meta], index) => (
          <div key={label} className={`pipeline-node pipeline-node-${index}`}>
            <small>{label}</small><strong>{title}</strong><em>{meta}</em>
            {index === 2 && <span className="pipeline-dots"><b /><b /><b /></span>}
          </div>
        ))}
        <div className="pipeline-outputs"><span>Runtime <b>VERIFIED</b></span><span>Dependencies <b>VERIFIED</b></span><span>Execution <b>VERIFIED</b></span></div>
      </div>
      <div className="pipeline-message"><span>›</span><p>{events[eventIndex]}</p></div>
      <div className="pipeline-stats">
        <span><small>CLAIMS</small><b>{visibleClaims || 3}</b></span>
        <span><small>EVIDENCE</small><b>9</b></span>
        <span><small>CONFIDENCE</small><b>HIGH</b></span>
        <span className="pipeline-stack"><small>REPORT STATUS</small><b>READY TO SHIP</b></span>
      </div>
    </div>
  )
}
