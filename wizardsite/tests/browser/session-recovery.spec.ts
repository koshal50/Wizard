import { test, expect, type Page } from "@playwright/test"
import crypto from "node:crypto"

test.skip(!process.env.WIZARD_SESSION_TEST_CONTEXT, "Run against the disposable PostgreSQL account fixture.")
const email = "account@example.test"
const password = "a-secure-password-123"

async function signInSession(page: Page) {
  const context = await (await page.request.get("/api/auth/context")).json()
  const response = await page.request.post("/login", { maxRedirects: 0,
    headers: { Origin: "http://localhost:3000", "X-CSRF-Token": context.csrf }, data: { email, password } })
  expect(response.status()).toBe(303)
}
async function registration(page: Page, address: string) {
  await page.getByLabel("Full name", { exact: true }).fill("Session Recovery")
  await page.getByLabel("Email address").fill(address)
  await page.getByLabel("Password", { exact: true }).fill(password)
  await page.getByLabel("Confirm password", { exact: true }).fill(password)
  await page.locator('[name="acceptTerms"]').check()
  await page.locator('button[type="submit"]').click()
}

test("registration exposes an existing session instead of a vague conflict", async ({ page }) => {
  await signInSession(page)
  let registrationRequests = 0
  page.on("request", request => { if (new URL(request.url()).pathname === "/register" && request.method() === "POST") registrationRequests++ })
  await page.goto("/register.html")
  await expect(page.getByRole("complementary", { name: "Current signed-in account" })).toContainText(email)
  await registration(page, "different@example.test")
  await expect(page.locator("#form-alert")).toContainText("already signed in")
  expect(registrationRequests).toBe(0)
  await page.getByRole("button", { name: /Continue as/ }).click()
  await expect(page).toHaveURL("http://localhost:3000/")
  expect((await (await page.request.get("/api/auth/context")).json()).account.email).toBe(email)
})

test("the existing session can sign out and sign in again", async ({ page }) => {
  await signInSession(page)
  await page.goto("/register.html")
  await page.getByRole("button", { name: "Sign out", exact: true }).click()
  await expect(page.locator("#form-alert")).toContainText("Signed out")
  expect((await (await page.request.get("/api/auth/context")).json()).account).toBeNull()
  await page.goto("/login.html")
  await page.getByLabel("Email address").fill(email)
  await page.getByLabel("Password", { exact: true }).fill("wrong-password")
  await page.locator('button[type="submit"]').click()
  await expect(page.locator("#form-alert")).toContainText("not accepted")
  await page.getByLabel("Password", { exact: true }).fill(password)
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL("http://localhost:3000/")
  expect((await (await page.request.get("/api/auth/context")).json()).account.email).toBe(email)
})

test("a registration conflict suggests recovery without claiming session failure", async ({ page }) => {
  await page.goto("/register.html")
  await registration(page, email)
  await expect(page.locator("#form-alert")).toContainText("Try signing in or use a different email address")
  expect((await (await page.request.get("/api/auth/context")).json()).account).toBeNull()
})

test("continuing an existing session preserves explicit CLI approval", async ({ page }) => {
  await signInSession(page)
  const verifierHash = crypto.createHash("sha256").update(crypto.randomBytes(32)).digest("hex")
  const pendingResponse = await page.request.post("/api/cli/requests", { data: { verifier_hash: verifierHash } })
  expect(pendingResponse.status()).toBe(201)
  const pending = await pendingResponse.json()
  const ticket = new URLSearchParams(new URL(pending.authorization_url).hash.slice(1)).get("ticket")
  const context = await (await page.request.get("/api/auth/context")).json()
  const binding = await page.request.post("/api/cli/browser/bind", {
    headers: { Origin: "http://localhost:3000", "X-CSRF-Token": context.csrf },
    data: { request_id: pending.request_id, ticket } })
  expect(binding.status()).toBe(200)
  await page.goto("/register.html?returnTo=%2Fcli%2Fconnect")
  await page.getByRole("button", { name: /Continue as/ }).click()
  await expect(page).toHaveURL("http://localhost:3000/cli/connect")
  await expect(page.getByRole("button", { name: "Authorize this account for this terminal" })).toBeVisible()
  await expect(page.getByTestId("authorization-code")).toHaveCount(0)
})
