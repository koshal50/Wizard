"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import styles from "./architecture.module.css"

type Evidence = { id: string; description: string; classification: string; path?: string; line_start?: number; line_end?: number }
type Group = { id: string; label: string; description: string; evidence_ids: string[] }
type Component = { id: string; label: string; type: string; description: string; path?: string; group_id?: string; evidence_ids: string[] }
type Connection = { id: string; source: string; target: string; type: string; label?: string; description: string; classification: string; evidence_ids: string[] }
type Graph = { title: string; repository_name: string; status: string; nodes: Component[]; relationships: Connection[]; evidence: Evidence[]; groups?: Group[]; limitations?: string[] }
type Saved = { id: string; title: string; repository_name: string; status: string; created_at: string }

async function load(path: string, signal: AbortSignal) {
  const response = await fetch(path, { credentials: "same-origin", cache: "no-store", signal })
  if (response.status === 401) throw new Error("Sign in to view your private architecture diagrams.")
  if (response.status === 403 || response.status === 404) throw new Error("This investigation is unavailable or belongs to another account.")
  if (!response.ok) throw new Error("The investigation service is unavailable. Please retry.")
  return response.json()
}

export function SavedArchitectures() {
  const [rows, setRows] = useState<Saved[]>()
  const [error, setError] = useState("")
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError(""); setRows(undefined)
    load("/api/investigations", controller.signal).then(data => setRows(data.investigations))
      .catch(e => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [retry])
  return <div className={styles.saved}>
    {error ? <div role="alert"><p>{error}</p><a href="/login.html">Sign in</a> · <button onClick={() => setRetry(retry + 1)}>Retry</button></div>
      : !rows ? <p role="status">Loading saved investigations…</p>
      : rows.length === 0 ? <p>No saved diagrams yet. Run <code>investigate architecture</code> in Wizard and consent to upload the result.</p>
      : rows.map(row => <Link className={styles.savedRow} href={`/investigations/${row.id}`} key={row.id}>
        <span>{row.title}<small>{row.repository_name} · {row.status}</small></span><span>Open diagram →</span>
      </Link>)}
  </div>
}

// Stable two-dimensional packing of saved architectural boundaries. A cluster
// never stretches into an unbounded dependency chain; cycles need no special IO.
function layout(graph: Graph): Node[] {
  const colors = ["#7fc6e6", "#99d8b0", "#d0b0ec", "#e5ba73", "#df9ab2"]
  const groups = [...(graph.groups || [])].sort((a, b) => a.id.localeCompare(b.id))
  const result: Node[] = []
  const clusters = groups.length ? groups : [{ id: "", label: "Architecture", description: "", evidence_ids: [] }]
  const columnCount = clusters.length >= 6 ? 3 : clusters.length > 1 ? 2 : 1
  const heights = Array<number>(columnCount).fill(0)
  // Pack into the shortest column, so small groups do not reserve the height of
  // an adjacent large group. Keep the most connected regions near the top.
  const groupDegree = (id: string) => graph.relationships.filter(e =>
    graph.nodes.find(n => n.id === e.source)?.group_id === id ||
    graph.nodes.find(n => n.id === e.target)?.group_id === id).length
  clusters.sort((a, b) => groupDegree(b.id) - groupDegree(a.id) || a.label.localeCompare(b.label))
  clusters.forEach((group, index) => {
    const column = heights.indexOf(Math.min(...heights))
    const x = column * 650, y = heights[column]
    const color = colors[index % colors.length]
    const degree = (id: string) => graph.relationships.filter(e => e.source === id || e.target === id).length
    const members = graph.nodes.filter(n => !groups.length || n.group_id === group.id)
      .sort((a, b) => degree(b.id) - degree(a.id) || (a.path || a.id).localeCompare(b.path || b.id))
    const width = 576
    const height = Math.ceil(members.length / 2) * 130 + 70
    if (groups.length) result.push({ id: group.id, type: "group", position: { x, y },
      data: { label: group.label }, selectable: false, draggable: false,
      style: { width, height, background: `${color}0b`, border: `1px solid ${color}66`,
        borderRadius: 18, color, pointerEvents: "none", fontSize: 16, fontWeight: 600, padding: 20 },
      ariaLabel: `${group.label}, architectural group` })
    members.forEach((n, i) => result.push({ id: n.id,
      ...(groups.length ? { parentId: group.id, extent: "parent" as const } : {}),
      data: { label: <div><small>{n.type}</small><strong>{n.label}</strong></div> },
      position: { x: (groups.length ? 0 : x) + (members.length === 1 ? 173 : 24 + i % 2 * 270),
        y: (groups.length ? 0 : y) + 60 + Math.floor(i / 2) * 130 },
      style: { width: 230, minHeight: 76, background: "#12304f", color: "#eaf7fb", border: `1px solid ${color}`,
        borderRadius: 10, padding: 14 },
      ariaLabel: `${n.label}, ${n.type}. Select to view evidence.` }))
    heights[column] += height + 80
  })
  return result
}

function Boundary({ data }: NodeProps) {
  return <div>{String(data.label)}</div>
}
const nodeTypes = { group: Boundary }

function Diagram({ graph }: { graph: Graph }) {
  const [selection, setSelection] = useState<Component | Connection>()
  const nodes = useMemo(() => layout(graph), [graph])
  const edges = useMemo<Edge[]>(() => graph.relationships.map(e => ({ id: e.id, source: e.source, target: e.target,
    label: e.classification === "inferred" || e.type !== "imports" || selection?.id === e.id ||
      selection?.id === e.source || selection?.id === e.target ? e.label || e.type : undefined,
    type: "default", interactionWidth: 24,
    style: { stroke: e.classification === "inferred" ? "#e5ba73" : "#7fc6e6", strokeWidth: selection?.id === e.id ? 3 : 1.5,
      opacity: !selection || selection.id === e.id || selection.id === e.source || selection.id === e.target ? 0.85 : 0.15,
      strokeDasharray: e.classification === "inferred" ? "6 5" : undefined },
    labelStyle: { fill: "#eaf7fb", fontSize: 11 }, labelBgStyle: { fill: "#071f3a" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#7fc6e6" }, ariaLabel: `${e.type}, ${e.classification}`,
  })), [graph, selection])
  return <div className={styles.workspace}>
    <div className={styles.canvas} aria-label="Interactive architecture diagram">
      <ReactFlow nodeTypes={nodeTypes} nodes={nodes} edges={edges} nodesDraggable={false} nodesConnectable={false} fitView minZoom={0.05} maxZoom={2}
        onNodeClick={(_, n) => setSelection(graph.nodes.find(c => c.id === n.id))}
        onEdgeClick={(_, e) => setSelection(graph.relationships.find(c => c.id === e.id))}
        onPaneClick={() => setSelection(undefined)} colorMode="dark">
        <Background color="#315579" gap={24} /><Controls showInteractive={false} />
      </ReactFlow>
    </div>
    <aside className={styles.details} aria-label="Architecture evidence" aria-live="polite">
      {selection ? <><p className={styles.eyebrow}>{"source" in selection ? `${selection.classification} relationship` : selection.type}</p>
        <h2>{"source" in selection ? selection.label || selection.type : selection.label}</h2>
        {"path" in selection && <code>{selection.path}</code>}
        {"group_id" in selection && <p className={styles.eyebrow}>{graph.groups?.find(g => g.id === selection.group_id)?.label}</p>}
        <p>{selection.description}</p>
        {!("source" in selection) && <><h3>Dependencies</h3>
          {graph.relationships.filter(e => e.source === selection.id).length === 0 && <p>No outgoing connections were established.</p>}
          {graph.relationships.filter(e => e.source === selection.id).map(e => <button className={styles.item} key={e.id} onClick={() => setSelection(e)}>
            {e.label || e.type} &rarr; {graph.nodes.find(n => n.id === e.target)?.label} &middot; {e.classification}
          </button>)}
        </>}
        {"source" in selection && <p>{graph.nodes.find(n => n.id === selection.source)?.label} → {graph.nodes.find(n => n.id === selection.target)?.label}</p>}
        <h3>Supporting evidence</h3>
        {selection.evidence_ids.length === 0 && <p>No supporting evidence is available.</p>}
        {selection.evidence_ids.map(id => graph.evidence.find(e => e.id === id)).filter((e): e is Evidence => !!e).map(e =>
          <article className={styles.evidence} key={e.id}><small>{e.classification}</small><p>{e.description}</p>
            {e.path && <code>{e.path}{e.line_start ? `:${e.line_start}${e.line_end ? `–${e.line_end}` : ""}` : ""}</code>}
          </article>)}
      </> : <><p className={styles.eyebrow}>Evidence explorer</p><h2>Follow the architecture</h2>
        <p>Select a shape or connection to inspect its description and supporting file evidence.</p>
        <p>Solid blue: observed. Dashed amber: inferred.</p><p>Scroll to zoom, drag the canvas to pan, or use fit view.</p></>}
      {!!graph.limitations?.length && <details><summary>Investigation coverage</summary>{graph.limitations.map((line, i) => <p key={i}>{line}</p>)}</details>}
      <details><summary>Components ({graph.nodes.length})</summary>{graph.nodes.map(n => <button className={styles.item} key={n.id} onClick={() => setSelection(n)}>{n.label}</button>)}</details>
      <details><summary>Connections ({graph.relationships.length})</summary>{graph.relationships.map(e => <button className={styles.item} key={e.id} onClick={() => setSelection(e)}>{graph.nodes.find(n => n.id === e.source)?.label} → {graph.nodes.find(n => n.id === e.target)?.label}: {e.type}</button>)}</details>
    </aside>
  </div>
}

export default function ArchitectureViewer({ id }: { id: string }) {
  const [graph, setGraph] = useState<Graph>()
  const [error, setError] = useState("")
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError(""); setGraph(undefined)
    load(`/api/investigations/${encodeURIComponent(id)}`, controller.signal).then(data => setGraph(data.graph))
      .catch(e => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [id, retry])
  return <main className={styles.page}>
    <header className={styles.header}><Link href="/" className={styles.brand}>Wizard<span>Developer Intelligence Platform</span></Link><Link href="/dashboard">Your diagrams ↗</Link></header>
    <div className={styles.intro}><p className={styles.eyebrow}>Architecture investigation</p>
      <h1>{graph?.repository_name || "Your application architecture"}</h1>
      <p>{graph ? `${graph.nodes.length} components · ${graph.relationships.length} connections · ${graph.groups?.length || 0} groups | ${graph.status}` : "Private repository intelligence, backed by local evidence."}</p>
    </div>
    {error ? <div className={styles.state} role="alert"><h2>Diagram unavailable</h2><p>{error}</p><a href="/login.html">Sign in</a> · <button onClick={() => setRetry(retry + 1)}>Retry</button></div>
      : !graph ? <div className={styles.state} role="status">Loading saved architecture…</div>
      : graph.nodes.length === 0 ? <div className={styles.state}>This investigation has no architecture nodes.</div>
      : <Diagram graph={graph} />}
  </main>
}
