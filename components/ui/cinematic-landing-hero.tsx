"use client"

import React, {
  useEffect,
  useMemo,
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

const apps = [
  {
    id: "finder",
    name: "Repository",
    icon: "https://cdn.jim-nielsen.com/macos/1024/finder-2021-09-10.png?rf=1024",
  },
  {
    id: "vscode",
    name: "VS Code",
    icon: "https://cdn.jim-nielsen.com/macos/1024/visual-studio-code-2021-06-03.png?rf=1024",
  },
  {
    id: "terminal",
    name: "Terminal",
    icon: "https://cdn.jim-nielsen.com/macos/1024/terminal-2021-06-03.png?rf=1024",
  },
  {
    id: "wizard",
    name: "Wizard",
    icon: "https://cdn.jim-nielsen.com/macos/1024/terminal-2021-06-03.png?rf=1024",
  },
  {
    id: "browser",
    name: "Browser",
    icon: "https://cdn.jim-nielsen.com/macos/1024/safari-2021-06-02.png?rf=1024",
  },
  {
    id: "report",
    name: "Report",
    icon: "https://cdn.jim-nielsen.com/macos/1024/notes-2021-05-25.png?rf=1024",
  },
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

function ease(value: number) {
  const x = clamp(value)
  return x * x * (3 - 2 * x)
}

function between(
  progress: number,
  start: number,
  end: number
) {
  return ease(
    (progress - start) /
      Math.max(0.001, end - start)
  )
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

function Surface({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="absolute inset-0 overflow-hidden">
      {children}
    </div>
  )
}

function RepositorySurface() {
  const [active, setActive] =
    useState(0)

  useEffect(() => {
    const timer =
      window.setInterval(() => {
        setActive(
          value =>
            (value + 1) %
            repositoryFiles.length
        )
      }, 1500)

    return () =>
      window.clearInterval(timer)
  }, [])

  return (
    <Surface>
      <WindowBar
        title="wizard repo / Finder"
        status="repository"
      />

      <div className="grid h-[calc(100%-32px)] grid-cols-[32%_68%] bg-[#111827]">
        <div className="overflow-hidden border-r border-white/5 p-5 font-mono text-[8px] text-slate-500">
          <div className="mb-4 text-[7px] tracking-[.2em] text-slate-400">
            REPOSITORY
          </div>

          <div className="mb-2 text-slate-300">
            ⌄ wizard-repo
          </div>

          <FileTree
            data={wizardFileStructure}
            className="text-[8px]"
          />
        </div>

        <div className="p-7 font-mono">
          <div className="text-[7px] uppercase tracking-[.2em] text-slate-600">
            Repository manifest
          </div>

          <h3 className="mt-3 text-xl font-medium text-white">
            Fast scan
          </h3>

          <p className="mt-3 max-w-md text-[9px] leading-relaxed text-slate-500">
            File names, directories,
            extensions and metadata
            are available before
            source contents are requested.
          </p>

          <div className="mt-8 rounded-lg border border-white/10 bg-white/[0.025] p-4">
            <div className="text-[7px] uppercase tracking-[.18em] text-slate-600">
              Current target
            </div>

            <div className="mt-2 text-sm text-white">
              {repositoryFiles[active]}
            </div>

            <div className="mt-4 flex gap-2 text-[7px] text-blue-300/70">
              <span>source</span>
              <span>indexed</span>
              <span>available</span>
            </div>
          </div>
        </div>
      </div>
    </Surface>
  )
}

function VSCodeSurface() {
  const [line, setLine] =
    useState(0)

  useEffect(() => {
    const timer =
      window.setInterval(() => {
        setLine(
          value =>
            (value + 1) %
            (code.length + 1)
        )
      }, 1200)

    return () =>
      window.clearInterval(timer)
  }, [])

  const visible =
    code.slice(
      0,
      Math.max(1, line)
    )

  return (
    <Surface>
      <WindowBar
        title="wizard-repo / VS Code"
        status="workspace"
      />

      <div className="grid h-[calc(100%-32px)] grid-cols-[23%_77%] bg-[#111827]">
        <div className="border-r border-white/5 p-4 font-mono text-[7px] text-slate-500">
          <div className="mb-4 text-[6px] tracking-[.2em] text-slate-400">
            EXPLORER
          </div>

          <div className="mb-2 text-slate-300">
            ⌄ wizard-repo
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

          <div className="px-2 py-1.5">
            ◇ Dockerfile
          </div>
        </div>

        <pre className="m-0 overflow-hidden p-7 font-mono text-[8px] leading-[2] text-slate-300 sm:text-[10px]">
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
    </Surface>
  )
}

function TerminalSurface() {
  const [count, setCount] =
    useState(0)

  useEffect(() => {
    const timer =
      window.setInterval(() => {
        setCount(
          value =>
            (value + 1) %
            (commands.length + 1)
        )
      }, 1500)

    return () =>
      window.clearInterval(timer)
  }, [])

  return (
    <Surface>
      <WindowBar
        title="terminal / wizard session"
        status="active"
      />

      <div className="relative h-[calc(100%-32px)] overflow-hidden bg-[#05080d] p-7 font-mono text-[9px] leading-[1.8] sm:text-[11px]">
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
                  className="mb-6"
                >
                  <div>
                    <span className="text-cyan-400">
                      wizard@repo
                    </span>

                    <span className="text-slate-500">
                      {" "}
                      ~/wizard-repo $
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
                      "server listening on port 3000"}
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

            <span className="ml-2 inline-block h-3 w-[2px] animate-pulse bg-white align-middle" />
          </div>
        </div>
      </div>
    </Surface>
  )
}

function WizardSurface({
  progress,
}: {
  progress: number
}) {
  const phase =
    progress < 0.32
      ? "planning"
      : progress < 0.58
        ? "executing"
        : progress < 0.76
          ? "evaluating"
          : "converging"

  return (
    <Surface>
      <WindowBar
        title="wizard / investigation"
        status={phase}
      />

      <div className="h-[calc(100%-32px)] bg-[#081321] p-7 font-mono">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[7px] uppercase tracking-[.2em] text-slate-600">
              Investigation
            </div>

            <h3 className="mt-2 text-xl font-medium text-white">
              verify runtime
            </h3>

            <div className="mt-1 text-[7px] text-slate-600">
              inv_7f31
            </div>
          </div>

          <div className="rounded-full border border-blue-300/15 bg-blue-300/[0.04] px-3 py-1.5 text-[7px] text-blue-200/70">
            Runtime Engine
          </div>
        </div>

        <div className="mt-10 grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <div className="rounded-lg border border-blue-300/15 bg-blue-300/[0.035] p-4">
            <div className="text-[6px] uppercase tracking-[.18em] text-slate-600">
              Investigation Node
            </div>

            <div className="mt-2 text-sm text-white">
              inspect runtime
            </div>

            <div className="mt-2 text-[7px] text-blue-300/70">
              hypothesis attached
            </div>
          </div>

          <div className="text-xl text-slate-700">
            →
          </div>

          <div className="rounded-lg border border-amber-300/15 bg-amber-300/[0.035] p-4">
            <div className="text-[6px] uppercase tracking-[.18em] text-slate-600">
              Runtime Action
            </div>

            <div className="mt-2 text-sm text-white">
              execute_command
            </div>

            <div className="mt-2 text-[7px] text-amber-300/70">
              npm start
            </div>
          </div>
        </div>

        <div className="my-7 h-px bg-white/5" />

        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg border border-emerald-300/15 bg-emerald-300/[0.025] p-4">
            <div className="text-[6px] uppercase tracking-[.18em] text-slate-600">
              Observation
            </div>

            <div className="mt-2 text-sm text-white">
              obs_034
            </div>

            <div className="mt-2 text-[7px] text-emerald-300/75">
              exit code 0
            </div>
          </div>

          <div className="rounded-lg border border-blue-300/15 bg-blue-300/[0.025] p-4">
            <div className="text-[6px] uppercase tracking-[.18em] text-slate-600">
              Claim
            </div>

            <div className="mt-2 text-sm text-white">
              runtime starts
            </div>

            <div className="mt-2 text-[7px] text-emerald-300/75">
              trust · high
            </div>
          </div>
        </div>

        <div className="mt-7 flex items-center gap-3 text-[7px] text-slate-500">
          <span className="h-1.5 w-1.5 rounded-full bg-blue-300" />
          Planner context remains progressive
        </div>
      </div>
    </Surface>
  )
}

function BrowserSurface() {
  return (
    <Surface>
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
    </Surface>
  )
}

function ReportSurface() {
  return (
    <Surface>
      <WindowBar
        title="wizard / verification report"
        status="available"
      />

      <div className="h-[calc(100%-32px)] overflow-hidden bg-[#081321]">
        <AIAgentPipeline />
      </div>
    </Surface>
  )
}

function getCurrentApp(
  progress: number
): AppId {
  if (progress < 0.16)
    return "finder"

  if (progress < 0.31)
    return "vscode"

  if (progress < 0.44)
    return "terminal"

  if (progress < 0.67)
    return "wizard"

  if (progress < 0.8)
    return "browser"

  return "report"
}

function getOpenApps(
  progress: number
): string[] {
  if (progress < 0.16)
    return ["finder"]

  if (progress < 0.31)
    return [
      "finder",
      "vscode",
    ]

  if (progress < 0.44)
    return [
      "finder",
      "vscode",
      "terminal",
    ]

  if (progress < 0.67)
    return [
      "finder",
      "vscode",
      "terminal",
      "wizard",
    ]

  if (progress < 0.8)
    return [
      "finder",
      "vscode",
      "terminal",
      "wizard",
      "browser",
    ]

  return [
    "finder",
    "vscode",
    "terminal",
    "wizard",
    "browser",
    "report",
  ]
}

function getStageProgress(
  progress: number
) {
  const stages = [
    0,
    0.16,
    0.31,
    0.44,
    0.67,
    0.8,
  ]

  let current = 0

  for (
    let i = 0;
    i < stages.length;
    i++
  ) {
    if (
      progress >= stages[i]
    ) {
      current = i
    }
  }

  const start =
    stages[current]

  const end =
    stages[
      Math.min(
        current + 1,
        stages.length - 1
      )
    ] || 1

  return clamp(
    (progress - start) /
      Math.max(
        0.001,
        end - start
      )
  )
}

export function CinematicHero({
  className,
}: {
  className?: string
}) {
  const root =
    useRef<HTMLElement>(null)

  const [progress, setProgress] =
    useState(0)

  const activeApp =
    getCurrentApp(progress)

  const openApps =
    getOpenApps(progress)

  const stageProgress =
    getStageProgress(progress)

  const handleDockClick = (
    appId: string
  ) => {
    void appId
  }

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

      const distance =
        Math.max(
          1,
          element.offsetHeight -
            window.innerHeight
        )

      const next =
        clamp(
          -rect.top / distance
        )

      setProgress(
        current =>
          Math.abs(
            current - next
          ) > 0.001
            ? next
            : current
      )
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

  const transition =
    between(
      progress,
      0.02,
      0.08
    )

  const outro =
    between(
      progress,
      0.92,
      1
    )

  const sceneScale =
    0.95 +
    transition * 0.05 -
    outro * 0.03

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
            transform:
              `scale(${sceneScale})`,
          }}
        >
          <SafeMeshGradient />

          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_45%,rgba(255,255,255,.07),transparent_48%)]" />

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
                Wizard works inside
                the workflow you
                already use.
              </p>
            </div>

            <div className="relative w-full max-w-[1180px] lg:ml-4">
              <div className="relative aspect-[650/400] w-full">
                <MacbookPro
                  className="absolute inset-0 h-full w-full text-[#07101f] drop-shadow-2xl"
                  aria-label="Wizard integrated developer workspace"
                  role="img"
                >
                  <div className="screen relative h-full w-full overflow-hidden bg-[#07101f]">
                    <div className="absolute inset-x-0 top-0 z-[300] flex h-8 items-center border-b border-white/10 bg-[#0b1424] px-3">
                      <div className="flex gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
                        <span className="h-1.5 w-1.5 rounded-full bg-yellow-300" />
                        <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
                      </div>

                      <span className="ml-3 font-mono text-[7px] text-slate-300 sm:text-[9px]">
                        Wizard workspace
                      </span>

                      <span className="ml-auto font-mono text-[6px] uppercase tracking-[.16em] text-slate-600 sm:text-[7px]">
                        autonomous verification
                      </span>
                    </div>

                    <div
                      className="absolute inset-x-0 bottom-0 top-8 overflow-hidden"
                      style={{
                        transform:
                          `translateZ(0)`,
                      }}
                    >
                      {activeApp ===
                        "finder" && (
                        <RepositorySurface />
                      )}

                      {activeApp ===
                        "vscode" && (
                        <VSCodeSurface />
                      )}

                      {activeApp ===
                        "terminal" && (
                        <TerminalSurface />
                      )}

                      {activeApp ===
                        "wizard" && (
                        <WizardSurface
                          progress={
                            progress
                          }
                        />
                      )}

                      {activeApp ===
                        "browser" && (
                        <BrowserSurface />
                      )}

                      {activeApp ===
                        "report" && (
                        <ReportSurface />
                      )}
                    </div>

                    <div className="absolute inset-x-0 bottom-0 z-[500] flex justify-center pb-2">
                      <MacOSDock
                        apps={apps}
                        onAppClick={
                          handleDockClick
                        }
                        openApps={
                          openApps
                        }
                        className="scale-[.58] origin-bottom sm:scale-[.7] md:scale-[.8]"
                      />
                    </div>

                    <div className="pointer-events-none absolute bottom-[54px] left-1/2 z-[450] -translate-x-1/2 font-mono text-[5px] uppercase tracking-[.18em] text-white/25">
                      {activeApp ===
                        "finder" &&
                        "repository"}

                      {activeApp ===
                        "vscode" &&
                        "developer workspace"}

                      {activeApp ===
                        "terminal" &&
                        "runtime"}

                      {activeApp ===
                        "wizard" &&
                        "investigation"}

                      {activeApp ===
                        "browser" &&
                        "browser evidence"}

                      {activeApp ===
                        "report" &&
                        "verification report"}
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