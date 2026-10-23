import { test, expect } from "@playwright/test"
import { layout, normalizedNodes, orthogonalPath, PAGE_SIZE, project, type Component, type Graph } from "../../components/architecture-model"

function largeGraph(): Graph {
  const nodes: Component[] = [], relationships: Graph["relationships"] = []
  for (let i = 0; i < 100; i++) {
    nodes.push({ id:`system${i}`, label:`Application ${i}`, type:"application", level:"subsystem", description:"", evidence_ids:[] })
    for (let j = 0; j < 4; j++) {
      nodes.push({ id:`file${i}_${j}`, label:`source${j}.ts`, type:"file", level:"file", parent_id:`system${i}`, path:`pkg${i}/source${j}.ts`, description:"", evidence_ids:["p"] })
      relationships.push({ id:`edge${i}_${j}`, source:`file${i}_${j}`, target:`file${(i+1)%100}_${j}`, type:"imports", label:"imports", classification:"observed", description:"Resolved dependency", evidence_ids:["p"] })
    }
  }
  return { title:"Scale check", repository_name:"scale", status:"incomplete", nodes, relationships, evidence:[{id:"p",description:"Test proof",classification:"observed",path:"package.json"}] }
}

test("overview is bounded, paginated and retains every collapsed relationship", () => {
  const graph=largeGraph(), started=performance.now()
  const overview=project(graph)
  expect(overview.visible).toHaveLength(PAGE_SIZE)
  expect(overview.total).toBe(100)
  expect(overview.visible.every(n=>n.level==="subsystem")).toBeTruthy()
  expect(overview.bundles.reduce((total,e)=>total+e.relationships.length,0)+overview.excluded).toBe(graph.relationships.length)
  expect(project(graph,undefined,false,1).visible.map(n=>n.id)).not.toEqual(overview.visible.map(n=>n.id))
  expect(project(graph,"system0").visible.every(n=>n.level==="file")).toBeTruthy()
  expect(project(graph,undefined,true).total).toBe(400)
  expect(performance.now()-started).toBeLessThan(2000)
})

test("cycles have deterministic finite vertical positions without overlapping nodes", () => {
  const view=project(largeGraph())
  const cycle=[...view.bundles,{id:"cycle",source:view.visible[1].id,target:view.visible[0].id,label:"calls",classification:"inferred",relationships:[]}]
  const first=layout(view.visible,cycle), second=layout([...view.visible].reverse(),[...cycle].reverse())
  expect([...first.positions.entries()].sort()).toEqual([...second.positions.entries()].sort())
  const positions=[...first.positions.values()]
  expect(new Set(positions.map(p=>`${p.x},${p.y}`)).size).toBe(positions.length)
  expect(Math.max(...positions.map(p=>p.y))).toBeGreaterThan(660)
  expect(first.width).toBeLessThanOrEqual(1000)
})

test("orthogonal routes contain only line segments with at most three right-angle bends", () => {
  for(const backward of [false,true]) {
    const path=orthogonalPath(120,100,480,400,backward,2)
    expect(path).not.toMatch(/[CQAS]/)
    const points=[...path.matchAll(/[ML] (-?[\d.]+) (-?[\d.]+)/g)].map(m=>[Number(m[1]),Number(m[2])])
    expect(points.length-2).toBeLessThanOrEqual(3)
    for(let i=1;i<points.length;i++) expect(points[i][0]===points[i-1][0]||points[i][1]===points[i-1][1]).toBeTruthy()
  }
})

test("older saved groups remain collapsible without changing saved graph evidence",()=>{
  const graph=largeGraph();graph.nodes=graph.nodes.slice(1,4).map(n=>({...n,level:undefined,parent_id:undefined,group_id:"old"}));graph.groups=[{id:"old",label:"Saved boundary",description:"Original grouping",evidence_ids:[]}];graph.relationships=[]
  const before=JSON.stringify(graph)
  expect(normalizedNodes(graph)).toHaveLength(4)
  expect(project(graph).visible.map(n=>n.label)).toEqual(["Saved boundary"])
  expect(project(graph,"old").visible).toHaveLength(3)
  expect(JSON.stringify(graph)).toBe(before)
})
