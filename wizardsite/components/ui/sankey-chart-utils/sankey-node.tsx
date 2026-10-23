"use client"
import { useSankey, type SankeyNodeDatum } from "./sankey-context"
import { motion, useReducedMotion } from "motion/react"
export function SankeyNode({ onSelect, selectedId }: { onSelect?: (node: SankeyNodeDatum) => void; selectedId?: string }) {
  const { nodes, setHoveredNodeIndex, setTooltipData, revealEpoch } = useSankey()
  const reduced = useReducedMotion()
  return <g>{nodes.map((node,index) => {
    const x = node.x0 || 0, width = (node.x1 || 0)-x, height = 64, y = ((node.y0 || 0)+(node.y1 || 0))/2-height/2
    const type = String(node.componentType || "component")
    const database = /database|store|postgres|mysql|sqlite|mongo/i.test(type)
    const external = /external/i.test(type)
    const entry = /entry/i.test(type)
    const selected = selectedId === node.componentId
    const hover = () => { setHoveredNodeIndex(index); setTooltipData({type:"node",nodeIndex:index,x,y,data:node}) }
    return <motion.g key={String(node.portId || index)+revealEpoch} initial={reduced ? false : {opacity:0}} animate={{opacity:1}} transition={{duration:.35,delay:reduced ? 0 : index*.025}}
      transform={`translate(${x}, ${y})`} tabIndex={0} role="button" aria-label={`${node.name}, ${type}. Inspect source evidence.`}
      onMouseEnter={hover} onFocus={hover} onMouseLeave={()=>{setHoveredNodeIndex(null);setTooltipData(null)}} onBlur={()=>{setHoveredNodeIndex(null);setTooltipData(null)}}
      onClick={()=>onSelect?.(node)} onKeyDown={event=>{if(event.key==="Enter" || event.key===" "){event.preventDefault();onSelect?.(node)}}}
      className="sankey-component" style={{cursor:"pointer",outline:"none"}}>
      {database ? <><path d={`M0,10 C0,-4 ${width},-4 ${width},10 L${width},54 C${width},68 0,68 0,54 Z`} fill={selected?"#f4f4f5":"white"} stroke={selected?"#18181b":"#d4d4d8"} /><ellipse cx={width/2} cy={10} rx={width/2} ry={9} fill="#f4f4f5" stroke="#d4d4d8" /></> : <rect width={width} height={height} rx={entry?28:10} fill={selected?"#f4f4f5":"white"} stroke={selected?"#18181b":"#d4d4d8"} strokeWidth={selected?1.5:1} strokeDasharray={external?"5 4":undefined} />}
      <text x={width/2} y={database?34:27} textAnchor="middle" fill="#18181b" fontSize={12} fontWeight={600}>{node.name.length>23?node.name.slice(0,21)+"...":node.name}</text>
      <text x={width/2} y={database?49:45} textAnchor="middle" fill="#71717a" fontSize={10}>{type.length>28?type.slice(0,26)+"...":type}</text>
    </motion.g>
  })}</g>
}
