"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { Background, BaseEdge, EdgeLabelRenderer, Handle, MarkerType, Position, ReactFlow, type Edge, type EdgeProps, type Node, type NodeProps, type ReactFlowInstance } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import styles from "./architecture.module.css"

import { layout, NODE_HEIGHT, NODE_WIDTH, orthogonalPath, PAGE_SIZE, project, type Component, type Evidence, type Graph } from "./architecture-model"

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

function ArchitectureNode({ data }: NodeProps) {
  const component = data.component as Component
  const database = /database|data.?store|postgres|mysql|mongo|redis|sqlite/i.test(component.type)
  const kind = database ? "database" : /entry/i.test(component.type) ? "entrypoint" : /external/i.test(component.type) ? "external" : component.level === "file" ? "file" : /module|package|library/i.test(component.type) ? "module" : "application"
  return <div className={`${styles.shape} ${styles[kind]}`} data-kind={kind}>
    {database && <svg className={styles.cylinder} viewBox="0 0 280 112" preserveAspectRatio="none" aria-hidden="true">
      <path d="M1 18 C1 -4 279 -4 279 18 L279 94 C279 116 1 116 1 94 Z" />
      <ellipse cx="140" cy="18" rx="139" ry="17" />
      <path d="M1 94 C1 116 279 116 279 94" fill="none" />
    </svg>}
    <Handle type="target" id="in-top" position={Position.Top} />
    <Handle type="target" id="in-bottom" position={Position.Bottom} style={{ left: "35%" }} />
    <Handle type="source" id="out-top" position={Position.Top} style={{ left: "65%" }} />
    <small>{component.type}</small><strong>{component.label}</strong>
    {data.expand ? <button className="nodrag nopan" onClick={event => { event.stopPropagation(); (data.expand as () => void)() }}>
      {String(data.expandLabel)}
    </button> : <span className={styles.sourceHint}>Select for evidence</span>}
    <Handle type="source" id="out-bottom" position={Position.Bottom} />
    <Handle type="source" id="out-right" position={Position.Right} style={{ top: "65%" }} />
  </div>
}

function ArchitectureEdge(props: EdgeProps) {
  const backward = Boolean(props.data?.backward), lane = Number(props.data?.lane || 0)
  const sameLevel = Boolean(props.data?.sameLevel), detour = Boolean(props.data?.detour), gutter = Number(props.data?.gutter)
  const path = orthogonalPath(props.sourceX, props.sourceY, props.targetX, props.targetY, backward, lane, { sameLevel, detour, gutter })
  const x = backward || detour ? gutter : (props.sourceX + props.targetX) / 2
  const y = sameLevel ? Math.max(props.sourceY, props.targetY) + 40 + lane * 56 : backward || detour ? (props.sourceY + props.targetY) / 2 : (props.sourceY + props.targetY) / 2 + lane * 8
  return <><BaseEdge id={props.id} path={path} style={props.style} markerEnd={props.markerEnd} interactionWidth={20} />
    <EdgeLabelRenderer><button className={`${styles.edgeLabel} nodrag nopan`} style={{ transform: `translate(-50%, -50%) translate(${x}px, ${y}px)` }}
      onClick={() => (props.data?.select as (() => void))()} aria-label={`Inspect relationship: ${String(props.label)}`}>{props.label}</button></EdgeLabelRenderer>
  </>
}
const nodeTypes = { architecture: ArchitectureNode }, edgeTypes = { architecture: ArchitectureEdge }

type Selection = { kind: "node" | "edge" | "relationship"; id: string }
function Diagram({ graph }: { graph: Graph }) {
  const [scope, setScope] = useState<string>(), [files, setFiles] = useState(false), [page, setPage] = useState(0)
  const [selection, setSelection] = useState<Selection>(), [observedOnly, setObservedOnly] = useState(false)
  const [panel, setPanel] = useState(true), [zoom, setZoom] = useState(1), [proofLimit, setProofLimit] = useState(12), [relationLimit, setRelationLimit] = useState(10)
  const flow = useRef<ReactFlowInstance>(), scroll = useRef<HTMLDivElement>(null)
  const projection = useMemo(() => project(graph, scope, files, page, observedOnly), [graph, scope, files, page, observedOnly])
  const placement = useMemo(() => layout(projection.visible, projection.bundles), [projection])
  function reset() {
    flow.current?.setViewport({ x: 0, y: 0, zoom: 1 })
    const anchor = placement.positions.get(projection.visible[0]?.id)
    scroll.current?.scrollTo({ top: 0, left: scroll.current.clientWidth < placement.width ? Math.max(0, (anchor?.x || 0) - 24) : 0 })
  }
  useEffect(() => { reset() }, [scope, files, page])
  function navigate(id?: string, showFiles = false) { setScope(id); setFiles(showFiles); setPage(0); setSelection(undefined); reset() }
  function select(kind: Selection["kind"], id: string) { setSelection({ kind, id }); setPanel(true); setProofLimit(12); setRelationLimit(10) }
  const nodes = useMemo<Node[]>(() => projection.visible.map(n => ({ id: n.id, type: "architecture", position: placement.positions.get(n.id)!,
    selected: selection?.kind === "node" && selection.id === n.id,
    style: { width: NODE_WIDTH, height: NODE_HEIGHT },
    data: { component: n, expand: projection.children(n.id).length ? () => navigate(n.id) : undefined,
      expandLabel: projection.children(n.id).some(c => c.level !== "file") ? "Expand subsystem" : "Inspect source files" },
    ariaLabel: `${n.label}, ${n.type}. Select to view evidence.` })), [projection, placement, selection])
  const edges = useMemo<Edge[]>(() => projection.bundles.map((e, i) => {
    const a = placement.positions.get(e.source)!, b = placement.positions.get(e.target)!
    const backward = b.y < a.y, sameLevel = b.y === a.y, detour = !backward && !sameLevel && b.y - a.y > 280
    const related = !selection || selection.kind === "node" && (selection.id === e.source || selection.id === e.target) ||
      selection.kind === "edge" && selection.id === e.id || selection.kind === "relationship" && e.relationships.some(r => r.id === selection.id)
    const color = e.classification === "observed" ? "#79b3ce" : "#d5ac73"
    return { id: e.id, type: "architecture", source: e.source, target: e.target,
      sourceHandle: backward ? "out-top" : "out-bottom", targetHandle: backward || sameLevel ? "in-bottom" : "in-top",
      label: e.label, data: { backward, sameLevel, detour, gutter: placement.width - 90 - i % 3 * 20, lane: sameLevel ? (a.x < b.x ? 0 : 1) : i % 3, select: () => select("edge", e.id) },
      style: { stroke: color, strokeWidth: related ? 1.35 : 1, opacity: related ? .8 : .12,
        strokeDasharray: e.classification === "observed" ? undefined : "5 5" },
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
      ariaLabel: `${e.label}, ${e.classification}, ${e.relationships.length} supporting relationships` }
  }), [projection, placement, selection])
  const chosen = selection?.kind === "node" ? projection.index.get(selection.id) : scope && !selection ? projection.index.get(scope) : undefined
  const bundle = selection?.kind === "edge" ? projection.bundles.find(e => e.id === selection.id) : undefined
  const relationships = bundle?.relationships || (selection?.kind === "relationship" ? graph.relationships.filter(e => e.id === selection.id) : [])
  const refs = [...new Set(chosen?.evidence_ids || relationships.flatMap(e => e.evidence_ids))]
  const evidenceIndex = useMemo(() => new Map(graph.evidence.map(e => [e.id, e])), [graph.evidence])
  const sourceFiles = chosen ? projection.sourceFiles(chosen.id) : []
  const contains = (id: string) => { let n = projection.index.get(id); for (let i = 0; n && i <= 8; i++, n = n.parent_id ? projection.index.get(n.parent_id) : undefined) if (n.id === chosen?.id) return true; return false }
  const dependencies = chosen ? graph.relationships.filter(e => contains(e.source) !== contains(e.target)) : []
  const savedObserved = graph.relationships.filter(e => e.classification === "observed").length
  return <section className={styles.explorer}>
    <div className={styles.toolbar} aria-label="Architecture navigation">
      <nav aria-label="Architecture levels"><button onClick={() => navigate()}>Overview</button>{projection.trail.map(n => <button key={n.id} onClick={() => navigate(n.id)}> / {n.label}</button>)}</nav>
      <div><button aria-label="Zoom in" onClick={() => flow.current?.zoomIn()}>+</button><button aria-label="Zoom out" onClick={() => flow.current?.zoomOut()}>-</button><button onClick={() => { flow.current?.fitView({ minZoom: .65, maxZoom: 1, padding: .1 }); scroll.current?.scrollTo({ top: 0 }) }}>Fit map</button><button onClick={reset}>Reset view</button><button onClick={() => setPanel(!panel)}>{panel ? "Hide evidence" : "Show evidence"}</button></div>
    </div>
    <div className={styles.viewSummary} role="status">
      {projection.fileView ? "File detail" : scope ? "Subsystem detail" : "Architecture overview"}: {projection.visible.length} of {projection.total} components in this view; {graph.nodes.length} in the saved investigation.
      <span>{projection.bundles.length} arrow bundles; {projection.excluded} relationships remain internal, outside this view, or filtered.</span>
    </div>
    <div className={`${styles.workspace} ${!panel ? styles.withoutPanel : ""}`}>
      <div ref={scroll} className={styles.scrollRegion} role="region" aria-label="Scrollable architecture map" tabIndex={0}>
        <div className={styles.canvas} style={{ height: Math.max(660, placement.height * zoom), width: Math.max(850, placement.width * zoom) }}>
          {projection.visible.length ? <ReactFlow nodeTypes={nodeTypes} edgeTypes={edgeTypes} nodes={nodes} edges={edges}
            onInit={instance => { flow.current = instance; requestAnimationFrame(reset) }} defaultViewport={{ x: 0, y: 0, zoom: 1 }} minZoom={.65} maxZoom={1.8}
            nodesDraggable={false} nodesConnectable={false} deleteKeyCode={null} zoomOnScroll={false} preventScrolling={false}
            onMove={(_, viewport) => setZoom(viewport.zoom)} onlyRenderVisibleElements
            onNodeClick={(_, n) => select("node", n.id)} onEdgeClick={(_, e) => select("edge", e.id)}
            onPaneClick={() => setSelection(undefined)} colorMode="dark">
            <Background color="#254361" gap={24} />
          </ReactFlow> : <p className={styles.state}>No supported components at this level. Inspect the available source evidence and coverage.</p>}
        </div>
      </div>
      {panel && <aside className={styles.details} aria-label="Architecture evidence" aria-live="polite">
        {chosen ? <><p className={styles.eyebrow}>{chosen.level || "module"} / {chosen.type}</p><h2>{chosen.label}</h2>
          {chosen.path && <code>{chosen.path}</code>}
          {!!projection.children(chosen.id).length && <button className={styles.item} onClick={() => navigate(chosen.id)}>Expand this component</button>}
          <h3>Connected behavior</h3>{dependencies.length === 0 && <p>No cross-component behavior was established.</p>}
          {dependencies.slice(0, relationLimit).map(e => <button className={styles.item} key={e.id} onClick={() => select("relationship", e.id)}>
            {projection.index.get(e.source)?.label} &rarr; {e.label || e.type} &rarr; {projection.index.get(e.target)?.label}<small>{e.classification}</small></button>)}
          {dependencies.length > relationLimit && <button className={styles.item} onClick={() => setRelationLimit(relationLimit + 10)}>More connections ({dependencies.length - relationLimit})</button>}
          {!!sourceFiles.length && <><h3>Source files ({sourceFiles.length})</h3>{sourceFiles.slice(0, 12).map(n => <button className={styles.item} key={n.id} onClick={() => select("node", n.id)}>{n.path}</button>)}
            <button className={styles.item} onClick={() => navigate(chosen.id, true)}>Explore source files</button></>}
        </> : relationships.length ? <><p className={styles.eyebrow}>{bundle?.classification || relationships[0].classification} relationship</p><h2>{bundle?.label || relationships[0].label || relationships[0].type}</h2>
          <p>{relationships.length} saved relationship{relationships.length === 1 ? "" : "s"} represented by this arrow.</p>
          {relationships.slice(0, relationLimit).map(e => <article className={styles.evidence} key={e.id}><small>{e.classification}</small><h3>{e.label || e.type}</h3><p>{e.description}</p>
            <code>{projection.index.get(e.source)?.label} &rarr; {projection.index.get(e.target)?.label}</code></article>)}
          {relationships.length > relationLimit && <button className={styles.item} onClick={() => setRelationLimit(relationLimit + 10)}>More relationship details</button>}
        </> : <><p className={styles.eyebrow}>Evidence explorer</p><h2>Follow the architecture</h2><p>Select a component or an action on an arrow to inspect its source evidence. Expand a subsystem for modules and source files.</p>
          <p>Solid blue: observed. Dashed amber: inferred or mixed. Use the wheel to scroll, drag to pan, and the controls to zoom.</p></>}
        {!!refs.length && <><h3>Supporting evidence</h3>{refs.slice(0, proofLimit).map(id => evidenceIndex.get(id)).filter((e): e is Evidence => !!e).map(e => <article className={styles.evidence} key={e.id}><small>{e.classification}</small><p>{e.description}</p>
          {e.path && <code>{e.path}{e.line_start ? `:${e.line_start}${e.line_end ? `-${e.line_end}` : ""}` : ""}</code>}</article>)}
          {refs.length > proofLimit && <button className={styles.item} onClick={() => setProofLimit(proofLimit + 12)}>More evidence ({refs.length - proofLimit})</button>}</>}
        <details className={styles.coverage}><summary>Investigation coverage</summary>
          <p>{graph.nodes.length} saved components; {savedObserved} observed and {graph.relationships.length - savedObserved} inferred relationships.</p>
          {graph.coverage ? <><p>{graph.coverage.examined_files.length} source files examined of {graph.coverage.candidate_files} discovered candidates; {graph.coverage.context_files.length} configuration/documentation files read.</p>
            <p>{graph.coverage.uninspected_file_count} source files uninspected; {graph.coverage.partial_files.length} reads known partial; {graph.coverage.unmeasured_read_count || 0} older reads without truncation metadata.</p>
            <h3>Areas examined</h3>{graph.coverage.examined_areas.map(area => <code key={area}>{area}<br /></code>)}
            {!!graph.coverage.uninspected_areas.length && <><h3>Areas with unread source</h3>{graph.coverage.uninspected_areas.map(area => <code key={area}>{area}<br /></code>)}</>}
            {!!graph.coverage.unlisted_area_count && <p>{graph.coverage.unlisted_area_count} further unread areas are not listed.</p>}
            <p>{graph.coverage.discovery_note}</p></> : <p>Detailed coverage was not recorded in this older investigation.</p>}
          {graph.limitations?.map((line, i) => <p key={i}>{line}</p>)}
          {!!projection.unassigned.length && <details><summary>Unassigned source evidence ({projection.unassigned.length})</summary>{projection.unassigned.slice(0, 12).map(n => <button className={styles.item} key={n.id} onClick={() => select("node", n.id)}>{n.path}</button>)}<button className={styles.item} onClick={() => navigate(undefined, true)}>Browse all inspected source files</button></details>}
        </details>
      </aside>}
    </div>
    <div className={styles.toolbar}>
      <div><button disabled={page === 0} onClick={() => { setPage(page - 1); reset() }}>Previous</button><span> Page {page + 1} of {Math.max(1, Math.ceil(projection.total / PAGE_SIZE))} </span><button disabled={(page + 1) * PAGE_SIZE >= projection.total} onClick={() => { setPage(page + 1); reset() }}>Next</button></div>
      <label><input type="checkbox" checked={observedOnly} onChange={e => setObservedOnly(e.target.checked)} /> Observed only</label>
    </div>
  </section>
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
      <p>{graph ? `${graph.nodes.length} components · ${graph.relationships.length} connections · ${graph.nodes.filter(n => n.level === "subsystem").length || graph.groups?.length || 0} subsystems | ${graph.status}` : "Private repository intelligence, backed by local evidence."}</p>
    </div>
    {error ? <div className={styles.state} role="alert"><h2>Diagram unavailable</h2><p>{error}</p><a href="/login.html">Sign in</a> · <button onClick={() => setRetry(retry + 1)}>Retry</button></div>
      : !graph ? <div className={styles.state} role="status">Loading saved architecture…</div>
      : graph.nodes.length === 0 ? <div className={styles.state}>This investigation has no architecture nodes.</div>
      : <Diagram key={id} graph={graph} />}
  </main>
}
