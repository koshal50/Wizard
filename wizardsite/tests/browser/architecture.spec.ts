import { test, expect } from "@playwright/test"
import { readFileSync } from "node:fs"


const fixturePath = process.env.WIZARD_DIAGRAM_TEST_CONTEXT
const saved = fixturePath ? JSON.parse(readFileSync(fixturePath, "utf8")) : {}
test.skip(!fixturePath, "Set WIZARD_DIAGRAM_TEST_CONTEXT to the disposable PostgreSQL browser fixture.")
const diagramPath = `/investigations/${saved.id}`

test("saved PostgreSQL graph renders shapes, connections, evidence and controls", async ({ page, context }) => {
  await context.addCookies([{ name: "wizard_site", value: saved.cookie, domain: "localhost", path: "/" }])
  await page.goto(diagramPath)
  await expect(page.getByRole("heading", { name: saved.graph.repository_name, exact: true })).toBeVisible()
  await expect(page.locator(".react-flow__node-default")).toHaveCount(saved.graph.nodes.length)
  await expect(page.locator(".react-flow__edge")).toHaveCount(saved.graph.relationships.length)
  await expect(page.locator(".react-flow__node-group")).toHaveCount(saved.graph.groups?.length || 0)
  const regions = await page.locator(".react-flow__node-group").evaluateAll(elements => elements.map(e => {
    const r = e.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }
  }))
  for (let i = 0; i < regions.length; i++) for (let j = i + 1; j < regions.length; j++) {
    const a = regions[i], b = regions[j]
    expect(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top).toBeTruthy()
  }
  const fetched = await page.request.get(`/api/investigations/${saved.id}`)
  expect((await fetched.json()).graph).toEqual(saved.graph)
  await page.getByRole("complementary", { name: "Privacy notice" }).getByRole("button", { name: "Continue", exact: true }).click()
  await page.locator(`.react-flow__node[data-id="${saved.graph.nodes[0].id}"]`).click()
  const panel = page.getByRole("complementary", { name: "Architecture evidence" })
  await expect(panel.getByRole("heading", { name: saved.graph.nodes[0].label, exact: true })).toBeVisible()
  await expect(panel.getByRole("heading", { name: "Supporting evidence" })).toBeVisible()
  const proof = saved.graph.evidence.find((e: any) => e.id === saved.graph.nodes[0].evidence_ids[0])
  await expect(panel.getByText(proof.description, { exact: true })).toBeVisible()
  await expect(panel.locator("article code").first()).toContainText(proof.path)
  await page.locator(".react-flow__controls-zoomin").click()
  await page.locator(".react-flow__controls-zoomout").click()
  await page.locator(".react-flow__controls-fitview").click()
  // Click a visible path segment rather than an SVG bounding-box center,
  // which can fall on another component in a multi-branch graph.
  const point = await page.locator(".react-flow__edges").evaluate(() => {
    for (const edge of document.querySelectorAll<SVGGElement>(".react-flow__edge")) {
      const path = edge.querySelector<SVGPathElement>(".react-flow__edge-interaction")!
      for (const fraction of [0.25, 0.5, 0.75]) {
        const local = path.getPointAtLength(path.getTotalLength() * fraction)
        const screen = new DOMPoint(local.x, local.y).matrixTransform(path.getScreenCTM()!)
        const hit = document.elementFromPoint(screen.x, screen.y)?.closest(".react-flow__edge")
        if (hit === edge) return { x: screen.x, y: screen.y, id: edge.getAttribute("data-id") }
      }
    }
    return null
  })
  expect(point).not.toBeNull()
  await page.mouse.click(point!.x, point!.y)
  const selectedEdge = saved.graph.relationships.find((e: any) => e.id === point!.id)
  await expect(panel.getByText(`${selectedEdge.classification} relationship`, { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.locator(".react-flow__node-default")).toHaveCount(saved.graph.nodes.length)
  await page.getByRole("link", { name: "Your diagrams" }).click()
  await expect(page.locator(`a[href='${diagramPath}']`)).toBeVisible()
})

test("anonymous and cross-owner retrieval are rejected by the backend", async ({ page, request }) => {
  await page.goto(diagramPath)
  await expect(page.getByRole("alert").filter({ hasText: "Diagram unavailable" })).toContainText("Sign in")
  const ctx = await (await request.get("/api/auth/context")).json()
  const registration = await request.post("/register", { headers: { Origin: new URL(page.url()).origin, "X-CSRF-Token": ctx.csrf },
    data: { email: `other-${Date.now()}@example.test`, fullName: "Other diagram owner", password: "browser-test-password-123", confirmPassword: "browser-test-password-123", acceptTerms: "on" }, maxRedirects: 0 })
  expect(registration.status()).toBe(303)
  expect((await request.get(`/api/investigations/${saved.id}`)).status()).toBe(404)
  const list = await (await request.get("/api/investigations")).json()
  expect(list.investigations).toEqual([])
})

test("loading, empty and missing diagram states", async ({ page, context, request }) => {
  await context.addCookies([{ name: "wizard_site", value: saved.cookie, domain: "localhost", path: "/" }])
  let release: () => void = () => {}
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route(`**/api/investigations/${saved.id}`, async route => { await gate; await route.continue() })
  await page.goto(diagramPath)
  await expect(page.getByRole("status")).toContainText("Loading saved architecture")
  release()
  await expect(page.locator(".react-flow__node-default")).toHaveCount(saved.graph.nodes.length)
  await page.unrouteAll()
  const response = await request.post("/api/investigations", { headers: { Authorization: saved.token }, data: { ...saved.graph, nodes: [], relationships: [], evidence: [], groups: [] } })
  expect(response.status()).toBe(201)
  const empty = await response.json()
  await page.goto(`/investigations/${empty.investigation_id}`)
  await expect(page.getByText("This investigation has no architecture nodes.")).toBeVisible()
  await page.goto("/investigations/00000000-0000-4000-8000-000000000000")
  await expect(page.getByRole("alert").filter({ hasText: "Diagram unavailable" })).toContainText("unavailable or belongs to another account")
})

test("mobile evidence selection and existing homepage button", async ({ page, context }) => {
  await context.addCookies([{ name: "wizard_site", value: saved.cookie, domain: "localhost", path: "/" }])
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(diagramPath)
  await page.getByRole("complementary", { name: "Privacy notice" }).getByRole("button", { name: "Continue", exact: true }).click()
  await page.locator(`.react-flow__node[data-id="${saved.graph.nodes[0].id}"]`).click()
  await expect(page.getByRole("heading", { name: "Supporting evidence" })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.goto("/")
  await expect(page.getByRole("link", { name: "Review Architectural Diagram" })).toHaveAttribute("href", "/dashboard")
})
