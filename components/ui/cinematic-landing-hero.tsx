"use client"

import React, { useEffect, useRef, useState } from "react"
import { gsap } from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { MeshGradient } from "@paper-design/shaders-react"
import { cn } from "@/lib/utils"

if (typeof window !== "undefined") gsap.registerPlugin(ScrollTrigger)

function supportsWebGL() {
  if (typeof document === "undefined") return false
  try {
    const canvas = document.createElement("canvas")
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"))
  } catch { return false }
}

export function SafeMeshGradient({ className, ...props }: React.ComponentProps<typeof MeshGradient>) {
  const [enabled, setEnabled] = useState(false)
  useEffect(() => setEnabled(supportsWebGL()), [])
  return enabled
    ? <MeshGradient {...props} className={className} />
    : <div aria-hidden="true" className={cn("bg-gradient-to-br from-[#2452F1] via-[#163DB9] to-[#022474]", className)} />
}

function WizardAgent() { return <span className="wizard-agent" aria-label="Wizard agent"><span className="wizard-hat" /><span className="wizard-body">W</span><span className="wizard-spark">✦</span></span> }
function Bar({ children }: { children: React.ReactNode }) { return <div className="window-bar"><i /><i /><i /><span>{children}</span></div> }

const stages = ["VS Code", "Terminal", "Repository", "Browser", "Report"]

function Workspace() {
  return <div data-screen-panel className="screen-panel screen-code"><Bar>wizard-repo / VS Code</Bar><div className="ide-body"><div className="file-tree"><b>EXPLORER</b><span>⌄ wizard-repo</span><em>◇ app/</em><em>◇ components/</em><em>◇ package.json</em><em>◇ README.md</em></div><pre><code><span className="pink">import</span> {'{'} verify {'}'} <span className="pink">from</span> <span className="green">&quot;@wizard/agent&quot;</span>{"\n\n"}<span className="blue">export async function</span> run() {'{'}{"\n"}  <span className="blue">const</span> evidence = <span className="pink">await</span> verify({'{'}{"\n"}    target: <span className="green">&quot;localhost:3000&quot;</span>,{"\n"}    mode: <span className="green">&quot;deep&quot;</span>{"\n"}  {'}'}){"\n"}{'}'}</code></pre><WizardAgent /></div></div>
}
function Terminal() { return <div data-screen-panel className="screen-panel screen-terminal"><Bar>terminal — wizard session</Bar><div className="crt-scanlines" aria-hidden="true" /><div className="terminal-copy"><p><span className="prompt">wizard@repo</span> ~/wizard-repo $ wizard inspect .</p><p className="dim">→ Reading repository structure</p><p className="dim">→ Checking package.json and routes</p><p className="dim">→ Starting development server</p><p><span className="prompt">wizard@repo</span> $ wizard verify --browser</p><p className="cursor-line">▋</p></div><WizardAgent /></div> }
function Repository() { const files = ["app/page.tsx", "components/hero.tsx", "components/ui/", "lib/utils.ts", "package.json"]; return <div data-screen-panel className="screen-panel screen-repo"><Bar>agent activity / repository map</Bar><div className="repo-map"><div className="repo-column"><b>REPOSITORY STRUCTURE</b>{files.map(file => <div className="repo-file" key={file}>◇ {file}</div>)}</div><div className="agent-log"><WizardAgent /><p>Wizard is reading <strong>components/ui/</strong></p><p className="success">✓ 18 files mapped</p><p className="success">✓ No missing imports</p></div></div></div> }
function Browser() { return <div data-screen-panel className="screen-panel screen-browser"><Bar>Chromium — localhost:3000</Bar><div className="browser-page"><div className="browser-nav">← <span>localhost:3000</span> ···</div><div className="browser-content"><span className="browser-pill">WIZARD BROWSER AGENT</span><h3>Running the real flow.</h3><p>Opening page · clicking primary CTA · capturing evidence</p><div className="browser-progress"><span /></div><div className="capture-card"><b>Screenshot captured</b><small>viewport 1280 × 800 · pass</small><strong>✓</strong></div></div><WizardAgent /></div></div> }
function Report() { return <div data-screen-panel className="screen-panel screen-report"><Bar>wizard / final verification report</Bar><div className="report-copy"><div className="report-mark">✓</div><div><span className="muted">FINAL VERIFICATION</span><h3>Ship with evidence.</h3><p>All critical paths passed. The repository is ready for review.</p></div></div><div className="report-stats"><span><b>05</b> stages</span><span><b>18</b> files</span><span><b>03</b> captures</span><strong>PASS</strong></div><WizardAgent /></div> }

export function CinematicHero({ className }: { className?: string }) {
  const root = useRef<HTMLElement>(null)
  const laptop = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(0)

  useEffect(() => {
    const scope = root.current
    if (!scope) return
    const ctx = gsap.context(() => {
      const card = scope.querySelector<HTMLElement>("[data-scene-card]")
      const copy = scope.querySelector<HTMLElement>("[data-scene-copy]")
      const panels = gsap.utils.toArray<HTMLElement>("[data-screen-panel]")
      const tabs = gsap.utils.toArray<HTMLElement>("[data-stage-tab]")
      if (!card || !copy || !panels.length) return
      gsap.set(card, { scale: 0.8, borderRadius: 28, force3D: true })
      gsap.set(copy, { autoAlpha: 1, y: 20, force3D: true })
      gsap.set(panels, { autoAlpha: 1, y: 0, scale: 1, force3D: true, clipPath: "inset(0 0% 0 0)" })
      gsap.set(panels.slice(1), { clipPath: "inset(0 100% 0 0)" })
      const tl = gsap.timeline({ scrollTrigger: { trigger: scope, start: "top top", end: "bottom bottom", scrub: 1.2, invalidateOnRefresh: true, onUpdate: self => setActive(Math.min(4, Math.floor(self.progress * 5))) } })
      tl.to(card, { scale: 1, borderRadius: 0, duration: 0.16, ease: "none" }).to(copy, { autoAlpha: 1, y: 0, duration: 0.1 }, "<")
      panels.slice(1).forEach((panel, index) => {
        const previous = panels[index]
        tl.to(previous, { clipPath: "inset(0 100% 0 0)", duration: 0.08, ease: "none" })
          .to(panel, { clipPath: "inset(0 0% 0 0)", duration: 0.16, ease: "none" }, "<")
      })
      tl.to({}, { duration: 0.2 }).to(card, { scale: 0.8, borderRadius: 28, duration: 0.14, ease: "none" })
      gsap.set(tabs, { color: "#8ba2c8" })
      gsap.set(tabs[0], { color: "#ffffff" })
      ScrollTrigger.create({
        trigger: scope,
        start: "top top",
        end: "bottom bottom",
        scrub: true,
        onUpdate: self => {
          const index = Math.min(stages.length - 1, Math.floor(self.progress * stages.length))
          gsap.set(tabs, { color: "#8ba2c8" })
          gsap.set(tabs[index], { color: "#ffffff" })
        },
      })
    }, scope)
    return () => ctx.revert()
  }, [])

  useEffect(() => {
    const move = (event: MouseEvent) => {
      if (!laptop.current || window.matchMedia("(prefers-reduced-motion: reduce), (pointer: coarse)").matches) return
      gsap.to(laptop.current, { rotationY: (event.clientX / innerWidth - 0.5) * 2, rotationX: -(event.clientY / innerHeight - 0.5) * 1.5, duration: 0.7, overwrite: "auto", force3D: true })
    }
    window.addEventListener("mousemove", move, { passive: true })
    return () => window.removeEventListener("mousemove", move)
  }, [])

  return <section ref={root} className={cn("relative z-10 min-h-[7200px] w-full overflow-visible bg-transparent font-sans", className)} style={{ contain: "layout style" }}><div className="sticky top-0 flex min-h-screen w-full items-center justify-center"><div data-scene-card className="scene-card relative flex min-h-screen w-full items-center justify-center overflow-hidden border-0 bg-gradient-to-br from-[#2452F1] via-[#163DB9] to-[#022474] text-white shadow-2xl" style={{ perspective: 1500, willChange: "transform" }}><SafeMeshGradient speed={0.45} colors={["#2452F1", "#022474", "#163DB9", "#0B1D99"]} distortion={0.7} swirl={0.12} grainMixer={0} grainOverlay={0} className="absolute inset-0 h-full w-full" /><div className="absolute inset-0 bg-[#022474]/20" /><div data-scene-copy className="absolute left-5 top-8 z-30 max-w-[280px] sm:left-10 sm:top-12 sm:max-w-[380px] lg:left-16 lg:top-1/2 lg:-translate-y-1/2"><p className="mb-3 font-mono text-[10px] uppercase tracking-[.3em] text-blue-100/70">Wizard investigation</p><h2 className="text-balance text-3xl font-semibold leading-[1.05] tracking-tight sm:text-4xl lg:text-5xl">AI writes the code. Wizard checks the reality.</h2><p className="mt-5 text-sm leading-relaxed text-blue-50/80 sm:text-base">Watch an agent read, execute, browse, and verify the work.</p></div><div ref={laptop} className="relative z-20 mt-52 w-[92vw] max-w-[760px] lg:ml-48 lg:mt-8" style={{ transformStyle: "preserve-3d", contain: "layout paint" }}><div className="rounded-t-2xl border-8 border-zinc-700 bg-zinc-950 p-2 shadow-2xl sm:rounded-t-3xl sm:border-[14px] sm:p-5"><div className="screen relative aspect-[16/10] overflow-hidden rounded-lg bg-[#07101f] p-2 font-mono text-[8px] sm:p-4 sm:text-[11px] md:text-xs"><div className="absolute left-0 right-0 top-0 z-20 flex gap-3 overflow-hidden border-b border-white/10 bg-[#0b1424] px-3 py-2 text-[7px] text-slate-400 sm:text-[10px]">{stages.map((stage, i) => <span key={stage} data-stage-tab className={cn("whitespace-nowrap transition-colors", active === i && "text-white")}>{stage}</span>)}</div>{[<Workspace key="code" />, <Terminal key="terminal" />, <Repository key="repo" />, <Browser key="browser" />, <Report key="report" />].map((panel, i) => <div key={i} data-screen-panel className="absolute inset-0 pt-7">{panel}</div>)}</div></div><div className="mx-auto h-3 w-[112%] -translate-x-[5%] rounded-b-xl bg-zinc-700 shadow-xl" /><div className="mx-auto h-2 w-1/3 rounded-full bg-zinc-600" /></div><div className="absolute bottom-6 left-5 right-5 z-30 flex flex-wrap gap-2 sm:left-10 sm:right-10 lg:left-16">{["Repository scan", "Evidence collected"].map((badge, i) => <span key={badge} data-scene-badge className="rounded-full border border-white/20 bg-white/10 px-3 py-1.5 font-mono text-[9px] uppercase tracking-wider text-blue-50 backdrop-blur-sm sm:px-4 sm:text-[10px]">{i === 0 ? "◈ " : "✓ "}{badge}</span>)}</div></div></div></section>
}

export default CinematicHero
