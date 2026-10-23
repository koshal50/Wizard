"use client"
import { useSankey, type SankeyLinkDatum } from "./sankey-context"
import { motion, useReducedMotion } from "motion/react"
export function SankeyLink({ onSelect, selectedId }: { onSelect?: (link: SankeyLinkDatum) => void; selectedId?: string }) {
  const { links, createPath, hoveredNodeIndex, hoveredLinkIndex, setHoveredLinkIndex, setTooltipData, revealEpoch } = useSankey()
  const reduced = useReducedMotion()
  return <g>{links.map((link,index)=>{
    const source = typeof link.source === "object" ? link.source : undefined
    const target = typeof link.target === "object" ? link.target : undefined
    if(!source || !target)return null
    const connected = hoveredNodeIndex === null || source.index === hoveredNodeIndex || target.index === hoveredNodeIndex
    const selected = selectedId === link.bundleId || hoveredLinkIndex === index
    const path = createPath({...link,y0:((source.y0||0)+(source.y1||0))/2,y1:((target.y0||0)+(target.y1||0))/2})
    const hover = ()=>{setHoveredLinkIndex(index);setTooltipData({type:"link",linkIndex:index,x:0,y:0,data:{...link,source:source.index||0,target:target.index||0}})}
    return <g key={String(link.bundleId || index)+revealEpoch}><motion.path d={path} fill="none" stroke={selected?"#18181b":"#a1a1aa"} strokeWidth={Math.min(14,2+Math.sqrt(link.value)*2)}
      strokeDasharray={link.classification==="inferred"?"6 5":undefined} strokeLinecap="round" opacity={selected ? .9 : connected ? .35 : .08}
      initial={reduced?false:{pathLength:0}} animate={{pathLength:1}} transition={{duration:reduced?0:.7}}
      tabIndex={0} role="button" aria-label={`${String(link.label || "Connection")}: ${source.name} to ${target.name}. Inspect supporting evidence.`}
      style={{cursor:"pointer"}} onMouseEnter={hover} onFocus={hover} onMouseLeave={()=>{setHoveredLinkIndex(null);setTooltipData(null)}} onBlur={()=>{setHoveredLinkIndex(null);setTooltipData(null)}} onClick={()=>onSelect?.({...link,source:source.index||0,target:target.index||0})}
      onKeyDown={event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();onSelect?.({...link,source:source.index||0,target:target.index||0})}}} />
      <text x={((source.x1||0)+(target.x0||0))/2} y={((source.y0||0)+(source.y1||0)+(target.y0||0)+(target.y1||0))/4-12} textAnchor="middle" fill="#71717a" fontSize={10} style={{pointerEvents:"none"}}>{String(link.label || "connection").slice(0,40)}</text></g>
  })}</g>
}
