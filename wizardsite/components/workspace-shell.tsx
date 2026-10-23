"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Bell, Search } from "lucide-react"
import { useState, type ReactNode } from "react"
import { useAccount } from "./account-session"
import { Button } from "./ui/button"
import { Avatar, AvatarFallback } from "./ui/avatar"
import { App1Sidebar } from "./ui/app-1-utils/app-1-sidebar"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "./ui/app-1-utils/sidebar"
export function WorkspaceShell({ children }: { children: ReactNode }) {
  const path = usePathname()
  const { session, error, loading, refresh, signOut } = useAccount()
  const [logoutError,setLogoutError] = useState("")
  const [busy,setBusy] = useState(false)
  const account = session?.account
  const initials = (account?.full_name || "").split(/\s+/).map(word=>word[0]).slice(0,2).join("").toUpperCase()
  async function logout() { setBusy(true); setLogoutError(""); try { await signOut() } catch(e) { setLogoutError(e instanceof Error ? e.message : "Could not sign out.") } finally { setBusy(false) } }
  return <div className="wizard-workspace dark"><SidebarProvider><App1Sidebar onSignOut={logout} busy={busy} signedIn={!!account} /><SidebarInset className="min-w-0">
    <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center gap-3 border-b bg-background px-4 sm:px-6"><SidebarTrigger aria-label="Toggle navigation" /><h1 className="truncate text-lg font-semibold">{path === "/dashboard" ? account ? `Welcome back, ${account.full_name.split(" ")[0]}` : "Your workspace" : path === "/profile" ? "Your profile" : "Project architecture"}</h1>
      {account && <div className="ml-auto flex items-center gap-1"><Button asChild variant="ghost" size="icon" aria-label="Search projects"><Link href="/dashboard#investigations" onClick={()=>setTimeout(()=>document.querySelector<HTMLInputElement>("[data-dashboard-search]")?.focus(),0)}><Search /></Link></Button><Button asChild variant="ghost" size="icon" aria-label="Recent activity"><Link href="/dashboard#activity"><Bell /></Link></Button><Link href="/profile" aria-label="Open your profile" className="ml-1 rounded-full focus-visible:outline-2 focus-visible:outline-offset-2"><Avatar className="size-8"><AvatarFallback className="text-xs">{initials}</AvatarFallback></Avatar></Link></div>}
    </header>
    {logoutError && <p role="alert" className="px-6 pt-4 text-sm text-destructive">{logoutError}</p>}
    {error ? <div className="workspace-state" role="alert"><h1>Could not load your workspace</h1><p>{error}</p><Button onClick={()=>void refresh()}>Retry connection</Button></div>
      : !session ? <div className="workspace-state" role="status"><p>Loading your workspace...</p></div>
      : !account ? <div className="workspace-state"><h1>Sign in to your workspace</h1><p>Run <code>/login</code> in Wizard to connect your terminal, or sign in to see your saved investigations.</p><Button asChild><Link href="/login.html">Sign in</Link></Button></div>
      : <div key={account.id} className="workspace-content" aria-busy={loading}>{children}</div>}
  </SidebarInset></SidebarProvider></div>
}
