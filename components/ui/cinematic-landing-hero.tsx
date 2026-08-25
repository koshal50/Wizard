"use client"

import React, { useEffect, useRef, useState } from "react"
import { gsap } from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { cn } from "@/lib/utils"
import { Browser } from "@/components/ui/browser"

gsap.registerPlugin(ScrollTrigger)

export function SafeMeshGradient({ className }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn("bg-[linear-gradient(135deg,#2452F1_0%,#163DB9_48%,#022474_100%)]", className)} />
}

const stages = ["VS Code", "Terminal", "Repository", "Browser", "Report"]
function Bar({ children }: { children: React.ReactNode }) { return <div className="window-bar"><i /><i /><i /><span>{children}</span></div> }

function Workspace() { return <div data-screen-panel className="screen-panel screen-code"><Bar>wizard-repo / VS Code <span className="live-dot">LIVE</span></Bar><div className="ide-body"><div className="file-tree"><b>EXPLORER</b><span>⌄ wizard-repo</span><em className="activity-file">◇ app/</em><em className="activity-file activity-delay-1">◇ components/</em><em>◇ package.json</em><em>◇ README.md</em></div><pre className="code-stream"><code><span className="typing-caret" aria-hidden="true" /> <span className="pink">import</span> {'{'} verify {'}'} <span className="pink">from</span> <span className="green">&quot;@wizard/agent&quot;</span>{"\n\n"}<span className="blue">export async function</span> run() {'{'}{"\n"}  <span className="blue">const</span> evidence = <span className="pink">await</span> verify({'{'}{"\n"}    target: <span className="green">&quot;localhost:3000&quot;</span>,{"\n"}    mode: <span className="green">&quot;deep&quot;</span>{"\n"}  {'}'}){"\n"}{'}'}</code></pre></div></div> }
function Terminal() { return <div data-screen-panel className="screen-panel screen-terminal"><Bar>terminal — wizard session</Bar><div className="crt-scanlines" aria-hidden="true" /><div className="terminal-copy"><p><span className="prompt">wizard@repo</span> ~/wizard-repo $ wizard inspect .</p><p className="dim">→ Reading repository structure</p><p className="dim">→ Checking package.json and routes</p><p className="dim">→ Starting development server</p><p><span className="prompt">wizard@repo</span> $ wizard verify --browser</p><p className="cursor-line">▋</p></div></div> }
function Repository() { const files = ["app/page.tsx", "components/hero.tsx", "components/ui/", "lib/utils.ts", "package.json"]; return <div data-screen-panel className="screen-panel screen-repo"><Bar>agent activity / repository map</Bar><div className="repo-map"><div className="repo-column"><b>REPOSITORY STRUCTURE</b>{files.map(file => <div className="repo-file" key={file}>◇ {file}</div>)}</div><div className="agent-log"><p>Wizard is reading <strong>components/ui/</strong></p><p className="success">✓ 18 files mapped</p><p className="success">✓ No missing imports</p></div></div></div> }
function BrowserPanel() { return <div data-screen-panel className="screen-panel screen-browser"><Browser className="h-full rounded-none border-0 shadow-none" /><span className="browser-agent-cursor" aria-hidden="true"><span /></span></div> }
function Report() { return <div data-screen-panel className="screen-panel screen-report"><Bar>wizard / final verification report</Bar><div className="report-copy"><div className="report-mark">✓</div><div><span className="muted">FINAL VERIFICATION</span><h3>Ship with evidence.</h3><p>All critical paths passed. The repository is ready for review.</p></div></div><div className="report-stats"><span><b>05</b> stages</span><span><b>18</b> files</span><span><b>03</b> captures</span><strong>PASS</strong></div></div> }

export function CinematicHero({ className }: { className?: string }) {
  const root = useRef<HTMLElement>(null)
  const laptop = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(0)
  useEffect(() => {
    const scope = root.current
    if (!scope) return
    const ctx = gsap.context(() => {
      const card = scope.querySelector<HTMLElement>("[data-scene-card]")
      const tabs = gsap.utils.toArray<HTMLElement>("[data-stage-tab]")
      const panels = gsap.utils.toArray<HTMLElement>("[data-screen-panel]")
      const underline = scope.querySelector<HTMLElement>("[data-tab-underline]")
      if (!card || panels.length !== stages.length) return
      gsap.set(card, { scale: 1, borderRadius: 0, force3D: true })
      gsap.set(panels, { display: "none", opacity: 1, x: 0, y: 0, scale: 1, force3D: true })
      gsap.set(panels[0], { display: "block" })
      const setStage = (index: number) => {
        panels.forEach((panel, i) => { gsap.set(panel, { display: i === index ? "block" : "none", x: 0, y: 0, scale: 1 }) })
        tabs.forEach((tab, i) => gsap.set(tab, { color: i === index ? "#fff" : "#8ba2c8" }))
        if (underline && tabs[index]) gsap.set(underline, { x: tabs[index].offsetLeft, width: tabs[index].offsetWidth })
      }
      setStage(0)
      const trigger = ScrollTrigger.create({
        trigger: scope, start: "top top", end: "bottom bottom", scrub: 1.8, invalidateOnRefresh: true,
        onUpdate: self => {
          const progress = self.progress
          const index = Math.min(stages.length - 1, Math.floor(progress * stages.length))
          if (index !== active) setActive(index)
          setStage(index)
          const expansion = progress < 0.14 ? progress / 0.14 : progress > 0.88 ? (1 - progress) / 0.12 : 1
          gsap.set(card, { scale: 0.84 + expansion * 0.16, borderRadius: 28 * (1 - expansion), force3D: true })
          const current = panels[index]
          if (current) gsap.set(current, { y: Math.sin(progress * Math.PI * 5) * -3, scale: 1 + Math.sin(progress * Math.PI * 3) * 0.006 })
        },
      })
      return () => trigger.kill()
    }, scope)
    return () => ctx.revert()
  }, [])
  useEffect(() => {
    const move = (event: MouseEvent) => { if (!laptop.current || window.matchMedia("(prefers-reduced-motion: reduce), (pointer: coarse)").matches) return; gsap.set(laptop.current, { rotationY: (event.clientX / innerWidth - 0.5) * 1.2, rotationX: -(event.clientY / innerHeight - 0.5) * 0.8, force3D: true }) }
    addEventListener("mousemove", move, { passive: true }); return () => removeEventListener("mousemove", move)
  }, [])
  return <section ref={root} className={cn("relative z-10 min-h-[7200px] w-full overflow-visible bg-transparent font-sans", className)}><div className="sticky top-0 flex min-h-screen w-full items-center justify-center overflow-hidden"><div data-scene-card className="scene-card relative flex min-h-screen w-full items-center justify-center overflow-hidden border-0 bg-gradient-to-br from-[#2452F1] via-[#163DB9] to-[#022474] text-white" style={{ perspective: 1500, willChange: "transform", contain: "layout paint" }}><SafeMeshGradient speed={0.3} colors={["#2452F1", "#022474", "#163DB9", "#0B1D99"]} distortion={0.7} swirl={0.12} grainMixer={0} grainOverlay={0} className="absolute inset-0 h-full w-full" /><div className="absolute inset-0 bg-[#022474]/20" /><div className="relative z-20 flex w-full max-w-[1440px] flex-col items-center gap-10 px-5 py-20 lg:flex-row lg:gap-16 lg:px-16"><div data-scene-copy className="w-full max-w-[350px] shrink-0 lg:mb-0"><p className="mb-3 font-mono text-[10px] uppercase tracking-[.3em] text-blue-100/70">Wizard investigation</p><h2 className="text-balance text-3xl font-semibold leading-[1.05] tracking-tight sm:text-4xl lg:text-5xl">AI writes the code. Wizard checks the reality.</h2><p className="mt-5 text-sm leading-relaxed text-blue-50/80 sm:text-base">Watch an agent read, execute, browse, and verify the work.</p></div><div ref={laptop} className="relative z-20 w-full max-w-[900px] lg:ml-24" style={{ transformStyle: "preserve-3d", contain: "layout paint" }}><div className="rounded-t-2xl border-8 border-zinc-700 bg-zinc-950 p-2 shadow-2xl sm:rounded-t-3xl sm:border-[14px] sm:p-5"><div className="screen relative aspect-[16/10] overflow-hidden rounded-lg bg-[#07101f] p-2 font-mono text-[8px] sm:p-4 sm:text-[11px] md:text-xs"><div className="absolute left-0 right-0 top-0 z-30 flex gap-3 overflow-hidden border-b border-white/10 bg-[#0b1424] px-3 py-2 text-[7px] text-slate-400 sm:text-[10px]">{stages.map((stage, i) => <span key={stage} data-stage-tab className="whitespace-nowrap">{stage}</span>)}<i data-tab-underline className="absolute bottom-0 left-0 h-px bg-white" /></div><div className="absolute inset-0 pt-7 sm:pt-9"><Workspace /><Terminal /><Repository /><BrowserPanel /><Report /></div></div></div><div className="mx-auto h-3 w-[75%] rounded-b-xl bg-zinc-700 shadow-xl sm:h-5" /></div></div></div></div></section>
}

export default CinematicHero
