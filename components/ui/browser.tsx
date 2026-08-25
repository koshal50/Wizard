"use client"

import { useState } from "react"
import { ArrowLeft, ArrowRight, Lock, MoreHorizontal, Plus, RefreshCw, Search, X } from "lucide-react"
import { cn } from "@/lib/utils"

export function Browser({ className }: { className?: string }) {
  const [url, setUrl] = useState("https://wizard.run/verify")
  const [loading, setLoading] = useState(false)
  const run = () => { setLoading(true); window.setTimeout(() => setLoading(false), 900) }
  return <div className={cn("flex h-full flex-col overflow-hidden rounded-xl border border-slate-700 bg-[#101827] text-slate-200 shadow-2xl", className)}>
    <div className="flex items-center gap-2 border-b border-slate-700 bg-[#182335] px-3 py-2 text-[9px]"><span className="h-2 w-2 rounded-full bg-red-400"/><span className="h-2 w-2 rounded-full bg-amber-300"/><span className="h-2 w-2 rounded-full bg-emerald-400"/><div className="ml-3 flex min-w-0 flex-1 items-center gap-2 rounded-md bg-[#0d1625] px-2 py-1"><Lock className="h-3 w-3 text-emerald-400"/><input aria-label="Address" value={url} onChange={e => setUrl(e.target.value)} onKeyDown={e => e.key === "Enter" && run()} className="min-w-0 flex-1 bg-transparent outline-none"/><Search className="h-3 w-3 text-slate-500"/></div><Plus className="h-3 w-3"/><MoreHorizontal className="h-3 w-3"/></div>
    <div className="flex items-center gap-2 border-b border-slate-800 px-3 py-1.5 text-slate-500"><ArrowLeft className="h-3 w-3"/><ArrowRight className="h-3 w-3"/><RefreshCw className={cn("h-3 w-3", loading && "animate-spin")} onClick={run}/><span className="ml-2 text-[8px]">Wizard Browser Agent</span></div>
    <div className="relative flex flex-1 items-center justify-center bg-[#f8fafc] p-4 text-slate-900"><div className="w-full max-w-[260px] rounded-lg border border-slate-200 bg-white p-4 shadow-sm"><div className="mb-3 text-[8px] font-bold uppercase tracking-[.2em] text-blue-600">Live verification</div><h3 className="text-base font-bold">Your build is ready.</h3><p className="mt-1 text-[9px] text-slate-500">Wizard clicked the CTA and captured the evidence.</p><button onClick={run} className="mt-4 rounded-md bg-blue-600 px-3 py-1.5 text-[9px] font-semibold text-white">{loading ? "Checking…" : "Run verification"}</button><div className="mt-4 flex items-center gap-2 text-[8px] text-emerald-600"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500"/>Screenshot captured · PASS</div></div><span className="absolute bottom-2 right-3 text-[7px] text-slate-400"><X className="inline h-2 w-2"/> browser session</span></div>
  </div>
}
