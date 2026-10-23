export type Evidence = { id: string; description: string; classification: string; path?: string; line_start?: number; line_end?: number }
export type Component = { id: string; label: string; type: string; description: string; path?: string; group_id?: string; parent_id?: string | null; level?: "subsystem" | "module" | "file"; evidence_ids: string[] }
export type Connection = { id: string; source: string; target: string; type: string; label?: string; description: string; classification: string; evidence_ids: string[] }
export type Coverage = { candidate_files: number; examined_files: string[]; context_files: string[]; examined_areas: string[]; uninspected_file_count: number; uninspected_areas: string[]; unlisted_area_count: number; unassigned_files: string[]; partial_files: string[]; unmeasured_read_count?: number; discovery_note: string }
export type Graph = { title: string; repository_name: string; status: string; nodes: Component[]; relationships: Connection[]; evidence: Evidence[]; groups?: { id: string; label: string; description: string; evidence_ids: string[] }[]; limitations?: string[]; coverage?: Coverage | null }
export type Bundle = { id: string; source: string; target: string; label: string; classification: string; relationships: Connection[] }
export const PAGE_SIZE = 24

export function normalizedNodes(graph: Graph): Component[] {
  // Older records keep their saved grouping as collapsible presentation metadata.
  // No repository access or new semantic architecture is generated in the website.
  if (graph.nodes.some(n => n.level === "subsystem") || !graph.groups?.length) return graph.nodes
  return [...graph.groups.map(g => ({ ...g, type: "legacy boundary", level: "subsystem" as const })),
    ...graph.nodes.map(n => ({ ...n, parent_id: n.group_id, level: "module" as const }))]
}

export function project(graph: Graph, scope?: string, files = false, page = 0, observedOnly = false) {
  const all = normalizedNodes(graph)
  const index = new Map(all.map(n => [n.id, n]))
  const descendant = (node: Component, ancestor: string) => {
    let current: Component | undefined = node
    for (let i = 0; current && i <= 8; i++, current = current.parent_id ? index.get(current.parent_id) : undefined) {
      if (current.id === ancestor) return true
    }
    return false
  }
  let candidates = scope ? all.filter(n => files ? n.level === "file" && descendant(n, scope) : n.parent_id === scope && n.level !== "file")
    : all.filter(n => files ? n.level === "file" : !n.parent_id && n.level !== "file")
  let fileView = files
  if (scope && !candidates.length && !files) {
    candidates = all.filter(n => n.level === "file" && descendant(n, scope))
    fileView = true
  }
  // Stable semantic sort; no silent omission: pagination is explicit in the toolbar.
  candidates.sort((a, b) => a.label.localeCompare(b.label) || a.id.localeCompare(b.id))
  const visible = candidates.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const ids = new Set(visible.map(n => n.id))
  const representative = new Map<string, string | undefined>()
  for (const n of all) {
    let current: Component | undefined = n, found: string | undefined
    for (let i = 0; current && i <= 8; i++, current = current.parent_id ? index.get(current.parent_id) : undefined) {
      if (ids.has(current.id)) { found = current.id; break }
    }
    representative.set(n.id, found)
  }
  const bundles = new Map<string, Bundle>()
  let excluded = 0
  for (const edge of graph.relationships) {
    const source = representative.get(edge.source), target = representative.get(edge.target)
    if (!source || !target || source === target || (observedOnly && edge.classification !== "observed")) { excluded++; continue }
    const id = `bundle:${source}:${target}`
    let bundle = bundles.get(id)
    if (!bundle) { bundle = { id, source, target, label: "", classification: edge.classification, relationships: [] }; bundles.set(id, bundle) }
    bundle.relationships.push(edge)
  }
  for (const bundle of bundles.values()) {
    const actions = [...bundle.relationships].sort((a, b) => (a.type === "imports" ? 1 : 0) - (b.type === "imports" ? 1 : 0) || a.id.localeCompare(b.id))
    const labels = [...new Set(actions.map(e => e.label || e.type))]
    bundle.label = labels.slice(0, 2).join(" / ") + (labels.length > 2 ? ` +${labels.length - 2}` : "")
    const classes = new Set(actions.map(e => e.classification))
    bundle.classification = classes.size > 1 ? "mixed" : actions[0].classification
  }
  const trail: Component[] = []
  let current = scope ? index.get(scope) : undefined
  for (let i = 0; current && i <= 8; i++, current = current.parent_id ? index.get(current.parent_id) : undefined) trail.unshift(current)
  return { all, index, visible, bundles: [...bundles.values()], total: candidates.length, excluded, trail, fileView,
    unassigned: all.filter(n => n.level === "file" && !n.parent_id),
    sourceFiles: (id: string) => all.filter(n => n.level === "file" && descendant(n, id)),
    children: (id: string) => all.filter(n => n.parent_id === id) }
}

export type Placement = { x: number; y: number }
export const NODE_WIDTH = 280, NODE_HEIGHT = 112
export function layout(nodes: Component[], edges: Bundle[]) {
  // Collapse strongly connected components, then rank the resulting dependency
  // DAG. Genuine cycles stay together instead of stretching indefinitely.
  const ids = new Set(nodes.map(n => n.id))
  const adjacency = new Map(nodes.map(n => [n.id, [] as string[]]))
  for (const edge of edges) if (ids.has(edge.source) && ids.has(edge.target)) adjacency.get(edge.source)!.push(edge.target)
  const order = new Map<string, number>(), low = new Map<string, number>(), stack: string[] = [], active = new Set<string>(), components: string[][] = []
  let next = 0
  function visit(id: string) {
    order.set(id, next); low.set(id, next++); stack.push(id); active.add(id)
    for (const target of adjacency.get(id)!.sort()) {
      if (!order.has(target)) { visit(target); low.set(id, Math.min(low.get(id)!, low.get(target)!)) }
      else if (active.has(target)) low.set(id, Math.min(low.get(id)!, order.get(target)!))
    }
    if (low.get(id) === order.get(id)) {
      const group: string[] = []; let member: string
      do { member = stack.pop()!; active.delete(member); group.push(member) } while (member !== id)
      components.push(group)
    }
  }
  for (const id of [...ids].sort()) if (!order.has(id)) visit(id)
  const membership = new Map<string, number>()
  components.forEach((members, i) => members.forEach(id => membership.set(id, i)))
  const dag = components.map(() => new Set<number>()), incoming = components.map(() => 0), rank = components.map(() => 0)
  for (const edge of edges) {
    const a = membership.get(edge.source)!, b = membership.get(edge.target)!
    if (a !== b && !dag[a].has(b)) { dag[a].add(b); incoming[b]++ }
  }
  const queue = incoming.map((v, i) => v === 0 ? i : -1).filter(i => i >= 0)
  for (let i = 0; i < queue.length; i++) for (const target of dag[queue[i]]) {
    rank[target] = Math.max(rank[target], rank[queue[i]] + 1)
    if (--incoming[target] === 0) queue.push(target)
  }
  const priority = (n: Component) => /entry|application/i.test(n.type) ? 0 : /database|store|external/i.test(n.type) ? 2 : 1
  const levels = new Map<number, Component[]>()
  for (const node of nodes) { const r = rank[membership.get(node.id)!]; levels.set(r, [...(levels.get(r) || []), node]) }
  const positions = new Map<string, Placement>()
  let y = 40
  for (const level of [...levels.keys()].sort((a, b) => a - b)) {
    const members = levels.get(level)!.sort((a, b) => priority(a) - priority(b) || a.label.localeCompare(b.label) || a.id.localeCompare(b.id))
    members.forEach((n, i) => positions.set(n.id, { x: members.length === 1 ? 230 : 40 + i % 2 * 390, y: y + Math.floor(i / 2) * 200 }))
    y += Math.ceil(members.length / 2) * 200 + 70
  }
  return { positions, width: 1000, height: Math.max(660, y + 40) }
}

export function orthogonalPath(sx: number, sy: number, tx: number, ty: number, backward: boolean, lane = 0,
  options: { sameLevel?: boolean; gutter?: number; detour?: boolean } = {}) {
  if (options.sameLevel) {
    const y = Math.max(sy, ty) + 40 + lane * 56
    return `M ${sx} ${sy} L ${sx} ${y} L ${tx} ${y} L ${tx} ${ty}`
  }
  if (backward || options.detour) {
    const x = options.gutter ?? Math.max(sx, tx) + 180 + lane * 12
    const y = ty + (backward ? 32 : -32)
    return `M ${sx} ${sy} L ${x} ${sy} L ${x} ${y} L ${tx} ${y} L ${tx} ${ty}`
  }
  const y = (sy + ty) / 2 + lane * 8
  return `M ${sx} ${sy} L ${sx} ${y} L ${tx} ${y} L ${tx} ${ty}`
}
