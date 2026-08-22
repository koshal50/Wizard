'use client'

import { useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowUpRight, Check, Github, X } from 'lucide-react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { AsciiArt } from '@/components/ui/sss'
import { createClient } from '@supabase/supabase-js'

gsap.registerPlugin(ScrollTrigger)

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
)

const investigationSteps = [
  ['01', 'Reads', 'Maps the repository and finds the signals that matter.'],
  ['02', 'Executes', 'Runs commands, installs dependencies, and starts the software.'],
  ['03', 'Observes', 'Collects logs, ports, test results, and runtime behavior.'],
  ['04', 'Verifies', 'Separates what is proven from what is still uncertain.'],
]

export default function Hero() {
  const stage = useRef<HTMLDivElement>(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle')

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from('.hero-reveal', { opacity: 0, y: 38, stagger: 0.12, duration: 1.1, ease: 'power3.out' })
      gsap.to('.laptop', {
        y: -18,
        rotateY: 5,
        scrollTrigger: { trigger: '.investigation', start: 'top bottom', end: 'center center', scrub: 1 },
      })
      gsap.from('.step-card', {
        opacity: 0,
        y: 40,
        stagger: 0.15,
        scrollTrigger: { trigger: '.steps', start: 'top 75%', end: 'center center', scrub: 1 },
      })
      gsap.to('.terminal-progress', {
        width: '100%',
        scrollTrigger: { trigger: '.investigation', start: 'top 55%', end: 'bottom 75%', scrub: 1 },
      })
    }, stage)
    return () => ctx.revert()
  }, [])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setStatus('submitting')
    const form = event.currentTarget
    const values = new FormData(form)
    const { error } = await supabase.from('wizard_contact_submissions').insert({
      name: String(values.get('name') ?? '').trim(),
      email: String(values.get('email') ?? '').trim(),
      website: String(values.get('website') ?? '').trim() || null,
      role: String(values.get('role') ?? '').trim() || null,
      message: String(values.get('message') ?? '').trim() || null,
    })
    if (error) { setStatus('error'); return }
    form.reset()
    setStatus('success')
    window.setTimeout(() => { setIsExpanded(false); setStatus('idle') }, 3000)
  }

  return (
    <div ref={stage} className="overflow-hidden bg-[#050B18] text-[#F4F7FF]">
      <section className="relative flex min-h-screen items-center justify-center px-6 py-28">
        <div className="absolute inset-0 opacity-45"><AsciiArt className="h-full w-full object-cover" /></div>
        <div className="absolute inset-0 bg-[#050B18]/45" />
        <div className="hero-reveal relative z-10 mx-auto max-w-5xl text-center">
          <p className="mb-7 font-mono text-xs uppercase tracking-[0.28em] text-[#75A7FF]">Open-source verification runtime</p>
          <h1 className="text-balance text-5xl font-medium leading-[0.94] tracking-[-0.065em] sm:text-7xl md:text-8xl">Build with AI.<br /><span className="text-[#75A7FF]">Verify with Wizard.</span></h1>
          <p className="mx-auto mt-8 max-w-2xl text-pretty text-lg leading-8 text-[#B7C4D9] sm:text-xl">Let Wizard investigate, execute, and verify your software automatically so you can build faster with confidence.</p>
          <div className="mt-10 flex flex-wrap justify-center gap-3">
            <button onClick={() => setIsExpanded(true)} className="rounded-full bg-[#F4F7FF] px-7 py-3 font-medium text-[#07132C] transition hover:bg-[#75A7FF]">Talk to the Wizard team</button>
            <a href="https://github.com" target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-full border border-[#7890B5]/40 px-7 py-3 text-[#F4F7FF] transition hover:border-[#75A7FF]"><Github className="h-4 w-4" /> View on GitHub <ArrowUpRight className="h-4 w-4" /></a>
          </div>
        </div>
        <ArrowDown className="hero-reveal absolute bottom-8 h-5 w-5 animate-bounce text-[#75A7FF]" />
      </section>

      <section className="mx-auto max-w-6xl px-6 py-28 sm:py-40">
        <p className="font-mono text-xs uppercase tracking-[0.25em] text-[#75A7FF]">The problem</p>
        <h2 className="mt-5 max-w-3xl text-4xl leading-tight tracking-[-0.05em] sm:text-6xl">Generated code is cheap. Knowing whether it works is expensive.</h2>
        <div className="mt-14 grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-center">
          <div className="rounded-2xl border border-[#7890B5]/20 bg-[#0C172D] p-7 font-mono text-sm leading-8 text-[#B7C4D9]"><span className="text-[#75A7FF]">README</span> says it runs<br />↓<br /><span className="text-[#75A7FF]">package.json</span> says something else<br />↓<br />dependency installation fails<br />↓<span className="text-[#FF9278]"> nobody noticed</span></div>
          <div className="text-center font-mono text-3xl text-[#75A7FF]">?</div>
          <div className="rounded-2xl border border-[#75A7FF]/35 bg-[#102653] p-7"><p className="font-mono text-xs uppercase tracking-widest text-[#75A7FF]">Wizard finds out</p><p className="mt-4 text-2xl leading-tight">Not a guess. An investigation.</p></div>
        </div>
      </section>

      <section className="investigation relative border-y border-[#7890B5]/15 bg-[#071126] px-6 py-28 sm:py-40">
        <div className="mx-auto grid max-w-6xl items-center gap-16 lg:grid-cols-2">
          <div><p className="font-mono text-xs uppercase tracking-[0.25em] text-[#75A7FF]">The difference is evidence</p><h2 className="mt-5 text-4xl leading-tight tracking-[-0.05em] sm:text-6xl">Wizard investigates software instead of guessing about it.</h2><p className="mt-7 max-w-lg text-lg leading-8 text-[#B7C4D9]">Give Wizard a repository. It explores the code, executes what matters, observes the result, and explains what actually happened.</p></div>
          <div className="laptop mx-auto w-full max-w-[520px] [perspective:1200px]"><div className="rounded-t-[20px] border-[10px] border-[#182B4B] bg-[#020611] p-2 shadow-2xl [transform:rotateX(5deg)_rotateY(-8deg)]"><div className="terminal min-h-[285px] rounded-lg border border-[#294267] bg-[#050B18] p-5 font-mono text-xs leading-7 text-[#9DB1CF] sm:text-sm"><div className="mb-5 flex items-center gap-2 border-b border-[#294267] pb-4"><span className="h-2 w-2 rounded-full bg-[#FF9278]" /><span className="h-2 w-2 rounded-full bg-[#FFD166]" /><span className="h-2 w-2 rounded-full bg-[#55E6A5]" /><span className="ml-auto text-[#75A7FF]">wizard verify</span></div><div><span className="text-[#55E6A5]">✓</span> Repository discovered</div><div><span className="text-[#55E6A5]">✓</span> Runtime: Node.js 20</div><div><span className="text-[#55E6A5]">✓</span> Installing dependencies...</div><div><span className="text-[#FFD166]">→</span> Starting application on port 3000</div><div><span className="text-[#75A7FF]">→</span> Collecting runtime evidence<span className="animate-pulse">_</span></div><div className="mt-4 h-1 overflow-hidden rounded bg-[#172A48]"><div className="terminal-progress h-full w-0 bg-[#55E6A5]" /></div></div></div><div className="mx-auto h-4 w-[112%] rounded-b-[50%] bg-[#294267] shadow-xl" /></div>
        </div>
      </section>

      <section className="steps mx-auto max-w-6xl px-6 py-28 sm:py-40"><p className="font-mono text-xs uppercase tracking-[0.25em] text-[#75A7FF]">How it works</p><h2 className="mt-5 max-w-3xl text-4xl tracking-[-0.05em] sm:text-6xl">Reads. Executes. Observes. Verifies.</h2><div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{investigationSteps.map(([number, title, body]) => <div key={number} className="step-card border-t border-[#7890B5]/30 pt-5"><span className="font-mono text-xs text-[#75A7FF]">{number}</span><h3 className="mt-8 text-2xl">{title}</h3><p className="mt-3 leading-7 text-[#B7C4D9]">{body}</p></div>)}</div></section>

      <section className="border-t border-[#7890B5]/15 bg-[#0C172D] px-6 py-28 text-center sm:py-40"><p className="font-mono text-xs uppercase tracking-[0.25em] text-[#75A7FF]">For AI coding agents</p><h2 className="mx-auto mt-5 max-w-4xl text-4xl tracking-[-0.05em] sm:text-6xl">Build. Verify. Fix. Repeat.</h2><p className="mx-auto mt-7 max-w-2xl text-lg leading-8 text-[#B7C4D9]">Give your coding agent a verification layer that returns evidence instead of “looks good.”</p><button onClick={() => setIsExpanded(true)} className="mt-10 rounded-full bg-[#75A7FF] px-8 py-3 font-medium text-[#07132C]">Talk to the Wizard team</button></section>

      {isExpanded && <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#020611]/85 p-4 backdrop-blur-sm"><div className="relative max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-3xl border border-[#7890B5]/30 bg-[#0C172D] p-6 shadow-2xl sm:p-10"><button onClick={() => setIsExpanded(false)} aria-label="Close contact form" className="absolute right-5 top-5 rounded-full p-2 text-[#B7C4D9] hover:bg-[#172A48]"><X className="h-5 w-5" /></button><h2 className="text-3xl tracking-tight">Talk to the Wizard team</h2><p className="mt-4 leading-7 text-[#B7C4D9]">Whether you&apos;re a developer building with AI or a business exploring reliable AI powered software development, we&apos;d love to hear from you.</p><form onSubmit={handleSubmit} className="mt-8 space-y-5"><label className="block font-mono text-xs tracking-widest text-[#B7C4D9]">FULL NAME *<input required name="name" className="mt-2 w-full rounded-lg border border-[#294267] bg-[#071126] p-3 text-[#F4F7FF] outline-none focus:border-[#75A7FF]" /></label><label className="block font-mono text-xs tracking-widest text-[#B7C4D9]">WORK EMAIL *<input required type="email" name="email" className="mt-2 w-full rounded-lg border border-[#294267] bg-[#071126] p-3 text-[#F4F7FF] outline-none focus:border-[#75A7FF]" /></label><label className="block font-mono text-xs tracking-widest text-[#B7C4D9]">COMPANY / PROJECT WEBSITE<input type="url" name="website" className="mt-2 w-full rounded-lg border border-[#294267] bg-[#071126] p-3 text-[#F4F7FF] outline-none focus:border-[#75A7FF]" /></label><label className="block font-mono text-xs tracking-widest text-[#B7C4D9]">YOUR ROLE<select name="role" defaultValue="" className="mt-2 w-full rounded-lg border border-[#294267] bg-[#071126] p-3 text-[#F4F7FF] outline-none"><option value="">Select your role</option><option>Developer</option><option>Founder</option><option>Engineering Leader</option><option>Other</option></select></label><label className="block font-mono text-xs tracking-widest text-[#B7C4D9]">ANYTHING ELSE?<textarea name="message" rows={4} className="mt-2 w-full resize-none rounded-lg border border-[#294267] bg-[#071126] p-3 text-[#F4F7FF] outline-none focus:border-[#75A7FF]" /></label>{status === 'error' && <p className="text-sm text-[#FF9278]">Something went wrong. Please try again.</p>}<button disabled={status === 'submitting' || status === 'success'} type="submit" className={`flex h-12 w-full items-center justify-center rounded-full font-medium transition ${status === 'success' ? 'bg-[#55E6A5] text-[#071126]' : 'bg-[#F4F7FF] text-[#071126]'}`}>{status === 'success' ? <Check className="h-6 w-6" /> : status === 'submitting' ? 'Sending…' : 'Submit'}</button></form></div></div>}
    </div>
  )
}
