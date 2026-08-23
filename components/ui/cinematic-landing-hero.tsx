"use client"

import { useEffect, useRef } from "react"
import { gsap } from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { cn } from "@/lib/utils"

gsap.registerPlugin(ScrollTrigger)

export function CinematicHero({ className }: { className?: string }) {
  const root = useRef<HTMLDivElement>(null)
  const card = useRef<HTMLDivElement>(null)
  const laptop = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const scope = root.current
    if (!scope) return

    const ctx = gsap.context(() => {
      gsap.set(".cinematic-card", { y: "110vh", autoAlpha: 1 })
      gsap.set(".cinematic-copy, .cinematic-laptop, .cinematic-badge, .cinematic-terminal-line", { autoAlpha: 0 })

      const timeline = gsap.timeline({
        scrollTrigger: {
          trigger: scope,
          start: "top top",
          end: "bottom bottom",
          scrub: 1,
          // CSS sticky keeps React's DOM tree stable. ScrollTrigger's pin spacer
          // mutates the DOM and can race React reconciliation during Fast Refresh.
          pin: false,
          invalidateOnRefresh: true,
        },
      })

      timeline
        .to(".cinematic-card", { y: 0, duration: 1.5, ease: "power3.inOut" })
        .to(".cinematic-card", { width: "100%", height: "100%", borderRadius: 0, duration: 1 })
        .fromTo(".cinematic-laptop", { y: 240, z: -700, rotationX: 55, rotationY: -28, scale: .65 }, { autoAlpha: 1, y: 0, z: 0, rotationX: 0, rotationY: 0, scale: 1, duration: 2, ease: "expo.out" }, "-=.4")
        .fromTo(".cinematic-copy", { y: 60, filter: "blur(18px)" }, { autoAlpha: 1, y: 0, filter: "blur(0px)", duration: 1.2 }, "-=1.4")
        .to(".cinematic-terminal-line", { autoAlpha: 1, stagger: .18, duration: .35 }, "-=1")
        .fromTo(".cinematic-badge", { y: 80, scale: .7 }, { autoAlpha: 1, y: 0, scale: 1, stagger: .15, duration: 1 }, "-=.8")
        .to({}, { duration: 1.6 })
        .to([".cinematic-laptop", ".cinematic-copy", ".cinematic-badge"], { autoAlpha: 0, y: -50, z: -200, duration: 1 })
        .to(".cinematic-card", { y: "-110vh", duration: 1.2, ease: "power3.in" })

    }, root)
    return () => ctx.revert()
  }, [])

  useEffect(() => {
    const move = (event: MouseEvent) => {
      if (!laptop.current) return
      gsap.to(laptop.current, { rotationY: (event.clientX / innerWidth - .5) * 12, rotationX: -(event.clientY / innerHeight - .5) * 10, duration: 1, ease: "power3.out" })
    }
    addEventListener("mousemove", move)
    return () => removeEventListener("mousemove", move)
  }, [])

  return <section ref={root} className={cn("relative flex min-h-[4200px] w-screen items-start justify-center overflow-hidden bg-transparent font-sans", className)}>
    <div ref={card} className="cinematic-card sticky top-0 flex h-[92vh] w-[92vw] items-center justify-center overflow-hidden rounded-[32px] border border-white/10 text-white shadow-2xl" style={{ perspective: 1500, background: "linear-gradient(145deg, #004FE5 0%, #0038B8 100%)" }}>
      <div className="cinematic-copy absolute left-6 top-10 z-10 max-w-xs text-center md:left-12 md:top-1/2 md:-translate-y-1/2 md:text-left">
        <p className="mb-3 font-mono text-xs uppercase tracking-[.3em] text-blue-200/60">Wizard investigation</p>
        <h2 className="text-3xl font-bold tracking-tight md:text-5xl">AI writes the code. Wizard checks the reality.</h2>
        <p className="mt-5 text-sm leading-relaxed text-blue-100/70 md:text-base">Reads. Executes. Observes. Verifies.</p>
      </div>
      <div ref={laptop} className="cinematic-laptop relative z-20 mt-24 w-[82vw] max-w-[680px] transform-style-3d">
        <div className="rounded-t-2xl border-8 border-zinc-700 bg-zinc-950 p-3 shadow-2xl md:rounded-t-3xl md:border-[14px] md:p-5">
          <div className="aspect-[16/10] overflow-hidden rounded-lg bg-[#07101f] p-4 font-mono text-[9px] leading-5 text-blue-100 md:p-8 md:text-sm">
            <p className="cinematic-terminal-line text-blue-400">$ wizard inspect .</p><p className="cinematic-terminal-line">Scanning repository...</p><p className="cinematic-terminal-line">Reading package.json</p><p className="cinematic-terminal-line">Mapping dependencies...</p><p className="cinematic-terminal-line">Detecting runtime: Node.js 20</p><p className="cinematic-terminal-line">Checking startup command...</p><p className="cinematic-terminal-line">Installing dependencies...</p><p className="cinematic-terminal-line">Starting application...</p><p className="cinematic-terminal-line">Checking port 3000...</p><p className="cinematic-terminal-line">Collecting runtime output...</p><p className="cinematic-terminal-line text-emerald-400">Wizard verified this repository.</p>
          </div>
        </div>
        <div className="mx-auto h-3 w-[112%] -translate-x-[5%] rounded-b-xl bg-gradient-to-b from-zinc-500 to-zinc-800 shadow-xl md:h-5" />
      </div>
      <div className="absolute bottom-5 left-4 right-4 z-30 flex flex-col gap-3 sm:bottom-10 sm:left-12 sm:right-12 sm:flex-row sm:justify-between">
        <div className="cinematic-badge rounded-xl border border-white/10 bg-white/10 px-4 py-3 text-center text-xs backdrop-blur-xl sm:text-left">Repository scan · Runtime verified</div>
        <div className="cinematic-badge rounded-xl border border-white/10 bg-white/10 px-4 py-3 text-center text-xs backdrop-blur-xl sm:text-left">Evidence collected</div>
      </div>
    </div>
  </section>
}
