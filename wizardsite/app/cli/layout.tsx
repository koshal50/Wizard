import type { Metadata } from "next"
import Link from "next/link"
import type { ReactNode } from "react"

export const metadata: Metadata = {
  title: "Connect Wizard CLI | Wizard",
  description: "Preview the Wizard CLI account connection experience.",
  robots: { index: false, follow: false },
}

export default function CliLayout({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-dvh bg-[#071F3A] px-6 py-8 text-[#F5FAFC] sm:px-10 sm:py-12">
      <div className="mx-auto flex min-h-[calc(100dvh-6rem)] max-w-3xl flex-col">
        <Link href="/" className="w-fit rounded font-semibold tracking-tight text-[#EAF7FB] hover:text-[#7FC6E6] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#7FC6E6]">Wizard</Link>
        <div className="my-auto py-16 sm:py-24">{children}</div>
        <footer className="flex flex-wrap gap-x-6 gap-y-3 border-t border-white/10 pt-6 text-sm text-[#B7CEDD]">
          <span>Wizard CLI</span>
          <Link className="rounded hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#7FC6E6]" href="/privacy">Privacy policy</Link>
          <Link className="rounded hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#7FC6E6]" href="/terms">Terms and conditions</Link>
        </footer>
      </div>
    </main>
  )
}
