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

interface AppDefinition {
  id: AppId
  name: string
  icon: string
}

const apps: AppDefinition[] = [
  {
    id: "finder",
    name: "Finder",
    icon:
      "https://cdn.jim-nielsen.com/macos/1024/finder-2021-09-10.png?rf=1024",
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
      "https://cdn.jim-nielsen.com/macos/1024/terminal-2021-06-03.png?rf=1024",
  },
  {
    id: "wizard",
    name: "Wizard",
    icon:
      "https://cdn.jim-nielsen.com/macos/1024/terminal-2021-06-03.png?rf=1024",
  },
  {
    id: "browser",
    name: "Browser",
    icon:
      "https://cdn.jim-nielsen.com/macos/1024/safari-2021-06-02.png?rf=1024",
  },
  {
    id: "report",
    name: "Report",
    icon:
      "https://cdn.jim-nielsen.com/macos/1024/notes-2021-05-25.png?rf=1024",
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

function smoothstep(value: number) {
  const x = clamp(value)
  return x * x * (3 - 2 * x)
}

function range(
  value: number,
  start: number,
  end: number
) {
  if (value <= start) return 0
  if (value >= end) return 1

  return smoothstep(
    (value - start) /
      Math.max(0.0001, end - start)
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

function VSCodeIcon({
  size = 32,
}: {
  size?: number
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <rect
        width="32"
        height="32"
        rx="7"
        fill="#007ACC"
      />

      <path
        d="M22.4 5.5 16.8 9.9 12.5 6.7 7.2 10.8v10.4l5.3 4.1 4.3-3.2 5.6 4.4 4.3-2.7V8.2l-4.3-2.7Z"
        fill="white"
        opacity=".96"
      />

      <path
        d="m16.8 9.9-4.3 3.3-2.4-1.9-1.5 1.2 3.9 3.1-3.9 3.1 1.5 1.2 2.4-1.9 4.3 3.3 5.6 4.4V5.5l-5.6 4.4Zm2.5 2.2v7.8l-4.8-3.9 4.8-3.9Z"
        fill="#007ACC"
      />
    </svg>
  )
}

function DockIcon({
  app,
  size = 34,
}: {
  app: AppDefinition
  size?: number
}) {
  if (app.id === "vscode") {
    return <VSCodeIcon size={size} />
  }

  return (
    <img
      src={app.icon}
      alt=""
      width={size}
      height={size}
      draggable={false}
      className="h-full w-full object-contain"
    />
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
      }, 1700)

    return () =>
      window.clearInterval(timer)
  }, [])

  return (
    <div className="absolute inset-0 overflow-hidden">
      <WindowBar
        title="wizard-repo / Finder"
        status="repository"
      />

      <div className="grid h-[calc(100%-32px)] grid-cols-[31%_69%] bg-[#111827]">
        <div className="overflow-hidden border-r border-white/5 p-4 font-mono text-[7px] text-slate-500 sm:p-6 sm:text-[8px]">
          <div className="mb-4 text-[6px] tracking-[.2em] text-slate-400 sm:text-[7px]">
            REPOSITORY
          </div>

          <div className="mb-2 text-slate-300">
            ⌄ wizard-repo
          </div>

          <FileTree
            data={wizardFileStructure}
            className="text-[7px] sm:text-[8px]"
          />
        </div>

        <div className="p-5 sm:p-8">
          <div className="font-mono text-[6px] uppercase tracking-[.2em] text-slate-600 sm:text-[7px]">
            Repository manifest
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

          <div className="mt-7 max-w-lg rounded-lg border border-white/10 bg-white/[0.025] p-4 sm:mt-10">
            <div className="font-mono text-[6px] uppercase tracking-[.18em] text-slate-600">
              Current target
            </div>

            <div className="mt-2 font-mono text-xs text-white sm:text-sm">
              {repositoryFiles[active]}
            </div>

            <div className="mt-4 flex gap-2 font-mono text-[6px] text-blue-300/70 sm:text-[7px]">
              <span>source</span>
              <span>indexed</span>
              <span>available</span>
            </div>
          </div>
        </div>
      </div>
    </div>
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
      }, 1350)

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
        title="wizard-repo / VS Code"
        status="workspace"
      />

      <div className="grid h-[calc(100%-32px)] grid-cols-[22%_78%] bg-[#111827]">
        <div className="border-r border-white/5 p-3 font-mono text-[6px] text-slate-500 sm:p-5 sm:text-[7px]">
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
                        visible.length -
                          1 &&
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
      }, 1750)

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
    </div>
  )
}

function WizardSurface({
  progress,
}: {
  progress: number
}) {
  const investigationPhase =
    progress < 0.45
      ? "planning"
      : progress < 0.7
        ? "executing"
        : "evaluating"

  return (
    <div className="absolute inset-0 overflow-hidden">
      <WindowBar
        title="wizard / investigation"
        status={investigationPhase}
      />

      <div className="h-[calc(100%-32px)] overflow-hidden bg-[#081321] p-5 font-mono sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[6px] uppercase tracking-[.2em] text-slate-600 sm:text-[7px]">
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

        <div className="mt-7 grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:mt-10 sm:gap-4">
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
              execute_command
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

function AppSurface({
  app,
  progress,
}: {
  app: AppId
  progress: number
}) {
  switch (app) {
    case "finder":
      return <RepositorySurface />

    case "vscode":
      return <VSCodeSurface />

    case "terminal":
      return <TerminalSurface />

    case "wizard":
      return (
        <WizardSurface
          progress={progress}
        />
      )

    case "browser":
      return <BrowserSurface />

    case "report":
      return <ReportSurface />

    default:
      return null
  }
}

function stageForProgress(
  progress: number
) {
  const stageCount = apps.length

  const raw =
    progress *
    stageCount

  return Math.min(
    stageCount - 1,
    Math.floor(raw)
  )
}

function transitionForProgress(
  progress: number
) {
  const stageCount = apps.length
  const raw =
    progress *
    stageCount

  const local =
    raw - Math.floor(raw)

  return local
}

function previousApp(
  stage: number
): AppId | null {
  if (stage <= 0)
    return null

  return apps[stage - 1].id
}

function currentApp(
  stage: number
): AppId {
  return apps[stage].id
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
          -rect.top /
            distance
        )

      setProgress(
        current =>
          Math.abs(
            current - next
          ) > 0.0005
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

      if (frame) {
        window.cancelAnimationFrame(
          frame
        )
      }
    }
  }, [])

  const stage =
    stageForProgress(progress)

  const localProgress =
    transitionForProgress(
      progress
    )

  const current =
    currentApp(stage)

  const previous =
    previousApp(stage)

  /*
   * The first 55% of each stage is deliberately
   * stable. The remaining 45% is the transition.
   *
   * This makes each application feel like a
   * destination rather than a frame in a slideshow.
   */
  const stable =
    range(
      localProgress,
      0,
      0.55
    )

  const transition =
    range(
      localProgress,
      0.55,
      1
    )

  /*
   * Dock exists only during the handoff.
   */
  const dockVisibility =
    range(
      localProgress,
      0.58,
      0.72
    ) *
    (1 -
      range(
        localProgress,
        0.86,
        0.98
      ))

  /*
   * Previous application physically
   * retreats into the desktop.
   */
  const previousScale =
    1 -
    transition * 0.72

  const previousX =
    -transition * 34

  const previousY =
    -transition * 12

  const previousRotate =
    -transition * 1.5

  const previousOpacity =
    1 -
    transition * 0.25

  /*
   * Current application enters from the
   * Dock and grows into the screen.
   */
  const currentEntrance =
    range(
      localProgress,
      0.78,
      1
    )

  const currentScale =
    stage === 0
      ? 1
      : 0.58 +
        currentEntrance *
          0.42

  const currentY =
    stage === 0
      ? 0
      : 18 -
        currentEntrance * 18

  const currentOpacity =
    stage === 0
      ? 1
      : 0.72 +
        currentEntrance * 0.28

  /*
   * The wallpaper is visible between
   * applications.
   */
  const desktopOpacity =
    stage === 0
      ? 0
      : transition *
        0.92

  /*
   * Synthetic agent pointer. This is local
   * to the MacBook, not the user's real cursor.
   */
  const cursorStartX =
    stage === 0
      ? 50
      : 50 -
        transition * 22

  const cursorStartY =
    stage === 0
      ? 50
      : 52 +
        transition * 8

  const cursorTargetX =
    50 +
    (stage % 2 === 0
      ? 15
      : -15)

  const cursorTargetY =
    84

  const cursorProgress =
    range(
      localProgress,
      0.63,
      0.82
    )

  const cursorX =
    cursorStartX +
    (cursorTargetX -
      cursorStartX) *
      cursorProgress

  const cursorY =
    cursorStartY +
    (cursorTargetY -
      cursorStartY) *
      cursorProgress

  const cursorScale =
    range(
      localProgress,
      0.8,
      0.83
    )

  const cursorVisible =
    stage > 0 &&
    localProgress > 0.61 &&
    localProgress < 0.89

  const dockApps =
    apps.map(app => ({
      ...app,
    }))

  const openApps =
    apps
      .slice(
        0,
        stage + 1
      )
      .map(app => app.id)

  const handleDockClick = (
    appId: string
  ) => {
    void appId
  }

  return (
    <section
      ref={root}
      className={cn(
        "relative min-h-[10800px] overflow-visible bg-transparent font-sans",
        className
      )}
    >
      <div className="sticky top-0 flex min-h-screen w-full items-center justify-center overflow-hidden">
        <div className="relative flex min-h-screen w-full items-center justify-center">
          <SafeMeshGradient />

          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_45%,rgba(255,255,255,.07),transparent_50%)]" />

          <div className="relative z-20 flex w-full max-w-[1540px] flex-col items-center gap-8 px-4 py-12 lg:flex-row lg:gap-14 lg:px-10">
            <div className="w-full max-w-[340px] shrink-0">
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

              <p className="mt-5 max-w-[310px] text-sm leading-relaxed text-blue-50/80">
                Wizard works inside
                the workflow you
                already use.
              </p>

              <p className="mt-8 font-mono text-[7px] uppercase tracking-[.24em] text-blue-100/35">
                {current === "finder" &&
                  "Inspecting repository"}

                {current === "vscode" &&
                  "Reading source"}

                {current === "terminal" &&
                  "Executing runtime"}

                {current === "wizard" &&
                  "Building evidence"}

                {current === "browser" &&
                  "Verifying behavior"}

                {current === "report" &&
                  "Tracing conclusions"}
              </p>
            </div>

            <div className="relative w-full max-w-[1180px] lg:ml-4">
              <div className="relative mx-auto aspect-[650/400] w-full">
                <MacbookPro
                  className="absolute inset-0 h-full w-full text-[#07101f] drop-shadow-2xl"
                  aria-label="Wizard autonomous investigation"
                  role="img"
                >
                  <div className="screen relative h-full w-full overflow-hidden bg-[#111827]">
                    {/*
                     * Actual Mac desktop wallpaper.
                     * This becomes visible during every
                     * application handoff.
                     */}
                    <div
                      className="absolute inset-0"
                      style={{
                        opacity:
                          stage === 0
                            ? 0
                            : desktopOpacity,
                        background:
                          "radial-gradient(circle at 50% 28%, rgba(110,160,255,.35), transparent 30%), radial-gradient(circle at 25% 70%, rgba(50,100,180,.25), transparent 34%), linear-gradient(145deg,#182b4a 0%,#0b1528 48%,#050a13 100%)",
                      }}
                    />

                    {/*
                     * Previous application.
                     * It is visible only while it
                     * retreats into the desktop.
                     */}
                    {previous && (
                      <div
                        className="absolute inset-[5%] z-20 overflow-hidden rounded-[10px] shadow-2xl"
                        style={{
                          transform:
                            `translate3d(${previousX}%,${previousY}%,0) scale(${previousScale}) rotate(${previousRotate}deg)`,
                          opacity:
                            previousOpacity *
                            (1 -
                              currentEntrance),
                          transformOrigin:
                            "center center",
                          pointerEvents:
                            "none",
                          willChange:
                            "transform, opacity",
                        }}
                      >
                        <AppSurface
                          app={
                            previous
                          }
                          progress={
                            progress
                          }
                        />
                      </div>
                    )}

                    {/*
                     * Current application.
                     *
                     * Before the transition it
                     * owns the whole screen.
                     *
                     * During the transition it
                     * returns from the Dock.
                     */}
                    <div
                      className="absolute inset-0 z-30 overflow-hidden"
                      style={{
                        transform:
                          `translate3d(0,${currentY}%,0) scale(${currentScale})`,
                        opacity:
                          currentOpacity,
                        transformOrigin:
                          "center center",
                        pointerEvents:
                          transition >
                          0.84
                            ? "auto"
                            : "none",
                        willChange:
                          "transform, opacity",
                      }}
                    >
                      <AppSurface
                        app={current}
                        progress={
                          progress
                        }
                      />
                    </div>

                    {/*
                     * Dock is deliberately outside
                     * the application layer.
                     *
                     * It appears only during the
                     * handoff.
                     */}
                    <div
                      className="absolute bottom-[5%] left-1/2 z-[100] -translate-x-1/2"
                      style={{
                        opacity:
                          dockVisibility,
                        transform:
                          `translate3d(-50%,${(1 - dockVisibility) * 22}px,0) scale(${0.86 + dockVisibility * 0.14})`,
                        pointerEvents:
                          dockVisibility >
                          0.8
                            ? "auto"
                            : "none",
                        transition:
                          "none",
                      }}
                    >
                      <MacOSDock
                        apps={
                          dockApps
                        }
                        onAppClick={
                          handleDockClick
                        }
                        openApps={
                          openApps
                        }
                        className="scale-[.62] sm:scale-[.7] md:scale-[.78]"
                      />
                    </div>

                    {/*
                     * Agent cursor.
                     *
                     * This is NOT the global
                     * SmoothCursor.
                     *
                     * It represents Wizard moving
                     * the pointer to the next app.
                     */}
                    {cursorVisible && (
                      <div
                        className="pointer-events-none absolute z-[150] hidden md:block"
                        style={{
                          left:
                            `${cursorX}%`,
                          top:
                            `${cursorY}%`,
                          transform:
                            `translate(-7px,-5px) scale(${1 - cursorScale * 0.12})`,
                          transition:
                            "none",
                          filter:
                            "drop-shadow(0 2px 3px rgba(0,0,0,.45))",
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

                        {cursorScale >
                          0.92 && (
                          <span className="absolute -right-1 -bottom-1 h-3 w-3 rounded-full border border-blue-300/80 bg-blue-400/20" />
                        )}
                      </div>
                    )}

                    {/*
                     * Tiny stage context.
                     *
                     * This is intentionally not a
                     * progress indicator.
                     */}
                    <div className="pointer-events-none absolute bottom-2 left-3 z-[200] font-mono text-[5px] uppercase tracking-[.18em] text-white/25 sm:text-[6px]">
                      {current ===
                        "finder" &&
                        "repository"}

                      {current ===
                        "vscode" &&
                        "source"}

                      {current ===
                        "terminal" &&
                        "execution"}

                      {current ===
                        "wizard" &&
                        "investigation"}

                      {current ===
                        "browser" &&
                        "browser evidence"}

                      {current ===
                        "report" &&
                        "verification"}
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