"use client"

import React, { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { Browser } from "@/components/ui/browser"

interface GradientProps extends React.HTMLAttributes<HTMLDivElement> {
  speed?: number
  colors?: string[]
  distortion?: number
  swirl?: number
  grainMixer?: number
  grainOverlay?: number
}

export function SafeMeshGradient({
  className,
  ...props
}: GradientProps) {
  return (
    <div
      aria-hidden="true"
      {...props}
      className={cn(
        "absolute inset-0 bg-[linear-gradient(135deg,#2452F1_0%,#163DB9_48%,#022474_100%)]",
        className
      )}
    />
  )
}

const stages = [
  "VS Code",
  "Terminal",
  "Repository",
  "Browser",
  "Report",
]

const code = [
  'import { verify } from "@wizard/agent"',
  "",
  "export async function run() {",
  "  const evidence = await verify({",
  '    target: "localhost:3000",',
  '    mode: "deep"',
  "  })",
  "  return evidence",
  "}",
]

const commands = [
  "wizard inspect .",
  "wizard read app/page.tsx",
  "wizard test --browser",
  "wizard report --save",
]

const files = [
  "app/page.tsx",
  "components/hero.tsx",
  "components/ui/",
  "lib/utils.ts",
  "package.json",
]

function Bar({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="window-bar">
      <i />
      <i />
      <i />

      <span>{children}</span>

      <b className="live-dot">LIVE</b>
    </div>
  )
}

function Workspace() {
  const [line, setLine] = useState(0)

  useEffect(() => {
    const id = window.setInterval(() => {
      setLine((v) => (v + 1) % (code.length + 1))
    }, 900)

    return () => window.clearInterval(id)
  }, [])

  const visibleCode = code.slice(
    0,
    Math.max(1, line)
  )

  return (
    <div
      data-screen-panel
      className="screen-panel"
    >
      <Bar>wizard-repo / VS Code</Bar>

      <div className="ide-body">
        <div className="file-tree">
          <b>EXPLORER</b>

          <span>⌄ wizard-repo</span>

          <em>◇ app/</em>
          <em>◇ components/</em>
          <em>◇ package.json</em>
          <em>◇ README.md</em>
        </div>

        <pre className="code-stream">
          <code>
            {visibleCode.map((text, i) => (
              <React.Fragment key={i}>
                <span
                  className={
                    i === line - 1
                      ? "code-current"
                      : ""
                  }
                >
                  {text || " "}
                </span>

                {i < visibleCode.length - 1 && "\n"}
              </React.Fragment>
            ))}

            <span className="typing-caret" />
          </code>
        </pre>
      </div>
    </div>
  )
}

function Terminal() {
  const [count, setCount] = useState(0)

  useEffect(() => {
    const id = window.setInterval(() => {
      setCount((v) => (v + 1) % (commands.length + 1))
    }, 1300)

    return () => window.clearInterval(id)
  }, [])

  return (
    <div
      className="absolute inset-0 flex flex-col bg-[#05080d] text-white"
      style={{
        zIndex: 10,
      }}
    >
      {/* Terminal window bar */}
      <div className="flex h-10 shrink-0 items-center border-b border-white/10 bg-[#0b1424] px-4 font-mono text-[10px] text-slate-300 sm:text-xs">
        <div className="mr-3 flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
          <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
          <span className="h-2.5 w-2.5 rounded-full bg-green-400" />
        </div>

        <span>terminal — wizard session</span>

        <span className="ml-auto rounded border border-green-400/30 px-2 py-0.5 text-[8px] text-green-400">
          LIVE
        </span>
      </div>

      {/* Terminal body */}
      <div
        className="relative flex-1 overflow-hidden p-5 font-mono text-[9px] leading-relaxed sm:p-8 sm:text-xs"
        style={{
          background:
            "radial-gradient(circle at top left, rgba(37,99,235,0.08), transparent 40%), #05080d",
        }}
      >
        {/* Scanlines */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "repeating-linear-gradient(0deg, rgba(255,255,255,0.025) 0px, rgba(255,255,255,0.025) 1px, transparent 1px, transparent 4px)",
          }}
        />

        {/* Actual terminal content */}
        <div className="relative z-10">
          {commands.slice(0, count).map((cmd, i) => (
            <div
              key={cmd}
              className="mb-5"
            >
              <div>
                <span className="text-cyan-400">
                  wizard@repo
                </span>

                <span className="text-slate-500">
                  {" "}
                  ~/wizard-repo
                </span>

                <span className="text-white">
                  {" "}
                  $
                </span>

                <span className="ml-2 text-white">
                  {cmd}
                </span>
              </div>

              <div className="mt-1 text-green-400/80">
                ✓ completed —{" "}
                {i === 0
                  ? "structure mapped"
                  : i === 1
                    ? "source indexed"
                    : i === 2
                      ? "browser verified"
                      : "report written"}
              </div>
            </div>
          ))}

          {/* Current prompt */}
          <div className="mt-2">
            <span className="text-cyan-400">
              wizard@repo
            </span>

            <span className="text-slate-500">
              {" "}
              ~/wizard-repo
            </span>

            <span className="text-white">
              {" "}
              $
            </span>

            <span className="ml-2 inline-block h-4 w-2 animate-pulse bg-white align-middle" />
          </div>
        </div>
      </div>
    </div>
  )
}

function Repository() {
  const [active, setActive] = useState(0)

  useEffect(() => {
    const id = window.setInterval(() => {
      setActive(
        (v) => (v + 1) % files.length
      )
    }, 850)

    return () => window.clearInterval(id)
  }, [])

  return (
    <div
      data-screen-panel
      className="screen-panel"
    >
      <Bar>agent activity / repository map</Bar>

      <div className="repo-map">
        <div className="repo-column">
          <b>REPOSITORY STRUCTURE</b>

          {files.map((file, i) => (
            <div
              className={cn(
                "repo-file",
                i === active &&
                "repo-file-active"
              )}
              key={file}
            >
              <span className="repo-fire">
                ◆
              </span>

              {file}
            </div>
          ))}
        </div>

        <div className="agent-log">
          <p>Agent reading</p>

          <strong>
            {files[active]}
          </strong>

          <p className="success">
            ✓ scanning source symbols
          </p>

          <p className="success">
            ✓ {active + 14} files mapped
          </p>
        </div>
      </div>
    </div>
  )
}

function BrowserPanel() {
  return (
    <div
      data-screen-panel
      className="screen-panel"
    >
      <Browser
  initialUrl="https://wizardagents.vercel.app"
  initialTabs={[
    {
      id: "wizard",
      title: "wizardagents.vercel.app",
      url: "https://wizardagents.vercel.app",
    },
  ]}
  showWindowControls={false}
  showBookmarksBar={false}
  showStatusBar={false}
  enableTabManagement={true}
  enableBookmarks={true}
  enableHistory={true}
  enableDownloads={false}
  enableSettings={false}
  className="h-full rounded-none border-0 shadow-none"
/>

      <span
        className="browser-agent-cursor"
        aria-hidden="true"
      >
        <span />
      </span>
    </div>
  )
}

function Report() {
  return (
    <div
      data-screen-panel
      className="screen-panel"
    >
      <Bar>wizard / live verification report</Bar>

      <div className="report-copy">
        <div className="report-mark">
          ✓
        </div>

        <div>
          <span className="muted">
            LIVE TRACE
          </span>

          <h3>
            Tracing the evidence.
          </h3>

          <p>
            Re-opening relevant files,
            executing checks, and verifying
            the browser path.
          </p>
        </div>
      </div>

      <div className="report-timeline">
        <span>
          ✓ app/page.tsx reopened
        </span>

        <span>
          ✓ wizard test --browser executed
        </span>

        <span className="report-pulse">
          ● browser evidence captured
        </span>
      </div>
    </div>
  )
}

function getStageFromProgress(
  progress: number
) {
  if (progress < 0.2) {
    return 0
  }

  if (progress < 0.4) {
    return 1
  }

  if (progress < 0.6) {
    return 2
  }

  if (progress < 0.8) {
    return 3
  }

  return 4
}

export function CinematicHero({
  className,
}: {
  className?: string
}) {
  const root = useRef<HTMLElement>(null)

  const [active, setActive] = useState(0)

  useEffect(() => {
    const onScroll = () => {
      const el = root.current

      if (!el) {
        return
      }

      const rect =
        el.getBoundingClientRect()

      const scrollableDistance = Math.max(
        1,
        el.offsetHeight -
        window.innerHeight
      )

      /*
       * Because the section moves upward
       * relative to the viewport as the
       * user scrolls, its top becomes
       * increasingly negative.
       *
       * Example:
       *
       * section top = 0
       * progress = 0
       *
       * section top = -3100
       * progress ≈ 0.5
       *
       * section top = -6200
       * progress ≈ 1
       */
      const progress = Math.min(
        0.999,
        Math.max(
          0,
          -rect.top /
          scrollableDistance
        )
      )

      const nextStage =
        getStageFromProgress(progress)

      setActive((current) =>
        current === nextStage
          ? current
          : nextStage
      )
    }

    window.addEventListener(
      "scroll",
      onScroll,
      { passive: true }
    )

    onScroll()

    return () => {
      window.removeEventListener(
        "scroll",
        onScroll
      )
    }
  }, [])

  return (
    <section
      ref={root}
      className={cn(
        "relative min-h-[6200px] overflow-visible bg-transparent font-sans",
        className
      )}
    >
      <div className="sticky top-0 flex min-h-screen w-full items-center justify-center overflow-hidden">
        <div className="scene-card relative flex min-h-screen w-full items-center justify-center overflow-hidden text-white">
          <SafeMeshGradient />

          <div className="relative z-20 flex w-full max-w-[1540px] flex-col items-center gap-8 px-4 py-12 lg:flex-row lg:gap-14 lg:px-10">
            <div className="w-full max-w-[350px] shrink-0">
              <p className="mb-3 font-mono text-[10px] uppercase tracking-[.3em] text-blue-100/70">
                Wizard investigation
              </p>

              <h2 className="text-balance text-3xl font-semibold leading-[1.05] tracking-tight sm:text-4xl lg:text-5xl">
                AI writes the code.
                Wizard checks the
                reality.
              </h2>

              <p className="mt-5 text-sm leading-relaxed text-blue-50/80">
                Watch an agent read,
                execute, browse, and
                verify the work.
              </p>
            </div>

            <div className="relative w-full max-w-[1060px] lg:ml-4">
              <div className="rounded-t-2xl border-8 border-zinc-700 bg-zinc-950 p-2 shadow-2xl sm:rounded-t-3xl sm:border-[14px] sm:p-5">
                <div className="screen relative aspect-[16/10] overflow-hidden rounded-lg bg-[#07101f] font-mono text-[8px] sm:text-[11px] md:text-xs">

                  <div className="absolute left-0 right-0 top-0 z-30 flex gap-3 overflow-hidden border-b border-white/10 bg-[#0b1424] px-3 py-2 text-[7px] text-slate-400 sm:text-[10px]">
                    {stages.map(
                      (stage, i) => (
                        <span
                          key={stage}
                          className={cn(
                            "whitespace-nowrap",
                            i === active &&
                            "text-white"
                          )}
                        >
                          {stage}
                        </span>
                      )
                    )}
                  </div>

                  {active === 0 && (
                    <Workspace />
                  )}

                  {active === 1 && (
                    <Terminal />
                  )}

                  {active === 2 && (
                    <Repository />
                  )}

                  {active === 3 && (
                    <BrowserPanel />
                  )}

                  {active === 4 && (
                    <Report />
                  )}
                </div>
              </div>

              <div className="mx-auto h-3 w-[92%] rounded-b-xl bg-zinc-700 sm:h-5 sm:rounded-b-2xl" />

              <div className="mx-auto h-2 w-1/3 rounded-b-full bg-zinc-600 sm:h-3" />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

export default CinematicHero