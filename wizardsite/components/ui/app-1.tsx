"use client"
// Adapted from the App1 component supplied by the user (21st / shadcnstore).
// Layout and primitives retained; demo metrics and identities replaced by real data.
import Link from "next/link"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { BarChart3, GitBranch, FileText, CircleCheck, ArrowUpRight } from "lucide-react"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { Progress } from "@/components/ui/progress"
import { app1ChartConfig, useApp1Data } from "./app-1-utils/app-1-data"
import { WorkspaceShell } from "@/components/workspace-shell"
import { useAccount } from "@/components/account-session"
import { useState } from "react"

function DashboardContent() {
  const { rows, projects, chart, error, reload } = useApp1Data()
  const { session } = useAccount()
  const [query, setQuery] = useState("")
  const completed = rows?.filter(row => row.status === "completed").length || 0
  const initials = (session?.account?.full_name || "").split(/\s+/).map(word => word[0]).slice(0,2).join("").toUpperCase()
  const stats = [
    { label: "Projects", value: rows ? projects.length : null, hint: "With saved investigations", icon: GitBranch },
    { label: "Investigations", value: rows?.length, hint: "Uploaded from Wizard CLI", icon: FileText },
    { label: "Completed", value: rows ? completed : null, hint: "Saved results marked complete", icon: CircleCheck },
    { label: "Completion rate", value: rows ? (rows.length ? Math.round(completed / rows.length * 100) + "%" : "N/A") : null, hint: "Of saved investigations", icon: BarChart3 },
  ]
  const visibleProjects = projects.filter(project => project.name.toLowerCase().includes(query.toLowerCase()))
  const recent = [...rows || []].sort((a,b) => Date.parse(b.created_at)-Date.parse(a.created_at)).slice(0,5)
  if (error) return <div className="p-6"><Card><CardHeader><CardTitle>Could not load your investigations</CardTitle><CardDescription role="alert">{error}</CardDescription></CardHeader><CardContent><Button onClick={reload}>Retry</Button></CardContent></Card></div>
  return <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{stats.map(stat => <Card key={stat.label}><CardHeader className="flex flex-row items-center justify-between"><CardTitle className="text-sm font-medium">{stat.label}</CardTitle><stat.icon aria-hidden className="size-5 text-muted-foreground" /></CardHeader><CardContent><p className="text-2xl font-semibold tabular-nums">{stat.value ?? "..."}</p><p className="text-xs text-muted-foreground">{stat.hint}</p></CardContent></Card>)}</div>
    <Card><CardHeader><CardTitle>Investigation activity</CardTitle><CardDescription>Saved and completed results over the last eight weeks</CardDescription></CardHeader><CardContent>
      {!rows ? <div className="grid h-64 place-items-center text-sm text-muted-foreground" role="status">Loading activity...</div> : !rows.length ? <div className="grid h-64 place-content-center gap-2 text-center"><p className="font-medium">Your first investigation starts in the terminal</p><p className="text-sm text-muted-foreground">Run a check in Wizard, then choose to upload the result.</p></div> : <ChartContainer config={app1ChartConfig} className="h-64 w-full">
        <AreaChart data={chart} margin={{ left: 4, right: 4, top: 8 }} accessibilityLayer><defs><linearGradient id="app1Completed" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--color-completed)" stopOpacity={.18} /><stop offset="100%" stopColor="var(--color-completed)" stopOpacity={.02} /></linearGradient></defs><CartesianGrid vertical={false} strokeDasharray="3 3" /><XAxis dataKey="week" tickLine={false} axisLine={false} tickMargin={8} /><YAxis tickLine={false} axisLine={false} width={32} allowDecimals={false} /><ChartTooltip content={<ChartTooltipContent />} /><ChartLegend content={<ChartLegendContent />} /><Area dataKey="saved" type="monotone" stroke="var(--color-saved)" strokeDasharray="4 4" fill="none" strokeWidth={2} /><Area dataKey="completed" type="monotone" stroke="var(--color-completed)" fill="url(#app1Completed)" strokeWidth={2} /></AreaChart>
      </ChartContainer>}
    </CardContent></Card>
    <div className="grid gap-6 lg:grid-cols-2">
      <Card id="investigations" className="scroll-mt-20"><CardHeader><CardTitle>Your projects</CardTitle><CardDescription>Saved investigations grouped by repository</CardDescription></CardHeader><CardContent className="flex flex-col gap-5">
        <input data-dashboard-search type="search" value={query} onChange={event => setQuery(event.target.value)} aria-label="Search projects" placeholder="Search projects..." className="h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        {!rows && <p className="text-sm text-muted-foreground" role="status">Loading projects...</p>}
        {rows && !visibleProjects.length && <p className="text-sm text-muted-foreground">{query ? "No projects match this search." : "No projects uploaded yet."}</p>}
        {visibleProjects.map(project => <div key={project.name} className="flex flex-col gap-2"><div className="flex items-center justify-between gap-2"><Link href={`/investigations/${project.latest.id}`} className="truncate text-sm font-medium hover:underline">{project.name}</Link><Badge variant={project.latest.status === "completed" ? "secondary" : "outline"}>{project.latest.status}</Badge></div><p className="text-xs text-muted-foreground">{project.count} saved investigations</p><div className="flex items-center gap-3"><Progress value={project.completed/project.count*100} aria-label={`${project.name}: completed saved investigations`} className="h-2" /><span className="shrink-0 text-xs text-muted-foreground tabular-nums">{project.completed}/{project.count}</span></div><div className="flex items-center justify-between gap-2 text-xs text-muted-foreground"><span>Completed investigations</span><Link href={`/investigations/${project.latest.id}`} className="inline-flex items-center gap-1 text-foreground hover:underline">Open latest <ArrowUpRight size={12} /></Link></div></div>)}
      </CardContent></Card>
      <Card id="activity" className="scroll-mt-20"><CardHeader><CardTitle>Recent activity</CardTitle><CardDescription>Your latest saved investigation results</CardDescription></CardHeader><CardContent><ol className="flex flex-col gap-4">
        {!rows && <li className="text-sm text-muted-foreground" role="status">Loading activity...</li>}
        {rows && !recent.length && <li className="text-sm text-muted-foreground">Your saved investigations will appear here.</li>}
        {recent.map(entry => <li key={entry.id} className="flex items-start gap-3"><Avatar className="size-8"><AvatarFallback className="text-xs">{initials}</AvatarFallback></Avatar><div className="min-w-0 flex-1"><p className="text-sm leading-snug"><span className="font-medium">{session?.account?.full_name}</span>{" "}<span className="text-muted-foreground">saved </span><Link href={`/investigations/${entry.id}`} className="font-medium hover:underline">{entry.repository_name}</Link></p><p className="mt-1 text-xs text-muted-foreground"><time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time></p></div></li>)}
      </ol></CardContent></Card>
    </div>
  </div>
}
export function App1() { return <WorkspaceShell><DashboardContent /></WorkspaceShell> }
export default App1
