"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { LayoutDashboard, GitBranch, UserRound, LogOut, Terminal, ArrowUpRight } from "lucide-react"
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "./sidebar"
export function App1Sidebar({ onSignOut, busy, signedIn }: { onSignOut: () => void; busy: boolean; signedIn: boolean }) {
  const path = usePathname()
  return <Sidebar collapsible="icon">
    <SidebarHeader className="h-16 justify-center border-b px-4"><Link href="/dashboard" className="flex items-center gap-2.5 overflow-hidden"><span className="grid size-8 shrink-0 place-items-center rounded-lg bg-foreground text-background"><Terminal size={17} /></span><span className="text-lg font-semibold tracking-tight group-data-[collapsible=icon]:hidden">Wizard</span></Link></SidebarHeader>
    <SidebarContent><SidebarGroup className="px-3 py-5"><SidebarGroupLabel>Workspace</SidebarGroupLabel><SidebarMenu className="gap-1">
      <SidebarMenuItem><SidebarMenuButton asChild isActive={path === "/dashboard"} tooltip="Overview"><Link href="/dashboard"><LayoutDashboard /><span>Overview</span></Link></SidebarMenuButton></SidebarMenuItem>
      <SidebarMenuItem><SidebarMenuButton asChild isActive={path.startsWith("/investigations/")} tooltip="Investigations"><Link href="/dashboard#investigations"><GitBranch /><span>Investigations</span></Link></SidebarMenuButton></SidebarMenuItem>
      <SidebarMenuItem><SidebarMenuButton asChild isActive={path === "/profile"} tooltip="Profile"><Link href="/profile"><UserRound /><span>Profile</span></Link></SidebarMenuButton></SidebarMenuItem>
    </SidebarMenu></SidebarGroup></SidebarContent>
    <SidebarFooter className="border-t p-3"><SidebarMenu><SidebarMenuItem><SidebarMenuButton asChild tooltip="Wizard website"><Link href="/"><ArrowUpRight /><span>Wizard website</span></Link></SidebarMenuButton></SidebarMenuItem>
      {signedIn && <SidebarMenuItem><SidebarMenuButton onClick={onSignOut} disabled={busy} tooltip="Sign out"><LogOut /><span>{busy ? "Signing out..." : "Sign out"}</span></SidebarMenuButton></SidebarMenuItem>}
    </SidebarMenu></SidebarFooter>
  </Sidebar>
}
