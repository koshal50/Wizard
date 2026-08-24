"use client"

import React, { useEffect, useRef, useState } from "react"
import { gsap } from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { MeshGradient } from "@paper-design/shaders-react"
import { cn } from "@/lib/utils"

if (typeof window !== "undefined") gsap.registerPlugin(ScrollTrigger)

function supportsWebGL() {
  try { const canvas = document.createElement("canvas"); return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl")) } catch { return false }
}

export function SafeMeshGradient({ className, ...props }: React.ComponentProps<typeof MeshGradient>) {
  const [enabled, setEnabled] = useState(false)
  useEffect(() => setEnabled(supportsWebGL()), [])
  return enabled ? <MeshGradient {...props} className={className} /> : <div aria-hidden="true" className={cn("bg-gradient-to-br from-[#2452F1] via-[#163DB9] to-[#022474]", className)} />
}

const stages = [
  { title: "VS Code workspace", tab: "wizard-repo / VS Code", kind: "code" },
  { title: "Terminal session", tab: "terminal — wizard", kind: "terminal" },
  { title: "Repository mapped", tab: "agent activity / repository", kind: "repo" },
  { title: "Browser verification", tab: "Chromium — localhost:3000", kind: "browser" },
  { title: "Final report", tab: "wizard / verification report", kind: "report" },
]

function WindowBar({ children }: { children: React.ReactNode }) { return <div className="window-bar"><span /><span /><span /><b>{children}</b></div> }
function Agent() { return <div className="agent"><span className="hat" /><strong>W</strong><i>✦</i></div> }

function StageContent({ kind }: { kind: string }) {
  if (kind === "code") return <div className="code-layout"><aside><b>EXPLORER</b><span>⌄ wizard-repo</span><em>◇ app/</em><em>◇ components/</em><em>◇ package.json</em><em>◇ README.md</em></aside><pre><span className="pink">import</span> {'{'} verify {'}'} <span className="pink">from</span> <span className="green">&quot;@wizard/agent&quot;</span>{"\n\n"}<span className="blue">export async function</span> verifyApp() {'{'}{"\n"}  <span className="blue">return await</span> verify({'{'}{"\n"}    target: <span className="green">&quot;localhost:3000&quot;</span>,{"\n"}    evidence: <span className="green">true</span>{"\n"}  {'}'}){"\n"}{'}'}</pre><Agent /></div>
  if (kind === "terminal") return <div className="terminal"><p><span className="prompt">wizard@repo</span> ~/wizard-repo $ wizard inspect .</p><p className="dim">→ Reading repository structure</p><p className="dim">→ Checking routes and dependencies</p><p><span className="prompt">wizard@repo</span> $ wizard verify --browser</p><p className="typing">▌</p><Agent /></div>
  if (kind === "repo") return <div className="repo"><div><b>REPOSITORY STRUCTURE</b>{["app/page.tsx", "components/hero.tsx", "components/ui/", "lib/utils.ts", "package.json"].map((file) => <p key={file}>◇ {file}</p>)}</div><section><Agent /><p>Wizard is reading <strong>components/ui/</strong></p><p className="success">✓ 18 files mapped</p><p className="success">✓ No missing imports</p></section></div>
  if (kind === "browser") return <div className="browser"><div className="browser-nav">← <span>localhost:3000</span> ···</div><div className="browser-main"><label>WIZARD BROWSER AGENT</label><h3>Running the real flow.</h3><p>Opening page · clicking CTA · capturing evidence</p><div className="progress"><i /></div><div className="capture"><b>Screenshot captured</b><small>viewport 1280 × 800 · pass</small><strong>✓</strong></div></div><Agent /></div>
  return <div className="report"><div className="check">✓</div><div><label>FINAL VERIFICATION</label><h3>Ship with evidence.</h3><p>All critical paths passed. The repository is ready for review.</p></div><Agent /></div>
}

export function CinematicHero({ className }: { className?: string }) {
  const root = useRef<HTMLElement>(null)
  const card = useRef<HTMLDivElement>(null)
  const intro = useRef<HTMLDivElement>(null)
  const laptop = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const scope = root.current
    if (!scope) return
    const ctx = gsap.context(() => {
      const panels = gsap.utils.toArray<HTMLElement>("[data-stage]")
      const progress = scope.querySelector<HTMLElement>("[data-progress]")
      const intro = scope.querySelector<HTMLElement>("[data-intro]")
      const cardElement = card.current
      const introElement = intro.current
      const firstPanel = panels[0]
      if (!cardElement || !introElement || !firstPanel || !progress) return
      gsap.set(panels, { autoAlpha: 0, y: 22, scale: .985 })
      gsap.set(firstPanel, { autoAlpha: 1, y: 0, scale: 1 })
      gsap.set(cardElement, { scale: .72, borderRadius: 28 })
      const tl = gsap.timeline({
        defaults: { ease: "none" },
        scrollTrigger: {
          trigger: scope,
          start: "top top",
          end: "bottom bottom",
          scrub: 0.8,
          invalidateOnRefresh: true,
          anticipatePin: 1,
        },
      })
      tl.to(cardElement, { scale: 1, borderRadius: 0, duration: 0.16 }, 0)
        .to(introElement, { autoAlpha: 1, y: 0, duration: 0.12 }, 0)
      stages.forEach((_, index) => {
        if (!index) return
        const previous = panels[index - 1]
        const current = panels[index]
        tl.to(previous, { autoAlpha: 0, y: -18, scale: 1.01, duration: 0.06 })
          .to(current, { autoAlpha: 1, y: 0, scale: 1, duration: 0.16 })
      })
      tl.to(progress, { scaleX: 1, duration: 0.12 })
        .to(cardElement, { scale: 0.72, borderRadius: 28, duration: 0.16 })
      requestAnimationFrame(() => ScrollTrigger.refresh())
    }, scope)
    return () => ctx.revert()
  }, [])
  useEffect(() => { const onMove = (event: MouseEvent) => { if (!laptop.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return; gsap.to(laptop.current, { rotationY: (event.clientX / innerWidth - .5) * 3, rotationX: -(event.clientY / innerHeight - .5) * 2, duration: .7, overwrite: "auto" }) }; addEventListener("mousemove", onMove); return () => removeEventListener("mousemove", onMove) }, [])
  return <section ref={root} className={cn("wizard-story", className)}><div className="story-viewport"><div ref={card} className="scene-card"><SafeMeshGradient speed={.7} colors={["#2452F1", "#022474", "#163DB9", "#0B1D99"]} distortion={.8} swirl={.1} grainMixer={0} grainOverlay={0} className="scene-gradient" /><div className="scene-shade" /><div ref={intro} data-intro className="scene-intro"><label>Wizard investigation</label><h2>AI writes the code. Wizard checks the reality.</h2><p>Watch an agent read, execute, browse, and verify the work.</p></div><div ref={laptop} className="laptop"><div className="bezel"><div className="screen">{stages.map((stage) => <div data-stage key={stage.kind} className="stage"><WindowBar>{stage.tab}</WindowBar><StageContent kind={stage.kind} /></div>)}</div></div><div className="base" /></div><div className="story-progress" aria-hidden="true"><i data-progress /></div></div></div><style jsx>{`\n.wizard-story{position:relative;min-height:7600px;background:#020617;color:#fff;font-family:var(--font-geist-sans),Arial,sans-serif}.story-viewport{position:sticky;top:0;height:100vh;display:flex;align-items:center;justify-content:center;padding:12px;overflow:hidden}.scene-card{position:relative;width:100%;height:calc(100vh - 24px);max-width:1440px;overflow:hidden;border:1px solid rgba(255,255,255,.14);display:flex;align-items:center;justify-content:center;isolation:isolate;box-shadow:0 25px 80px rgba(0,0,0,.35)}.scene-gradient,.scene-shade{position:absolute;inset:0}.scene-shade{background:rgba(2,36,116,.2)}.scene-intro{position:absolute;z-index:4;left:7%;top:50%;width:min(360px,35vw);transform:translateY(24px);opacity:0}.scene-intro label,.report label{font:10px ui-monospace,monospace;letter-spacing:.28em;text-transform:uppercase;color:rgba(219,234,254,.7)}.scene-intro h2{font-size:clamp(28px,3.2vw,52px);line-height:1.04;letter-spacing:-.05em;margin:12px 0}.scene-intro p{color:rgba(239,246,255,.75);line-height:1.6}.laptop{position:relative;z-index:3;width:min(760px,72vw);margin-left:18vw;transform-style:preserve-3d}.bezel{border:12px solid #27272a;border-bottom-width:18px;border-radius:24px 24px 8px 8px;background:#030712;padding:14px;box-shadow:0 25px 50px rgba(0,0,0,.4)}.screen{position:relative;aspect-ratio:16/10;overflow:hidden;border-radius:7px;background:#07101f;font:11px ui-monospace,monospace}.stage{position:absolute;inset:0;padding:0 14px;color:#dbeafe}.window-bar{height:28px;display:flex;align-items:center;gap:5px;border-bottom:1px solid rgba(255,255,255,.1);color:#94a3b8}.window-bar span{width:7px;height:7px;border-radius:50%;background:#64748b}.window-bar b{font-size:9px;font-weight:500;margin-left:8px}.code-layout,.repo,.terminal,.browser,.report{height:calc(100% - 28px);position:relative;padding:18px}.code-layout{display:flex;gap:18px}.code-layout aside{display:flex;flex-direction:column;gap:9px;width:28%;color:#94a3b8}.code-layout aside b,.repo>b{font-size:9px;color:#dbeafe}.code-layout aside em{font-style:normal}.code-layout pre{line-height:1.7;color:#cbd5e1;margin:0}.pink{color:#f472b6}.green{color:#86efac}.blue{color:#60a5fa}.agent{position:absolute;right:20px;bottom:18px;width:30px;height:42px;text-align:center;color:#fbbf24}.agent strong{display:block;background:#7c3aed;border-radius:50% 50% 35% 35%;height:25px;padding-top:5px;color:white}.agent i{font-style:normal}.hat{position:absolute;top:-7px;left:4px;border-left:11px solid transparent;border-right:11px solid transparent;border-bottom:14px solid #f97316}.terminal p{margin:0 0 10px}.prompt,.success{color:#86efac}.dim{color:#64748b}.typing{color:#60a5fa}.repo{display:grid;grid-template-columns:1fr 1fr;gap:15px}.repo p{margin:10px 0;color:#a5b4fc}.repo section{border-left:1px solid rgba(255,255,255,.12);padding-left:15px}.browser-nav{padding:8px;background:#111827;color:#94a3b8}.browser-main{padding:20px}.browser-main label{font-size:8px;letter-spacing:.2em;color:#60a5fa}.browser-main h3,.report h3{font-size:20px;margin:12px 0 6px}.browser-main p,.report p{color:#94a3b8}.progress{height:4px;background:#1e293b;margin:22px 0}.progress i,.story-progress i{display:block;height:100%;background:#60a5fa;transform:scaleX(0);transform-origin:left}.capture{position:relative;padding:12px;background:#0f172a;border:1px solid #334155}.capture small{display:block;color:#64748b;margin-top:5px}.capture strong{position:absolute;right:12px;top:14px;color:#86efac}.report{display:flex;align-items:center;gap:16px}.check{display:grid;place-items:center;width:42px;height:42px;border-radius:50%;background:#14532d;color:#86efac;font-size:22px}.stage-dots{position:absolute;z-index:5;bottom:7%;left:7%;right:7%;display:flex;justify-content:space-between;color:rgba(219,234,254,.6);font:10px ui-monospace,monospace}.stage-dots span{display:flex;gap:6px;align-items:center}.stage-dots i{font-style:normal;color:#93c5fd}.story-progress{position:absolute;z-index:6;bottom:4%;left:7%;right:7%;height:2px;background:rgba(255,255,255,.2)}@media(max-width:800px){.wizard-story{min-height:6200px}.story-viewport{padding:0}.scene-card{height:100vh;border:0;align-items:flex-start}.scene-intro{left:7%;top:7%;width:86%;transform:translateY(18px)}.scene-intro h2{font-size:31px}.scene-intro p{margin-top:10px}.laptop{width:94vw;margin:150px 0 0}.bezel{border-width:7px 7px 12px;padding:6px;border-radius:14px 14px 4px 4px}.screen{font-size:7px}.stage{padding:0 5px}.code-layout,.repo,.terminal,.browser,.report{padding:9px}.code-layout{gap:8px}.code-layout aside{width:31%;gap:5px}.window-bar{height:20px}.window-bar b{font-size:7px}.window-bar span{width:5px;height:5px}.code-layout,.repo,.terminal,.browser,.report{height:calc(100% - 20px)}.browser-main{padding:10px}.browser-main h3,.report h3{font-size:15px}.report p{font-size:8px}.stage-dots{left:7%;right:7%;bottom:6%;gap:3px}.stage-dots span{font-size:0}.stage-dots span:first-child{font-size:9px}.stage-dots i{font-size:9px}.story-progress{bottom:3%}}\n`}</style></section>
}
export default CinematicHero
