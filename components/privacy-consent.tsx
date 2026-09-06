"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

export function PrivacyConsent() {
  const [visible, setVisible] = useState(false)
  useEffect(() => { setVisible(document.cookie.includes("wizard_consent=1") === false) }, [])
  if (!visible) return null
  const dismiss = () => { document.cookie = "wizard_consent=1; Max-Age=31536000; Path=/; SameSite=Lax"; setVisible(false) }
  return <aside aria-label="Privacy notice" className="fixed inset-x-4 bottom-4 z-[200] mx-auto max-w-2xl rounded-2xl border border-white/15 bg-[#071F3A]/95 p-5 text-[#F5FAFC] shadow-2xl backdrop-blur-xl"><p className="font-mono text-[10px] uppercase tracking-[.2em] text-[#7FC6E6]">Privacy first</p><p className="mt-2 text-sm leading-6 text-[#B7CEDD]">Wizard does not currently use analytics or optional tracking. We use only what is necessary for the site to work. Read our <Link className="text-white underline underline-offset-4" href="/privacy">privacy policy</Link> and <Link className="text-white underline underline-offset-4" href="/cookies">cookie policy</Link>.</p><div className="mt-4 flex flex-wrap gap-3"><button type="button" onClick={dismiss} className="rounded-full bg-[#EAF7FB] px-5 py-2 text-sm font-medium text-[#071F3A] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7FC6E6]">Continue</button><Link href="/cookies" className="rounded-full border border-white/20 px-5 py-2 text-sm text-[#EAF7FB] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7FC6E6]">Cookie details</Link></div></aside>
}
