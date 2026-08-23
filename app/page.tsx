import Hero from "@/components/hero"
import { CinematicHero } from "@/components/ui/cinematic-landing-hero"

function StoreBadge({ store, detail }: { store: string; detail: string }) {
  return (
    <a href="#download" className="flex min-w-[154px] items-center gap-3 rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-left text-white transition-colors hover:bg-white/20">
      <span aria-hidden="true" className="text-xl leading-none">{store === "App Store" ? "" : "▶"}</span>
      <span className="flex flex-col leading-tight">
        <span className="text-[9px] uppercase tracking-[0.14em] text-blue-100/65">{detail}</span>
        <span className="text-sm font-medium">{store}</span>
      </span>
    </a>
  )
}

function WizardFooter() {
  return (
    <footer id="download" className="relative z-40 border-t border-white/15 bg-[#022474] px-6 py-14 font-sans text-white sm:px-10 sm:py-20">
      <div className="mx-auto flex max-w-[1440px] flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-xl">
          <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.3em] text-blue-200/70">Build with confidence</p>
          <h2 className="text-balance text-3xl font-semibold tracking-tight sm:text-5xl">Meet Wizard where your work happens.</h2>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-blue-50/70 sm:text-base">Investigate every build, verify every detail, and keep your team moving with evidence you can trust.</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row" aria-label="Download Wizard">
          <StoreBadge store="App Store" detail="Download on the" />
          <StoreBadge store="Google Play" detail="Get it on" />
        </div>
      </div>
      <div className="mx-auto mt-12 flex max-w-[1440px] flex-col gap-3 border-t border-white/10 pt-5 text-xs text-blue-100/50 sm:flex-row sm:items-center sm:justify-between">
        <span>© 2026 Wizard. Software you can verify.</span>
        <span>Built for developers, by developers.</span>
      </div>
    </footer>
  )
}

export default function Home() {
  return (
    <main className="min-h-screen bg-black">
      <Hero />
      <CinematicHero />
      <WizardFooter />
    </main>
  )
}
