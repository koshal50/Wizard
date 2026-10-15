import Link from "next/link"
import { CircleCheck, Terminal } from "lucide-react"
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

export function CliPreviewNotice({ children }: { children: ReactNode }) {
  return <p className="mt-8 max-w-xl border-l-2 border-[#7FC6E6]/50 pl-4 text-sm leading-6 text-[#B7CEDD]"><strong className="font-medium text-[#EAF7FB]">UI preview.</strong> {children}</p>
}

// Design preview only. Mount a real completion state only after the future
// backend confirms authorization; visiting this component grants no access.
export function CliCompletionPreview() {
  return (
    <section aria-labelledby="completion-heading">
      <p className="font-mono text-xs uppercase tracking-[.2em] text-[#7FC6E6]">Completion preview</p>
      <CircleCheck aria-hidden="true" className="mt-6 h-12 w-12 text-[#7FC6E6]" strokeWidth={1.5} />
      <h1 id="completion-heading" className="mt-5 text-4xl font-semibold tracking-tight sm:text-5xl">Ready to return to Wizard CLI</h1>
      <p className="mt-5 max-w-xl leading-relaxed text-[#B7CEDD]">Once your connection is confirmed, you can return to your terminal and continue with Wizard CLI.</p>
      <CliPreviewNotice>This is the future success screen. No account or CLI has been connected.</CliPreviewNotice>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Link href="/" className={cliPrimaryLink}>Return to website</Link>
        <Link href="/cli/connect" className={cliSecondaryLink}>Back to connection preview</Link>
      </div>
    </section>
  )
}

export function CliCodePlaceholder() {
  return (
    <section aria-labelledby="code-heading" className="mt-8 max-w-xl rounded-2xl border border-[#7FC6E6]/25 bg-[#123A6B]/40 p-6 sm:p-8">
      <div className="flex items-center gap-3 text-[#7FC6E6]">
        <Terminal aria-hidden="true" className="h-5 w-5 shrink-0" />
        <h2 id="code-heading" className="font-mono text-xs uppercase tracking-[.15em]">Authorization code</h2>
      </div>
      <div className="mt-5 rounded-xl border border-dashed border-[#7FC6E6]/40 bg-[#071F3A] px-4 py-6 text-center font-mono text-lg text-[#EAF7FB]">Code will appear here</div>
      <p className="mt-5 text-sm leading-6 text-[#B7CEDD]">Once authorization is available, copy your one-time code and enter it in Wizard CLI to finish connecting your account.</p>
      <p className="mt-4 border-t border-white/10 pt-4 text-sm text-[#B7CEDD]">Expiration: available when a real code is issued.</p>
    </section>
  )
}
