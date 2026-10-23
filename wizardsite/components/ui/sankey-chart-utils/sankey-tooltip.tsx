"use client"
import { useSankey } from "./sankey-context"
export function SankeyTooltip() {
  const { tooltipData, mousePos, width, height, margin } = useSankey()
  if(!tooltipData || !mousePos)return null
  const data=tooltipData.data
  return <foreignObject x={Math.max(0,Math.min(mousePos.x-margin.left+12,width-260))} y={Math.max(0,Math.min(mousePos.y-margin.top+12,height-90))} width={240} height={85} style={{overflow:"visible",pointerEvents:"none"}}>
    <div role="tooltip" className="rounded-lg border bg-white px-3 py-2 text-xs text-zinc-900 shadow-md"><strong className="block">{String(data.name || data.label || "Connection")}</strong><span className="mt-1 block text-zinc-500">{tooltipData.type==="node" ? String(data.componentType || "Component") : `${data.value} saved relationships`}</span><span className="mt-1 block text-zinc-500">Select to inspect evidence</span></div>
  </foreignObject>
}
