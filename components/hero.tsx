'use client'

import { useEffect, useRef, useState } from 'react'
import { Check, X } from 'lucide-react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { AsciiArt } from '@/components/ui/sss'
import { createClient } from '@supabase/supabase-js'

gsap.registerPlugin(ScrollTrigger)

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
)

const steps = [
  ['Reads', 'Maps the repository and finds the signals that matter.'],
  ['Executes', 'Runs commands, installs dependencies, and starts the software.'],
  ['Observes', 'Collects logs, ports, test results, and runtime behavior.'],
  ['Verifies', 'Separates what is proven from what is still uncertain.'],
]

export default function Hero() {
  const scrolly = useRef<HTMLDivElement>(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle')

  useEffect(() => {
    const context = gsap.context(() => {
      gsap.from('.hero-copy', { opacity: 0, y: 28, duration: 1, ease: 'power3.out' })
      gsap.from('.story-card', {
        y: 260, rotationX: 22, opacity: 0,
        scrollTrigger: { trigger: '.story', start: 'top 80%', end: 'center center', scrub: 1 },
      })
      gsap.from('.story-line', {
        opacity: 0, x: -30, stagger: 0.12,
        scrollTrigger: { trigger: '.story', start: 'top 60%', end: 'center center', scrub: 1 },
      })
      gsap.to('.story-progress', {
        width: '100%',
        scrollTrigger: { trigger: '.story', start: 'top 55%', end: 'bottom 70%', scrub: 1 },
      })
    }, scrolly)
    return () => context.revert()
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
    <div ref={scrolly} className="overflow-hidden bg-[#050B18] text-[#F4F7FF]">
      <section className="relative flex min-h-screen items-center justify-center px-6 py-28">
        <div className="absolute inset-0"><AsciiArt className="h-full w-full object-cover" /></div>
        <div className="hero-copy relative z-10 mx-auto max-w-4xl text-center">
          <h1 className="text-balance text-5xl font-medium leading-[0.94] tracking-[-0.065em] sm:text-7xl md:text-8xl">Build with AI.<br /><span className="text-[#75A7FF]">Verify with Wizard.</span></h1>
          <p className="mx-auto mt-8 max-w-2xl text-pretty text-lg leading-8 text-[#B7C4D9] sm:text-xl">Let Wizard investigate, execute, and verify your software automatically so you can build faster with confidence.</p>
          <button onClick={() => setIsExpanded(true)} className="mt-10 rounded-full bg-[#F4F7FF] px-7 py-3 font-medium text-[#07132C] transition hover:bg-[#75A7FF]">Request a demo</button>
        </div>
      </section>

      <section className="story relative border-y border-[#7890B5]/15 bg-[#102653] px-6 py-32 sm:py-44">
        <div className="mx-auto grid max-w-6xl items-center gap-14 lg:grid-cols-2">
          <div><p className="font-mono text-xs uppercase tracking-[0.25em] text-[#75A7FF]">Wizard investigates</p><h2 className="mt-5 text-4xl leading-tight tracking-[-0.05em] sm:text-6xl">Not a guess. An investigation.</h2><p className="mt-7 max-w-lg text-lg leading-8 text-[#B7C4D9]">Give Wizard a repository. It explores the code, executes what matters, observes the result, and verifies what actually happened.</p></div>
          <div className="story-card mx-auto w-full max-w-[520px] rounded-[2rem] border border-[#7890B5]/30 bg-[#071126] p-5 shadow-2xl [perspective:1200px]">
            <div className="rounded-xl border border-[#294267] bg-[#050B18] p-5 font-mono text-sm leading-8 text-[#9DB1CF]"><div className="mb-5 border-b border-[#294267] pb-4 text-[#75A7FF]">wizard verify</div>{steps.map(([title, body]) => <div className="story-line" key={title}><span className="text-[#55E6A5]">✓</span> {title}: {body}</div>)}<div className="mt-5 h-1 overflow-hidden rounded bg-[#172A48]"><div className="story-progress h-full w-0 bg-[#55E6A5]" /></div></div>
          </div>
        </div>
      </section>

      {isExpanded && <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#020611]/85 p-4 backdrop-blur-sm"><div className="relative max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-3xl border border-[#7890B5]/30 bg-[#0C172D] p-6 shadow-2xl sm:p-10"><button onClick={() => setIsExpanded(false)} aria-label="Close contact form" className="absolute right-5 top-5 rounded-full p-2 text-[#B7C4D9] hover:bg-[#172A48]"><X className="h-5 w-5" /></button><h2 className="text-3xl tracking-tight">Talk to the Wizard team</h2><p className="mt-4 leading-7 text-[#B7C4D9]">Whether you&apos;re a developer building with AI or a business exploring reliable AI powered software development, we&apos;d love to hear from you.</p><form onSubmit={handleSubmit} className="mt-8 space-y-5"><label className="block font-mono text-xs tracking-widest text-[#B7C4D9]">FULL NAME *<input required name="name" className="mt-2 w-full rounded-lg border border-[#294267] bg-[#071126] p-3 text-[#F4F7FF] outline-none focus:border-[#75A7FF]" /></label><label className="block font-mono text-xs tracking-widest text-[#B7C4D9]">WORK EMAIL *<input required type="email" name="email" className="mt-2 w-full rounded-lg border border-[#294267] bg-[#071126] p-3 text-[#F4F7FF] outline-none focus:border-[#75A7FF]" /></label><label className="block font-mono text-xs tracking-widest text-[#B7C4D9]">COMPANY / PROJECT WEBSITE<input type="url" name="website" className="mt-2 w-full rounded-lg border border-[#294267] bg-[#071126] p-3 text-[#F4F7FF] outline-none focus:border-[#75A7FF]" /></label><label className="block font-mono text-xs tracking-widest text-[#B7C4D9]">YOUR ROLE<select name="role" defaultValue="" className="mt-2 w-full rounded-lg border border-[#294267] bg-[#071126] p-3 text-[#F4F7FF] outline-none"><option value="">Select your role</option><option>Developer</option><option>Founder</option><option>Engineering Leader</option><option>Other</option></select></label><label className="block font-mono text-xs tracking-widest text-[#B7C4D9]">WHAT ARE YOU BUILDING?<textarea name="message" rows={4} className="mt-2 w-full rounded-lg border border-[#294267] bg-[#071126] p-3 text-[#F4F7FF] outline-none focus:border-[#75A7FF]" /></label><button disabled={status === 'submitting'} className={`flex min-h-12 w-full items-center justify-center rounded-xl font-medium transition ${status === 'success' ? 'bg-[#55E6A5] text-white' : 'bg-[#75A7FF] text-[#07132C]'}`}>{status === 'success' ? <Check className="h-6 w-6" /> : status === 'submitting' ? 'Submitting…' : 'Submit'}</button>{status === 'error' && <p className="text-sm text-[#FF9278]">Something went wrong. Please try again.</p>}</form></div></div>}
    </div>
  )
}
