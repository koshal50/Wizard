"use client"

import { useEffect, useRef, useState } from "react"
import { gsap } from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { MeshGradient } from "@paper-design/shaders-react"
import { cn } from "@/lib/utils"

gsap.registerPlugin(ScrollTrigger)

const terminalLines = [
  "$ wizard inspect .",
  "Scanning repository...",
  "Reading package.json",
  "Mapping dependencies...",
  "Detecting runtime: Node.js 20",
  "Checking startup command...",
  "Installing dependencies...",
  "Starting application...",
  "Checking port 3000...",
  "Collecting runtime output...",
  "Wizard verified this repository.",
]

function supportsWebGL() {
  if (typeof document === "undefined") return false
  try {
    const canvas = document.createElement("canvas")
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl") || canvas.getContext("experimental-webgl"))
  } catch {
    return false
  }
}

export function SafeMeshGradient({ className, ...props }: React.ComponentProps<typeof MeshGradient>) {
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    setEnabled(supportsWebGL())
  }, [])

  if (!enabled) {
    return <div aria-hidden="true" className={cn("bg-gradient-to-br from-[#2452F1] via-[#163DB9] to-[#022474]", className)} />
  }

  return <MeshGradient {...props} className={className} />
}

export function CinematicHero({ className }: { className?: string }) {
  const root = useRef<HTMLElement>(null)
  const laptop = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const scope = root.current
    if (!scope) return

    const ctx = gsap.context(() => {
      const card = scope.querySelector<HTMLElement>("[data-scene-card]")
      const copy = scope.querySelector<HTMLElement>("[data-scene-copy]")
      const screen = scope.querySelector<HTMLElement>("[data-scene-laptop]")
      const lines = gsap.utils.toArray<HTMLElement>("[data-terminal-line]")
      const badges = gsap.utils.toArray<HTMLElement>("[data-scene-badge]")
      if (!card || !copy || !screen) return

      gsap.set([copy, screen, ...badges], { autoAlpha: 0 })
      gsap.set(card, { scale: 0.72, borderRadius: 24 })
      gsap.set(screen, { y: 80, scale: 0.82, rotationX: 18, rotationY: -8 })
      gsap.set(copy, { y: 40, filter: "blur(10px)" })
      gsap.set(lines, { autoAlpha: 0, y: 8 })
      gsap.set(badges, { y: 28, scale: 0.94 })

      const timeline = gsap.timeline({
        scrollTrigger: {
          trigger: scope,
          start: "top top",
          end: "bottom bottom",
          scrub: 0.8,
          invalidateOnRefresh: true,
        },
      })

      timeline
        .to(card, { scale: 1.08, borderRadius: 0, duration: 0.28, ease: "power2.out" })
        .to(screen, { autoAlpha: 1, y: 0, scale: 1, rotationX: 0, rotationY: 0, duration: 0.28, ease: "power3.out" }, "<")
        .to(copy, { autoAlpha: 1, y: 0, filter: "blur(0px)", duration: 0.2 }, "<0.04")
        .to(lines, { autoAlpha: 1, y: 0, stagger: 0.055, duration: 0.12, ease: "none" }, "<0.04")
        .to(badges, { autoAlpha: 1, y: 0, scale: 1, stagger: 0.06, duration: 0.2 }, "<0.12")
        .to({}, { duration: 0.35 })
        .to(screen, { y: -18, scale: 1.03, duration: 0.18, ease: "none" })
        .to(lines.slice(6), { color: "#6ee7b7", duration: 0.18, stagger: 0.04 }, "<")
        .to({}, { duration: 0.45 })
        .to(card, { scale: 0.72, borderRadius: 24, duration: 0.2, ease: "power2.inOut" })
    }, scope)

    return () => ctx.revert()
  }, [])

  useEffect(() => {
    const move = (event: MouseEvent) => {
      if (!laptop.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
      gsap.to(laptop.current, {
        rotationY: (event.clientX / window.innerWidth - 0.5) * 5,
        rotationX: -(event.clientY / window.innerHeight - 0.5) * 4,
        duration: 0.8,
        ease: "power3.out",
        overwrite: "auto",
      })
    }
    window.addEventListener("mousemove", move)
    return () => window.removeEventListener("mousemove", move)
  }, [])

  return (
    <section ref={root} className={cn("relative z-10 min-h-[4200px] w-full overflow-visible bg-transparent font-sans", className)}>
      <div className="sticky top-0 flex min-h-screen items-center justify-center px-3 py-4 sm:px-6 sm:py-6 lg:px-10">
        <div data-scene-card className="relative flex min-h-[calc(100vh-2rem)] w-full max-w-[1440px] flex-col items-center justify-center overflow-hidden rounded-[24px] border border-white/15 bg-gradient-to-br from-[#2452F1] via-[#163DB9] to-[#022474] text-white shadow-2xl sm:min-h-[calc(100vh-3rem)] sm:rounded-[40px] lg:flex-row" style={{ perspective: 1500 }}>
          <SafeMeshGradient
            speed={0.7}
            colors={["#2452F1", "#022474", "#163DB9", "#0B1D99"]}
            distortion={0.8}
            swirl={0.1}
            grainMixer={0}
            grainOverlay={0}
            className="absolute inset-0 h-full w-full"
          />
          <div className="absolute inset-0 bg-[#022474]/20" />

          <div data-scene-copy className="relative z-10 order-1 w-full max-w-[320px] px-5 pt-8 text-center sm:max-w-[420px] sm:px-8 sm:pt-12 sm:text-left lg:absolute lg:left-16 lg:top-1/2 lg:order-none lg:w-auto lg:-translate-y-1/2 lg:px-0 lg:pt-0">
            <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.3em] text-blue-100/70 sm:text-xs">Wizard investigation</p>
            <h2 className="text-balance text-3xl font-semibold leading-[1.05] tracking-tight sm:text-4xl lg:text-5xl">AI writes the code. Wizard checks the reality.</h2>
            <p className="mt-5 text-sm leading-relaxed text-blue-50/80 sm:text-base">Reads. Executes. Observes. Verifies.</p>
          </div>

          <div ref={laptop} data-scene-laptop className="relative z-20 order-2 mt-5 w-[92vw] max-w-[680px] transform-style-3d sm:mt-8 lg:order-none lg:ml-52 lg:mt-8">
            <div className="rounded-t-2xl border-8 border-zinc-700 bg-zinc-950 p-2 shadow-2xl sm:rounded-t-3xl sm:border-[14px] sm:p-5">
              <div className="aspect-[16/10] overflow-hidden rounded-lg bg-[#07101f] p-3 font-mono text-[8px] leading-[1.65] text-blue-100 sm:p-6 sm:text-xs md:text-sm">
                {terminalLines.map((line, index) => (
                  <p key={line} data-terminal-line className={index === 0 ? "text-blue-400" : index === terminalLines.length - 1 ? "text-emerald-400" : undefined}>{line}</p>
                ))}
              </div>
            </div>
            <div className="mx-auto h-3 w-[112%] -translate-x-[5%] rounded-b-xl bg-gradient-to-b from-zinc-500 to-zinc-800 shadow-xl sm:h-5" />
          </div>

          <div className="relative z-30 order-3 grid w-[92vw] max-w-[680px] gap-3 px-3 pb-6 sm:grid-cols-2 sm:px-0 sm:pb-10 lg:absolute lg:bottom-10 lg:left-16 lg:right-16 lg:order-none lg:w-auto lg:max-w-none lg:px-0">
            <div data-scene-badge className="rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-center text-xs backdrop-blur-xl sm:text-left">Repository scan · Runtime verified</div>
            <div data-scene-badge className="rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-center text-xs backdrop-blur-xl sm:text-left">Evidence collected</div>
          </div>
        </div>
      </div>
    </section>
  )
}
