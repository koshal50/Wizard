import { ArrowUpRight, Check, Github, ShieldCheck } from 'lucide-react'
import { AsciiArt } from '@/components/ui/redshift'

const discoveries = [
  ['Runtime', 'Node.js 20 · verified'],
  ['Application', 'Express REST API · observed'],
  ['Dependencies', '47 detected · 3 failed'],
  ['Deployment', 'Docker · verified'],
]

export default function Hero() {
  return (
    <div className="bg-background text-foreground">
      <section className="relative isolate flex min-h-[680px] items-center overflow-hidden border-b border-border px-6 py-24 sm:px-10 lg:min-h-[760px] lg:px-16">
        <div className="absolute inset-0 -z-20 bg-black">
          <AsciiArt className="h-full w-full opacity-70" />
        </div>
        <div className="absolute inset-0 -z-10 bg-black/65" aria-hidden="true" />
        <div className="absolute inset-x-0 bottom-0 -z-10 h-1/2 bg-gradient-to-t from-black via-black/70 to-transparent" aria-hidden="true" />
        <div className="mx-auto flex w-full max-w-7xl flex-col items-start gap-10">
          <div className="max-w-4xl">
            <p className="mb-6 font-mono text-xs uppercase tracking-[0.22em] text-accent">Open-source verification runtime</p>
            <h1 className="max-w-4xl text-pretty text-5xl font-medium leading-[0.94] tracking-[-0.055em] text-white sm:text-7xl lg:text-8xl">
              AI writes the code. <span className="text-accent">Wizard checks the reality.</span>
            </h1>
            <p className="mt-8 max-w-2xl text-pretty text-lg leading-relaxed text-white/75 sm:text-xl">
              Wizard autonomously investigates software repositories, executes what matters, collects evidence, and verifies what actually works.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <a href="#how-it-works" className="inline-flex items-center justify-center gap-2 rounded-full bg-accent px-6 py-3 font-medium text-accent-foreground transition-transform hover:scale-[1.02]">
                Try Wizard <ArrowUpRight className="size-4" />
              </a>
              <a href="https://github.com" className="inline-flex items-center justify-center gap-2 rounded-full border border-white/25 px-6 py-3 font-medium text-white transition-colors hover:bg-white/10">
                <Github className="size-4" /> View on GitHub
              </a>
            </div>
          </div>
          <p className="font-mono text-xs text-white/45">Not a guess. An investigation.</p>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-12 px-6 py-24 sm:px-10 lg:grid-cols-[0.8fr_1.2fr] lg:px-16">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.22em] text-accent">The problem</p>
          <h2 className="mt-5 max-w-lg text-4xl font-medium leading-tight tracking-[-0.04em] sm:text-5xl">Generated code is cheap. Knowing whether it works is expensive.</h2>
        </div>
        <div className="border-l border-border pl-6 font-mono text-sm leading-loose text-muted-foreground sm:pl-10">
          <p className="text-foreground">README says it runs with <span className="text-accent">npm start</span></p>
          <p>↓</p>
          <p>package.json says something else</p>
          <p>↓</p>
          <p>dependency installation fails</p>
          <p>↓</p>
          <p>application crashes</p>
          <p>↓</p>
          <p className="text-destructive">nobody noticed</p>
          <p className="mt-5 text-lg font-medium text-foreground">Wizard finds out.</p>
        </div>
      </section>

      <section id="how-it-works" className="border-y border-border bg-card px-6 py-24 sm:px-10 lg:px-16">
        <div className="mx-auto max-w-7xl">
          <div className="max-w-2xl">
            <p className="font-mono text-xs uppercase tracking-[0.22em] text-accent">How it works</p>
            <h2 className="mt-5 text-4xl font-medium tracking-[-0.04em] sm:text-6xl">Wizard investigates software instead of guessing about it.</h2>
          </div>
          <div className="mt-16 grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-3 lg:grid-cols-6">
            {['Repository', 'Reads', 'Executes', 'Observes', 'Verifies', 'Explains'].map((step, index) => (
              <div key={step} className="bg-card p-5">
                <span className="font-mono text-xs text-accent">0{index + 1}</span>
                <p className="mt-10 font-medium">{step}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-12 px-6 py-24 sm:px-10 lg:grid-cols-2 lg:px-16">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.22em] text-accent">The difference is evidence</p>
          <h2 className="mt-5 text-4xl font-medium tracking-[-0.04em] sm:text-5xl">Most AI tools generate answers. Wizard generates evidence.</h2>
          <div className="mt-8 space-y-4 text-muted-foreground">
            {['Reads code → Investigates code', 'Predicts behavior → Tests behavior', 'Generates explanations → Builds evidence', 'Gives an answer → Gives an answer plus why'].map((item) => (
              <div key={item} className="flex items-center gap-3 border-b border-border pb-4"><Check className="size-4 text-accent" />{item}</div>
            ))}
          </div>
        </div>
        <div className="border border-border bg-card p-6 font-mono text-sm sm:p-8">
          <p className="text-accent">CLAIM</p><p className="my-3 text-muted-foreground">↓</p><p className="text-foreground">The API starts successfully</p><p className="my-3 text-muted-foreground">↓</p><p className="text-accent">EVIDENCE</p><p className="mt-3 text-muted-foreground">process running · port 3000 responding · output collected</p>
        </div>
      </section>

      <section className="border-y border-border bg-card px-6 py-24 sm:px-10 lg:px-16">
        <div className="mx-auto max-w-7xl">
          <div className="flex max-w-3xl items-end justify-between gap-6">
            <div><p className="font-mono text-xs uppercase tracking-[0.22em] text-accent">A living understanding</p><h2 className="mt-5 text-4xl font-medium tracking-[-0.04em] sm:text-6xl">See what Wizard can actually verify.</h2></div>
            <ShieldCheck className="hidden size-12 text-accent sm:block" />
          </div>
          <div className="mt-12 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
            {discoveries.map(([label, value]) => <div key={label} className="bg-card p-6"><p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">{label}</p><p className="mt-8 text-lg">{value}</p></div>)}
          </div>
          <p className="mt-8 max-w-xl text-muted-foreground">Every conclusion can be traced back to the evidence that produced it. When Wizard cannot verify something, it tells you.</p>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 py-24 text-center sm:px-10 lg:px-16">
        <p className="font-mono text-xs uppercase tracking-[0.22em] text-accent">Build. Verify. Fix. Repeat.</p>
        <h2 className="mx-auto mt-5 max-w-3xl text-4xl font-medium tracking-[-0.04em] sm:text-6xl">Give your AI coding agent a verification layer.</h2>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground">Stop asking AI what your code does. Ask Wizard to find out — then return the evidence so the agent can fix what is broken.</p>
        <a href="#how-it-works" className="mt-9 inline-flex items-center gap-2 rounded-full bg-accent px-6 py-3 font-medium text-accent-foreground">Let Wizard investigate <ArrowUpRight className="size-4" /></a>
      </section>
    </div>
  )
}

