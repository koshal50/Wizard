"use client"

import React, { useEffect, useMemo, useRef, useState } from "react"
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
            "url(\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)' opacity='0.215'/></svg>\"), radial-gradient(150% 48.4% at 41.58% 6%, rgba(234, 247, 251, 0.92) 0%, rgba(234, 247, 251, 0) 53%), radial-gradient(150% 48.4% at 42.42% 33%, rgba(127, 198, 230, 0.92) 0%, rgba(127, 198, 230, 0) 53%), radial-gradient(150% 48.4% at 51.19% 67%, rgba(46, 124, 192, 0.92) 0%, rgba(46, 124, 192, 0) 53%), radial-gradient(150% 48.4% at 53.67% 94%, rgba(18, 58, 107, 0.92) 0%, rgba(18, 58, 107, 0) 53%)",
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
  return Math.min(max, Math.max(min, value))
}

function range(
  value: number,
  start: number,
  end: number
) {
  return clamp(
    (value - start) / Math.max(0.0001, end - start)
  )
}

function smooth(value: number) {
  const x = clamp(value)
  return x * x * (3 - 2 * x)
}

function springValue(
  value: number,
  power = 0.82
) {
  return Math.pow(clamp(value), power)
}

function Bar({
  children,
  status = "LIVE",
}: {
  children: React.ReactNode
  status?: string
}) {
  return (
    <div className="window-bar">
      <i />
      <i />
      <i />

      <span>{children}</span>

      <b className="live-dot">{status}</b>
    </div>
  )
}

function Workspace({
  progress,
}: {
  progress: number
}) {
  const visibleLines = Math.max(
    1,
    Math.floor(
      springValue(range(progress, 0.04, 0.28)) *
        code.length
    )
  )

  const currentLine = Math.min(
    code.length - 1,
    Math.max(0, visibleLines - 1)
  )

  const selectedFile =
    progress < 0.2
      ? "package.json"
      : progress < 0.28
        ? "README.md"
        : "app/page.tsx"

  return (
    <div
      data-screen-panel
      className="absolute inset-0 overflow-hidden bg-[#111827]"
    >
      <Bar>wizard repo / investigation workspace</Bar>

      <div className="ide-body">
        <div className="file-tree">
          <b>EXPLORER</b>

          <span>⌄ wizard repo</span>

          <em
            className={
              selectedFile === "package.json"
                ? "repo-selected"
                : ""
            }
          >
            ◇ package.json
          </em>

          <em
            className={
              selectedFile === "README.md"
                ? "repo-selected"
                : ""
            }
          >
            ◇ README.md
          </em>

          <em
            className={
              selectedFile === "app/page.tsx"
                ? "repo-selected"
                : ""
            }
          >
            ◇ app/
          </em>

          <em>◇ components/</em>
          <em>◇ lib/</em>
        </div>

        <pre className="code-stream">
          <code>
            {code
              .slice(0, visibleLines)
              .map((text, index) => (
                <React.Fragment key={index}>
                  <span
                    className={
                      index === currentLine
                        ? "code-current"
                        : ""
                    }
                  >
                    {text || " "}
                  </span>

                  {index <
                    visibleLines - 1 &&
                    "\n"}
                </React.Fragment>
              ))}

            <span className="typing-caret" />
          </code>
        </pre>
      </div>

      <div
        className="absolute bottom-3 right-3 rounded border border-blue-300/20 bg-blue-500/10 px-2 py-1 text-[7px] text-blue-100"
        style={{
          transform: `translateY(${(1 - range(progress, 0.08, 0.22)) * 10}px)`,
        }}
      >
        INVESTIGATION NODE · node_014
      </div>
    </div>
  )
}

function Terminal({
  progress,
}: {
  progress: number
}) {
  const open = smooth(
    range(progress, 0.255, 0.32)
  )

  const execute = smooth(
    range(progress, 0.31, 0.43)
  )

  const close = smooth(
    range(progress, 0.43, 0.49)
  )

  const commandIndex = Math.min(
    commands.length - 1,
    Math.floor(execute * commands.length)
  )

  const terminalScale =
    0.72 +
    open * 0.28 -
    close * 0.2

  const terminalX =
    18 -
    close * 14

  const terminalY =
    24 -
    close * 26

  return (
    <div
      className="pointer-events-none absolute inset-0 z-30"
      style={{
        clipPath:
          open <= 0
            ? "inset(100% 0 0 0)"
            : "inset(0 0 0 0)",
      }}
    >
      <div
        className="absolute left-[9%] top-[12%] h-[68%] w-[72%] overflow-hidden rounded-lg border border-white/15 bg-[#05080d] shadow-2xl"
        style={{
          transformOrigin: "bottom left",
          transform: `translate3d(${terminalX}px, ${terminalY}px, 0) scale(${terminalScale})`,
          opacity: 1,
        }}
      >
        <div className="flex h-8 items-center border-b border-white/10 bg-[#0b1424] px-3 font-mono text-[7px] text-slate-400 sm:text-[9px]">
          <div className="mr-3 flex gap-1.5">
            <span className="h-2 w-2 rounded-full bg-red-400" />
            <span className="h-2 w-2 rounded-full bg-yellow-400" />
            <span className="h-2 w-2 rounded-full bg-green-400" />
          </div>

          terminal · wizard runtime

          <span className="ml-auto text-green-400">
            EXECUTING
          </span>
        </div>

        <div className="relative h-[calc(100%-2rem)] overflow-hidden p-5 font-mono text-[8px] leading-relaxed text-white sm:p-7 sm:text-[10px]">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,.1),transparent_45%)]" />

          <div className="relative z-10">
            {commands
              .slice(
                0,
                Math.max(
                  1,
                  commandIndex + 1
                )
              )
              .map((command, index) => (
                <div
                  key={command}
                  className="mb-4"
                >
                  <div>
                    <span className="text-cyan-400">
                      wizard@repo
                    </span>

                    <span className="text-slate-500">
                      {" "}
                      ~/wizard repo
                    </span>

                    <span>
                      {" "}
                      $
                    </span>

                    <span className="ml-2">
                      {command}
                    </span>
                  </div>

                  {index <=
                    Math.floor(
                      execute * commands.length
                    ) && (
                    <div className="mt-1 text-green-400/80">
                      ✓ completed ·{" "}
                      {index === 0
                        ? "structure mapped"
                        : index === 1
                          ? "manifest inspected"
                          : index === 2
                            ? "runtime verified"
                            : "browser evidence captured"}
                    </div>
                  )}
                </div>
              ))}

            <span className="text-cyan-400">
              wizard@repo
            </span>

            <span className="text-slate-500">
              {" "}
              ~/wizard repo
            </span>

            <span> $</span>

            <span className="ml-2 inline-block h-3 w-1.5 animate-pulse bg-white align-middle" />
          </div>
        </div>

        {execute > 0.68 && (
          <div className="absolute bottom-3 right-3 rounded border border-green-400/20 bg-green-400/10 px-2 py-1 text-[7px] text-green-300">
            EXIT CODE 0
          </div>
        )}
      </div>
    </div>
  )
}

function RepositoryInvestigation({
  progress,
}: {
  progress: number
}) {
  const graphProgress = smooth(
    range(progress, 0.45, 0.63)
  )

  const activeFile =
    files[
      Math.min(
        files.length - 1,
        Math.floor(graphProgress * files.length)
      )
    ]

  const nodeOne =
    smooth(range(progress, 0.45, 0.5))

  const nodeTwo =
    smooth(range(progress, 0.5, 0.55))

  const nodeThree =
    smooth(range(progress, 0.55, 0.6))

  return (
    <div
      className="pointer-events-none absolute inset-0 z-20"
      style={{
        transform: `scale(${0.96 + graphProgress * 0.04})`,
        clipPath:
          graphProgress <= 0
            ? "inset(100% 0 0 0)"
            : "inset(0 0 0 0)",
      }}
    >
      <div className="absolute inset-0 bg-[#07111f]/90 backdrop-blur-[1px]" />

      <div className="absolute inset-[7%] overflow-hidden rounded-lg border border-white/10 bg-[#081321]/95">
        <Bar>investigation graph / runtime verification</Bar>

        <div className="relative h-[calc(100%-2rem)]">
          <div className="absolute left-5 top-4 text-[7px] uppercase tracking-[0.25em] text-slate-500">
            HOW WE GOT THERE
          </div>

          <div
            className="absolute left-[10%] top-[28%] flex h-12 w-28 flex-col justify-center rounded border border-blue-300/20 bg-blue-500/10 px-3"
            style={{
              transform: `translateY(${(1 - nodeOne) * 24}px)`,
            }}
          >
            <span className="text-[6px] text-blue-200">
              INVESTIGATION NODE
            </span>
            <strong className="mt-1 text-[8px] text-white">
              Read package.json
            </strong>
          </div>

          <div
            className="absolute left-[39%] top-[50%] flex h-12 w-28 flex-col justify-center rounded border border-amber-300/20 bg-amber-400/10 px-3"
            style={{
              transform: `translateY(${(1 - nodeTwo) * 24}px)`,
            }}
          >
            <span className="text-[6px] text-amber-200">
              OBSERVATION
            </span>
            <strong className="mt-1 text-[8px] text-white">
              obs_031
            </strong>
          </div>

          <div
            className="absolute right-[10%] top-[28%] flex h-12 w-28 flex-col justify-center rounded border border-emerald-300/20 bg-emerald-400/10 px-3"
            style={{
              transform: `translateY(${(1 - nodeThree) * 24}px)`,
            }}
          >
            <span className="text-[6px] text-emerald-200">
              CLAIM
            </span>
            <strong className="mt-1 text-[8px] text-white">
              Runtime = Node 18
            </strong>
          </div>

          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
          >
            <path
              d="M 24 36 C 31 36, 33 50, 39 56"
              fill="none"
              stroke="rgba(147,197,253,.5)"
              strokeWidth="0.4"
              strokeDasharray="100"
              strokeDashoffset={100 - nodeTwo * 100}
            />

            <path
              d="M 61 56 C 68 50, 70 36, 76 36"
              fill="none"
              stroke="rgba(110,231,183,.55)"
              strokeWidth="0.4"
              strokeDasharray="100"
              strokeDashoffset={100 - nodeThree * 100}
            />
          </svg>

          <div className="absolute bottom-4 left-5 right-5 flex items-center justify-between border-t border-white/10 pt-3">
            <span className="text-[7px] text-slate-500">
              AGENT READING
            </span>

            <strong className="text-[8px] text-blue-100">
              {activeFile}
            </strong>

            <span className="text-[7px] text-emerald-400">
              {Math.round(graphProgress * 42)} files mapped
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

function BrowserInvestigation({
  progress,
}: {
  progress: number
}) {
  const browserProgress = smooth(
    range(progress, 0.62, 0.81)
  )

  const browserOpen = smooth(
    range(progress, 0.61, 0.68)
  )

  const browserClose = smooth(
    range(progress, 0.79, 0.84)
  )

  const scale =
    0.76 +
    browserOpen * 0.24 -
    browserClose * 0.16

  const x =
    36 -
    browserClose * 30

  const y =
    28 -
    browserClose * 20

  return (
    <div
      className="pointer-events-none absolute inset-0 z-40"
      style={{
        clipPath:
          browserOpen <= 0
            ? "inset(100% 0 0 0)"
            : "inset(0 0 0 0)",
      }}
    >
      <div
        className="absolute left-[7%] top-[7%] h-[82%] w-[86%] overflow-hidden rounded-xl border border-slate-300/30 bg-white shadow-2xl"
        style={{
          transformOrigin: "center center",
          transform: `translate3d(${x}px, ${y}px, 0) scale(${scale})`,
        }}
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
          enableTabManagement
          enableBookmarks
          enableHistory
          enableDownloads={false}
          enableSettings={false}
          className="h-full rounded-none border-0 shadow-none"
        />

        <div className="pointer-events-none absolute bottom-3 left-3 flex items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-2.5 py-1 text-[7px] text-slate-500 shadow-sm backdrop-blur">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          agent verification
        </div>

        <div
          className="pointer-events-none absolute left-[18%] top-[38%] h-8 w-8 rounded-full border border-blue-400/60"
          style={{
            transform: `translate(
              ${Math.sin(browserProgress * Math.PI * 5) * 18}px,
              ${Math.sin(browserProgress * Math.PI * 3) * 12}px
            )`,
          }}
        />
      </div>
    </div>
  )
}

function EvidenceLayer({
  progress,
}: {
  progress: number
}) {
  const evidence = smooth(
    range(progress, 0.78, 0.92)
  )

  const lineOne = smooth(
    range(progress, 0.78, 0.84)
  )

  const lineTwo = smooth(
    range(progress, 0.83, 0.88)
  )

  const lineThree = smooth(
    range(progress, 0.87, 0.92)
  )

  if (evidence <= 0) {
    return null
  }

  return (
    <div className="pointer-events-none absolute inset-0 z-50">
      <div className="absolute left-[6%] top-[7%] text-[7px] uppercase tracking-[0.25em] text-slate-400">
        EVIDENCE RESOLUTION
      </div>

      <div
        className="absolute left-[7%] top-[22%] w-[28%] rounded border border-amber-300/20 bg-[#101827]/95 p-3"
        style={{
          transform: `translateX(${(1 - lineOne) * -60}px)`,
        }}
      >
        <span className="text-[6px] text-amber-300">
          OBSERVATION
        </span>
        <p className="mt-1 text-[8px] text-white">
          package.json declares Node.js 18
        </p>
        <small className="text-[6px] text-slate-500">
          obs_031 · immutable
        </small>
      </div>

      <div
        className="absolute left-[36%] top-[44%] h-px w-[25%] origin-left bg-emerald-300/60"
        style={{
          transform: `scaleX(${lineTwo})`,
        }}
      />

      <div
        className="absolute right-[7%] top-[29%] w-[28%] rounded border border-emerald-300/20 bg-[#101827]/95 p-3"
        style={{
          transform: `translateX(${(1 - lineTwo) * 60}px)`,
        }}
      >
        <span className="text-[6px] text-emerald-300">
          CLAIM
        </span>
        <p className="mt-1 text-[8px] text-white">
          Runtime = Node.js 18
        </p>
        <small className="text-[6px] text-emerald-400">
          TRUST · HIGH
        </small>
      </div>

      <div
        className="absolute left-[7%] bottom-[14%] w-[28%] rounded border border-blue-300/20 bg-[#101827]/95 p-3"
        style={{
          transform: `translateY(${(1 - lineThree) * 45}px)`,
        }}
      >
        <span className="text-[6px] text-blue-300">
          OBSERVATION
        </span>
        <p className="mt-1 text-[8px] text-white">
          npm install completed
        </p>
        <small className="text-[6px] text-slate-500">
          obs_034 · exit code 0
        </small>
      </div>

      <div
        className="absolute right-[7%] bottom-[12%] w-[28%] rounded border border-white/15 bg-[#101827]/95 p-3"
        style={{
          transform: `translateY(${(1 - evidence) * 40}px)`,
        }}
      >
        <span className="text-[6px] text-slate-400">
          EVIDENCE ENGINE
        </span>

        <div className="mt-2 space-y-1.5">
          <div className="flex justify-between text-[7px]">
            <span>Runtime</span>
            <span className="text-emerald-400">
              VERIFIED
            </span>
          </div>

          <div className="flex justify-between text-[7px]">
            <span>Dependencies</span>
            <span className="text-emerald-400">
              VERIFIED
            </span>
          </div>

          <div className="flex justify-between text-[7px]">
            <span>Browser</span>
            <span className="text-emerald-400">
              VERIFIED
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

function ReportLayer({
  progress,
}: {
  progress: number
}) {
  const report = smooth(
    range(progress, 0.9, 1)
  )

  const graph = smooth(
    range(progress, 0.9, 0.95)
  )

  const checkpoint = smooth(
    range(progress, 0.94, 0.98)
  )

  return (
    <div
      className="pointer-events-none absolute inset-0 z-[60]"
      style={{
        clipPath:
          report <= 0
            ? "inset(100% 0 0 0)"
            : "inset(0 0 0 0)",
      }}
    >
      <div
        className="absolute inset-[5%] overflow-hidden rounded-xl border border-white/15 bg-[#07111f]"
        style={{
          transform: `scale(${0.94 + report * 0.06})`,
        }}
      >
        <Bar status="CONVERGED">
          wizard / verification report
        </Bar>

        <div className="relative h-[calc(100%-2rem)] overflow-hidden p-5">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-[6px] uppercase tracking-[0.25em] text-slate-500">
                VERIFICATION REPORT
              </p>

              <h3 className="mt-2 text-sm font-semibold text-white">
                Repository verification
              </h3>

              <p className="mt-1 text-[7px] text-slate-500">
                Evidence backed investigation · complete
              </p>
            </div>

            <div className="rounded border border-emerald-300/20 bg-emerald-400/10 px-2 py-1 text-[7px] text-emerald-300">
              VERIFIED
            </div>
          </div>

          <div className="relative mt-6 h-[55%]">
            <svg
              className="absolute inset-0 h-full w-full"
              viewBox="0 0 100 60"
              preserveAspectRatio="none"
            >
              <path
                d="M 15 14 L 50 30 L 85 14"
                fill="none"
                stroke="rgba(147,197,253,.5)"
                strokeWidth="0.35"
                strokeDasharray="100"
                strokeDashoffset={100 - graph * 100}
              />

              <path
                d="M 50 30 L 50 50"
                fill="none"
                stroke="rgba(110,231,183,.5)"
                strokeWidth="0.35"
                strokeDasharray="100"
                strokeDashoffset={100 - checkpoint * 100}
              />
            </svg>

            <div className="absolute left-[5%] top-[8%] rounded border border-blue-300/20 bg-blue-400/10 px-3 py-2">
              <span className="text-[6px] text-blue-200">
                INVESTIGATION
              </span>
              <p className="mt-1 text-[7px] text-white">
                Read package.json
              </p>
            </div>

            <div className="absolute left-[40%] top-[40%] rounded border border-amber-300/20 bg-amber-400/10 px-3 py-2">
              <span className="text-[6px] text-amber-200">
                OBSERVATION
              </span>
              <p className="mt-1 text-[7px] text-white">
                exit code 0
              </p>
            </div>

            <div className="absolute right-[5%] top-[8%] rounded border border-emerald-300/20 bg-emerald-400/10 px-3 py-2">
              <span className="text-[6px] text-emerald-200">
                CLAIM
              </span>
              <p className="mt-1 text-[7px] text-white">
                Dependencies installable
              </p>
            </div>

            <div
              className="absolute left-1/2 top-[78%] -translate-x-1/2 rounded border border-white/15 bg-white/5 px-4 py-2"
              style={{
                transform: `translateX(-50%) scale(${0.8 + checkpoint * 0.2})`,
              }}
            >
              <span className="text-[6px] text-slate-400">
                CHECKPOINT
              </span>

              <p className="mt-1 text-[7px] text-white">
                Runtime verification satisfied
              </p>

              <p className="mt-1 text-[6px] text-emerald-400">
                ✓ convergence reached
              </p>
            </div>
          </div>

          <div className="absolute bottom-4 left-5 right-5 flex items-center justify-between border-t border-white/10 pt-3">
            <span className="text-[7px] text-slate-500">
              CLAIMS
            </span>

            <strong className="text-[8px] text-white">
              3 verified
            </strong>

            <span className="text-[7px] text-slate-500">
              EVIDENCE
            </span>

            <strong className="text-[8px] text-white">
              9 observations
            </strong>

            <span className="text-[7px] text-slate-500">
              TRUST
            </span>

            <strong className="text-[8px] text-emerald-400">
              HIGH
            </strong>
          </div>
        </div>
      </div>
    </div>
  )
}

function InvestigationTimeline({
  progress,
}: {
  progress: number
}) {
  const events = [
    ["01", "Investigation created", 0.04],
    ["02", "Repository manifest", 0.13],
    ["03", "Runtime observed", 0.25],
    ["04", "Dependencies verified", 0.39],
    ["05", "Investigation graph", 0.53],
    ["06", "Browser evidence", 0.69],
    ["07", "Claims validated", 0.83],
    ["08", "Convergence", 0.97],
  ]

  return (
    <div className="pointer-events-none absolute bottom-6 left-1/2 z-[80] hidden w-[min(760px,72%)] -translate-x-1/2 lg:block">
      <div className="relative h-px bg-white/10">
        <div
          className="absolute left-0 top-0 h-px bg-white/60"
          style={{
            width: `${progress * 100}%`,
          }}
        />

        {events.map(
          ([number, label, position]) => {
            const p =
              typeof position === "number"
                ? position
                : 0

            const active =
              progress >= p

            return (
              <div
                key={String(number)}
                className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2"
                style={{
                  left: `${p * 100}%`,
                }}
              >
                <span
                  className={cn(
                    "block h-2 w-2 rounded-full border",
                    active
                      ? "border-white bg-white"
                      : "border-white/25 bg-[#123A6B]"
                  )}
                />

                {active && (
                  <span className="absolute left-1/2 top-4 -translate-x-1/2 whitespace-nowrap text-[6px] text-white/70">
                    {label}
                  </span>
                )}
              </div>
            )
          }
        )}
      </div>
    </div>
  )
}

function getStageLabel(
  progress: number
) {
  if (progress < 0.28) {
    return "DISCOVERY"
  }

  if (progress < 0.49) {
    return "EXECUTION"
  }

  if (progress < 0.63) {
    return "INVESTIGATION GRAPH"
  }

  if (progress < 0.81) {
    return "BROWSER VERIFICATION"
  }

  if (progress < 0.92) {
    return "EVIDENCE ENGINE"
  }

  return "CONVERGENCE"
}

export function CinematicHero({
  className,
}: {
  className?: string
}) {
  const root = useRef<HTMLElement>(null)

  const [progress, setProgress] =
    useState(0)

  const progressRef =
    useRef(0)

  const reducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches

  useEffect(() => {
    let frame = 0

    const update = () => {
      frame = 0

      const element = root.current

      if (!element) {
        return
      }

      const rect =
        element.getBoundingClientRect()

      const distance = Math.max(
        1,
        element.offsetHeight -
          window.innerHeight
      )

      const next = clamp(
        -rect.top / distance
      )

      progressRef.current = next

      element.style.setProperty(
        "--scene-progress",
        next.toFixed(4)
      )

      const intro =
        smooth(range(next, 0, 0.12))

      const outro =
        smooth(range(next, 0.88, 1))

      const scale =
        0.9 +
        intro * 0.1 -
        outro * 0.025

      const radius =
        28 -
        intro * 28 +
        outro * 28

      element.style.setProperty(
        "--scene-scale",
        scale.toFixed(4)
      )

      element.style.setProperty(
        "--scene-radius",
        `${radius.toFixed(2)}px`
      )

      setProgress((current) =>
        Math.abs(current - next) > 0.001
          ? next
          : current
      )
    }

    const onScroll = () => {
      if (frame) {
        return
      }

      frame =
        window.requestAnimationFrame(update)
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
        window.cancelAnimationFrame(frame)
      }
    }
  }, [])

  const investigationState =
    useMemo(
      () => getStageLabel(progress),
      [progress]
    )

  const sceneProgress =
    reducedMotion ? 1 : progress

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
            borderRadius:
              "var(--scene-radius, 28px)",
            transform:
              "scale(var(--scene-scale, 0.9))",
            willChange: "transform",
          }}
        >
          <SafeMeshGradient />

          <div className="pointer-events-none absolute inset-0 z-10">
            <div
              className="absolute inset-0"
              style={{
                background:
                  "radial-gradient(circle at 50% 45%, rgba(255,255,255,.08), transparent 45%)",
                opacity:
                  0.35 +
                  sceneProgress * 0.2,
              }}
            />
          </div>

          <div className="relative z-20 flex w-full max-w-[1540px] flex-col items-center gap-8 px-4 py-12 lg:flex-row lg:gap-14 lg:px-10">
            <div className="w-full max-w-[350px] shrink-0">
              <p className="mb-3 font-mono text-[10px] uppercase tracking-[.3em] text-blue-100/70">
                Wizard investigation
              </p>

              <h2 className="text-balance text-3xl font-semibold leading-[1.05] tracking-tight sm:text-4xl lg:text-5xl">
                AI writes the code.
                <br />
                Wizard checks the
                reality.
              </h2>

              <p className="mt-5 max-w-[330px] text-sm leading-relaxed text-blue-50/80">
                Watch an autonomous
                investigation turn
                repository actions into
                evidence backed knowledge.
              </p>

              <div className="mt-8">
                <div className="mb-2 flex items-center justify-between font-mono text-[8px] uppercase tracking-[.2em] text-blue-100/50">
                  <span>
                    Investigation state
                  </span>

                  <span className="text-blue-100/80">
                    {investigationState}
                  </span>
                </div>

                <div className="h-px w-full bg-white/10">
                  <div
                    className="h-px bg-white/70"
                    style={{
                      width: `${progress * 100}%`,
                    }}
                  />
                </div>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-2 font-mono text-[7px] uppercase tracking-[.15em] text-blue-100/50">
                <div className="rounded border border-white/10 bg-white/5 px-2 py-2">
                  <span className="block">
                    Evidence
                  </span>

                  <strong className="mt-1 block text-white/80">
                    Immutable
                  </strong>
                </div>

                <div className="rounded border border-white/10 bg-white/5 px-2 py-2">
                  <span className="block">
                    Truth
                  </span>

                  <strong className="mt-1 block text-white/80">
                    Runtime owned
                  </strong>
                </div>
              </div>
            </div>

            <div className="scene-laptop relative w-full max-w-[1180px] lg:ml-4">
              <div className="relative aspect-[650/400] w-full">
                <MacbookPro
                  className="absolute inset-0 h-full w-full text-[#07101f] drop-shadow-2xl"
                  aria-label="Wizard autonomous investigation workspace"
                  role="img"
                >
                  <div className="screen relative h-full w-full overflow-hidden bg-[#07101f] font-mono text-[8px] sm:text-[11px] md:text-xs">
                    <div className="absolute left-0 right-0 top-0 z-[100] flex items-center gap-3 overflow-hidden border-b border-white/10 bg-[#0b1424] px-3 py-2 text-[7px] text-slate-400 sm:text-[10px]">
                      <span className="text-white">
                        WIZARD
                      </span>

                      <span className="text-slate-600">
                        /
                      </span>

                      <span>
                        investigation
                      </span>

                      <span className="ml-auto whitespace-nowrap text-emerald-400">
                        ● {investigationState}
                      </span>
                    </div>

                    <div className="absolute inset-0 top-8 overflow-hidden">
                      <Workspace
                        progress={progress}
                      />

                      <Terminal
                        progress={progress}
                      />

                      <RepositoryInvestigation
                        progress={progress}
                      />

                      <BrowserInvestigation
                        progress={progress}
                      />

                      <EvidenceLayer
                        progress={progress}
                      />

                      <ReportLayer
                        progress={progress}
                      />
                    </div>

                    <InvestigationTimeline
                      progress={progress}
                    />
                  </div>
                </MacbookPro>
              </div>
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        .scene-card {
          transform-origin: center center;
          transition:
            transform 120ms linear,
            border-radius 120ms linear;
        }

        .window-bar {
          height: 32px;
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 0 10px;
          background: #0b1424;
          border-bottom: 1px solid rgba(255,255,255,.08);
          color: rgba(203,213,225,.72);
          font-size: 7px;
          letter-spacing: .02em;
        }

        .window-bar i {
          width: 7px;
          height: 7px;
          border-radius: 999px;
          background: rgba(255,255,255,.22);
          flex: 0 0 auto;
        }

        .window-bar i:first-child {
          background: #fb7185;
        }

        .window-bar i:nth-child(2) {
          background: #facc15;
        }

        .window-bar i:nth-child(3) {
          background: #4ade80;
        }

        .window-bar span {
          margin-left: 4px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .live-dot {
          margin-left: auto;
          color: #4ade80;
          font-size: 6px;
          font-weight: 500;
          letter-spacing: .12em;
        }

        .ide-body {
          display: grid;
          grid-template-columns: 27% 73%;
          height: calc(100% - 32px);
          background: #111827;
        }

        .file-tree {
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding: 16px 10px;
          border-right: 1px solid rgba(255,255,255,.06);
          color: rgba(148,163,184,.75);
          font-size: 7px;
          overflow: hidden;
        }

        .file-tree b {
          color: rgba(226,232,240,.7);
          font-size: 6px;
          letter-spacing: .18em;
          margin-bottom: 4px;
        }

        .file-tree em {
          font-style: normal;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          padding: 3px 5px;
          border-radius: 3px;
        }

        .file-tree .repo-selected {
          color: #dbeafe;
          background: rgba(59,130,246,.13);
          box-shadow: inset 2px 0 0 rgba(147,197,253,.8);
        }

        .code-stream {
          margin: 0;
          padding: 20px;
          overflow: hidden;
          color: rgba(226,232,240,.78);
          font-size: 8px;
          line-height: 1.8;
        }

        .code-current {
          display: inline-block;
          min-width: 100%;
          color: white;
          background: rgba(59,130,246,.12);
          box-shadow: inset 2px 0 0 rgba(96,165,250,.8);
        }

        .typing-caret {
          display: inline-block;
          width: 5px;
          height: 10px;
          margin-left: 2px;
          vertical-align: middle;
          background: #93c5fd;
          animation: wizard-caret 900ms steps(2,end) infinite;
        }

        @keyframes wizard-caret {
          0%, 45% {
            opacity: 1;
          }

          46%, 100% {
            opacity: 0;
          }
        }

        @media (max-width: 1024px) {
          .scene-card {
            transform: none !important;
            border-radius: 0 !important;
          }

          .window-bar {
            height: 28px;
          }

          .ide-body {
            height: calc(100% - 28px);
          }

          .file-tree {
            padding: 10px 7px;
            gap: 5px;
          }

          .code-stream {
            padding: 12px;
            font-size: 7px;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .scene-card {
            transition: none;
          }

          .typing-caret {
            animation: none;
            opacity: 1;
          }
        }
      `}</style>
    </section>
  )
}

export default CinematicHero