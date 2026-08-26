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

type WorkspaceTab =
  | "vscode"
  | "terminal"
  | "wizard"
  | "browser"
  | "report"

type InvestigationPhase =
  | "workspace"
  | "inspect"
  | "plan"
  | "execute"
  | "observe"
  | "reason"
  | "verify"
  | "converge"

const TABS: {
  id: WorkspaceTab
  label: string
  title: string
}[] = [
  {
    id: "vscode",
    label: "VS Code",
    title: "wizard repo / VS Code",
  },
  {
    id: "terminal",
    label: "Terminal",
    title: "terminal / wizard session",
  },
  {
    id: "wizard",
    label: "Wizard",
    title: "wizard / investigation",
  },
  {
    id: "browser",
    label: "Browser",
    title: "wizardagents.vercel.app",
  },
  {
    id: "report",
    label: "Report",
    title: "wizard / verification report",
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

const files = [
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

function smooth(value: number) {
  const x = clamp(value)
  return x * x * (3 - 2 * x)
}

function windowProgress(
  progress: number,
  start: number,
  end: number
) {
  return smooth(
    clamp(
      (progress - start) /
        Math.max(0.001, end - start)
    )
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
    <div className="flex h-7 shrink-0 items-center border-b border-white/10 bg-[#0b1424] px-2.5 font-mono">
      <div className="flex gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
        <span className="h-1.5 w-1.5 rounded-full bg-yellow-300" />
        <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
      </div>

      <span className="ml-2 truncate text-[6px] text-slate-300 sm:text-[7px]">
        {title}
      </span>

      {status && (
        <span className="ml-auto text-[5px] uppercase tracking-[.14em] text-slate-500 sm:text-[6px]">
          {status}
        </span>
      )}
    </div>
  )
}

/* =========================================================
   MACOS WINDOW
========================================================= */

function WorkspaceWindow({
  children,
  className,
  style,
}: {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <div
      className={cn(
        "absolute overflow-hidden rounded-lg border border-white/10 bg-[#0b1424] shadow-[0_22px_55px_rgba(0,0,0,.34)]",
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

function VSCodeSurface({
  progress,
  focus,
}: {
  progress: number
  focus: number
}) {
  const reveal = windowProgress(
    progress,
    0,
    0.2
  )

  const codeAmount = windowProgress(
    progress,
    0.03,
    0.22
  )

  const visibleLines = Math.max(
    1,
    Math.min(
      code.length,
      Math.floor(
        codeAmount * code.length
      ) + 1
    )
  )

  return (
    <WorkspaceWindow
      className="left-[3%] top-[8%] z-20 h-[64%] w-[60%]"
      style={{
        opacity:
          progress < 0.01
            ? 0.96
            : 0.9 +
              reveal * 0.1,
        transform: `
          translate3d(
            ${(1 - reveal) * -12}px,
            ${(1 - reveal) * 7}px,
            0
          )
          scale(${0.985 + reveal * 0.015})
        `,
        filter:
          focus < 0.35
            ? "brightness(.68) saturate(.8)"
            : "brightness(1)",
      }}
    >
      <WindowBar
        title="wizard-repo / VS Code"
        status="workspace"
      />

      <div className="grid h-[calc(100%-28px)] grid-cols-[24%_76%] bg-[#111827]">
        <div className="overflow-hidden border-r border-white/5 p-2 font-mono text-[5px] text-slate-500 sm:text-[6px]">
          <div className="mb-2 text-[5px] tracking-[.14em] text-slate-400">
            EXPLORER
          </div>

          <div className="mb-2 text-slate-400">
            ⌄ wizard repo
          </div>

          <div className="rounded bg-blue-500/10 px-1.5 py-1 text-blue-200">
            ◇ package.json
          </div>

          <div className="py-1">
            ◇ README.md
          </div>

          <div className="py-1">
            ◇ app/
          </div>

          <div className="py-1">
            ◇ components/
          </div>

          <div className="py-1">
            ◇ lib/
          </div>

          <div className="py-1">
            ◇ Dockerfile
          </div>
        </div>

        <pre className="m-0 overflow-hidden p-3 font-mono text-[6px] leading-[1.8] text-slate-300 sm:text-[7px]">
          <code>
            {code
              .slice(0, visibleLines)
              .map(
                (line, index) => (
                  <React.Fragment
                    key={index}
                  >
                    <span
                      className={
                        index ===
                        visibleLines - 1
                          ? "rounded bg-blue-500/10 text-white"
                          : ""
                      }
                    >
                      {line || " "}
                    </span>

                    {index <
                      visibleLines - 1 &&
                      "\n"}
                  </React.Fragment>
                )
              )}

            <span className="ml-1 inline-block h-2 w-[2px] animate-pulse bg-blue-300" />
          </code>
        </pre>
      </div>
    </WorkspaceWindow>
  )
}

/* =========================================================
   TERMINAL
========================================================= */

function TerminalSurface({
  progress,
  focus,
}: {
  progress: number
  focus: number
}) {
  const reveal = windowProgress(
    progress,
    0.12,
    0.38
  )

  const commandAmount = windowProgress(
    progress,
    0.15,
    0.46
  )

  const visibleCommands =
    Math.min(
      commands.length,
      Math.floor(
        commandAmount *
          commands.length
      )
    )

  return (
    <WorkspaceWindow
      className="right-[3%] top-[13%] z-30 h-[52%] w-[57%]"
      style={{
        opacity:
          progress < 0.12
            ? 0
            : reveal,
        transform: `
          translate3d(
            ${(1 - reveal) * 25}px,
            ${(1 - reveal) * 15}px,
            0
          )
          scale(${0.97 + reveal * 0.03})
        `,
        filter:
          focus < 0.35
            ? "brightness(.62) saturate(.75)"
            : "brightness(1)",
      }}
    >
      <WindowBar
        title="terminal / wizard session"
        status="active"
      />

      <div className="relative h-[calc(100%-28px)] overflow-hidden bg-[#05080d] p-3 font-mono text-[6px] leading-[1.7] sm:p-4 sm:text-[7px]">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,.1),transparent_48%)]" />

        <div className="relative">
          {commands
            .slice(0, visibleCommands)
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

                  <div className="mt-1 text-emerald-400/75">
                    {index === 0 &&
                      "investigation request created"}

                    {index === 1 &&
                      "repository manifest available"}

                    {index === 2 &&
                      "dependencies installed"}

                    {index === 3 &&
                      "server listening on port 3000"}
                  </div>
                </div>
              )
            )}

          <div className="mt-2">
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
    </WorkspaceWindow>
  )
}

/* =========================================================
   WIZARD INVESTIGATION SURFACE
========================================================= */

function WizardSurface({
  progress,
  focus,
}: {
  progress: number
  focus: number
}) {
  const reveal = windowProgress(
    progress,
    0.2,
    0.52
  )

  const planning = windowProgress(
    progress,
    0.24,
    0.47
  )

  const execution = windowProgress(
    progress,
    0.42,
    0.64
  )

  const observation = windowProgress(
    progress,
    0.56,
    0.76
  )

  const trust = windowProgress(
    progress,
    0.7,
    0.9
  )

  const branch = windowProgress(
    progress,
    0.48,
    0.72
  )

  return (
    <WorkspaceWindow
      className="left-[9%] top-[8%] z-50 h-[82%] w-[82%]"
      style={{
        opacity:
          progress < 0.2
            ? 0
            : reveal,
        transform: `
          translate3d(
            0,
            ${(1 - reveal) * 24}px,
            0
          )
          scale(${0.965 + reveal * 0.035})
        `,
        filter:
          focus < 0.45
            ? "brightness(.7)"
            : "brightness(1)",
      }}
    >
      <WindowBar
        title="wizard / investigation"
        status={
          progress > 0.88
            ? "converging"
            : "investigating"
        }
      />

      <div className="relative h-[calc(100%-28px)] overflow-hidden bg-[#081321]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_52%_40%,rgba(59,130,246,.08),transparent_46%)]" />

        <div className="relative z-10 flex h-full flex-col p-4 font-mono">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[5px] uppercase tracking-[.2em] text-slate-500">
                Investigation
              </div>

              <div className="mt-1 text-[10px] text-white sm:text-[12px]">
                verify runtime
              </div>

              <div className="mt-1 text-[5px] text-slate-600">
                inv_7f31
              </div>
            </div>

            <div className="rounded-full border border-blue-300/15 bg-blue-300/[0.04] px-2 py-1 text-[5px] text-blue-200/70">
              Runtime Engine
            </div>
          </div>

          <div className="relative mt-5 flex-1">
            <div
              className="absolute left-[9%] top-[17%] h-px origin-left bg-blue-300/30"
              style={{
                width: `${30 + planning * 20}%`,
                transform:
                  "rotate(7deg)",
              }}
            />

            <div
              className="absolute left-[38%] top-[27%] h-px origin-left bg-emerald-300/30"
              style={{
                width: `${20 + execution * 15}%`,
                transform:
                  "rotate(-4deg)",
              }}
            />

            <div
              className="absolute left-[38%] top-[27%] h-px origin-left bg-amber-300/25"
              style={{
                width: `${18 + branch * 16}%`,
                transform:
                  "rotate(25deg)",
              }}
            />

            <div
              className="absolute left-[9%] top-[17%] rounded-md border border-blue-300/20 bg-blue-300/[0.035] p-2"
              style={{
                transform: `scale(${0.96 + planning * 0.04})`,
              }}
            >
              <div className="text-[5px] text-slate-500">
                INVESTIGATION NODE
              </div>

              <div className="mt-1 text-[6px] text-white">
                inspect runtime
              </div>

              <div className="mt-1 text-[5px] text-blue-300/70">
                hypothesis attached
              </div>
            </div>

            <div
              className="absolute left-[37%] top-[19%] rounded-md border border-amber-300/20 bg-amber-300/[0.035] p-2"
              style={{
                opacity:
                  0.55 +
                  execution * 0.45,
                transform: `scale(${0.96 + execution * 0.04})`,
              }}
            >
              <div className="text-[5px] text-slate-500">
                TOOL REQUEST
              </div>

              <div className="mt-1 text-[6px] text-white">
                execute_command
              </div>

              <div className="mt-1 text-[5px] text-amber-300/70">
                npm start
              </div>
            </div>

            <div
              className="absolute left-[62%] top-[8%] rounded-md border border-emerald-300/20 bg-emerald-300/[0.035] p-2"
              style={{
                opacity:
                  0.25 +
                  observation * 0.75,
                transform: `scale(${0.94 + observation * 0.06})`,
              }}
            >
              <div className="text-[5px] text-slate-500">
                OBSERVATION
              </div>

              <div className="mt-1 text-[6px] text-white">
                obs_034
              </div>

              <div className="mt-1 text-[5px] text-emerald-300/75">
                exit code 0
              </div>
            </div>

            <div
              className="absolute left-[59%] top-[48%] rounded-md border border-blue-300/20 bg-blue-300/[0.035] p-2"
              style={{
                opacity:
                  0.15 +
                  trust * 0.85,
                transform: `scale(${0.94 + trust * 0.06})`,
              }}
            >
              <div className="text-[5px] text-slate-500">
                CLAIM
              </div>

              <div className="mt-1 text-[6px] text-white">
                runtime starts
              </div>

              <div className="mt-1 text-[5px] text-emerald-300">
                trust · high
              </div>
            </div>

            <div
              className="absolute left-[28%] top-[62%] rounded-md border border-violet-300/15 bg-violet-300/[0.025] p-2"
              style={{
                opacity:
                  0.1 +
                  branch * 0.9,
                transform: `
                  translate3d(
                    ${branch * 4}px,
                    ${branch * -2}px,
                    0
                  )
                `,
              }}
            >
              <div className="text-[5px] text-slate-500">
                NEW PATH
              </div>

              <div className="mt-1 text-[6px] text-white">
                browser verification
              </div>

              <div className="mt-1 text-[5px] text-violet-300/70">
                evidence required
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 border-t border-white/5 pt-3">
            <div>
              <div className="text-[4px] uppercase tracking-[.15em] text-slate-600">
                Context
              </div>

              <div className="mt-1 text-[5px] text-slate-400">
                targeted files
              </div>
            </div>

            <div>
              <div className="text-[4px] uppercase tracking-[.15em] text-slate-600">
                Evidence
              </div>

              <div className="mt-1 text-[5px] text-slate-400">
                immutable observations
              </div>
            </div>

            <div>
              <div className="text-[4px] uppercase tracking-[.15em] text-slate-600">
                Truth
              </div>

              <div className="mt-1 text-[5px] text-emerald-400/75">
                Runtime owned
              </div>
            </div>
          </div>
        </div>
      </div>
    </WorkspaceWindow>
  )
}

/* =========================================================
   BROWSER SURFACE
========================================================= */

function BrowserSurface({
  progress,
  focus,
}: {
  progress: number
  focus: number
}) {
  const reveal = windowProgress(
    progress,
    0.54,
    0.76
  )

  return (
    <WorkspaceWindow
      className="right-[3%] top-[8%] z-60 h-[79%] w-[84%]"
      style={{
        opacity:
          progress < 0.54
            ? 0
            : reveal,
        transform: `
          translate3d(
            ${(1 - reveal) * 24}px,
            ${(1 - reveal) * -8}px,
            0
          )
          scale(${0.965 + reveal * 0.035})
        `,
        filter:
          focus < 0.45
            ? "brightness(.68)"
            : "brightness(1)",
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

      <div className="pointer-events-none absolute bottom-2 left-2 rounded-full border border-slate-200 bg-white/90 px-2 py-1 font-mono text-[5px] text-slate-500 shadow-sm backdrop-blur">
        browser tool
      </div>
    </WorkspaceWindow>
  )
}

/* =========================================================
   REPOSITORY SURFACE
========================================================= */

function RepositorySurface({
  progress,
  focus,
}: {
  progress: number
  focus: number
}) {
  const reveal = windowProgress(
    progress,
    0.28,
    0.52
  )

  const index =
    Math.min(
      files.length - 1,
      Math.floor(
        reveal * files.length
      )
    )

  return (
    <WorkspaceWindow
      className="left-[3%] bottom-[5%] z-10 h-[39%] w-[49%]"
      style={{
        opacity:
          progress < 0.28
            ? 0
            : 0.8 +
              reveal * 0.2,
        transform: `
          translate3d(
            ${(1 - reveal) * -15}px,
            ${(1 - reveal) * 12}px,
            0
          )
          scale(${0.98 + reveal * 0.02})
        `,
        filter:
          focus < 0.3
            ? "brightness(.6)"
            : "brightness(.95)",
      }}
    >
      <WindowBar
        title="repository map"
        status="reading"
      />

      <div className="grid h-[calc(100%-28px)] grid-cols-[56%_44%] bg-[#081321]">
        <div className="overflow-hidden border-r border-white/5 p-2">
          <div className="mb-2 font-mono text-[5px] tracking-[.15em] text-slate-500">
            REPOSITORY
          </div>

          <FileTree
            data={wizardFileStructure}
            className="max-h-[90%] overflow-hidden text-[6px]"
          />
        </div>

        <div className="p-3 font-mono">
          <div className="text-[5px] tracking-[.15em] text-slate-600">
            CURRENT FILE
          </div>

          <div className="mt-2 text-[6px] text-white">
            {files[index]}
          </div>

          <div className="mt-3 space-y-1.5 text-[5px] text-slate-500">
            <div>
              source available
            </div>

            <div>
              symbols indexed
            </div>

            <div>
              dependency relation found
            </div>
          </div>
        </div>
      </div>
    </WorkspaceWindow>
  )
}

/* =========================================================
   REPORT SURFACE
========================================================= */

function ReportSurface({
  progress,
  focus,
}: {
  progress: number
  focus: number
}) {
  const reveal = windowProgress(
    progress,
    0.74,
    1
  )

  return (
    <WorkspaceWindow
      className="left-[7%] top-[7%] z-[100] h-[84%] w-[86%]"
      style={{
        opacity:
          progress < 0.74
            ? 0
            : reveal,
        transform: `
          translate3d(
            0,
            ${(1 - reveal) * 20}px,
            0
          )
          scale(${0.97 + reveal * 0.03})
        `,
        filter:
          focus < 0.45
            ? "brightness(.7)"
            : "brightness(1)",
      }}
    >
      <WindowBar
        title="wizard / verification report"
        status={
          progress > 0.94
            ? "available"
            : "assembling"
        }
      />

      <div className="h-[calc(100%-28px)] overflow-hidden bg-[#081321]">
        <AIAgentPipeline />
      </div>
    </WorkspaceWindow>
  )
}

/* =========================================================
   TAB STRIP
========================================================= */

function WorkspaceTabs({
  activeTab,
  progress,
}: {
  activeTab: WorkspaceTab
  progress: number
}) {
  return (
    <div className="absolute bottom-2 left-1/2 z-[400] flex -translate-x-1/2 items-end gap-1.5 rounded-xl border border-white/10 bg-black/25 px-2 py-1.5 shadow-xl backdrop-blur-md">
      {TABS.map((tab) => {
        const active =
          tab.id === activeTab

        const contextual =
          tab.id === "wizard"

        return (
          <div
            key={tab.id}
            className={cn(
              "relative flex items-center rounded-md px-2 py-1.5 font-mono transition-all duration-700",
              active
                ? "bg-white/[0.11] text-white shadow-[0_4px_16px_rgba(0,0,0,.18)]"
                : "text-slate-500",
              contextual &&
                !active &&
                "text-blue-200/55"
            )}
          >
            <span className="text-[5px] sm:text-[6px]">
              {tab.label}
            </span>

            {active && (
              <span className="ml-1.5 h-1 w-1 rounded-full bg-blue-300 shadow-[0_0_7px_rgba(147,197,253,.8)]" />
            )}
          </div>
        )
      })}

      <div className="ml-1 border-l border-white/10 pl-2 font-mono text-[5px] text-slate-600">
        {progress > 0.9
          ? "investigation retained"
          : "workspace"}
      </div>
    </div>
  )
}

/* =========================================================
   ACTIVE SURFACE LOGIC
========================================================= */

function getActiveSurface(
  progress: number
): WorkspaceTab {
  if (progress < 0.11)
    return "vscode"

  if (progress < 0.22)
    return "terminal"

  if (progress < 0.43)
    return "wizard"

  if (progress < 0.54)
    return "vscode"

  if (progress < 0.72)
    return "browser"

  if (progress < 0.84)
    return "wizard"

  return "report"
}

function getPhase(
  progress: number
): InvestigationPhase {
  if (progress < 0.11)
    return "workspace"

  if (progress < 0.22)
    return "inspect"

  if (progress < 0.36)
    return "plan"

  if (progress < 0.52)
    return "execute"

  if (progress < 0.66)
    return "observe"

  if (progress < 0.78)
    return "reason"

  if (progress < 0.92)
    return "verify"

  return "converge"
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

  const activeTab =
    getActiveSurface(progress)

  const phase =
    getPhase(progress)

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
        (current) =>
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

  const focusMap: Record<
    WorkspaceTab,
    number
  > = {
    vscode:
      activeTab === "vscode"
        ? 1
        : 0.45,
    terminal:
      activeTab === "terminal"
        ? 1
        : 0.4,
    wizard:
      activeTab === "wizard"
        ? 1
        : 0.42,
    browser:
      activeTab === "browser"
        ? 1
        : 0.38,
    report:
      activeTab === "report"
        ? 1
        : 0.4,
  }

  const intro =
    smooth(
      clamp(
        progress / 0.1
      )
    )

  const outro =
    smooth(
      clamp(
        (progress - 0.92) /
          0.08
      )
    )

  const sceneScale =
    0.94 +
    intro * 0.06 -
    outro * 0.035

  const sceneRadius =
    20 -
    intro * 20 +
    outro * 20

  return (
    <section
      ref={root}
      className={cn(
        "relative min-h-[7600px] overflow-visible bg-transparent font-sans",
        className
      )}
    >
      <div className="sticky top-0 flex min-h-screen w-full items-center justify-center overflow-hidden">
        <div
          className="scene-card relative flex min-h-screen w-full items-center justify-center overflow-hidden text-white"
          style={{
            transform: `scale(${sceneScale})`,
            borderRadius: `${sceneRadius}px`,
            transformOrigin:
              "center center",
          }}
        >
          <SafeMeshGradient />

          <div className="pointer-events-none absolute inset-0 z-10 bg-[radial-gradient(circle_at_58%_45%,rgba(255,255,255,.075),transparent_48%)]" />

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

              <div className="mt-7 flex items-center gap-2 font-mono text-[7px] uppercase tracking-[.18em] text-blue-100/55">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 shadow-[0_0_9px_rgba(110,231,183,.75)]" />

                {phase ===
                  "workspace" &&
                  "developer workspace"}

                {phase ===
                  "inspect" &&
                  "repository inspection"}

                {phase ===
                  "plan" &&
                  "investigation planning"}

                {phase ===
                  "execute" &&
                  "runtime execution"}

                {phase ===
                  "observe" &&
                  "evidence collection"}

                {phase ===
                  "reason" &&
                  "evidence reasoning"}

                {phase ===
                  "verify" &&
                  "verification"}

                {phase ===
                  "converge" &&
                  "investigation available"}
              </div>
            </div>

            <div className="relative w-full max-w-[1180px] lg:ml-4">
              <div className="relative aspect-[650/400] w-full">
                <MacbookPro
                  className="absolute inset-0 h-full w-full text-[#07101f] drop-shadow-2xl"
                  aria-label="Wizard integrated developer workspace"
                  role="img"
                >
                  <div className="screen relative h-full w-full overflow-hidden bg-[#07101f] font-mono">
                    <div className="absolute left-0 right-0 top-0 z-[300] flex h-7 items-center border-b border-white/10 bg-[#0b1424] px-3">
                      <span className="text-[7px] font-medium tracking-[.16em] text-white/85 sm:text-[9px]">
                        WIZARD
                      </span>

                      <span className="mx-2 text-[7px] text-white/20">
                        /
                      </span>

                      <span className="text-[6px] text-slate-500 sm:text-[8px]">
                        autonomous repository
                        verification
                      </span>

                      <div className="ml-auto flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(74,222,128,.7)]" />

                        <span className="text-[5px] uppercase tracking-[.12em] text-emerald-300/75 sm:text-[7px]">
                          {phase ===
                          "converge"
                            ? "available"
                            : "investigating"}
                        </span>
                      </div>
                    </div>

                    <div className="absolute inset-x-0 bottom-0 top-7 overflow-hidden">
                      <VSCodeSurface
                        progress={
                          progress
                        }
                        focus={
                          focusMap.vscode
                        }
                      />

                      <TerminalSurface
                        progress={
                          progress
                        }
                        focus={
                          focusMap.terminal
                        }
                      />

                      <RepositorySurface
                        progress={
                          progress
                        }
                        focus={
                          focusMap.vscode
                        }
                      />

                      <WizardSurface
                        progress={
                          progress
                        }
                        focus={
                          focusMap.wizard
                        }
                      />

                      <BrowserSurface
                        progress={
                          progress
                        }
                        focus={
                          focusMap.browser
                        }
                      />

                      <ReportSurface
                        progress={
                          progress
                        }
                        focus={
                          focusMap.report
                        }
                      />
                    </div>

                    <WorkspaceTabs
                      activeTab={
                        activeTab
                      }
                      progress={
                        progress
                      }
                    />
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