import type { ReactNode } from "react"

export const cliPrimaryLink = "inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-[#7FC6E6]/25 bg-[#123A6B] px-6 py-3 text-center text-sm font-medium text-[#EAF7FB] shadow-[0_8px_30px_rgba(18,58,107,0.35)] transition-colors hover:bg-[#1b4a8c] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#7FC6E6]"
export const cliSecondaryLink = "inline-flex min-h-12 items-center justify-center rounded-full border border-white/20 px-6 py-3 text-center text-sm text-[#EAF7FB] transition-colors hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#7FC6E6]"

export function CliHeading({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <p className="font-mono text-xs uppercase tracking-[.2em] text-[#7FC6E6]">Wizard / CLI connection</p>
      <h1 className="mt-4 max-w-xl text-balance text-4xl font-semibold leading-tight tracking-[-.035em] sm:text-5xl">{title}</h1>
      <p className="mt-5 max-w-xl text-base leading-relaxed text-[#B7CEDD] sm:text-lg">{children}</p>
    </>
  )
}
