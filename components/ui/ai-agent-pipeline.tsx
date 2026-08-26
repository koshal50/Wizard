"use client"

import { useEffect, useState } from "react"

const events = [
  ["09:41:02", "Scope locked", "Validated task requirements and target surface"],
  ["09:41:04", "Repository inspected", "8 relevant files selected from 42 discovered"],
  ["09:41:07", "Implementation verified", "TypeScript and responsive UI checks passed"],
  ["09:41:10", "Browser evidence captured", "wizardagents.vercel.app loaded and replayed"],
]

export default function AIAgentPipeline() {
  const [active, setActive] = useState(3)
  const [run, setRun] = useState(1247)

  useEffect(() => {
    const eventTimer = window.setInterval(() => setActive((value) => (value + 1) % events.length), 2600)
    const runTimer = window.setInterval(() => setRun((value) => value + 1), 7200)
    return () => { window.clearInterval(eventTimer); window.clearInterval(runTimer) }
  }, [])

  return (
    <div className="verification-report">
      <div className="verification-report__header">
        <div><span className="verification-report__status" /> <span>WIZARD VERIFICATION REPORT</span></div>
        <span className="verification-report__id">RUN WZ-02481 · LIVE TRACE</span>
      </div>
      <div className="verification-report__summary">
        <div className="verification-report__check">✓</div>
        <div><p className="verification-report__eyebrow">VERIFICATION COMPLETE</p><h3>Change is ready for review</h3><p>Wizard inspected the repository, replayed the browser path, and attached evidence for every conclusion.</p></div>
      </div>
      <div className="verification-report__grid">
        <section><p className="verification-report__label">EXECUTION TRACE</p><div className="verification-report__timeline">{events.map(([time, title, detail], index) => <div key={time} className={index === active ? "is-active" : ""}><span>{time}</span><div><strong>{title}</strong><small>{detail}</small></div><i>✓</i></div>)}</div></section>
        <section className="verification-report__findings"><p className="verification-report__label">FINDINGS</p><div><b>8</b><span>files inspected</span></div><div><b>3</b><span>checks passed</span></div><div><b>0</b><span>blocking issues</span></div></section>
      </div>
      <div className="verification-report__footer"><span>Recommendation: ship with confidence</span><span>{run.toLocaleString()} verified runs · 342ms avg</span></div>
    </div>
  )
}


