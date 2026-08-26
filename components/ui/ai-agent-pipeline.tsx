"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"

type EventType =
  | "REQUEST"
  | "MANIFEST"
  | "PLAN"
  | "NODE"
  | "OBSERVATION"
  | "CLAIM"
  | "TRUST"
  | "CHECKPOINT"
  | "CONVERGENCE"
  | "REPORT"

interface InvestigationEvent {
  type: EventType
  id: string
  text: string
  detail: string
  parent?: string
}

const events: InvestigationEvent[] = [
  {
    type: "REQUEST",
    id: "inv_001",
    text: "Investigation created",
    detail: "intent: verify runtime",
  },
  {
    type: "MANIFEST",
    id: "manifest_001",
    text: "Repository manifest generated",
    detail: "42 files · 3 technologies identified",
  },
  {
    type: "PLAN",
    id: "plan_001",
    text: "Technology Plan created",
    detail: "runtime · dependencies · execution",
  },
  {
    type: "NODE",
    id: "node_014",
    text: "Read package.json",
    detail: "hypothesis: repository declares Node.js runtime",
  },
  {
    type: "OBSERVATION",
    id: "obs_031",
    text: "Node.js 18 declared",
    detail: "source: package.json · line 12",
    parent: "node_014",
  },
  {
    type: "CLAIM",
    id: "claim_007",
    text: "Runtime = Node.js 18",
    detail: "supported by obs_031",
    parent: "obs_031",
  },
  {
    type: "TRUST",
    id: "trust_007",
    text: "Claim trust recalculated",
    detail: "claim_007 · HIGH",
    parent: "claim_007",
  },
  {
    type: "NODE",
    id: "node_019",
    text: "Execute npm install",
    detail: "hypothesis: dependencies are installable",
  },
  {
    type: "OBSERVATION",
    id: "obs_034",
    text: "Command completed",
    detail: "npm install · exit code 0",
    parent: "node_019",
  },
  {
    type: "CLAIM",
    id: "claim_008",
    text: "Dependencies are installable",
    detail: "supported by obs_034",
    parent: "obs_034",
  },
  {
    type: "TRUST",
    id: "trust_008",
    text: "Claim trust recalculated",
    detail: "claim_008 · HIGH",
    parent: "claim_008",
  },
  {
    type: "NODE",
    id: "node_027",
    text: "Start application",
    detail: "hypothesis: application executes successfully",
  },
  {
    type: "OBSERVATION",
    id: "obs_041",
    text: "Application responded",
    detail: "localhost:3000 · response received",
    parent: "node_027",
  },
  {
    type: "CLAIM",
    id: "claim_009",
    text: "Application executes",
    detail: "supported by obs_041",
    parent: "obs_041",
  },
  {
    type: "TRUST",
    id: "trust_009",
    text: "Claim trust recalculated",
    detail: "claim_009 · HIGH",
    parent: "claim_009",
  },
  {
    type: "CHECKPOINT",
    id: "checkpoint_002",
    text: "Runtime verification satisfied",
    detail: "required evidence available",
  },
  {
    type: "CONVERGENCE",
    id: "convergence_001",
    text: "Investigation converged",
    detail: "all required checkpoints satisfied",
  },
  {
    type: "REPORT",
    id: "report_001",
    text: "Verification Report generated",
    detail: "verification_report.md",
  },
]

const nodes = [
  ["INVESTIGATION", "Investigation Graph", "node_014"],
  ["OBSERVATION", "Observation Store", "obs_031"],
  ["KNOWLEDGE", "Knowledge Graph", "claim_007"],
]

const getStats = (index: number) => {
  const currentEvents = events.slice(0, index + 1)

  return {
    nodes: currentEvents.filter(
      (event) => event.type === "NODE"
    ).length,

    observations: currentEvents.filter(
      (event) => event.type === "OBSERVATION"
    ).length,

    claims: currentEvents.filter(
      (event) => event.type === "CLAIM"
    ).length,

    trusts: currentEvents.filter(
      (event) => event.type === "TRUST"
    ).length,

    checkpoints: currentEvents.filter(
      (event) => event.type === "CHECKPOINT"
    ).length,

    converged: currentEvents.some(
      (event) => event.type === "CONVERGENCE"
    ),

    reportGenerated: currentEvents.some(
      (event) => event.type === "REPORT"
    ),
  }
}

export default function AIAgentPipeline() {
  const [eventIndex, setEventIndex] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setEventIndex((value) => {
        if (value >= events.length - 1) {
          return 0
        }

        return value + 1
      })
    }, 2700)

    return () => window.clearInterval(timer)
  }, [])

  const currentEvent = events[eventIndex]
  const stats = getStats(eventIndex)

  const trustStatus =
    stats.trusts > 0 ? "HIGH" : "CALCULATING"

  const reportStatus = stats.reportGenerated
    ? "GENERATED"
    : stats.converged
      ? "CONVERGING"
      : "INVESTIGATING"

  return (
    <div
      className="pipeline-report"
      role="region"
      aria-label="Wizard verification investigation trace"
    >
      <div className="pipeline-header">
        <span className="pipeline-live">
          <i />
          WIZARD VERIFICATION · LIVE
        </span>

        <span>
          {stats.claims} claims · 0 contradictions
        </span>
      </div>

      <div
        className="pipeline-graph"
        aria-label="Wizard investigation architecture"
      >
        <div className="pipeline-flow pipeline-flow-one" />
        <div className="pipeline-flow pipeline-flow-two" />
        <div className="pipeline-flow pipeline-flow-three" />

        {nodes.map(
          ([label, title, meta], index) => (
            <div
              key={label}
              className={`pipeline-node pipeline-node-${index}`}
            >
              <small>{label}</small>

              <strong>{title}</strong>

              <em>{meta}</em>

              {index === 2 && (
                <span className="pipeline-dots">
                  <b />
                  <b />
                  <b />
                </span>
              )}
            </div>
          )
        )}

        <div className="pipeline-outputs">
          <span>
            Runtime <b>VERIFIED</b>
          </span>

          <span>
            Dependencies <b>VERIFIED</b>
          </span>

          <span>
            Execution{" "}
            <b>
              {stats.claims >= 3
                ? "VERIFIED"
                : "PENDING"}
            </b>
          </span>
        </div>
      </div>

      <motion.div
        className="pipeline-message"
        key={currentEvent.id}
        initial={{
          opacity: 0,
          y: 4,
        }}
        animate={{
          opacity: 1,
          y: 0,
        }}
        transition={{
          duration: 0.25,
        }}
      >
        <span>›</span>

        <div className="pipeline-event">
          <div className="pipeline-event-main">
            <small>
              {currentEvent.type} · {currentEvent.id}
            </small>

            <p>{currentEvent.text}</p>
          </div>

          <span className="pipeline-event-detail">
            {currentEvent.detail}
          </span>
        </div>
      </motion.div>

      <div className="pipeline-stats">
        <span>
          <small>NODES</small>
          <b>{stats.nodes}</b>
        </span>

        <span>
          <small>OBSERVATIONS</small>
          <b>{stats.observations}</b>
        </span>

        <span>
          <small>CLAIMS</small>
          <b>{stats.claims}</b>
        </span>

        <span className="pipeline-stack">
          <small>TRUST</small>
          <b>{trustStatus}</b>
        </span>
      </div>

      <div className="pipeline-trace">
        <span>
          <small>TRACE</small>
        </span>

        <span>
          Investigation
          <b>→</b>
          Observation
          <b>→</b>
          Claim
          <b>→</b>
          Trust
        </span>

        {currentEvent.parent && (
          <span className="pipeline-trace-parent">
            ↳ {currentEvent.parent}
          </span>
        )}
      </div>

      <div className="pipeline-status">
        <span>
          <small>CHECKPOINTS</small>
          <b>
            {stats.checkpoints}
          </b>
        </span>

        <span>
          <small>CONVERGENCE</small>
          <b>
            {stats.converged
              ? "REACHED"
              : "PENDING"}
          </b>
        </span>

        <span>
          <small>REPORT</small>
          <b>{reportStatus}</b>
        </span>
      </div>
    </div>
  )
}