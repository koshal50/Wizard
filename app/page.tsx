import Hero from "@/components/hero"
import { CinematicHero, SafeMeshGradient } from "@/components/ui/cinematic-landing-hero"
import { SmoothCursor } from "@/components/ui/smooth-cursor"

function WizardFooter() {
  return (
    <footer id="download" className="relative flex min-h-screen items-center overflow-hidden border-t border-white/15 px-6 py-14 font-sans text-white sm:px-10 sm:py-20">
      <SafeMeshGradient speed={0.45} colors={["#2452F1", "#022474", "#163DB9", "#0B1D99"]} distortion={0.7} swirl={0.12} grainMixer={0} grainOverlay={0} className="absolute inset-0 h-full w-full" />
      <div className="absolute inset-0 bg-[#022474]/25" />
      <div className="relative z-10 mx-auto w-full max-w-[1440px]">
        <div className="flex flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-xl">
            <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.3em] text-blue-200/70">Build with confidence</p>
            <h2 className="text-balance text-3xl font-semibold tracking-tight sm:text-5xl">Meet Wizard where your work happens.</h2>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-blue-50/70 sm:text-base">Investigate every build, verify every detail, and keep your team moving with evidence you can trust.</p>
          </div>
          <p className="text-4xl font-bold tracking-tight text-white sm:text-6xl">Coming soon.</p>
        </div>
        <div className="mt-16 flex flex-col gap-3 border-t border-white/10 pt-5 text-xs text-blue-100/50 sm:flex-row sm:items-center sm:justify-between">
          <span>© 2026 Wizard. Software you can verify.</span>
          <span>Built for developers, by developers.</span>
        </div>
      </div>
    </footer>
  )
}

export default function Home() {
  return <main className="min-h-screen bg-black"><Hero /><CinematicHero /><WizardFooter /><SmoothCursor /></main>
}
