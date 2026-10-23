import type { ReactNode } from "react"

export const cliPrimaryLink = "inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-zinc-900 px-5 py-3 text-center text-sm font-medium text-white transition-colors hover:bg-zinc-800 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-zinc-500 disabled:opacity-50"
export const cliSecondaryLink = "inline-flex min-h-11 items-center justify-center rounded-md border border-zinc-200 bg-white px-5 py-3 text-center text-sm text-zinc-900 transition-colors hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-zinc-500 disabled:opacity-50"

export function CliHeading({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <p className="font-mono text-xs uppercase tracking-[.2em] text-zinc-500">Wizard / CLI connection</p>
      <h1 className="mt-4 max-w-xl text-balance text-4xl font-semibold leading-tight tracking-[-.035em] sm:text-5xl">{title}</h1>
      <p className="mt-5 max-w-xl text-base leading-relaxed text-zinc-500 sm:text-lg">{children}</p>
    </>
  )
}
