import { test, expect, type Page } from "@playwright/test"
import { spawn, spawnSync } from "node:child_process"
import path from "node:path"
import crypto from "node:crypto"

const backend = process.env.WIZARD_BACKEND_WORKTREE || path.resolve(process.cwd(), "../../Wizard")
const python = path.join(backend, "venv/Scripts/python.exe")
const executable = path.join(backend, "venv/Scripts/wizard.exe")
const origin = "http://localhost:3000"
const email = "web-e2e-" + crypto.randomBytes(6).toString("hex") + "@example.test"
const password = crypto.randomBytes(18).toString("hex") + "A1"
const storageCode = `
import sys,json,ctypes
from ctypes import wintypes
from wizard.cli.account_storage import CredentialStore
s=CredentialStore("http://localhost:3000")
if sys.argv[1]=="snapshot":
 print(json.dumps(s.load()))
else:
 value=json.load(sys.stdin)
 if value is not None: s.save(value)
 else:
  api=ctypes.WinDLL("Advapi32.dll",use_last_error=True)
  api.CredDeleteW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD]
  api.CredDeleteW(s.target,1,0)
`
function storage(action: "snapshot" | "restore", value?: string) {
  const result = spawnSync(python, ["-c", storageCode, action], {cwd: backend, input: value, encoding:"utf8"})
  if (result.status !== 0) throw new Error("Native account credential backup/restore failed")
  return result.stdout.trim()
}
async function cli() {
  const previous = storage("snapshot"); storage("restore", "null")
  const processHandle = spawn(executable, ["/login"], {cwd: backend, env: {
    ...process.env, WIZARD_ACCOUNT_URL: origin, WIZARD_ACCOUNT_LOCAL_DEV: "1",
    COLUMNS: "2400", NO_COLOR: "1", FORCE_COLOR: "0", NODE_NO_WARNINGS: "1",
    BROWSER: '"' + process.execPath.replaceAll("\\", "/") + '" "' +
      path.resolve("tests/browser/browser-noop.cjs").replaceAll("\\", "/") + '" %s',
  }})
  let output = ""
  processHandle.stdout.on("data", chunk => { output += chunk.toString() })
  // Never log CLI output: it contains a binding ticket.
  let errorSeen = false
  processHandle.stderr.on("data", () => { errorSeen = true })
  try {
  await expect.poll(() => /http:\/\/localhost:3000\/cli\/authorize#request_id=[a-f0-9-]{36}&ticket=[A-Za-z0-9_-]{43}/.test(output)).toBeTruthy()
  } catch (_) { processHandle.kill(); storage("restore", previous); throw new Error("Actual CLI did not provide a complete authorization URL") }
  const url = output.match(/http:\/\/localhost:3000\/cli\/authorize#request_id=[a-f0-9-]{36}&ticket=[A-Za-z0-9_-]{43}/)![0]
  return { url, processHandle, previous, output: () => output, errorSeen: () => errorSeen }
}
async function cleanup(run: Awaited<ReturnType<typeof cli>>) {
  if (run.processHandle.exitCode === null) {
    run.processHandle.stdin.end("/cancel-login\n")
    await new Promise(resolve => {
      run.processHandle.once("exit", resolve)
      setTimeout(() => { if (run.processHandle.exitCode === null) run.processHandle.kill(); resolve(null) }, 4000)
    })
  }
  storage("restore", run.previous)
}
async function signIn(page: Page) {
  await page.locator('[name="email"]').fill(email)
  await page.getByLabel("Password", {exact:true}).fill(password)
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(/\/cli\/connect$/)
}
async function approveAndExchange(page: Page, run: Awaited<ReturnType<typeof cli>>) {
  await page.getByRole("button", {name:"Authorize this account for this terminal"}).click()
  const box = page.getByTestId("authorization-code")
  await expect(box).toHaveText(/^[A-F0-9]{12}$/)
  const code = (await box.textContent())!
  await page.reload()
  await expect(page.getByTestId("authorization-code")).toHaveText(code)
  run.processHandle.stdin.write(code + "\n")
  await expect.poll(() => run.output().includes("connected and verified")).toBeTruthy()
  await expect.poll(() => run.processHandle.exitCode).toBe(0)
  await expect(page).toHaveURL(/\/cli\/complete$/)
  await expect(page.getByRole("heading", {name:"Ready to return to Wizard CLI"})).toBeVisible()
  expect(run.errorSeen()).toBe(false)
  // The CLI verified /api/account/me before persistence; verify saved account too.
  const saved = JSON.parse(storage("snapshot"))
  expect(saved.account.email).toBe(email)
  const me = await page.request.get("/api/account/me", {headers:{Authorization:"Bearer " + saved.access_token}})
  expect(me.status()).toBe(200)
  expect((await me.json()).account.email).toBe(email)
  // Retire only the test credential before restoring any previous local credential.
  expect((await page.request.delete("/api/account/credential", {headers:{Authorization:"Bearer " + saved.access_token}})).status()).toBe(200)
}
test.describe.serial("real frontend + PostgreSQL + actual wizard.exe /login", () => {
  test("registration, explicit approval, reload, exchange, secure persistence and completion", async ({page}) => {
    const run = await cli()
    try {
      await page.goto(run.url)
      await expect(page).toHaveURL(origin + "/cli/authorize", {timeout:20000})
      await page.getByRole("link", {name:"Continue to sign in"}).click()
      await page.getByRole("link", {name:/Create one/i}).click()
      await expect(page).toHaveURL(/register.html\?returnTo=%2Fcli%2Fconnect/)
      await page.getByLabel("Full name", {exact:true}).fill("Browser Integration")
      await page.locator('[name="email"]').fill(email)
      await page.getByLabel("Password", {exact:true}).fill(password)
      await page.getByLabel("Confirm password", {exact:true}).fill(password)
      await page.locator('[name="acceptTerms"]').check()
      await page.locator('button[type="submit"]').click()
      await expect(page).toHaveURL(/\/cli\/connect$/)
      await expect(page.getByText(email, {exact:false})).toBeVisible()
      await expect(page.getByTestId("authorization-code")).toHaveCount(0)
      await approveAndExchange(page, run)
    } finally { await cleanup(run) }
  })
  test("existing sign-in, rejected password, and already authenticated continuation", async ({page}) => {
    const first = await cli()
    try {
      await page.goto(first.url)
      await page.getByRole("link", {name:"Continue to sign in"}).click()
      await page.locator('[name="email"]').fill(email)
      await page.getByLabel("Password", {exact:true}).fill("wrong-password")
      await page.locator('button[type="submit"]').click()
      await expect(page.locator("#form-alert")).toContainText("not accepted")
      await signIn(page)
      await page.getByRole("button", {name:"Cancel connection"}).click()
      await expect(page.getByRole("heading", {name:"CLI connection cancelled"})).toBeVisible()
    } finally { await cleanup(first) }
    const second = await cli()
    try {
      await page.goto(second.url)
      await page.getByRole("link", {name:"Continue as Browser Integration", exact:true}).click()
      await expect(page).toHaveURL(/\/cli\/connect$/)
      await approveAndExchange(page, second)
    } finally { await cleanup(second) }
  })

  test("code expiry UI hides the code and cancellation still reaches the server", async ({page}) => {
    const run = await cli()
    try {
      await page.goto(run.url)
      await page.getByRole("link", {name:"Continue to sign in"}).click()
      await signIn(page)
      await page.getByRole("button", {name:"Authorize this account for this terminal"}).click()
      await expect(page.getByTestId("authorization-code")).toHaveText(/^[A-F0-9]{12}$/)
      // Advance browser time only. Server expiry boundaries are covered by PostgreSQL tests.
      await page.clock.install()
      await page.clock.fastForward(601000)
      await expect(page.getByTestId("authorization-code")).toHaveCount(0)
      await expect(page.locator("p[role=alert]")).toContainText("expired")
      await page.getByRole("button", {name:"Cancel connection"}).click()
      await expect(page.getByRole("heading", {name:"CLI connection cancelled"})).toBeVisible()
    } finally { await cleanup(run) }
  })
})
test("direct connect/complete visits and tampered context cannot mint or claim success", async ({page}) => {
  await page.goto("/cli/complete")
  await expect(page.locator("p[role=alert]")).toContainText("No pending CLI request")
  await expect(page.getByRole("heading", {name:"Ready to return to Wizard CLI"})).toHaveCount(0)
  await page.goto("/cli/connect")
  await expect(page.locator("p[role=alert]")).toContainText("No pending CLI request")
  await expect(page.getByTestId("authorization-code")).toHaveCount(0)
  await page.goto("/cli/authorize#request_id=invalid&ticket=invalid")
  await expect(page.locator("p[role=alert]")).toContainText("Invalid authorization URL")
})
test("anonymous cancellation is confirmed, and fixed hint links survive auth navigation", async ({page}) => {
  const run = await cli()
  try {
    await page.goto(run.url)
    await page.getByRole("link", {name:"Continue to sign in"}).click()
    await page.getByRole("link", {name:"Forgot password?"}).click()
    await expect(page).toHaveURL(/forgot-password.html\?returnTo=%2Fcli%2Fconnect/)
    await page.getByRole("button", {name:"Cancel CLI connection"}).click()
    await expect(page.getByText("Backend confirmed CLI connection cancellation.")).toBeVisible()
    await page.goto("/cli/connect")
    await expect(page.getByTestId("authorization-code")).toHaveCount(0)
  } finally { await cleanup(run) }
})

test("ordinary sign-in ignores arbitrary return hints and keeps existing navigation", async ({page}) => {
  await page.goto("/login.html?returnTo=https%3A%2F%2Fevil.example")
  await expect(page.getByRole("button", {name:"Cancel CLI connection"})).toHaveCount(0)
  await expect(page.getByRole("link", {name:"Create one"})).toHaveAttribute("href", "register.html")
  await page.locator('[name="email"]').fill(email)
  await page.getByLabel("Password", {exact:true}).fill(password)
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(origin + "/")
  const ctx = await page.request.get("/api/auth/context")
  const session = await ctx.json()
  expect(session.account.email).toBe(email)
  expect(session.cli_pending).toBe(false)

})
