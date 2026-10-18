"use client"

import { useEffect, useRef, useState } from "react"
import { CircleCheck, Terminal } from "lucide-react"
import { CliHeading, cliPrimaryLink, cliSecondaryLink } from "./cli-authorization"

type Account = { id: string; email: string; full_name: string }
type Context = { csrf: string; account: Account | null; cli_pending: boolean }
type Status = { request_id: string; state: "pending" | "approved" | "exchanged"; expires_at?: string; code?: string; code_expires_at?: string }
type View = { context: Context; status?: Status }
class ApiError extends Error {
  constructor(public status: number, message: string, public retry = 2) { super(message) }
}
async function api(path: string, csrf?: string, body?: object): Promise<any> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 8000)
  try {
    const response = await fetch(path, {
      method: body ? "POST" : "GET", credentials: "same-origin", cache: "no-store",
      headers: body ? { "Content-Type": "application/json", "X-CSRF-Token": csrf || "" } : {},
      body: body ? JSON.stringify(body) : undefined, signal: controller.signal,
    })
    const data = await response.json().catch(() => { throw new Error("Invalid server response. Retry or restart /login.") })
    if (!response.ok) {
      const message = response.status === 429 ? "Too many attempts. Wait before retrying."
        : response.status === 410 ? "This authorization expired or was cancelled. Start a new /login."
        : response.status === 401 ? "Sign in again to continue this request."
        : response.status === 409 && data.error === "already_exchanged" ? "The CLI already exchanged this request. Check the original terminal."
        : "Authorization unavailable (" + String(data.error || response.status).replace(/[^a-z_0-9]/g, "") + "). Retry or start a new /login."
      throw new ApiError(response.status, message, Math.min(120, Math.max(2, Number(response.headers.get("Retry-After")) || 2)))
    }
    return data
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new Error("Cannot reach the account service or its response was invalid. Retry; no success is assumed.")
  } finally { clearTimeout(timer) }
}
async function context(): Promise<Context> {
  const value = await api("/api/auth/context")
  if (!/^[a-f0-9]{64}$/.test(value.csrf) || typeof value.cli_pending !== "boolean" ||
      (value.account !== null && (!value.account || typeof value.account.email !== "string" ||
      typeof value.account.id !== "string" || typeof value.account.full_name !== "string"))) throw new Error("Invalid session response.")
  return value
}
async function status(): Promise<Status> {
  return checkedStatus(await api("/api/cli/browser"))
}
function checkedStatus(value: any): Status {
  if (!/^[a-f0-9-]{36}$/.test(value.request_id) || !["pending", "approved", "exchanged"].includes(value.state)) throw new Error("Invalid authorization state.")
  if (value.state !== "exchanged" && !Number.isFinite(Date.parse(value.expires_at))) throw new Error("Invalid request expiration.")
  if (value.state === "approved" && (!/^[A-F0-9]{12}$/.test(value.code) ||
      !Number.isFinite(Date.parse(value.code_expires_at)))) throw new Error("Invalid authorization code response.")
  return value
}
export default function CliFlow({ page }: { page: "authorize" | "connect" | "complete" }) {
  const [view, setView] = useState<View>()
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [cancelled, setCancelled] = useState(false)
  const [expired, setExpired] = useState(false)
  const [copied, setCopied] = useState(false)
  const [now, setNow] = useState(Date.now())
  const [retry, setRetry] = useState(0)
  // One initialization promise per mount prevents StrictMode duplicate binding.
  const initialization = useRef<Promise<View>>()
  useEffect(() => {
    let alive = true
    setError("")
    if (!initialization.current) initialization.current = (async () => {
      const ctx = await context()
      if (page === "authorize" && window.location.hash) {
        const fragment = new URLSearchParams(window.location.hash.slice(1))
        if (Array.from(fragment.keys()).length !== 2 || fragment.getAll("request_id").length !== 1 ||
            fragment.getAll("ticket").length !== 1 ||
            !/^[a-f0-9-]{36}$/.test(fragment.get("request_id") || "") ||
            !/^[A-Za-z0-9_-]{43}$/.test(fragment.get("ticket") || "")) throw new Error("Invalid authorization URL. Copy the complete URL from a new CLI /login.")
        const binding = await api("/api/cli/browser/bind", ctx.csrf, {
          request_id: fragment.get("request_id"), ticket: fragment.get("ticket"),
        })
        if (binding.request_id !== fragment.get("request_id") ||
            !["/cli/connect", "/login.html?returnTo=%2Fcli%2Fconnect"].includes(binding.continue_to)) throw new Error("Invalid binding response.")
        window.history.replaceState(null, "", "/cli/authorize")
        ctx.cli_pending = true
      }
      if (!ctx.cli_pending) throw new Error("No pending CLI request. Start /login in Wizard and open its complete authorization URL.")
      if (!ctx.account) {
        if (page !== "authorize") window.location.replace("/login.html?returnTo=%2Fcli%2Fconnect")
        return { context: ctx }
      }
      return { context: ctx, status: await status() }
    })()
    initialization.current.then(result => { if (alive) { setView(result); setExpired(false) } })
      .catch(e => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [page, retry])
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  const pollingRequestId = view?.status?.request_id
  const pollingState = view?.status?.state
  useEffect(() => {
    if (!pollingRequestId || cancelled || expired || pollingState === "exchanged") return
    let active = true
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      let delay = 2000
      try {
        const next = await status()
        if (!active) return
        if (next.request_id !== pollingRequestId) throw new Error("The browser selected a different CLI request. Reload and check the request ID.")
        setView(old => old ? { ...old, status: next } : old)
        setError("")
        if (next.state === "exchanged") {
          if (page !== "complete") window.location.replace("/cli/complete")
          return
        }
        const end = Date.parse(next.code_expires_at || next.expires_at || "")
        if (Date.now() >= end) { setExpired(true); setError("Authorization expired. Start a fresh /login."); return }
      } catch (e) {
        if (!active) return
        const failure = e as ApiError
        setError(failure.message)
        if (failure.status && ![429, 502, 503, 504].includes(failure.status)) { setExpired(true); return }
        delay = 1000 * (failure.retry || 3)
      }
      if (active) timer = setTimeout(poll, delay)
    }
    timer = setTimeout(poll, 2000)
    return () => { active = false; clearTimeout(timer) }
  }, [pollingRequestId, pollingState, page, cancelled, expired])
  async function approve() {
    if (!view || busy) return
    setBusy(true); setError("")
    try {
      const fresh = await context()
      if (fresh.account?.id !== view.context.account?.id || !fresh.cli_pending) throw new Error("Account or pending request changed. Reload and check before approving.")
      const current = await status()
      if (current.request_id !== view.status?.request_id) throw new Error("Pending request changed. Reload and check before approving.")
      const approved = checkedStatus(await api("/api/cli/browser/approve", fresh.csrf, {}))
      if (approved.request_id !== current.request_id) throw new Error("Pending request changed.")
      setView({ context: fresh, status: approved })
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  async function cancel() {
    if (busy) return
    setBusy(true); setError("")
    try {
      const fresh = await context()
      const result = await api("/api/cli/browser/cancel", fresh.csrf, {})
      if (result.state !== "cancelled" || (view?.status && result.request_id !== view.status.request_id)) throw new Error("Cancellation was not confirmed.")
      setCancelled(true)
    } catch (e) { setError("Cancellation was not confirmed. " + (e as Error).message) }
    finally { setBusy(false) }
  }
  const state = view?.status
  const end = state?.code_expires_at || state?.expires_at
  const seconds = end ? Math.max(0, Math.ceil((Date.parse(end) - now) / 1000)) : 0
  if (cancelled) return <><CliHeading title="CLI connection cancelled">The backend confirmed cancellation. Start a new /login when you are ready.</CliHeading><a href="/" className={cliPrimaryLink}>Return to website</a></>
  if (page === "complete" && state?.state === "exchanged") return <section aria-labelledby="completion-heading">
    <CircleCheck aria-hidden="true" className="mt-6 h-12 w-12 text-[#7FC6E6]" />
    <CliHeading title="Ready to return to Wizard CLI">The backend confirmed your code was exchanged. Check your original terminal for credential verification and secure-storage success.</CliHeading>
    <a href="/" className={cliPrimaryLink + " mt-8"}>Return to website</a>
  </section>
  return <>
    <CliHeading title={page === "authorize" ? "Your Wizard account. Your terminal." : "Connect your Wizard CLI"}>
      {page === "authorize" ? "Connect your terminal using your existing Wizard account. Review and approve the connection before a code is issued." : "Confirm your account, then enter the one-time code in the terminal that started /login."}
    </CliHeading>
    {error && <p role="alert" className="mt-6 border-l-2 border-[#7FC6E6] pl-4 text-[#EAF7FB]">{error}</p>}
    {!view && !error && <p role="status" className="mt-8">Checking your sessionÃ¢â‚¬Â¦</p>}
    {view?.context.account && <div className="mt-6 max-w-xl text-[#B7CEDD]">
      <p>Account: <strong className="text-[#EAF7FB]">{view.context.account.full_name}</strong> ({view.context.account.email})</p>
      {state && <p className="mt-2 break-all font-mono text-xs">CLI request: {state.request_id}</p>}
    </div>}
    {page === "authorize" && view && <a href={view.context.account ? "/cli/connect" : "/login.html?returnTo=%2Fcli%2Fconnect"} className={cliPrimaryLink + " mt-8"}>Continue{!view.context.account && " to sign in"}</a>}
    {page !== "authorize" && state?.state === "pending" && !expired && seconds > 0 &&
      <button onClick={approve} disabled={busy} className={cliPrimaryLink + " mt-8"}>Authorize this account for this terminal</button>}
    {state?.state === "approved" && !expired && seconds > 0 && <section aria-labelledby="code-heading" className="mt-8 max-w-xl rounded-2xl border border-[#7FC6E6]/25 bg-[#123A6B]/40 p-6 sm:p-8">
      <div className="flex items-center gap-3 text-[#7FC6E6]"><Terminal aria-hidden="true" className="h-5 w-5" /><h2 id="code-heading" className="font-mono text-xs uppercase tracking-[.15em]">Authorization code</h2></div>
      <div data-testid="authorization-code" className="mt-5 rounded-xl border border-dashed border-[#7FC6E6]/40 bg-[#071F3A] px-4 py-6 text-center font-mono text-2xl tracking-widest">{state.code}</div>
      <button className={cliSecondaryLink + " mt-4"} onClick={async () => {
        try { await navigator.clipboard.writeText(state.code!); setCopied(true) }
        catch { setError("Copy unavailable. Select the code and copy it manually.") }
      }}>{copied ? "Copied" : "Copy code"}</button>
      <p className="mt-5 text-sm text-[#B7CEDD]">Paste this code into the original Wizard terminal. Keep this page open for confirmation.</p>
      <p className="mt-4 border-t border-white/10 pt-4 text-sm text-[#B7CEDD]">Expires at {new Date(end!).toLocaleString()} Ã‚Â· {seconds}s remaining</p>
    </section>}
    {state?.state === "exchanged" && page !== "complete" && <a href="/cli/complete" className={cliPrimaryLink + " mt-8"}>View confirmed completion</a>}
    <div className="mt-8 flex flex-wrap gap-3">
      {view && state?.state !== "exchanged" && <button onClick={cancel} disabled={busy} className={cliSecondaryLink}>Cancel connection</button>}
      {error && <button className={cliSecondaryLink} onClick={() => { initialization.current = undefined; setRetry(n => n + 1) }}>Retry session check</button>}
      {!view && error && <a href="/" className={cliSecondaryLink}>Return to website</a>}
    </div>
    {busy && <p role="status" className="mt-4">Waiting for account serviceÃ¢â‚¬Â¦</p>}
  </>
}
