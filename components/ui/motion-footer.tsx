"use client"

import { ArrowUpRight, Check, ExternalLink } from "lucide-react"

const links = [
  { label: "Wizard website", href: "https://wizardagents.vercel.app" },
  { label: "Documentation", href: "https://wizardagents.vercel.app" },
  { label: "Coming soon", href: "https://wizardagents.vercel.app" },
]

export function CinematicFooter() {
  return (
    <footer id="download" className="relative isolate overflow-hidden border-t border-white/10 bg-[#061b4f] px-6 py-20 text-white sm:px-10 sm:py-28">
      <div className="pointer-events-none absolute inset-0 opacity-80" style={{ background: "radial-gradient(65% 70% at 50% 15%, rgba(76,145,255,.72), transparent 68%), linear-gradient(180deg, #0a3d9d 0%, #061b4f 72%)" }} />
      <div className="pointer-events-none absolute inset-0 opacity-15" style={{ backgroundImage: "linear-gradient(rgba(255,255,255,.18) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.18) 1px, transparent 1px)", backgroundSize: "72px 72px", maskImage: "linear-gradient(to bottom, black, transparent 80%)" }} />
      <div className="relative mx-auto flex min-h-[70vh] w-full max-w-6xl flex-col justify-between gap-16">
        <div className="flex items-start justify-between gap-8">
          <p className="font-mono text-[10px] uppercase tracking-[.32em] text-blue-100/65">Wizard · agent runtime</p>
          <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1 font-mono text-[10px] text-blue-100/70">CLI + PLUGIN</span>
        </div>
        <div className="grid gap-12 lg:grid-cols-[1.2fr_.8fr] lg:items-end">
          <div>
            <p className="mb-5 max-w-xl text-sm leading-relaxed text-blue-100/70">A verification layer for AI-assisted software work. Inspect the change, run the evidence, and ship with a record of what actually happened.</p>
            <h2 className="max-w-4xl text-balance text-5xl font-semibold tracking-[-.06em] sm:text-7xl lg:text-8xl">Build with proof.</h2>
          </div>
          <div className="flex flex-col gap-3 lg:items-end">
            <p className="font-mono text-[10px] uppercase tracking-[.25em] text-blue-100/50">Available soon</p>
            <div className="flex items-center gap-3 rounded-full border border-white/20 bg-white/10 px-5 py-3 text-sm font-medium backdrop-blur">Coming soon <Check className="h-4 w-4 text-blue-200" /></div>
          </div>
        </div>
        <div className="grid gap-8 border-t border-white/15 pt-8 sm:grid-cols-3">
          {links.map((link) => <a key={link.label} href={link.href} target="_blank" rel="noreferrer" className="group flex items-center justify-between border-b border-white/10 pb-3 text-sm text-blue-100/70 transition-colors hover:text-white"><span>{link.label}</span><ArrowUpRight className="h-4 w-4 transition-transform group-hover:-translate-y-1 group-hover:translate-x-1" /></a>)}
        </div>
        <div className="flex flex-col gap-3 border-t border-white/10 pt-5 text-xs text-blue-100/45 sm:flex-row sm:items-center sm:justify-between"><span>© 2026 Wizard</span><a className="inline-flex items-center gap-2 hover:text-white" href="https://wizardagents.vercel.app" target="_blank" rel="noreferrer">wizardagents.vercel.app <ExternalLink className="h-3 w-3" /></a></div>
      </div>
    </footer>
  )
}

export default CinematicFooter
