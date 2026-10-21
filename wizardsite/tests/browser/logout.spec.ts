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
async function logoutCommand(expected: string) {
  const command = spawn(executable, ["/logout"], {cwd: backend, env: {...process.env, NO_COLOR:"1"}})
  let output = ""
  command.stdout.on("data", chunk => { output += chunk.toString() })
  command.stderr.resume()
  try {
    await expect.poll(() => command.exitCode).toBe(0)
    expect(output).toContain(expected)
  } finally { if (command.exitCode === null) command.kill() }
}

async function registerAccount(page: Page, address: string, name: string) {
  await page.getByRole("link", {name:/Create one/i}).click()
  await page.getByLabel("Full name", {exact:true}).fill(name)
  await page.locator('[name="email"]').fill(address)
  await page.getByLabel("Password", {exact:true}).fill(password)
  await page.getByLabel("Confirm password", {exact:true}).fill(password)
  await page.locator('[name="acceptTerms"]').check()
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(/\/cli\/connect$/)
  await expect(page.getByTestId("authorization-code")).toHaveCount(0)
}

async function finishLogin(page: Page, run: Awaited<ReturnType<typeof cli>>) {
  expect(JSON.parse(storage("snapshot"))).toBe(null)
  expect(run.output()).not.toContain("connected and verified")
  await page.getByRole("button", {name:"Authorize this account for this terminal"}).click()
  const box = page.getByTestId("authorization-code")
  await expect(box).toHaveText(/^[A-F0-9]{12}$/)
  const code = (await box.textContent())!
  expect(JSON.parse(storage("snapshot"))).toBe(null)
  run.processHandle.stdin.write(code + "\n")
  await expect.poll(() => run.processHandle.exitCode).toBe(0)
  expect(run.output()).toContain("connected and verified")
  await expect(page).toHaveURL(/\/cli\/complete$/)
  return {code, saved:JSON.parse(storage("snapshot"))}
}

test("real logout, retained browser session, fresh approval, different account, and cross-process pending cancellation", async ({page}) => {
  test.setTimeout(180000)
  const runs: Awaited<ReturnType<typeof cli>>[] = []
  const tokens: string[] = []
  try {
    const first = await cli(); runs.push(first)
    await page.goto(first.url)
    await page.getByRole("link", {name:"Continue to sign in"}).click()
    await registerAccount(page, email, "Logout Browser Account")
    const initial = await finishLogin(page, first); tokens.push(initial.saved.access_token)
    await logoutCommand("Youve been logged out of Wizard.")
    expect(JSON.parse(storage("snapshot"))).toBe(null)
    expect((await (await page.request.get("/api/auth/context")).json()).account.email).toBe(email)
    expect((await page.request.get("/api/account/me", {headers:{Authorization:"Bearer " + initial.saved.access_token}})).status()).toBe(401)
    await logoutCommand("Youre already logged out.")

    const same = await cli(); runs.push(same)
    await page.goto(same.url)
    await expect(page.getByRole("link", {name:"Continue as Logout Browser Account"})).toBeVisible()
    await expect(page.getByRole("button", {name:"Use a different account"})).toBeVisible()
    await expect(page.getByTestId("authorization-code")).toHaveCount(0)
    await page.getByRole("link", {name:"Continue as Logout Browser Account"}).click()
    const reconnected = await finishLogin(page, same); tokens.push(reconnected.saved.access_token)
    expect(reconnected.code).not.toBe(initial.code)
    expect(reconnected.saved.account.id).toBe(initial.saved.account.id)
    await logoutCommand("Youve been logged out of Wizard.")

    const different = await cli(); runs.push(different)
    await page.goto(different.url)
    await page.getByRole("button", {name:"Use a different account"}).click()
    await expect(page).toHaveURL(/login.html\?returnTo=%2Fcli%2Fconnect/)
    await registerAccount(page, "different-" + email, "Different Browser Account")
    const switched = await finishLogin(page, different); tokens.push(switched.saved.access_token)
    expect(switched.saved.account.id).not.toBe(initial.saved.account.id)
    await logoutCommand("Youve been logged out of Wizard.")

    const pending = await cli(); runs.push(pending)
    await logoutCommand("Youve been logged out of Wizard.")
    await page.goto(pending.url)
    await expect(page.locator("p[role=alert]")).toContainText(/expired|cancelled/)
    pending.processHandle.stdin.write(switched.code + "\n")
    await expect.poll(() => pending.output().includes("cancelled")).toBeTruthy()
    expect(JSON.parse(storage("snapshot"))).toBe(null)
  } finally {
    // Revoke only credentials issued by this test, even after an assertion failure.
    for (const token of tokens) await page.request.delete("/api/account/credential", {headers:{Authorization:"Bearer " + token}})
    for (const run of runs.reverse()) await cleanup(run)
  }
})
