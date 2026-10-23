"use client"
import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, ArrowRight, ChevronRight, FileCode2, GitBranch, Network, RotateCcw } from "lucide-react"
import { Button } from "./ui/button"
import { Badge } from "./ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card"
import ArchitectureCanvas from "./architecture-canvas"
import { project, PAGE_SIZE, type Graph } from "./architecture-model"

function Diagram({ graph }: { graph: Graph }) {
  const [scope,setScope] = useState<string>(), [files,setFiles] = useState(false), [page,setPage] = useState(0)
  const [observed,setObserved] = useState(false), [selection,setSelection] = useState<{kind:"node"|"edge";id:string}>()
  const projection = useMemo(()=>project(graph,scope,files,page,observed),[graph,scope,files,page,observed])
  const chosen = selection?.kind === "node" ? projection.index.get(selection.id) : undefined
  const edge = selection?.kind === "edge" ? projection.bundles.find(edge=>edge.id===selection.id) : undefined
  const refs = new Set(chosen?.evidence_ids || edge?.relationships.flatMap(edge=>edge.evidence_ids) || [])
  const evidence = graph.evidence.filter(item=>refs.has(item.id))
  const relationships = chosen ? graph.relationships.filter(edge=>edge.source===chosen.id || edge.target===chosen.id) : edge?.relationships || []
  function navigate(id?:string,sourceFiles=false) { setScope(id);setFiles(sourceFiles);setPage(0);setSelection(undefined) }
  return <div className="architecture-page flex flex-col gap-6 p-4 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><Link href="/dashboard" className="mb-4 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft size={14} />All investigations</Link><h2 className="text-2xl font-semibold tracking-tight">{graph.repository_name}</h2><p className="mt-2 text-sm text-muted-foreground">{graph.nodes.filter(node=>node.level==="subsystem").length} subsystems / {graph.nodes.length} components / {graph.relationships.length} saved relationships</p></div><Badge variant="outline" className="capitalize">{graph.status}</Badge></div>
    <Card><CardHeader className="gap-4"><div className="flex flex-wrap items-center justify-between gap-3"><CardTitle className="text-base">Project connections</CardTitle><div className="flex flex-wrap items-center gap-2"><Button variant="outline" size="sm" onClick={()=>navigate(scope,!files)}><FileCode2 size={14}/>{files?"Component view":"Source files"}</Button><Button variant="ghost" size="sm" onClick={()=>navigate()}><RotateCcw size={14}/>Reset</Button></div></div>
      <nav aria-label="Diagram location" className="flex flex-wrap items-center gap-2 text-sm"><button onClick={()=>navigate()} className="text-muted-foreground hover:text-foreground">Overview</button>{projection.trail.map(node=><span key={node.id} className="inline-flex items-center gap-2"><ChevronRight size={12}/><button onClick={()=>navigate(node.id)}>{node.label}</button></span>)}</nav>
      <CardDescription>{scope ? "Inside this component. Select a shape to explore its contents; select a connection for its evidence." : "High-level system view. Select a system to explore its components. Only connections supported by the saved graph are shown."}</CardDescription>
    </CardHeader><CardContent>
      {!!projection.visible.length && <ArchitectureCanvas key={`${scope}:${files}:${page}:${observed}`} nodes={projection.visible} connections={projection.bundles} boundaryLabel={scope ? projection.index.get(scope)?.label || graph.repository_name : graph.repository_name}
        selectedId={selection?.id} childrenCount={id=>projection.children(id).length}
        onNodeSelect={id=>{if(projection.children(id).length)navigate(id);else setSelection({kind:"node",id})}}
        onEdgeSelect={id=>setSelection({kind:"edge",id})}/>}
      {!!projection.visible.length && <p className="mt-3 text-xs text-muted-foreground">Dotted arrows show containment in this view. Other arrows show saved dependencies; dashed dependencies include inference. Drag shapes to rearrange; click to explore.{!projection.bundles.length && " No dependencies between these components were saved at this level."}</p>}
      {!projection.visible.length && <p className="py-12 text-center text-sm text-muted-foreground">No components match this view. Change the filter or return to Overview.</p>}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t pt-4 text-xs text-muted-foreground"><span>{projection.visible.length} of {projection.total} components / {projection.bundles.length} connection groups. {projection.excluded} relationships are internal, outside this page, or filtered.</span><label className="inline-flex items-center gap-2"><input type="checkbox" checked={observed} onChange={event=>{setObserved(event.target.checked);setPage(0);setSelection(undefined)}}/>Observed only</label></div>
      {projection.total>PAGE_SIZE && <div className="mt-4 flex items-center justify-end gap-3"><Button variant="outline" size="sm" disabled={!page} onClick={()=>{setPage(page-1);setSelection(undefined)}}>Previous</Button><span className="text-xs text-muted-foreground">{page+1} / {Math.ceil(projection.total/PAGE_SIZE)}</span><Button variant="outline" size="sm" disabled={(page+1)*PAGE_SIZE>=projection.total} onClick={()=>{setPage(page+1);setSelection(undefined)}}>Next</Button></div>}
    </CardContent></Card>
    <div className="grid gap-6 lg:grid-cols-2"><Card><CardHeader><CardTitle className="text-base">{chosen?.label || edge?.label || "Source evidence"}</CardTitle><CardDescription>{chosen?.description || "Select a component or connection above. Saved evidence stays linked to the original investigation."}</CardDescription></CardHeader><CardContent>
      {chosen?.path && <code className="mb-4 block break-all text-xs text-muted-foreground">{chosen.path}</code>}
      {chosen && !!projection.children(chosen.id).length && <Button variant="outline" size="sm" className="mb-4" onClick={()=>navigate(chosen.id)}>Explore component <ArrowRight size={14}/></Button>}
      <div className="flex flex-col gap-3">{evidence.map(item=><div className="rounded-lg border p-3" key={item.id}><Badge variant="secondary" className="mb-2">{item.classification}</Badge><p className="text-sm leading-relaxed">{item.description}</p>{item.path && <code className="mt-2 block break-all text-xs text-muted-foreground">{item.path}{item.line_start?`:${item.line_start}${item.line_end && item.line_end!==item.line_start?`-${item.line_end}`:""}`:""}</code>}</div>)}
      {(chosen || edge) && !evidence.length && <p className="text-sm text-muted-foreground">No supporting source references were saved for this selection.</p>}</div>
    </CardContent></Card><Card><CardHeader><CardTitle className="text-base">{chosen || edge?"Related connections":"Investigation coverage"}</CardTitle><CardDescription>{chosen || edge?"Actual saved relationships, with their evidence classification.":"What was inspected, and what remains outside the saved evidence."}</CardDescription></CardHeader><CardContent className="flex flex-col gap-3">
      {chosen || edge ? relationships.map(item=><div className="rounded-lg border p-3" key={item.id}><p className="text-sm font-medium">{projection.index.get(item.source)?.label || item.source} <span className="text-muted-foreground">to</span> {projection.index.get(item.target)?.label || item.target}</p><p className="mt-1 text-xs text-muted-foreground">{item.label || item.type} / {item.classification}</p><p className="mt-2 text-sm text-muted-foreground">{item.description}</p></div>) : <>
        {graph.coverage ? <><div className="grid grid-cols-2 gap-4"><div><p className="text-2xl font-semibold">{graph.coverage.examined_files.length}</p><p className="text-xs text-muted-foreground">Files examined</p></div><div><p className="text-2xl font-semibold">{graph.coverage.uninspected_file_count}</p><p className="text-xs text-muted-foreground">Not examined</p></div></div><p className="text-sm leading-relaxed text-muted-foreground">{graph.coverage.discovery_note}</p></> : <p className="text-sm text-muted-foreground">Detailed coverage was not recorded in this saved investigation.</p>}
        {graph.limitations?.map((text,index)=><p className="text-xs leading-relaxed text-muted-foreground" key={index}>{text}</p>)}
      </>}
    </CardContent></Card></div>
  </div>
}
export default function ArchitectureViewer({id}:{id:string}) {
  const [graph,setGraph] = useState<Graph>(), [error,setError] = useState(""), [revision,setRevision] = useState(0)
  useEffect(()=>{
    const controller=new AbortController();let active=true
    const timer=setTimeout(()=>controller.abort(),10000)
    setGraph(undefined);setError("")
    fetch(`/api/investigations/${encodeURIComponent(id)}`,{credentials:"same-origin",cache:"no-store",signal:controller.signal}).then(async response=>{
      if(!response.ok)throw new Error(response.status===401?"Sign in again to view this investigation.":response.status===403||response.status===404?"This investigation is unavailable or belongs to another account.":"Could not load this investigation.")
      const data=await response.json()
      if(!data.graph || !Array.isArray(data.graph.nodes) || !Array.isArray(data.graph.relationships) || !Array.isArray(data.graph.evidence))throw new Error("The saved graph could not be read.")
      if(active)setGraph(data.graph)
    }).catch(failure=>{if(active)setError(failure.name==="AbortError"?"The request took too long. Please retry.":failure.message)}).finally(()=>clearTimeout(timer))
    return ()=>{active=false;clearTimeout(timer);controller.abort()}
  },[id,revision])
  if(error)return <div className="p-6"><Card><CardHeader><CardTitle>Diagram unavailable</CardTitle><CardDescription role="alert">{error}</CardDescription></CardHeader><CardContent><Button onClick={()=>setRevision(value=>value+1)}>Retry</Button></CardContent></Card></div>
  if(!graph)return <p role="status" className="p-6 text-sm text-muted-foreground">Loading architecture...</p>
  return <Diagram graph={graph}/>
}
