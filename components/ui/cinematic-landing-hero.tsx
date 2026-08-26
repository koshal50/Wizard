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
import MacOSDock from "@/components/ui/mac-os-dock"

interface GradientProps
  extends React.HTMLAttributes<HTMLDivElement> {
  speed?: number
  colors?: string[]
  distortion?: number
  swirl?: number
  grainMixer?: number
  grainOverlay?: number
}

type AppId =
  | "finder"
  | "vscode"
  | "terminal"
  | "wizard"
  | "browser"
  | "report"

const applications: AppId[] = [
  "finder",
  "vscode",
  "terminal",
  "wizard",
  "browser",
  "report",
]

const applicationNames: Record<AppId, string> = {
  finder: "Finder",
  vscode: "VS Code",
  terminal: "Terminal",
  wizard: "Wizard",
  browser: "Browser",
  report: "Verification Report",
}

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
  "wizard verify runtime",
  "wizard inspect .",
  "npm install",
  "npm start",
]

const repositoryFiles = [
  "package.json",
  "README.md",
  "app/page.tsx",
  "components/hero.tsx",
  "lib/utils.ts",
  "Dockerfile",
]

function clamp(value: number) {
  return Math.min(1, Math.max(0, value))
}

function ease(value: number) {
  const x = clamp(value)
  return x * x * (3 - 2 * x)
}

function phase(
  value: number,
  start: number,
  end: number
) {
  if (value <= start) return 0
  if (value >= end) return 1

  return ease(
    (value - start) /
      Math.max(0.0001, end - start)
  )
}

/* =========================================================
   OCEANIC BACKGROUND
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
        <filter id="wizard-ocean-grain">
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
          filter="url(#wizard-ocean-grain)"
        />
      </svg>
    </div>
  )
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
    <div className="flex h-8 shrink-0 items-center border-b border-white/10 bg-[#0b1424] px-3 font-mono">
      <div className="flex gap-1.5">
        <span className="h-2 w-2 rounded-full bg-red-400" />
        <span className="h-2 w-2 rounded-full bg-yellow-300" />
        <span className="h-2 w-2 rounded-full bg-green-400" />
      </div>

      <span className="ml-3 truncate text-[7px] text-slate-300 sm:text-[9px]">
        {title}
      </span>

      {status && (
        <span className="ml-auto text-[6px] uppercase tracking-[.18em] text-slate-500 sm:text-[7px]">
          {status}
        </span>
      )}
    </div>
  )
}

/* =========================================================
   FINDER
========================================================= */

function FinderSurface() {
  const [active, setActive] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActive(
        value =>
          (value + 1) %
          repositoryFiles.length
      )
    }, 1900)

    return () =>
      window.clearInterval(timer)
  }, [])

  return (
    <div className="absolute inset-0 overflow-hidden">
      <WindowBar
        title="wizard repo / Finder"
        status="repository"
      />

      <div className="grid h-[calc(100%-32px)] grid-cols-[30%_70%] bg-[#111827]">
        <div className="overflow-hidden border-r border-white/5 p-4 font-mono text-[7px] text-slate-500 sm:p-6 sm:text-[8px]">
          <div className="mb-4 text-[6px] uppercase tracking-[.2em] text-slate-400 sm:text-[7px]">
            Repository
          </div>

          <div className="mb-2 text-slate-300">
            ⌄ wizard repo
          </div>

          <FileTree
            data={wizardFileStructure}
            className="text-[7px] sm:text-[8px]"
          />
        </div>

        <div className="p-5 sm:p-8">
          <div className="font-mono text-[6px] uppercase tracking-[.2em] text-slate-600 sm:text-[7px]">
            Repository Manifest
          </div>

          <h3 className="mt-3 text-lg font-medium text-white sm:text-2xl">
            Fast scan
          </h3>

          <p className="mt-3 max-w-md text-[8px] leading-relaxed text-slate-500 sm:text-[9px]">
            Wizard starts with metadata.
            File names, directories,
            extensions and sizes are
            available before source
            contents are requested.
          </p>

          <div className="mt-8 max-w-lg rounded-lg border border-white/10 bg-white/[0.025] p-4 sm:mt-10">
            <div className="font-mono text-[6px] uppercase tracking-[.18em] text-slate-600">
              Reading
            </div>

            <div className="mt-2 font-mono text-xs text-white sm:text-sm">
              {repositoryFiles[active]}
            </div>

            <div className="mt-4 flex gap-3 font-mono text-[6px] text-blue-300/70 sm:text-[7px]">
              <span>metadata</span>
              <span>indexed</span>
              <span>available</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* =========================================================
   VS CODE
========================================================= */

function VSCodeSurface() {
  const [line, setLine] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setLine(
        value =>
          (value + 1) %
          (code.length + 1)
      )
    }, 1450)

    return () =>
      window.clearInterval(timer)
  }, [])

  const visible =
    code.slice(
      0,
      Math.max(1, line)
    )

  return (
    <div className="absolute inset-0 overflow-hidden">
      <WindowBar
        title="wizard repo / VS Code"
        status="workspace"
      />

      <div className="grid h-[calc(100%-32px)] grid-cols-[22%_78%] bg-[#111827]">
        <div className="border-r border-white/5 p-3 font-mono text-[6px] text-slate-500 sm:p-5 sm:text-[7px]">
          <div className="mb-4 text-[6px] uppercase tracking-[.2em] text-slate-400">
            Explorer
          </div>

          <div className="mb-2 text-slate-300">
            ⌄ wizard repo
          </div>

          <div className="rounded bg-blue-500/10 px-2 py-1.5 text-blue-200">
            ◇ app/
          </div>

          <div className="px-2 py-1.5">
            ◇ components/
          </div>

          <div className="px-2 py-1.5">
            ◇ package.json
          </div>

          <div className="px-2 py-1.5">
            ◇ README.md
          </div>
        </div>

        <pre className="m-0 overflow-hidden p-5 font-mono text-[7px] leading-[2] text-slate-300 sm:p-8 sm:text-[10px]">
          <code>
            {visible.map(
              (text, index) => (
                <React.Fragment
                  key={index}
                >
                  <span
                    className={cn(
                      index ===
                        visible.length - 1 &&
                        "rounded bg-blue-500/10 text-white"
                    )}
                  >
                    {text || " "}
                  </span>

                  {index <
                    visible.length - 1 &&
                    "\n"}
                </React.Fragment>
              )
            )}

            <span className="ml-1 inline-block h-3 w-[2px] animate-pulse bg-blue-300" />
          </code>
        </pre>
      </div>
    </div>
  )
}

/* =========================================================
   TERMINAL
========================================================= */

function TerminalSurface() {
  const [count, setCount] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCount(
        value =>
          (value + 1) %
          (commands.length + 1)
      )
    }, 1850)

    return () =>
      window.clearInterval(timer)
  }, [])

  return (
    <div className="absolute inset-0 overflow-hidden">
      <WindowBar
        title="terminal / wizard session"
        status="active"
      />

      <div className="relative h-[calc(100%-32px)] overflow-hidden bg-[#05080d] p-5 font-mono text-[7px] leading-[1.8] sm:p-8 sm:text-[10px]">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,.11),transparent_45%)]" />

        <div className="relative">
          {commands
            .slice(0, count)
            .map(
              (
                command,
                index
              ) => (
                <div
                  key={command}
                  className="mb-5 sm:mb-6"
                >
                  <div>
                    <span className="text-cyan-400">
                      wizard@repo
                    </span>

                    <span className="text-slate-500">
                      {" "}
                      ~/wizard repo $
                    </span>

                    <span className="ml-2 text-white">
                      {command}
                    </span>
                  </div>

                  <div className="mt-1 text-emerald-400/75">
                    {index === 0 &&
                      "investigation request created"}

                    {index === 1 &&
                      "repository manifest generated"}

                    {index === 2 &&
                      "dependencies installed"}

                    {index === 3 &&
                      "runtime listening on port 3000"}
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
              ~/wizard repo $
            </span>

            <span className="ml-2 inline-block h-3 w-[2px] animate-pulse bg-white align-middle" />
          </div>
        </div>
      </div>
    </div>
  )
}

/* =========================================================
   WIZARD
========================================================= */

function WizardSurface() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <WindowBar
        title="wizard / autonomous investigation"
        status="runtime"
      />

      <div className="h-[calc(100%-32px)] overflow-hidden bg-[#081321] p-5 font-mono sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[6px] uppercase tracking-[.2em] text-slate-600">
              Investigation
            </div>

            <h3 className="mt-2 text-lg font-medium text-white sm:text-2xl">
              verify runtime
            </h3>

            <div className="mt-1 text-[6px] text-slate-600 sm:text-[7px]">
              inv_7f31
            </div>
          </div>

          <div className="rounded-full border border-blue-300/15 bg-blue-300/[0.04] px-2 py-1 text-[6px] text-blue-200/70 sm:px-3 sm:py-1.5 sm:text-[7px]">
            Runtime Engine
          </div>
        </div>

        <div className="mt-8 grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:mt-11 sm:gap-4">
          <div className="rounded-lg border border-blue-300/15 bg-blue-300/[0.035] p-3 sm:p-4">
            <div className="text-[5px] uppercase tracking-[.18em] text-slate-600 sm:text-[6px]">
              Investigation Node
            </div>

            <div className="mt-2 text-[10px] text-white sm:text-sm">
              inspect runtime
            </div>

            <div className="mt-2 text-[6px] text-blue-300/70 sm:text-[7px]">
              hypothesis attached
            </div>
          </div>

          <div className="text-sm text-slate-700 sm:text-xl">
            →
          </div>

          <div className="rounded-lg border border-amber-300/15 bg-amber-300/[0.035] p-3 sm:p-4">
            <div className="text-[5px] uppercase tracking-[.18em] text-slate-600 sm:text-[6px]">
              Runtime Action
            </div>

            <div className="mt-2 text-[10px] text-white sm:text-sm">
              execute command
            </div>

            <div className="mt-2 text-[6px] text-amber-300/70 sm:text-[7px]">
              npm start
            </div>
          </div>
        </div>

        <div className="my-5 h-px bg-white/5 sm:my-7" />

        <div className="grid grid-cols-2 gap-2 sm:gap-4">
          <div className="rounded-lg border border-emerald-300/15 bg-emerald-300/[0.025] p-3 sm:p-4">
            <div className="text-[5px] uppercase tracking-[.18em] text-slate-600 sm:text-[6px]">
              Observation
            </div>

            <div className="mt-2 text-[10px] text-white sm:text-sm">
              obs_034
            </div>

            <div className="mt-2 text-[6px] text-emerald-300/75 sm:text-[7px]">
              exit code 0
            </div>
          </div>

          <div className="rounded-lg border border-blue-300/15 bg-blue-300/[0.025] p-3 sm:p-4">
            <div className="text-[5px] uppercase tracking-[.18em] text-slate-600 sm:text-[6px]">
              Claim
            </div>

            <div className="mt-2 text-[10px] text-white sm:text-sm">
              runtime starts
            </div>

            <div className="mt-2 text-[6px] text-emerald-300/75 sm:text-[7px]">
              trust · high
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* =========================================================
   BROWSER
========================================================= */

function BrowserSurface() {
  return (
    <div className="absolute inset-0 overflow-hidden">
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
    </div>
  )
}

/* =========================================================
   REPORT
========================================================= */

function ReportSurface() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <WindowBar
        title="wizard / verification report"
        status="available"
      />

      <div className="h-[calc(100%-32px)] overflow-hidden bg-[#081321]">
        <AIAgentPipeline />
      </div>
    </div>
  )
}

function Surface({
  app,
}: {
  app: AppId
}) {
  switch (app) {
    case "finder":
      return <FinderSurface />

    case "vscode":
      return <VSCodeSurface />

    case "terminal":
      return <TerminalSurface />

    case "wizard":
      return <WizardSurface />

    case "browser":
      return <BrowserSurface />

    case "report":
      return <ReportSurface />
  }
}

/* =========================================================
   DOCK
========================================================= */

const dockApps = [
  {
    id: "finder",
    name: "Finder",
    icon:
      "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%232A80FF'/%3E%3Cpath d='M8 11.5C8 9.57 9.57 8 11.5 8h9C22.43 8 24 9.57 24 11.5v9c0 1.93-1.57 3.5-3.5 3.5h-9C9.57 24 8 22.43 8 20.5v-9Z' fill='white' fill-opacity='.92'/%3E%3Ccircle cx='13' cy='15' r='1.5' fill='%232A80FF'/%3E%3Ccircle cx='19' cy='15' r='1.5' fill='%232A80FF'/%3E%3Cpath d='M12 19c2.5 1.8 5.5 1.8 8 0' stroke='%232A80FF' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E",
  },
  {
    id: "vscode",
    name: "VS Code",
    icon: "",
  },
  {
    id: "terminal",
    name: "Terminal",
    icon:
      "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%231B1B1B'/%3E%3Cpath d='m9 11 5 5-5 5' stroke='%23fff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpath d='M16 21h7' stroke='%2394A3B8' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E",
  },
  {
    id: "wizard",
    name: "Wizard",
    icon:
      "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%230B1424'/%3E%3Cpath d='M16 6 18.7 13.3 26 16l-7.3 2.7L16 26l-2.7-7.3L6 16l7.3-2.7L16 6Z' fill='%2360A5FA'/%3E%3Ccircle cx='16' cy='16' r='3' fill='white' fill-opacity='.9'/%3E%3C/svg%3E",
  },
  {
    id: "browser",
    name: "Browser",
    icon:
      "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%23F8FAFC'/%3E%3Ccircle cx='16' cy='16' r='9' fill='none' stroke='%232563EB' stroke-width='2'/%3E%3Cpath d='M7 16h18M16 7c3 3 4.5 6 4.5 9s-1.5 6-4.5 9M16 7c-3 3-4.5 6-4.5 9s1.5 6 4.5 9' stroke='%232563EB' stroke-width='1.2'/%3E%3C/svg%3E",
  },
  {
    id: "report",
    name: "Verification Report",
    icon:
      "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%23E5E7EB'/%3E%3Cpath d='M10 7h9l4 4v14H10V7Z' fill='white' stroke='%239CA3AF'/%3E%3Cpath d='M19 7v5h4M13 16h7M13 20h7' stroke='%236B7280' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E",
  },
]

/* =========================================================
   CINEMATIC HERO
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

      if (!element) return

      const rect =
        element.getBoundingClientRect()

      const distance =
        Math.max(
          1,
          element.offsetHeight -
            window.innerHeight
        )

      const next =
        clamp(
          -rect.top /
            distance
        )

      setProgress(next)
    }

    const onScroll = () => {
      if (frame) return

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

      if (frame) {
        window.cancelAnimationFrame(
          frame
        )
      }
    }
  }, [])

  /*
   * ========================================================
   * APPLICATION STAGE
   * ========================================================
   */

  const raw =
    progress *
    applications.length

  const stage =
    Math.min(
      applications.length - 1,
      Math.floor(raw)
    )

  const local =
    raw -
    Math.floor(raw)

  const current =
    applications[stage]

  const next =
    stage <
    applications.length - 1
      ? applications[stage + 1]
      : null

  /*
   * ========================================================
   * ONE OUTER CINEMATIC OBJECT
   * ========================================================
   */

  const sceneEntry =
    phase(
      progress,
      0,
      0.16
    )

  const sceneExit =
    phase(
      progress,
      0.88,
      1
    )

  const sceneScale =
    0.78 +
    sceneEntry * 0.22 -
    sceneExit * 0.22

  const sceneRadius =
    36 -
    sceneEntry * 36 +
    sceneExit * 36

  /*
   * ========================================================
   * APPLICATION HANDOFF
   * ========================================================
   */

  const minimize =
    phase(
      local,
      0.72,
      0.80
    )

  const desktop =
    phase(
      local,
      0.78,
      0.85
    )

  const dock =
    phase(
      local,
      0.83,
      0.89
    )

  const pointer =
    phase(
      local,
      0.88,
      0.94
    )

  const click =
    phase(
      local,
      0.93,
      0.96
    )

  const opening =
    phase(
      local,
      0.96,
      1
    )

  /*
   * Only outgoing application minimizes.
   */

  const outgoingScale =
    1 -
    minimize * 0.58

  const outgoingX =
    -minimize * 17

  const outgoingY =
    -minimize * 11

  const outgoingRotation =
    -minimize * 1.2

  const outgoingOpacity =
    1 -
    desktop * 0.48

  /*
   * Next application is full display size.
   * It only slides upward.
   */

  const incomingY =
    100 -
    opening * 100

  const desktopOpacity =
    next
      ? desktop
      : 0

  const dockVisible =
    next
      ? dock *
        (1 - opening)
      : 0

  const nextIndex =
    next
      ? applications.indexOf(next)
      : stage

  const iconFraction =
    applications.length <= 1
      ? 0.5
      : nextIndex /
        (applications.length - 1)

  const cursorX =
    40 +
    (25 +
      iconFraction * 50 -
      40) *
      pointer

  const cursorY =
    56 +
    31 *
      pointer

  return (
    <section
      ref={root}
      className={cn(
        "relative min-h-[15000px] overflow-visible bg-transparent font-sans",
        className
      )}
    >
      <div className="sticky top-0 h-screen w-full overflow-hidden">

        {/* =====================================================
            ONE CINEMATIC SCENE
            Background + text + MacBook all scale together.
           ===================================================== */}

        <div
          className="absolute left-1/2 top-1/2"
          style={{
            width:
              "100vw",
            height:
              "100vh",
            transform:
              `translate(-50%,-50%) scale(${sceneScale})`,
            transformOrigin:
              "center center",
            willChange:
              "transform",
          }}
        >

          {/* ===================================================
              OCEANIC BACKGROUND
             =================================================== */}

          <div
            aria-hidden="true"
            className="absolute inset-0 overflow-hidden"
            style={{
              borderRadius:
                `${sceneRadius}px`,
            }}
          >
            <SafeMeshGradient />
          </div>

          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_45%,rgba(255,255,255,.08),transparent_52%)]" />

          {/* ===================================================
              SCENE CONTENT

              Responsive composition only.
             =================================================== */}

          <div className="absolute inset-0 flex items-center justify-center">
            <div
              className="
                flex
                w-full
                max-w-[1540px]
                flex-col
                items-center
                gap-8
                px-4
                sm:gap-10
                md:gap-12
                lg:flex-row
                lg:gap-14
                lg:px-10
              "
            >

              {/* =================================================
                  TEXT
                 ================================================= */}

              <div className="w-full max-w-[340px] shrink-0 lg:w-[340px]">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-[.3em] text-blue-100/70">
                  Wizard investigation
                </p>

                <h2 className="text-balance text-3xl font-semibold leading-[1.05] tracking-tight sm:text-4xl lg:text-5xl">
                  AI writes the code.
                  <br />
                  Wizard checks the
                  reality.
                </h2>

                <p className="mt-5 max-w-[310px] text-sm leading-relaxed text-blue-50/80">
                  Wizard works inside
                  the workflow you
                  already use.
                </p>

                <p className="mt-8 font-mono text-[7px] uppercase tracking-[.24em] text-blue-100/35">
                  {applicationNames[current]}
                </p>
              </div>

              {/* =================================================
                  MACBOOK
                 ================================================= */}

              <div
                className="
                  relative
                  w-full
                  max-w-[1180px]
                  shrink-0
                  sm:w-[92vw]
                  md:w-[88vw]
                  lg:w-full
                "
              >
                <div className="relative aspect-[650/400] w-full">

                  <MacbookPro
                    className="absolute inset-0 h-full w-full text-[#07101f] drop-shadow-2xl"
                    aria-label="Wizard autonomous investigation"
                    role="img"
                  >
                    <div
                      className="screen relative h-full w-full overflow-hidden bg-[#111827]"
                      style={{
                        isolation:
                          "isolate",
                      }}
                    >

                      {/* =================================================
                          DESKTOP
                         ================================================= */}

                      <div
                        className="absolute inset-0 z-0"
                        style={{
                          opacity:
                            desktopOpacity,
                          background:
                            "radial-gradient(circle at 50% 25%,rgba(104,154,255,.4),transparent 32%),radial-gradient(circle at 20% 72%,rgba(48,94,170,.32),transparent 35%),linear-gradient(145deg,#1b3154 0%,#0d1b32 48%,#050b15 100%)",
                        }}
                      />

                      {/* =================================================
                          CURRENT APPLICATION
                         ================================================= */}

                      <div
                        className="absolute inset-0 z-20 overflow-hidden"
                        style={{
                          transform:
                            `translate3d(${outgoingX}%,${outgoingY}%,0) scale(${outgoingScale}) rotate(${outgoingRotation}deg)`,
                          transformOrigin:
                            "center center",
                          opacity:
                            outgoingOpacity,
                          pointerEvents:
                            "none",
                        }}
                      >
                        <Surface
                          app={current}
                        />
                      </div>

                      {/* =================================================
                          NEXT APPLICATION
                         ================================================= */}

                      {next &&
                        opening >
                          0 && (
                          <div
                            className="absolute inset-0 z-40 overflow-hidden"
                            style={{
                              transform:
                                `translate3d(0,${incomingY}%,0)`,
                              opacity:
                                opening,
                              pointerEvents:
                                "none",
                            }}
                          >
                            <Surface
                              app={next}
                            />
                          </div>
                        )}

                      {/* =================================================
                          DOCK
                         ================================================= */}

                      <div
                        className="absolute bottom-[5%] left-1/2 z-[100]"
                        style={{
                          opacity:
                            dockVisible,
                          transform:
                            `translate3d(-50%,${(1 - dockVisible) * 18}px,0)`,
                          pointerEvents:
                            dockVisible >
                            0.96
                              ? "auto"
                              : "none",
                        }}
                      >
                        <MacOSDock
                          apps={
                            dockApps
                          }
                          onAppClick={() => {}}
                          openApps={
                            next
                              ? [next]
                              : [current]
                          }
                          className="scale-[.72] sm:scale-[.78] md:scale-[.84]"
                        />
                      </div>

                      {/* =================================================
                          WIZARD CURSOR
                         ================================================= */}

                      {next &&
                        pointer >
                          0 &&
                        opening ===
                          0 && (
                          <div
                            aria-hidden="true"
                            className="pointer-events-none absolute z-[150] hidden md:block"
                            style={{
                              left:
                                `${cursorX}%`,
                              top:
                                `${cursorY}%`,
                              transform:
                                `translate(-6px,-5px) scale(${
                                  click >
                                  0.2
                                    ? 0.82
                                    : 1
                                })`,
                              filter:
                                "drop-shadow(0 2px 3px rgba(0,0,0,.5))",
                            }}
                          >
                            <svg
                              width="18"
                              height="22"
                              viewBox="0 0 22 25"
                              fill="none"
                            >
                              <path
                                d="M18.8 18.4 12.1 3.2c-.5-1.2-2.2-1.2-2.7 0L2.4 18.4c-.7 1.6.9 3.1 2.5 2.4l5.9-2.2c.2-.1.5-.1.7 0l5.8 2.2c1.6.7 2.3-.9 1.5-2.4Z"
                                fill="#111827"
                                stroke="white"
                                strokeWidth="1.4"
                              />
                            </svg>

                            {click >
                              0.2 && (
                              <span className="absolute -right-2 -bottom-2 h-4 w-4 rounded-full border border-blue-300/80 bg-blue-400/20" />
                            )}
                          </div>
                        )}
                    </div>
                  </MacbookPro>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

export default CinematicHero