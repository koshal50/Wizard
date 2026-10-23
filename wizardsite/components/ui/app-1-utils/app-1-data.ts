"use client"
import { useEffect, useMemo, useState } from "react"
import type { ChartConfig } from "@/components/ui/chart"
export type SavedInvestigation = { id: string; title: string; repository_name: string; status: string; created_at: string }
export const app1ChartConfig = { saved: { label: "Saved", color: "#7eacaa" }, completed: { label: "Completed", color: "#b9a0ea" } } satisfies ChartConfig
export function useApp1Data() {
  const [rows, setRows] = useState<SavedInvestigation[]>()
  const [error, setError] = useState("")
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 10000)
    let alive = true
    setError(""); setRows(undefined)
    fetch("/api/investigations", { credentials: "same-origin", cache: "no-store", signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 401 ? "Your session expired. Sign in again." : "Could not load saved investigations.")
        const data = await response.json()
        if (!Array.isArray(data.investigations) || !data.investigations.every((r: SavedInvestigation) => r && typeof r.id === "string" && typeof r.title === "string" && typeof r.status === "string" && typeof r.repository_name === "string" && Number.isFinite(Date.parse(r.created_at)))) throw new Error("The investigation response could not be read.")
        if (alive) setRows(data.investigations)
      }).catch(e => { if (alive) setError(e.name === "AbortError" ? "The request took too long. Please retry." : e.message) })
      .finally(() => clearTimeout(timer))
    return () => { alive = false; clearTimeout(timer); controller.abort() }
  }, [revision])
  const projects = useMemo(() => {
    const groups = new Map<string, SavedInvestigation[]>()
    for (const row of rows || []) groups.set(row.repository_name, [...groups.get(row.repository_name) || [], row])
    return Array.from(groups, ([name, investigations]) => {
      const sorted = [...investigations].sort((a,b) => Date.parse(b.created_at)-Date.parse(a.created_at))
      return { name, latest: sorted[0], count: sorted.length, completed: sorted.filter(row => row.status === "completed").length }
    }).sort((a,b) => Date.parse(b.latest.created_at)-Date.parse(a.latest.created_at))
  }, [rows])
  const chart = useMemo(() => Array.from({ length: 8 }, (_, index) => {
    const start = new Date(); start.setHours(0,0,0,0); start.setDate(start.getDate() - (start.getDay()+6)%7 - (7-index)*7)
    const end = new Date(start); end.setDate(end.getDate()+7)
    const matching = (rows || []).filter(row => Date.parse(row.created_at) >= +start && Date.parse(row.created_at) < +end)
    return { week: start.toLocaleDateString(undefined, {month:"short",day:"numeric"}), saved: matching.length, completed: matching.filter(row => row.status === "completed").length }
  }), [rows])
  return { rows, projects, chart, error, reload: () => setRevision(value => value+1) }
}
