"use client"

import { ArrowUpRight, ExternalLink } from "lucide-react"

const links = [
  {
    label: "Wizard website",
    href: "https://wizardagents.vercel.app",
  },
  {
    label: "Documentation",
    href: "https://wizardagents.vercel.app",
  },
]

export function CinematicFooter() {
  return (
    <footer
      id="download"
      className="relative isolate overflow-hidden border-t border-[#EAF7FB]/10 bg-[#071F3A] px-6 py-20 text-[#F5FAFC] sm:px-10 sm:py-28"
    >
      {/* Oceanic depth */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(80% 65% at 50% 0%, rgba(127,198,230,.22), transparent 68%), radial-gradient(55% 55% at 85% 70%, rgba(46,124,192,.16), transparent 72%), linear-gradient(180deg, #123A6B 0%, #071F3A 78%)",
        }}
      />

      {/* Subtle grain */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.08]"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.5'/%3E%3C/svg%3E\")",
          mixBlendMode: "overlay",
        }}
      />

      <div className="relative mx-auto flex min-h-[70vh] w-full max-w-6xl flex-col justify-between gap-16">
        {/* System identity */}
        <div className="flex items-start justify-between gap-8">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[.32em] text-[#EAF7FB]/65">
              Wizard · repository verification
            </p>

            <p className="mt-2 max-w-md text-[10px] leading-relaxed text-[#B7CEDD]/55">
              Evidence driven verification for unfamiliar software
              repositories.
            </p>
          </div>

          <div className="flex items-center gap-2 rounded-full border border-[#EAF7FB]/15 bg-[#EAF7FB]/[0.06] px-3 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[#7FC6E6]" />

            <span className="font-mono text-[9px] uppercase tracking-[.18em] text-[#B7CEDD]/75">
              Coming soon
            </span>
          </div>
        </div>

        {/* Main statement */}
        <div className="grid gap-12 lg:grid-cols-[1.25fr_.75fr] lg:items-end">
          <div>
            <p className="mb-5 max-w-2xl text-sm leading-relaxed text-[#B7CEDD]/75">
              Wizard investigates unfamiliar repositories, verifies what
              actually works, and produces an evidence backed record of what
              it found.
            </p>

            <h2 className="max-w-4xl text-balance text-5xl font-semibold tracking-[-.06em] text-[#F5FAFC] sm:text-7xl lg:text-8xl">
              Build with proof.
            </h2>
          </div>

          {/* Verification state */}
          <div className="lg:justify-self-end">
            <div className="w-full min-w-[240px] border border-[#EAF7FB]/12 bg-[#EAF7FB]/[0.04] p-5">
              <div className="mb-5 flex items-center justify-between">
                <span className="font-mono text-[9px] uppercase tracking-[.24em] text-[#B7CEDD]/50">
                  System status
                </span>

                <span className="font-mono text-[9px] text-[#7FC6E6]">
                  READY
                </span>
              </div>

              <div className="space-y-3 font-mono text-[9px]">
                <div className="flex items-center justify-between">
                  <span className="text-[#B7CEDD]/55">
                    Investigation
                  </span>

                  <span className="text-[#EAF7FB]/75">
                    READY
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[#B7CEDD]/55">
                    Evidence
                  </span>

                  <span className="text-[#EAF7FB]/75">
                    TRACEABLE
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[#B7CEDD]/55">
                    Verification
                  </span>

                  <span className="text-[#EAF7FB]/75">
                    DETERMINISTIC
                  </span>
                </div>
              </div>

              <div className="mt-5 border-t border-[#EAF7FB]/10 pt-4">
                <span className="font-mono text-[8px] uppercase tracking-[.2em] text-[#B7CEDD]/40">
                  Evidence before conclusion
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <div className="grid gap-8 border-t border-[#EAF7FB]/12 pt-8 sm:grid-cols-2">
          {links.map((link) => (
            <a
              key={link.label}
              href={link.href}
              target="_blank"
              rel="noreferrer"
              className="group flex items-center justify-between border-b border-[#EAF7FB]/10 pb-3 text-sm text-[#B7CEDD]/70 transition-colors hover:text-[#F5FAFC]"
            >
              <span>{link.label}</span>

              <ArrowUpRight className="h-4 w-4 transition-transform group-hover:-translate-y-1 group-hover:translate-x-1" />
            </a>
          ))}
        </div>

        {/* Footer metadata */}
        <div className="flex flex-col gap-3 border-t border-[#EAF7FB]/10 pt-5 text-xs text-[#B7CEDD]/45 sm:flex-row sm:items-center sm:justify-between">
          <span>© 2026 Wizard</span>

          <a
            className="inline-flex items-center gap-2 transition-colors hover:text-[#F5FAFC]"
            href="https://wizardagents.vercel.app"
            target="_blank"
            rel="noreferrer"
          >
            wizardagents.vercel.app

            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </div>
    </footer>
  )
}

export default CinematicFooter