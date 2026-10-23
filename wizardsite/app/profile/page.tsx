"use client"
import { useState } from "react"
import { Terminal, ArrowUpRight } from "lucide-react"
import Link from "next/link"
import { useAccount } from "@/components/account-session"
import { WorkspaceShell } from "@/components/workspace-shell"
import { Button } from "@/components/ui/button"
export default function Profile() {
  const { session, signOut } = useAccount()
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  async function logout() {
    setBusy(true); setError("")
    try { await signOut() } catch (failure) { setError(failure instanceof Error ? failure.message : "Could not sign out.") }
    finally { setBusy(false) }
  }
  return <WorkspaceShell><section className="workspace-page profile-page">
    <div className="workspace-page-heading"><div><p className="workspace-eyebrow">Your account</p><h1>Profile</h1><p>The account connected to your browser.</p></div></div>
    <section className="profile-section"><h2>Account details</h2><dl><div><dt>Name</dt><dd>{session?.account?.full_name}</dd></div><div><dt>Email</dt><dd>{session?.account?.email}</dd></div></dl></section>
    <section className="profile-section"><h2>Your terminal</h2><p>CLI access is authorized separately from this browser session. To connect a terminal, run <code>/login</code> in Wizard.</p><div className="profile-command"><Terminal size={16} /><code>/login</code></div><p>Local investigations appear here only after you choose to upload them.</p></section>
    <section className="profile-section"><h2>Browser session</h2><p>Signing out ends this website session. It does not revoke an already connected terminal.</p><Button variant="outline" onClick={logout} disabled={busy}>{busy ? "Signing out..." : "Sign out of website"}</Button>{error && <p role="alert" className="workspace-error">{error}</p>}</section>
    <Link href="/privacy" className="workspace-text-link">How your data is handled <ArrowUpRight size={14} /></Link>
  </section></WorkspaceShell>
}
