import Link from "next/link"
import type React from "react"

export function PolicyPage({ title, eyebrow, updated, children }: { title: string; eyebrow: string; updated: string; children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-[#071F3A] px-6 py-16 text-[#F5FAFC] sm:px-10 lg:px-16">
      <div className="mx-auto max-w-3xl">
        <Link href="/" className="font-mono text-xs uppercase tracking-[.2em] text-[#B7CEDD]/70 hover:text-white">← Wizard</Link>
        <p className="mt-20 font-mono text-xs uppercase tracking-[.25em] text-[#7FC6E6]">{eyebrow}</p>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-6xl">{title}</h1>
        <p className="mt-4 text-sm text-[#B7CEDD]/70">Last updated: {updated}</p>
        <article className="policy-content mt-12">{children}</article>
        <div className="mt-16 border-t border-white/10 pt-6 text-sm text-[#B7CEDD]/65">Questions? Contact <a className="text-[#EAF7FB] underline underline-offset-4" href="mailto:shivamgawali585@gmail.com">shivamgawali585@gmail.com</a>.</div>
      </div>
    </main>
  )
}

export function PolicySection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section><h2>{title}</h2>{children}</section>
}

export function PolicyList({ items }: { items: string[] }) {
  return <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
}

export const policyContact = "Wizard, currently under development, can be contacted at shivamgawali585@gmail.com. No separate physical mailing address or incorporated legal entity has been provided yet; this must be completed before launch."

export const policyDisclaimer = "This template is informational and is not legal advice. Have a qualified lawyer review these policies for the countries where Wizard is offered before launch."
