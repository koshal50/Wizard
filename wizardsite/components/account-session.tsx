"use client"

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react"

export type BrowserAccount = { id: string; email: string; full_name: string }
type Session = { account: BrowserAccount | null; csrf: string; cli_pending: boolean }
type AccountState = { session?: Session; error: string; loading: boolean; refresh: () => Promise<void>; signOut: () => Promise<void> }
const AccountContext = createContext<AccountState | null>(null)

async function request(path: string, init?: RequestInit) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 8000)
  try {
    const response = await fetch(path, { ...init, credentials: "same-origin", cache: "no-store", signal: controller.signal })
    const value = await response.json().catch(() => { throw new Error("The account service returned an invalid response. Please retry.") })
    if (!response.ok) throw new Error("The account service is unavailable. Please retry.")
    return value
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw new Error("The account service took too long to respond. Please retry.")
    throw error
  } finally { clearTimeout(timer) }
}
async function readSession(): Promise<Session> {
  const value = await request("/api/auth/context")
  if (!/^[a-f0-9]{64}$/.test(value.csrf) || typeof value.cli_pending !== "boolean" ||
      (value.account !== null && (!value.account || typeof value.account.id !== "string" ||
       typeof value.account.email !== "string" || typeof value.account.full_name !== "string"))) {
    throw new Error("Your account session could not be verified. Please retry.")
  }
  return value
}
export function AccountProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>()
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const pending = useRef<Promise<void>>()
  const mounted = useRef(false)
  const generation = useRef(0)
  const refresh = useCallback(() => {
    if (pending.current) return pending.current
    const version = generation.current
    const work = (async () => {
      if (mounted.current) setLoading(true)
      try {
        const next = await readSession()
        if (mounted.current && generation.current === version) { setSession(next); setError("") }
      } catch (failure) {
        if (mounted.current && generation.current === version) { setSession(undefined); setError(failure instanceof Error ? failure.message : "Could not load your account.") }
      } finally { if (mounted.current && generation.current === version) setLoading(false) }
    })()
    pending.current = work
    void work.finally(() => { if (pending.current === work) pending.current = undefined })
    return work
  }, [])
  useEffect(() => {
    mounted.current = true
    void refresh()
    const focus = () => { if (document.visibilityState === "visible") void refresh() }
    window.addEventListener("focus", focus)
    document.addEventListener("visibilitychange", focus)
    return () => { mounted.current = false; window.removeEventListener("focus", focus); document.removeEventListener("visibilitychange", focus) }
  }, [refresh])
  const signOut = useCallback(async () => {
    generation.current += 1
    const current = await readSession()
    if (current.account && current.account.id !== session?.account?.id) {
      await refresh()
      throw new Error("The signed-in account changed. Review the account and try again.")
    }
    if (current.account) {
      const result = await request("/logout", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": current.csrf }, body: "{}" })
      if (result.signed_out !== true) throw new Error("Sign out was not confirmed. Please retry.")
    }
    const next = await readSession()
    if (next.account) throw new Error("Sign out was not confirmed. Please retry.")
    generation.current += 1
    if (mounted.current) { setSession(next); setError(""); setLoading(false) }
  }, [session?.account?.id, refresh])
  return <AccountContext.Provider value={{ session, error, loading, refresh, signOut }}>{children}</AccountContext.Provider>
}
export function useAccount() {
  const state = useContext(AccountContext)
  if (!state) throw new Error("AccountProvider is required")
  return state
}
