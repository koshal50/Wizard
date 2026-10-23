"use client"

import { useEffect, useMemo } from "react"
import {
  Background, Controls, Handle, MarkerType, Position, ReactFlow,
  useNodesState, type Node, type NodeProps,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { layout, NODE_HEIGHT, NODE_WIDTH, type Bundle, type Component } from "./architecture-model"

const palettes = [
  { fill: "#2e2542", stroke: "#b096df", text: "#e6d7ff" },
  { fill: "#1c3730", stroke: "#78bca2", text: "#cdf1e2" },
  { fill: "#3a3020", stroke: "#d6ae6b", text: "#f8dfb1" },
  { fill: "#3b2531", stroke: "#d895af", text: "#f8d8e5" },
]
function palette(type: string) {
  if (/database|store/i.test(type)) return palettes[2]
  if (/external/i.test(type)) return palettes[3]
  if (/entry|application/i.test(type)) return palettes[0]
  return palettes[1]
}
type ComponentNode = Node<{ component: Component; count: number }, "component">
function ComponentShape({ data, selected }: NodeProps<ComponentNode>) {
  const { component, count } = data, colors = palette(component.type)
  const database = /database|store/i.test(component.type)
  return <div style={{ width: NODE_WIDTH, height: NODE_HEIGHT, position: "relative", cursor: "grab" }}>
    <Handle type="target" position={Position.Top} style={{ background: colors.stroke }} />
    <svg width={NODE_WIDTH} height={NODE_HEIGHT} style={{ position: "absolute", inset: 0, overflow: "visible", pointerEvents: "none" }} aria-hidden="true">
      {database ? <><path d={`M1,18 C1,-3 ${NODE_WIDTH-1},-3 ${NODE_WIDTH-1},18 V94 C${NODE_WIDTH-1},115 1,115 1,94 Z`} fill={colors.fill} stroke={colors.stroke} strokeWidth={selected ? 2.5 : 1.5}/><ellipse cx={NODE_WIDTH/2} cy={18} rx={NODE_WIDTH/2-1} ry={14} fill={colors.fill} stroke={colors.stroke}/></> : <rect x={1} y={1} width={NODE_WIDTH-2} height={NODE_HEIGHT-2} rx={/external/i.test(component.type) ? 28 : 12} fill={colors.fill} stroke={colors.stroke} strokeWidth={selected ? 2.5 : 1.5}/>}
    </svg>
    <div className="relative flex h-full flex-col items-center justify-center gap-1 px-4 text-center" style={{ color: colors.text }}>
      <span className="line-clamp-2 text-sm font-semibold">{component.label}</span>
      <span className="text-xs opacity-80">{component.type}</span>
      <span className="text-[10px] opacity-75">{count ? `${count} components · Click to explore` : "Click for source evidence"}</span>
    </div>
    <Handle type="source" position={Position.Bottom} style={{ background: colors.stroke }} />
  </div>
}
const nodeTypes = { component: ComponentShape }

export default function ArchitectureCanvas({ nodes: components, connections, boundaryLabel, selectedId, childrenCount, onNodeSelect, onEdgeSelect }: {
  boundaryLabel: string
  nodes: Component[]; connections: Bundle[]; selectedId?: string
  childrenCount: (id: string) => number
  onNodeSelect: (id: string) => void; onEdgeSelect: (id: string) => void
}) {
  const initial = useMemo(() => {
    const diagram = layout(components, connections)
    const children = components.map(component => ({ id: component.id, type: "component" as const,
      position: { x: diagram.positions.get(component.id)!.x, y: diagram.positions.get(component.id)!.y + 180 }, data: { component, count: childrenCount(component.id) },
      ariaLabel: `${component.label}. Drag to move; click to inspect.`,
    }))
    return [{ id: "view-boundary", type: "component" as const, position: { x: 230, y: 0 },
      data: { component: { id: "view-boundary", label: boundaryLabel, type: "boundary", description: "Current diagram scope", evidence_ids: [] }, count: 0 },
      ariaLabel: `${boundaryLabel}, current scope`,
    }, ...children]
    // The parent remounts the canvas when the visible hierarchy changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [components, connections])
  const [nodes, setNodes, onNodesChange] = useNodesState<ComponentNode>(initial)
  useEffect(() => { setNodes(current => current.map(node => ({ ...node, selected: node.id === selectedId }))) }, [selectedId, setNodes])
  const edges = useMemo(() => [...components.map(component => ({
    id: `contains:${component.id}`, source: "view-boundary", target: component.id,
    type: "default", label: "contains",
    markerEnd: { type: MarkerType.ArrowClosed, color: "#82738f", width: 18, height: 18 },
    style: { stroke: "#82738f", strokeWidth: 1.5, strokeDasharray: "3 6" },
    labelStyle: { fill: "#b4a7c0", fontSize: 10 }, labelBgStyle: { fill: "#18181e" },
  })), ...connections.map(connection => ({
    id: connection.id, source: connection.source, target: connection.target,
    type: "default", label: connection.label,
    markerEnd: { type: MarkerType.ArrowClosed, color: "#c1a0ec", width: 22, height: 22 },
    style: { stroke: connection.id === selectedId ? "#eddcff" : "#bba0df", strokeWidth: connection.id === selectedId ? 3 : 2,
      strokeDasharray: connection.classification === "observed" ? undefined : "6 4" },
    labelStyle: { fill: "#e7d9f8", fontSize: 11 }, labelBgStyle: { fill: "#18181e", fillOpacity: .95 },
    labelBgPadding: [7, 4] as [number, number], labelBgBorderRadius: 5, interactionWidth: 24,
  }))], [components, connections, selectedId])
  return <div className="h-[560px] w-full overflow-hidden rounded-xl border bg-background" aria-label="Interactive architecture diagram">
    <ReactFlow colorMode="dark" nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange}
      onNodeClick={(_, node) => { if(node.id !== "view-boundary") onNodeSelect(node.id) }} onEdgeClick={(_, edge) => { if(!edge.id.startsWith("contains:")) onEdgeSelect(edge.id) }}
      fitView fitViewOptions={{ padding: .25, maxZoom: 1.15 }} minZoom={.15} maxZoom={2}
      nodesConnectable={false} deleteKeyCode={null} nodeDragThreshold={5} attributionPosition="bottom-left">
      <Background color="#36303f" gap={24} size={1}/>
      <Controls showInteractive={false}/>
    </ReactFlow>
  </div>
}
