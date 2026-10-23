import { test, expect } from "@playwright/test"
import { readFileSync } from "node:fs"
import { project } from "../../components/architecture-model"

const fixturePath=process.env.WIZARD_DIAGRAM_TEST_CONTEXT
const saved=fixturePath ? JSON.parse(readFileSync(fixturePath,"utf8")) : {}
const largePath=process.env.WIZARD_DIAGRAM_LARGE_GRAPH
const larger=largePath ? JSON.parse(readFileSync(largePath,"utf8")) : undefined
test.skip(!fixturePath,"Set WIZARD_DIAGRAM_TEST_CONTEXT to the isolated PostgreSQL fixture.")
const diagramPath=`/investigations/${saved.id}`
async function privacy(page: any) {
  const notice=page.getByRole("complementary",{name:"Privacy notice"})
  await notice.getByRole("button",{name:"Continue",exact:true}).click()
}

test("persisted overview, behavior labels, cylinders, expansion and source evidence",async({page,context})=>{
  await context.addCookies([{name:"wizard_site",value:saved.cookie,domain:"localhost",path:"/"}])
  await page.goto(diagramPath)
  await privacy(page)
  const overview=project(saved.graph)
  await expect(page.locator('.react-flow__node')).toHaveCount(overview.visible.length)
  await expect(page.locator('.react-flow__node')).not.toHaveCount(saved.graph.nodes.length)
  await expect(page.locator('.react-flow__edge')).toHaveCount(overview.bundles.length)
  await expect(page.locator('[data-kind="database"] svg ellipse')).toHaveCount(overview.visible.filter(n=>n.type==='database').length)
  expect((await (await page.request.get(`/api/investigations/${saved.id}`)).json()).graph).toEqual(saved.graph)
  for(const edge of overview.bundles) await expect(page.getByRole('button',{name:`Inspect relationship: ${edge.label}`,exact:true})).toBeVisible()
  // Opposing boundary arrows must keep their action labels independently readable.
  const labels=await page.locator('button[aria-label^="Inspect relationship:"]').all()
  for(let i=0;i<labels.length;i++) for(let j=i+1;j<labels.length;j++) {
    const a=await labels[i].boundingBox(), b=await labels[j].boundingBox()
    expect(a&&b&&(a.x+a.width<=b.x||b.x+b.width<=a.x||a.y+a.height<=b.y||b.y+b.height<=a.y)).toBeTruthy()
  }
  const arrow=overview.bundles[0]
  await page.getByRole('button',{name:`Inspect relationship: ${arrow.label}`,exact:true}).click()
  const panel=page.getByRole('complementary',{name:'Architecture evidence'})
  await expect(panel.getByRole('heading',{name:'Supporting evidence'})).toBeVisible()
  await expect(panel.getByText(`${arrow.relationships.length} saved relationship${arrow.relationships.length===1?'':'s'} represented by this arrow.`,{exact:true})).toBeVisible()
  const first=overview.visible.find(n=>saved.graph.nodes.some((c:any)=>c.parent_id===n.id))!
  await page.locator(`.react-flow__node[data-id="${first.id}"]`).click()
  await expect(panel.getByRole('heading',{name:first.label,exact:true})).toBeVisible()
  await expect(panel.getByRole('heading',{name:'Connected behavior'})).toBeVisible()
  await page.locator(`.react-flow__node[data-id="${first.id}"]`).getByRole('button').click()
  await expect(page.getByRole('status').filter({hasText:/Subsystem detail|File detail/})).toBeVisible()
  const child=project(saved.graph,first.id)
  await expect(page.locator('.react-flow__node')).toHaveCount(child.visible.length)
  await page.getByRole('button',{name:'Explore source files',exact:true}).click()
  await expect(page.getByRole('status').filter({hasText:'File detail'})).toBeVisible()
  const file=project(saved.graph,first.id,true).visible[0]
  await page.locator(`.react-flow__node[data-id="${file.id}"]`).click()
  await expect(panel.locator('code').first()).toContainText(file.path!)
  await expect(panel.getByRole('heading',{name:'Supporting evidence'})).toBeVisible()
  await page.getByRole('button',{name:'Overview',exact:true}).click()
  await page.getByRole('button',{name:'Zoom in',exact:true}).click()
  await page.getByRole('button',{name:'Zoom out',exact:true}).click()
  await page.getByRole('button',{name:'Fit map',exact:true}).click()
  await page.getByRole('button',{name:'Reset view',exact:true}).click()
  const region=page.getByRole('region',{name:'Scrollable architecture map'})
  const before=await region.evaluate(e=>e.scrollTop)
  await region.hover();await page.mouse.wheel(0,500)
  await expect.poll(()=>region.evaluate(e=>e.scrollTop)).toBeGreaterThan(before)
  await page.reload()
  await expect(page.locator('.react-flow__node')).toHaveCount(overview.visible.length)
  await page.getByRole('link',{name:'Your diagrams'}).click()
  await expect(page.locator(`a[href='${diagramPath}']`)).toBeVisible()
})

test("anonymous and cross-owner retrieval remain private",async({page,request})=>{
  await page.goto(diagramPath)
  await expect(page.getByRole('alert').filter({hasText:'Diagram unavailable'})).toContainText('Sign in')
  const ctx=await(await request.get('/api/auth/context')).json()
  const registration=await request.post('/register',{headers:{Origin:new URL(page.url()).origin,'X-CSRF-Token':ctx.csrf},data:{email:`other-${Date.now()}@example.test`,fullName:'Other owner',password:'browser-test-password-123',confirmPassword:'browser-test-password-123',acceptTerms:'on'},maxRedirects:0})
  expect(registration.status()).toBe(303)
  expect((await request.get(`/api/investigations/${saved.id}`)).status()).toBe(404)
  expect((await(await request.get('/api/investigations')).json()).investigations).toEqual([])
})

test("loading, empty, missing and legacy diagram states",async({page,context,request})=>{
  await context.addCookies([{name:'wizard_site',value:saved.cookie,domain:'localhost',path:'/'}])
  let release:()=>void=()=>{}
  const gate=new Promise<void>(resolve=>{release=resolve})
  await page.route(`**/api/investigations/${saved.id}`,async route=>{await gate;await route.continue()})
  await page.goto(diagramPath)
  await expect(page.getByRole('status').filter({hasText:'Loading saved architecture'})).toBeVisible()
  release();await expect(page.locator('.react-flow__node')).toHaveCount(project(saved.graph).visible.length)
  await page.unrouteAll()
  const response=await request.post('/api/investigations',{headers:{Authorization:saved.token},data:{...saved.graph,nodes:[],relationships:[],evidence:[],groups:[],coverage:null}})
  expect(response.status()).toBe(201)
  await page.goto(`/investigations/${(await response.json()).investigation_id}`)
  await expect(page.getByText('This investigation has no architecture nodes.')).toBeVisible()
  await page.goto('/investigations/00000000-0000-4000-8000-000000000000')
  await expect(page.getByRole('alert').filter({hasText:'Diagram unavailable'})).toContainText('unavailable or belongs to another account')
  const legacy={...saved.graph,nodes:saved.graph.nodes.filter((n:any)=>n.level==='subsystem').map((n:any)=>({...n,level:'module',parent_id:null})),relationships:[],coverage:null,groups:[]}
  const older=await request.post('/api/investigations',{headers:{Authorization:saved.token},data:legacy})
  expect(older.status()).toBe(201)
  await page.goto(`/investigations/${(await older.json()).investigation_id}`)
  await expect(page.locator('.react-flow__node')).toHaveCount(legacy.nodes.length)
})

test("mobile navigation, horizontal pan, evidence panel and homepage",async({page,context})=>{
  await context.addCookies([{name:'wizard_site',value:saved.cookie,domain:'localhost',path:'/'}])
  await page.setViewportSize({width:390,height:844});await page.goto(diagramPath);await privacy(page)
  const node=project(saved.graph).visible[0]
  await page.locator(`.react-flow__node[data-id="${node.id}"]`).click()
  await expect(page.getByRole('heading',{name:'Supporting evidence'})).toBeVisible()
  const region=page.getByRole('region',{name:'Scrollable architecture map'})
  expect(await region.evaluate(e=>e.scrollWidth>e.clientWidth)).toBeTruthy()
  await page.getByRole('button',{name:'Hide evidence',exact:true}).click()
  await expect(page.getByRole('complementary',{name:'Architecture evidence'})).toHaveCount(0)
  await page.getByRole('button',{name:'Show evidence',exact:true}).click()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy()
  await page.goto('/')
  await expect(page.getByRole('link',{name:'Review Architectural Diagram'})).toHaveAttribute('href','/dashboard')
})

test("actual multi-package repository overview preserves measured coverage and saved proof",async({page,context,request})=>{
  test.skip(!larger,'Provide the actual large repository export via WIZARD_DIAGRAM_LARGE_GRAPH.')
  const result=await request.post('/api/investigations',{headers:{Authorization:saved.token},data:larger})
  expect(result.status()).toBe(201)
  const id=(await result.json()).investigation_id
  await context.addCookies([{name:'wizard_site',value:saved.cookie,domain:'localhost',path:'/'}])
  await page.goto(`/investigations/${id}`);await privacy(page)
  await expect(page.locator('.react-flow__node')).toHaveCount(project(larger).visible.length)
  expect(project(larger).visible.length).toBeLessThan(larger.nodes.length)
  expect((await(await page.request.get(`/api/investigations/${id}`)).json()).graph).toEqual(larger)
  await page.getByText('Investigation coverage',{exact:true}).click()
  await expect(page.getByText(new RegExp(`${larger.coverage.uninspected_file_count} source files uninspected`))).toBeVisible()
  expect(await page.locator('.react-flow__node').first().evaluate(e=>e.getBoundingClientRect().width)).toBeGreaterThan(200)
})
