"use client"

import React, {
  useEffect,
  useRef,
  useState,
} from "react"
import { cn } from "@/lib/utils"
import { Browser } from "@/components/ui/browser"
import {
  FileTree,
  wizardFileStructure,
} from "@/components/ui/file-tree"
import { MacbookPro } from "@/components/ui/macbook-pro"
import AIAgentPipeline from "@/components/ui/ai-agent-pipeline"

interface GradientProps
  extends React.HTMLAttributes<HTMLDivElement> {
  speed?: number
  colors?: string[]
  distortion?: number
  swirl?: number
  grainMixer?: number
  grainOverlay?: number
}

/* =========================================================
   BACKGROUND
========================================================= */

export function SafeMeshGradient({
  className,
  ...props
}: GradientProps) {
  return (
    <div
      aria-hidden="true"
      {...props}
      className={cn(
        "absolute inset-0 overflow-hidden",
        className
      )}
    >
      <div
        className="absolute inset-0"
        style={{
          backgroundColor: "#123A6B",
          backgroundImage:
            "url(\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)' opacity='0.215'/></svg>\"), radial-gradient(150% 48.4% at 41.58% 6%, rgba(234,247,251,.92) 0%, rgba(234,247,251,0) 53%), radial-gradient(150% 48.4% at 42.42% 33%, rgba(127,198,230,.92) 0%, rgba(127,198,230,0) 53%), radial-gradient(150% 48.4% at 51.19% 67%, rgba(46,124,192,.92) 0%, rgba(46,124,192,0) 53%), radial-gradient(150% 48.4% at 53.67% 94%, rgba(18,58,107,.92) 0%, rgba(18,58,107,0) 53%)",
          backgroundSize:
            "120px 120px, auto, auto, auto, auto",
          backgroundBlendMode:
            "overlay, normal, normal, normal, normal",
        }}
      />

      <svg
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 h-full w-full"
        style={{
          opacity: 0.215,
          mixBlendMode: "overlay",
        }}
      >
        <filter id="wizard-oceanic-grain">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.8"
            numOctaves="2"
            stitchTiles="stitch"
          />

          <feColorMatrix
            type="saturate"
            values="0"
          />
        </filter>

        <rect
          width="100%"
          height="100%"
          filter="url(#wizard-oceanic-grain)"
        />
      </svg>
    </div>
  )
}

/* =========================================================
   DATA
========================================================= */

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
  "wizard read package.json",
  "wizard verify runtime",
  "wizard test --browser",
]

const files = [
  "package.json",
  "README.md",
  "app/page.tsx",
  "components/hero.tsx",
  "lib/utils.ts",
]

function clamp(
  value: number,
  min = 0,
  max = 1
) {
  return Math.min(
    max,
    Math.max(min, value)
  )
}

function smooth(value: number) {
  const x = clamp(value)
  return x * x * (3 - 2 * x)
}

/* =========================================================
   WINDOW BAR
========================================================= */

function WindowBar({
  title,
  status,
}: {
  title: string
  status?: string
}) {
  return (
    <div
      className="flex h-7 shrink-0 items-center gap-1.5 border-b border-white/10 bg-[#0b1424] px-2.5 font-mono"
    >
      <div className="flex gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
        <span className="h-1.5 w-1.5 rounded-full bg-yellow-300" />
        <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
      </div>

      <span className="ml-1 truncate text-[6px] text-slate-300 sm:text-[7px]">
        {title}
      </span>

      {status && (
        <span className="ml-auto shrink-0 text-[5px] uppercase tracking-[.15em] text-emerald-400">
          {status}
        </span>
      )}
    </div>
  )
}

/* =========================================================
   BASE WINDOW
========================================================= */

function Window({
  children,
  style,
  className,
}: {
  children: React.ReactNode
  style?: React.CSSProperties
  className?: string
}) {
  return (
    <div
      className={cn(
        "absolute overflow-hidden rounded-md border border-white/10 bg-[#0b1424] shadow-[0_18px_40px_rgba(0,0,0,.3)]",
        className
      )}
      style={{
        willChange:
          "transform, opacity",
        ...style,
      }}
    >
      {children}
    </div>
  )
}

/* =========================================================
   VS CODE
========================================================= */

function WorkspaceWindow({
  progress,
}: {
  progress: number
}) {
  const amount = smooth(
    clamp(progress / 0.22)
  )

  const lines = Math.max(
    1,
    Math.min(
      code.length,
      Math.floor(
        amount * code.length
      ) + 1
    )
  )

  return (
    <Window
      className="left-[3%] top-[7%] z-10 h-[51%] w-[56%]"
      style={{
        opacity: 0.98,
        transform: `
          translate3d(
            0,
            ${(1 - amount) * 12}px,
            0
          )
          scale(${0.98 + amount * 0.02})
        `,
      }}
    >
      <WindowBar
        title="wizard repo / VS Code"
        status="INSPECTING"
      />

      <div className="grid h-[calc(100%-28px)] grid-cols-[25%_75%] bg-[#111827]">
        <div className="flex flex-col gap-1.5 overflow-hidden border-r border-white/5 p-2 font-mono text-[5px] text-slate-500 sm:text-[6px]">
          <b className="mb-1 text-[5px] tracking-[.15em] text-slate-400">
            EXPLORER
          </b>

          <span className="text-slate-400">
            ⌄ wizard repo
          </span>

          <span className="rounded bg-blue-500/10 px-1.5 py-1 text-blue-200">
            ◇ package.json
          </span>

          <span>
            ◇ README.md
          </span>

          <span>
            ◇ app/
          </span>

          <span>
            ◇ components/
          </span>

          <span>
            ◇ lib/
          </span>
        </div>

        <pre className="m-0 overflow-hidden p-3 font-mono text-[6px] leading-[1.8] text-slate-300 sm:text-[7px]">
          <code>
            {code
              .slice(0, lines)
              .map((line, index) => (
                <React.Fragment
                  key={index}
                >
                  <span
                    className={
                      index === lines - 1
                        ? "bg-blue-500/10 text-white"
                        : ""
                    }
                  >
                    {line || " "}
                  </span>

                  {index <
                    lines - 1 &&
                    "\n"}
                </React.Fragment>
              ))}

            <span className="ml-1 inline-block h-2 w-[2px] animate-pulse bg-blue-300" />
          </code>
        </pre>
      </div>
    </Window>
  )
}

/* =========================================================
   TERMINAL
========================================================= */

function TerminalWindow({
  progress,
}: {
  progress: number
}) {
  const amount = smooth(
    clamp(
      (progress - 0.13) /
        0.27
    )
  )

  const visible = Math.max(
    0,
    Math.min(
      commands.length,
      Math.floor(
        amount *
          commands.length
      )
    )
  )

  return (
    <Window
      className="right-[3%] top-[10%] z-20 h-[45%] w-[54%]"
      style={{
        opacity:
          progress < 0.12
            ? 0
            : amount,
        transform: `
          translate3d(
            ${(1 - amount) * 20}px,
            ${(1 - amount) * 14}px,
            0
          )
          scale(${0.97 + amount * 0.03})
        `,
      }}
    >
      <WindowBar
        title="terminal / wizard session"
        status={
          visible >=
          commands.length
            ? "EXIT 0"
            : "RUNNING"
        }
      />

      <div className="relative h-[calc(100%-28px)] overflow-hidden bg-[#05080d] p-3 font-mono text-[6px] leading-[1.6] sm:p-4 sm:text-[7px]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,.09),transparent_45%)]" />

        <div className="relative">
          {commands
            .slice(0, visible)
            .map(
              (
                command,
                index
              ) => (
                <div
                  key={command}
                  className="mb-3"
                >
                  <div>
                    <span className="text-cyan-400">
                      wizard@repo
                    </span>

                    <span className="text-slate-500">
                      {" "}
                      ~/wizard-repo $
                    </span>

                    <span className="text-white">
                      {" "}
                      {command}
                    </span>
                  </div>

                  <div className="mt-1 text-green-400/80">
                    ✓{" "}
                    {index === 0
                      ? "repository structure mapped"
                      : index === 1
                        ? "source indexed"
                        : index === 2
                          ? "runtime verified"
                          : "browser verification requested"}
                  </div>
                </div>
              )
            )}

          <div>
            <span className="text-cyan-400">
              wizard@repo
            </span>

            <span className="text-slate-500">
              {" "}
              ~/wizard-repo $
            </span>

            <span className="ml-1 inline-block h-2 w-[2px] animate-pulse bg-white align-middle" />
          </div>
        </div>
      </div>
    </Window>
  )
}

/* =========================================================
   REPOSITORY
========================================================= */

function RepositoryWindow({
  progress,
}: {
  progress: number
}) {
  const amount = smooth(
    clamp(
      (progress - 0.31) /
        0.24
    )
  )

  const activeFile =
    files[
      Math.min(
        files.length - 1,
        Math.floor(
          amount * files.length
        )
      )
    ]

  return (
    <Window
      className="bottom-[4%] left-[3%] z-30 h-[42%] w-[53%]"
      style={{
        opacity:
          progress < 0.3
            ? 0
            : amount,
        transform: `
          translate3d(
            ${(1 - amount) * -18}px,
            ${(1 - amount) * 18}px,
            0
          )
          scale(${0.97 + amount * 0.03})
        `,
      }}
    >
      <WindowBar
        title="agent activity / repository map"
        status="READING"
      />

      <div className="grid h-[calc(100%-28px)] grid-cols-[55%_45%] bg-[#081321]">
        <div className="overflow-hidden border-r border-white/5 p-2">
          <div className="mb-2 font-mono text-[5px] tracking-[.15em] text-slate-500">
            REPOSITORY STRUCTURE
          </div>

          <FileTree
            data={wizardFileStructure}
            className="max-h-[90%] overflow-hidden text-[6px]"
          />
        </div>

        <div className="p-3 font-mono">
          <div className="text-[5px] tracking-[.15em] text-slate-500">
            AGENT READING
          </div>

          <strong className="mt-2 block text-[7px] text-blue-100">
            {activeFile}
          </strong>

          <div className="mt-3 space-y-1.5 text-[5px] text-emerald-400/75">
            <div>
              ✓ scanning source symbols
            </div>

            <div>
              ✓ 18 files mapped
            </div>

            <div>
              ✓ dependency relationship found
            </div>
          </div>

          <div className="mt-4 text-[5px] leading-relaxed text-slate-600">
            trace → investigation
            node → observation
          </div>
        </div>
      </div>
    </Window>
  )
}

/* =========================================================
   KNOWLEDGE GRAPH
========================================================= */

function KnowledgeWindow({
  progress,
}: {
  progress: number
}) {
  const amount = smooth(
    clamp(
      (progress - 0.43) /
        0.2
    )
  )

  return (
    <Window
      className="bottom-[5%] right-[3%] z-40 h-[35%] w-[48%]"
      style={{
        opacity:
          progress < 0.42
            ? 0
            : amount,
        transform: `
          translate3d(
            ${(1 - amount) * 18}px,
            ${(1 - amount) * 16}px,
            0
          )
          scale(${0.97 + amount * 0.03})
        `,
      }}
    >
      <WindowBar
        title="knowledge graph / evidence"
        status="VALIDATING"
      />

      <div className="h-[calc(100%-28px)] bg-[#091523] p-3 font-mono">
        <div className="flex justify-between text-[5px] tracking-[.15em]">
          <span className="text-slate-400">
            WHAT WE KNOW
          </span>

          <span className="text-emerald-400">
            RUNTIME OWNED
          </span>
        </div>

        <div className="mt-5 flex items-center gap-2">
          <div className="min-w-0 flex-1 rounded border border-amber-300/15 bg-amber-300/[0.03] p-2">
            <small className="block text-[4px] text-slate-500">
              OBSERVATION
            </small>

            <strong className="mt-1 block text-[6px] text-white">
              obs_031
            </strong>

            <p className="mt-1 text-[5px] leading-relaxed text-slate-500">
              package.json declares
              Node.js 18
            </p>
          </div>

          <div className="h-px w-4 bg-emerald-400/50" />

          <div className="min-w-0 flex-1 rounded border border-emerald-300/15 bg-emerald-300/[0.03] p-2">
            <small className="block text-[4px] text-slate-500">
              CLAIM
            </small>

            <strong className="mt-1 block text-[6px] text-white">
              Runtime = Node.js 18
            </strong>

            <p className="mt-1 text-[5px] text-emerald-400">
              TRUST · HIGH
            </p>
          </div>
        </div>

        <div className="absolute bottom-2 left-3 right-3 flex justify-between border-t border-white/5 pt-1.5 text-[4px] text-slate-600">
          <span>
            immutable observation
          </span>

          <span>
            evidence engine
          </span>

          <span>
            claim validated
          </span>
        </div>
      </div>
    </Window>
  )
}

/* =========================================================
   BROWSER
========================================================= */

function BrowserWindow({
  progress,
}: {
  progress: number
}) {
  const amount = smooth(
    clamp(
      (progress - 0.59) /
        0.22
    )
  )

  return (
    <Window
      className="left-[18%] top-[14%] z-50 h-[70%] w-[78%] bg-white"
      style={{
        opacity:
          progress < 0.58
            ? 0
            : amount,
        transform: `
          translate3d(
            ${(1 - amount) * 24}px,
            ${(1 - amount) * -10}px,
            0
          )
          scale(${0.96 + amount * 0.04})
        `,
      }}
    >
      <Browser
        initialUrl="https://wizardagents.vercel.app"
        initialTabs={[
          {
            id: "wizard",
            title:
              "wizardagents.vercel.app",
            url:
              "https://wizardagents.vercel.app",
          },
        ]}
        showWindowControls={false}
        showBookmarksBar={false}
        showStatusBar={false}
        enableTabManagement
        enableBookmarks
        enableHistory
        enableDownloads={false}
        enableSettings={false}
        className="h-full rounded-none border-0 shadow-none"
      />

      <div className="pointer-events-none absolute bottom-2 left-2 flex items-center gap-1 rounded-full border border-slate-200 bg-white/90 px-2 py-1 font-mono text-[5px] text-slate-500 shadow-sm backdrop-blur">
        <span className="h-1 w-1 rounded-full bg-emerald-500" />
        browser evidence captured
      </div>
    </Window>
  )
}

/* =========================================================
   REPORT
========================================================= */

function ReportWindow({
  progress,
}: {
  progress: number
}) {
  const amount = smooth(
    clamp(
      (progress - 0.73) /
        0.24
    )
  )

  const ready =
    progress > 0.94

  return (
    <Window
      className="left-[8%] top-[6%] z-[100] h-[84%] w-[86%]"
      style={{
        opacity:
          progress < 0.72
            ? 0
            : amount,
        transform: `
          translate3d(
            0,
            ${(1 - amount) * 22}px,
            0
          )
          scale(${0.95 + amount * 0.05})
        `,
      }}
    >
      <WindowBar
        title="wizard / verification report"
        status={
          ready
            ? "CONVERGED"
            : "ASSEMBLING"
        }
      />

      <div className="relative h-[calc(100%-28px)] overflow-hidden bg-[#081321]">
        <AIAgentPipeline />

        <div className="pointer-events-none absolute bottom-2 left-3 right-3 flex justify-between border-t border-white/5 pt-1.5 font-mono text-[4px] text-slate-600">
          <span>
            3 claims
          </span>

          <span>
            9 observations
          </span>

          <span>
            0 contradictions
          </span>

          <span className="text-emerald-400/70">
            {ready
              ? "CONVERGENCE REACHED"
              : "EVALUATING"}
          </span>
        </div>
      </div>
    </Window>
  )
}

/* =========================================================
   STAGE LABEL
========================================================= */

function StageLabel({
  progress,
}: {
  progress: number
}) {
  let label = "DISCOVERY"

  if (progress >= 0.18)
    label = "EXECUTION"

  if (progress >= 0.36)
    label = "INVESTIGATION"

  if (progress >= 0.54)
    label = "EVIDENCE"

  if (progress >= 0.7)
    label = "VERIFICATION"

  if (progress >= 0.9)
    label = "CONVERGENCE"

  return (
    <div className="mt-7 flex items-center gap-2 font-mono text-[7px] uppercase tracking-[.2em] text-blue-100/60">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 shadow-[0_0_10px_rgba(110,231,183,.7)]" />

      {label}
    </div>
  )
}

/* =========================================================
   HERO
========================================================= */

export function CinematicHero({
  className,
}: {
  className?: string
}) {
  const root =
    useRef<HTMLElement>(null)

  const [progress, setProgress] =
    useState(0)

  useEffect(() => {
    let frame = 0

    const update = () => {
      frame = 0

      const element =
        root.current

      if (!element)
        return

      const rect =
        element.getBoundingClientRect()

      const distance = Math.max(
        1,
        element.offsetHeight -
          window.innerHeight
      )

      const value = clamp(
        -rect.top / distance
      )

      setProgress(value)
    }

    const onScroll = () => {
      if (frame)
        return

      frame =
        window.requestAnimationFrame(
          update
        )
    }

    window.addEventListener(
      "scroll",
      onScroll,
      { passive: true }
    )

    window.addEventListener(
      "resize",
      onScroll,
      { passive: true }
    )

    update()

    return () => {
      window.removeEventListener(
        "scroll",
        onScroll
      )

      window.removeEventListener(
        "resize",
        onScroll
      )

      if (frame)
        window.cancelAnimationFrame(
          frame
        )
    }
  }, [])

  const intro =
    smooth(
      clamp(progress / 0.12)
    )

  const scale =
    0.94 + intro * 0.06

  const radius =
    20 - intro * 20

  return (
    <section
      ref={root}
      className={cn(
        "relative min-h-[7200px] overflow-visible bg-transparent font-sans",
        className
      )}
    >
      <div className="sticky top-0 flex min-h-screen w-full items-center justify-center overflow-hidden">
        <div
          className="scene-card relative flex min-h-screen w-full items-center justify-center overflow-hidden text-white"
          style={{
            transform: `scale(${scale})`,
            borderRadius: `${radius}px`,
            transformOrigin:
              "center center",
          }}
        >
          <SafeMeshGradient />

          <div className="pointer-events-none absolute inset-0 z-10 bg-[radial-gradient(circle_at_60%_45%,rgba(255,255,255,.08),transparent_45%)]" />

          <div className="relative z-20 flex w-full max-w-[1540px] flex-col items-center gap-8 px-4 py-12 lg:flex-row lg:gap-14 lg:px-10">
            <div className="w-full max-w-[350px] shrink-0">
              <p className="mb-3 font-mono text-[10px] uppercase tracking-[.3em] text-blue-100/70">
                Wizard investigation
              </p>

              <h2 className="text-balance text-3xl font-semibold leading-[1.05] tracking-tight sm:text-4xl lg:text-5xl">
                AI writes the
                code.
                <br />
                Wizard checks the
                reality.
              </h2>

              <p className="mt-5 max-w-[320px] text-sm leading-relaxed text-blue-50/80">
                Watch an autonomous
                investigation inspect,
                execute, browse, and
                verify the work.
              </p>

              <StageLabel
                progress={progress}
              />
            </div>

            <div className="relative w-full max-w-[1180px] lg:ml-4">
              <div className="relative aspect-[650/400] w-full">
                <MacbookPro
                  className="absolute inset-0 h-full w-full text-[#07101f] drop-shadow-2xl"
                  aria-label="Wizard autonomous repository investigation"
                  role="img"
                >
                  <div className="screen relative h-full w-full overflow-hidden bg-[#07101f] font-mono">
                    {/* Permanent MacBook workspace header */}

                    <div className="absolute left-0 right-0 top-0 z-[300] flex h-7 items-center border-b border-white/10 bg-[#0b1424] px-3">
                      <span className="text-[7px] font-medium tracking-[.16em] text-white/85 sm:text-[9px]">
                        WIZARD
                      </span>

                      <span className="mx-2 text-[7px] text-white/20">
                        /
                      </span>

                      <span className="text-[6px] text-slate-500 sm:text-[8px]">
                        autonomous investigation
                      </span>

                      <div className="ml-auto flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(74,222,128,.7)]" />

                        <span className="text-[5px] uppercase tracking-[.12em] text-emerald-300/75 sm:text-[7px]">
                          {progress >
                          0.94
                            ? "converged"
                            : "investigating"}
                        </span>
                      </div>
                    </div>

                    {/* Workspace starts below permanent header */}

                    <div className="absolute inset-x-0 bottom-0 top-7 overflow-hidden">
                      <WorkspaceWindow
                        progress={
                          progress
                        }

                      />

                      <TerminalWindow
                        progress={
                          progress
                        }
                      />

                      <RepositoryWindow
                        progress={
                          progress
                        }
                      />

                      <KnowledgeWindow
                        progress={
                          progress
                        }
                      />

                      <BrowserWindow
                        progress={
                          progress
                        }
                      />

                      <ReportWindow
                        progress={
                          progress
                        }
                      />
                    </div>
                  </div>
                </MacbookPro>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

export default CinematicHero