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

/* =========================================================
   UTILITIES
========================================================= */

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

function progressBetween(
  value: number,
  start: number,
  end: number
) {
  return clamp(
    (value - start) /
      Math.max(0.0001, end - start)
  )
}

function ease(value: number) {
  const x = clamp(value)
  return x * x * (3 - 2 * x)
}

/*
 * A slightly slower easing curve.
 *
 * The purpose is deliberate:
 * the scene should feel like an investigation
 * happening in time, not like UI elements responding
 * immediately to the scrollbar.
 */
function slowEase(value: number) {
  const x = clamp(value)
  return x * x * x * (x * (x * 6 - 15) + 10)
}

/* =========================================================
   WINDOW FRAME
========================================================= */

function WindowBar({
  title,
  status,
}: {
  title: string
  status?: string
}) {
  return (
    <div className="wizard-window-bar">
      <div className="wizard-window-lights">
        <i />
        <i />
        <i />
      </div>

      <span className="wizard-window-title">
        {title}
      </span>

      {status && (
        <span className="wizard-window-status">
          {status}
        </span>
      )}
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
  const reveal = slowEase(
    progressBetween(
      progress,
      0.02,
      0.22
    )
  )

  const visibleLines = Math.max(
    1,
    Math.min(
      code.length,
      Math.floor(
        reveal * code.length
      ) + 1
    )
  )

  const selectedFile =
    progress < 0.09
      ? "package.json"
      : progress < 0.16
        ? "README.md"
        : "app/page.tsx"

  return (
    <div
      className="wizard-window workspace-window"
      style={{
        opacity: 1,
        transform: `
          translate3d(
            ${0}px,
            ${(1 - reveal) * 14}px,
            0
          )
          scale(${0.985 + reveal * 0.015})
        `,
      }}
    >
      <WindowBar
        title="wizard repo / workspace"
        status="INSPECTING"
      />

      <div className="workspace-body">
        <div className="workspace-tree">
          <b>EXPLORER</b>

          <span>⌄ wizard repo</span>

          <em
            className={
              selectedFile ===
              "package.json"
                ? "workspace-selected"
                : ""
            }
          >
            ◇ package.json
          </em>

          <em
            className={
              selectedFile ===
              "README.md"
                ? "workspace-selected"
                : ""
            }
          >
            ◇ README.md
          </em>

          <em
            className={
              selectedFile ===
              "app/page.tsx"
                ? "workspace-selected"
                : ""
            }
          >
            ◇ app/
          </em>

          <em>◇ components/</em>
          <em>◇ lib/</em>
        </div>

        <pre className="workspace-code">
          <code>
            {code
              .slice(0, visibleLines)
              .map((line, index) => (
                <React.Fragment
                  key={index}
                >
                  <span
                    className={
                      index ===
                      visibleLines - 1
                        ? "workspace-current-line"
                        : ""
                    }
                  >
                    {line || " "}
                  </span>

                  {index <
                    visibleLines - 1 &&
                    "\n"}
                </React.Fragment>
              ))}

            <span className="wizard-caret" />
          </code>
        </pre>
      </div>

      <div className="workspace-footer">
        <span>
          investigation node_014
        </span>

        <span>
          manifest → source
        </span>
      </div>
    </div>
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
  const open = slowEase(
    progressBetween(
      progress,
      0.18,
      0.29
    )
  )

  const execution = slowEase(
    progressBetween(
      progress,
      0.27,
      0.46
    )
  )

  const commandsVisible = Math.max(
    0,
    Math.min(
      commands.length,
      Math.floor(
        execution *
          commands.length
      )
    )
  )

  return (
    <div
      className="wizard-window terminal-window"
      style={{
        opacity: open,
        transform: `
          translate3d(
            ${24 - open * 24}px,
            ${18 - open * 18}px,
            0
          )
          scale(${0.96 + open * 0.04})
        `,
      }}
    >
      <WindowBar
        title="terminal · wizard session"
        status={
          execution > 0.95
            ? "EXIT 0"
            : "RUNNING"
        }
      />

      <div className="terminal-body">
        <div className="terminal-glow" />

        <div className="terminal-content">
          {commands
            .slice(0, commandsVisible)
            .map(
              (
                command,
                index
              ) => (
                <div
                  key={command}
                  className="terminal-command"
                >
                  <div>
                    <span className="terminal-user">
                      wizard@repo
                    </span>

                    <span className="terminal-path">
                      {" "}
                      ~/wizard-repo
                    </span>

                    <span>
                      {" "}
                      $
                    </span>

                    <span className="terminal-command-text">
                      {" "}
                      {command}
                    </span>
                  </div>

                  <div className="terminal-result">
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

          <div className="terminal-prompt">
            <span className="terminal-user">
              wizard@repo
            </span>

            <span className="terminal-path">
              {" "}
              ~/wizard-repo
            </span>

            <span> $</span>

            <span className="wizard-caret terminal-caret" />
          </div>
        </div>

        {execution > 0.78 && (
          <div className="terminal-exit">
            process exited with code 0
          </div>
        )}
      </div>
    </div>
  )
}

/* =========================================================
   REPOSITORY WINDOW
========================================================= */

function RepositoryWindow({
  progress,
}: {
  progress: number
}) {
  const open = slowEase(
    progressBetween(
      progress,
      0.38,
      0.52
    )
  )

  const fileIndex = Math.min(
    files.length - 1,
    Math.floor(
      open * files.length
    )
  )

  const activeFile =
    files[fileIndex]

  return (
    <div
      className="wizard-window repository-window"
      style={{
        opacity: open,
        transform: `
          translate3d(
            ${-18 + open * 18}px,
            ${20 - open * 20}px,
            0
          )
          scale(${0.96 + open * 0.04})
        `,
      }}
    >
      <WindowBar
        title="agent activity / repository"
        status="READING"
      />

      <div className="repository-body">
        <div className="repository-tree">
          <span className="repository-heading">
            REPOSITORY STRUCTURE
          </span>

          <FileTree
            data={
              wizardFileStructure
            }
            className="repository-file-tree"
          />
        </div>

        <div className="repository-inspector">
          <span className="repository-label">
            AGENT READING
          </span>

          <strong>
            {activeFile}
          </strong>

          <div className="repository-check">
            ✓ scanning source symbols
          </div>

          <div className="repository-check">
            ✓ {14 + fileIndex} files mapped
          </div>

          <div className="repository-check">
            ✓ dependency relationship found
          </div>

          <div className="repository-trace">
            trace → Investigation Node
            → Observation
          </div>
        </div>
      </div>
    </div>
  )
}

/* =========================================================
   KNOWLEDGE WINDOW
========================================================= */

function KnowledgeWindow({
  progress,
}: {
  progress: number
}) {
  const open = slowEase(
    progressBetween(
      progress,
      0.51,
      0.65
    )
  )

  const observation =
    slowEase(
      progressBetween(
        progress,
        0.53,
        0.62
      )
    )

  const claim =
    slowEase(
      progressBetween(
        progress,
        0.58,
        0.68
      )
    )

  return (
    <div
      className="wizard-window knowledge-window"
      style={{
        opacity: open,
        transform: `
          translate3d(
            0,
            ${20 - open * 20}px,
            0
          )
          scale(${0.96 + open * 0.04})
        `,
      }}
    >
      <WindowBar
        title="knowledge graph / evidence"
        status="VALIDATING"
      />

      <div className="knowledge-body">
        <div className="knowledge-title">
          <span>
            WHAT WE KNOW
          </span>

          <small>
            runtime owned
          </small>
        </div>

        <div className="knowledge-chain">
          <div
            className="knowledge-node observation"
            style={{
              opacity: observation,
              transform: `
                translateX(
                  ${(1 - observation) *
                  -18}px
                )
              `,
            }}
          >
            <small>
              OBSERVATION
            </small>

            <strong>
              obs_031
            </strong>

            <p>
              package.json declares
              Node.js 18
            </p>
          </div>

          <div
            className="knowledge-connector"
            style={{
              transform: `scaleX(${observation})`,
            }}
          />

          <div
            className="knowledge-node claim"
            style={{
              opacity: claim,
              transform: `
                translateX(
                  ${(1 - claim) *
                  18}px
                )
              `,
            }}
          >
            <small>
              CLAIM
            </small>

            <strong>
              Runtime = Node.js 18
            </strong>

            <p className="knowledge-high">
              TRUST · HIGH
            </p>
          </div>
        </div>

        <div className="knowledge-bottom">
          <span>
            Evidence Engine
          </span>

          <span>
            immutable observation
          </span>

          <span>
            claim validated
          </span>
        </div>
      </div>
    </div>
  )
}

/* =========================================================
   BROWSER WINDOW
========================================================= */

function BrowserWindow({
  progress,
}: {
  progress: number
}) {
  const open = slowEase(
    progressBetween(
      progress,
      0.62,
      0.76
    )
  )

  return (
    <div
      className="wizard-window browser-window"
      style={{
        opacity: open,
        transform: `
          translate3d(
            ${24 - open * 24}px,
            ${18 - open * 18}px,
            0
          )
          scale(${0.97 + open * 0.03})
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

      <div className="browser-verification-badge">
        <span />
        Browser evidence captured
      </div>
    </div>
  )
}

/* =========================================================
   FINAL REPORT
========================================================= */

function ReportWindow({
  progress,
}: {
  progress: number
}) {
  const open = slowEase(
    progressBetween(
      progress,
      0.76,
      0.94
    )
  )

  const reportReady =
    progress > 0.92

  return (
    <div
      className="wizard-window report-window"
      style={{
        opacity: open,
        transform: `
          translate3d(
            0,
            ${26 - open * 26}px,
            0
          )
          scale(${0.95 + open * 0.05})
        `,
      }}
    >
      <WindowBar
        title="wizard / verification report"
        status={
          reportReady
            ? "CONVERGED"
            : "ASSEMBLING"
        }
      />

      <div className="report-body">
        <div className="report-heading">
          <div>
            <span>
              VERIFICATION REPORT
            </span>

            <h3>
              Repository verification
            </h3>

            <p>
              Evidence backed investigation
            </p>
          </div>

          <div className="report-pass">
            ✓ VERIFIED
          </div>
        </div>

        <div className="report-columns">
          <div className="report-section">
            <small>
              VERIFIED CLAIMS
            </small>

            <div className="report-row">
              <span>
                Runtime
              </span>

              <strong>
                Node.js 18
              </strong>

              <b>
                HIGH
              </b>
            </div>

            <div className="report-row">
              <span>
                Dependencies
              </span>

              <strong>
                Installable
              </strong>

              <b>
                HIGH
              </b>
            </div>

            <div className="report-row">
              <span>
                Browser
              </span>

              <strong>
                Evidence captured
              </strong>

              <b>
                HIGH
              </b>
            </div>
          </div>

          <div className="report-section">
            <small>
              EVIDENCE TRAIL
            </small>

            <div className="report-event">
              <span>
                obs_031
              </span>

              <p>
                package.json declares
                Node.js 18
              </p>
            </div>

            <div className="report-event">
              <span>
                obs_034
              </span>

              <p>
                npm install completed
                with exit code 0
              </p>
            </div>

            <div className="report-event">
              <span>
                obs_041
              </span>

              <p>
                Browser verification
                captured evidence
              </p>
            </div>
          </div>
        </div>

        <div className="report-footer">
          <span>
            3 claims
          </span>

          <span>
            9 observations
          </span>

          <span>
            0 contradictions
          </span>

          <span className="report-converged">
            {reportReady
              ? "CONVERGENCE REACHED"
              : "EVALUATING CHECKPOINTS"}
          </span>
        </div>
      </div>
    </div>
  )
}

/* =========================================================
   STORY STATE
========================================================= */

function InvestigationLabel({
  progress,
}: {
  progress: number
}) {
  const state =
    progress < 0.2
      ? "DISCOVERY"
      : progress < 0.38
        ? "EXECUTION"
        : progress < 0.55
          ? "REPOSITORY INVESTIGATION"
          : progress < 0.7
            ? "EVIDENCE VALIDATION"
            : progress < 0.84
              ? "BROWSER VERIFICATION"
              : "CONVERGENCE"

  return (
    <div className="investigation-label">
      <span className="investigation-pulse" />
      <span>
        {state}
      </span>
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

      setProgress((current) =>
        Math.abs(current - next) >
        0.001
          ? next
          : current
      )
    }

    const onScroll = () => {
      if (frame) {
        return
      }

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
        window.cancelAnimationFrame(frame)
      }
    }
  }, [])

  const sceneScale =
    0.92 +
    slowEase(
      progressBetween(
        progress,
        0,
        0.12
      )
    ) *
      0.08

  const sceneRadius =
    24 -
    slowEase(
      progressBetween(
        progress,
        0,
        0.12
      )
    ) *
      24

  const storyComplete =
    progress > 0.96

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
            transform: `scale(${sceneScale})`,
            borderRadius: `${sceneRadius}px`,
          }}
        >
          <SafeMeshGradient />

          <div className="pointer-events-none absolute inset-0 z-10 bg-[radial-gradient(circle_at_55%_45%,rgba(255,255,255,.08),transparent_48%)]" />

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
                execute, verify, and
                build an evidence trail.
              </p>

              <InvestigationLabel
                progress={progress}
              />

              {storyComplete && (
                <div className="mt-4 text-[9px] font-mono uppercase tracking-[.2em] text-emerald-200/70">
                  Investigation converged
                </div>
              )}
            </div>

            <div className="scene-laptop relative w-full max-w-[1180px] lg:ml-4">
              <div className="relative aspect-[650/400] w-full">
                <MacbookPro
                  className="absolute inset-0 h-full w-full text-[#07101f] drop-shadow-2xl"
                  aria-label="Wizard autonomous repository investigation"
                  role="img"
                >
                  <div className="screen relative h-full w-full overflow-hidden bg-[#07101f] font-mono">
                    <div className="absolute left-0 right-0 top-0 z-[200] flex h-7 items-center border-b border-white/10 bg-[#0b1424] px-3">
                      <span className="text-[7px] font-medium tracking-[.16em] text-white/80 sm:text-[9px]">
                        WIZARD
                      </span>

                      <span className="mx-2 text-[7px] text-white/20">
                        /
                      </span>

                      <span className="text-[7px] text-slate-500 sm:text-[9px]">
                        autonomous investigation
                      </span>

                      <div className="ml-auto flex items-center gap-2 text-[6px] uppercase tracking-[.12em] sm:text-[8px]">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />

                        <span className="text-emerald-300/80">
                          {storyComplete
                            ? "converged"
                            : "investigating"}
                        </span>
                      </div>
                    </div>

                    <div className="absolute inset-x-0 bottom-0 top-7 overflow-hidden">
                      <WorkspaceWindow
                        progress={progress}
                      />

                      <TerminalWindow
                        progress={progress}
                      />

                      <RepositoryWindow
                        progress={progress}
                      />

                      <KnowledgeWindow
                        progress={progress}
                      />

                      <BrowserWindow
                        progress={progress}
                      />

                      <ReportWindow
                        progress={progress}
                      />
                    </div>
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
            transform 180ms linear,
            border-radius 180ms linear;
        }

        .wizard-window {
          position: absolute;
          overflow: hidden;
          border: 1px solid rgba(255,255,255,.11);
          border-radius: 8px;
          background: #0b1424;
          box-shadow:
            0 20px 45px rgba(0,0,0,.25),
            0 4px 14px rgba(0,0,0,.16);
          will-change: transform, opacity;
        }

        .wizard-window-bar {
          height: 28px;
          display: flex;
          align-items: center;
          gap: 5px;
          padding: 0 9px;
          background: #0b1424;
          border-bottom: 1px solid rgba(255,255,255,.08);
          color: rgba(203,213,225,.72);
          font-size: 7px;
          white-space: nowrap;
        }

        .wizard-window-lights {
          display: flex;
          gap: 4px;
          flex-shrink: 0;
        }

        .wizard-window-lights i {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: rgba(255,255,255,.2);
        }

        .wizard-window-lights i:first-child {
          background: #fb7185;
        }

        .wizard-window-lights i:nth-child(2) {
          background: #facc15;
        }

        .wizard-window-lights i:nth-child(3) {
          background: #4ade80;
        }

        .wizard-window-title {
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .wizard-window-status {
          margin-left: auto;
          color: #4ade80;
          font-size: 5px;
          letter-spacing: .12em;
        }

        /* ---------------------------------------------
           WINDOW POSITIONS
           --------------------------------------------- */

        .workspace-window {
          left: 4%;
          top: 7%;
          width: 54%;
          height: 54%;
          z-index: 10;
        }

        .terminal-window {
          left: 43%;
          top: 11%;
          width: 51%;
          height: 45%;
          z-index: 20;
        }

        .repository-window {
          left: 4%;
          top: 49%;
          width: 48%;
          height: 43%;
          z-index: 30;
        }

        .knowledge-window {
          right: 4%;
          top: 52%;
          width: 49%;
          height: 38%;
          z-index: 40;
        }

        .browser-window {
          left: 23%;
          top: 17%;
          width: 70%;
          height: 70%;
          z-index: 50;
        }

        .report-window {
          left: 12%;
          top: 8%;
          width: 76%;
          height: 82%;
          z-index: 70;
        }

        /* ---------------------------------------------
           WORKSPACE
           --------------------------------------------- */

        .workspace-body {
          display: grid;
          grid-template-columns: 25% 75%;
          height: calc(100% - 28px);
          background: #111827;
        }

        .workspace-tree {
          display: flex;
          flex-direction: column;
          gap: 6px;
          padding: 11px 8px;
          overflow: hidden;
          border-right: 1px solid rgba(255,255,255,.06);
          color: rgba(148,163,184,.72);
          font-size: 6px;
        }

        .workspace-tree b {
          color: rgba(226,232,240,.62);
          font-size: 5px;
          letter-spacing: .18em;
        }

        .workspace-tree em {
          padding: 3px 4px;
          border-radius: 3px;
          font-style: normal;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .workspace-selected {
          color: #dbeafe !important;
          background: rgba(59,130,246,.13);
          box-shadow: inset 2px 0 0 rgba(96,165,250,.8);
        }

        .workspace-code {
          margin: 0;
          overflow: hidden;
          padding: 15px;
          color: rgba(226,232,240,.76);
          font-size: 7px;
          line-height: 1.8;
        }

        .workspace-current-line {
          display: inline-block;
          min-width: 100%;
          background: rgba(59,130,246,.1);
          color: white;
          box-shadow: inset 2px 0 0 rgba(96,165,250,.7);
        }

        .workspace-footer {
          position: absolute;
          bottom: 5px;
          left: 25%;
          right: 0;
          display: flex;
          justify-content: space-between;
          padding: 0 9px;
          color: rgba(148,163,184,.45);
          font-size: 5px;
        }

        /* ---------------------------------------------
           TERMINAL
           --------------------------------------------- */

        .terminal-body {
          position: relative;
          height: calc(100% - 28px);
          overflow: hidden;
          background: #05080d;
        }

        .terminal-glow {
          position: absolute;
          inset: 0;
          background:
            radial-gradient(
              circle at 15% 0%,
              rgba(37,99,235,.1),
              transparent 45%
            );
        }

        .terminal-content {
          position: relative;
          padding: 14px;
          color: #f8fafc;
          font-size: 6px;
          line-height: 1.65;
        }

        .terminal-command {
          margin-bottom: 8px;
        }

        .terminal-user {
          color: #22d3ee;
        }

        .terminal-path {
          color: #64748b;
        }

        .terminal-command-text {
          color: white;
        }

        .terminal-result {
          margin-top: 2px;
          color: rgba(74,222,128,.75);
        }

        .terminal-caret {
          margin-left: 4px;
          height: 7px;
          width: 3px;
        }

        .terminal-exit {
          position: absolute;
          bottom: 7px;
          right: 8px;
          padding: 3px 5px;
          border: 1px solid rgba(74,222,128,.2);
          border-radius: 3px;
          background: rgba(74,222,128,.06);
          color: rgba(74,222,128,.7);
          font-size: 5px;
        }

        /* ---------------------------------------------
           REPOSITORY
           --------------------------------------------- */

        .repository-body {
          display: grid;
          grid-template-columns: 55% 45%;
          height: calc(100% - 28px);
          background: #081321;
        }

        .repository-tree {
          overflow: hidden;
          border-right: 1px solid rgba(255,255,255,.07);
          padding: 10px;
        }

        .repository-heading {
          display: block;
          margin-bottom: 7px;
          color: rgba(148,163,184,.6);
          font-size: 5px;
          letter-spacing: .18em;
        }

        .repository-file-tree {
          max-height: calc(100% - 15px);
          overflow: hidden;
          font-size: 6px;
        }

        .repository-inspector {
          padding: 12px 10px;
        }

        .repository-label {
          display: block;
          color: rgba(148,163,184,.55);
          font-size: 5px;
          letter-spacing: .15em;
        }

        .repository-inspector strong {
          display: block;
          margin-top: 5px;
          color: #dbeafe;
          font-size: 7px;
        }

        .repository-check {
          margin-top: 8px;
          color: rgba(110,231,183,.75);
          font-size: 6px;
        }

        .repository-trace {
          margin-top: 12px;
          color: rgba(148,163,184,.45);
          font-size: 5px;
          line-height: 1.6;
        }

        /* ---------------------------------------------
           KNOWLEDGE
           --------------------------------------------- */

        .knowledge-body {
          height: calc(100% - 28px);
          padding: 11px;
          background: #091523;
        }

        .knowledge-title {
          display: flex;
          justify-content: space-between;
          color: rgba(226,232,240,.7);
          font-size: 6px;
          letter-spacing: .15em;
        }

        .knowledge-title small {
          color: rgba(110,231,183,.65);
          font-size: 5px;
        }

        .knowledge-chain {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-top: 18px;
        }

        .knowledge-node {
          flex: 1;
          min-width: 0;
          padding: 8px;
          border-radius: 5px;
          border: 1px solid rgba(255,255,255,.1);
          background: rgba(255,255,255,.025);
        }

        .knowledge-node small {
          display: block;
          font-size: 5px;
          color: rgba(148,163,184,.65);
        }

        .knowledge-node strong {
          display: block;
          margin-top: 4px;
          color: white;
          font-size: 6px;
        }

        .knowledge-node p {
          margin: 4px 0 0;
          color: rgba(148,163,184,.65);
          font-size: 5px;
          line-height: 1.5;
        }

        .knowledge-node.observation {
          border-color: rgba(251,191,36,.2);
        }

        .knowledge-node.claim {
          border-color: rgba(110,231,183,.2);
        }

        .knowledge-high {
          color: rgba(110,231,183,.8) !important;
        }

        .knowledge-connector {
          flex: 0 0 18px;
          height: 1px;
          transform-origin: left center;
          background: rgba(110,231,183,.5);
        }

        .knowledge-bottom {
          position: absolute;
          bottom: 7px;
          left: 11px;
          right: 11px;
          display: flex;
          justify-content: space-between;
          border-top: 1px solid rgba(255,255,255,.06);
          padding-top: 6px;
          color: rgba(148,163,184,.45);
          font-size: 5px;
        }

        /* ---------------------------------------------
           BROWSER
           --------------------------------------------- */

        .browser-window {
          overflow: hidden;
          background: white;
        }

        .browser-verification-badge {
          position: absolute;
          bottom: 7px;
          left: 8px;
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 4px 6px;
          border: 1px solid rgba(15,23,42,.08);
          border-radius: 999px;
          background: rgba(255,255,255,.92);
          color: rgba(71,85,105,.8);
          font-size: 5px;
          box-shadow: 0 2px 8px rgba(15,23,42,.08);
          backdrop-filter: blur(6px);
        }

        .browser-verification-badge span {
          width: 4px;
          height: 4px;
          border-radius: 50%;
          background: #22c55e;
        }

        /* ---------------------------------------------
           REPORT
           --------------------------------------------- */

        .report-body {
          height: calc(100% - 28px);
          padding: 15px;
          background: #081321;
        }

        .report-heading {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
        }

        .report-heading span {
          color: rgba(148,163,184,.55);
          font-size: 5px;
          letter-spacing: .18em;
        }

        .report-heading h3 {
          margin: 5px 0 0;
          color: white;
          font-size: 10px;
        }

        .report-heading p {
          margin: 3px 0 0;
          color: rgba(148,163,184,.55);
          font-size: 5px;
        }

        .report-pass {
          padding: 4px 6px;
          border: 1px solid rgba(110,231,183,.2);
          border-radius: 4px;
          background: rgba(110,231,183,.06);
          color: rgba(110,231,183,.85);
          font-size: 5px;
        }

        .report-columns {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
          margin-top: 15px;
        }

        .report-section {
          min-width: 0;
          padding: 8px;
          border: 1px solid rgba(255,255,255,.07);
          border-radius: 5px;
          background: rgba(255,255,255,.02);
        }

        .report-section > small {
          color: rgba(148,163,184,.5);
          font-size: 5px;
          letter-spacing: .14em;
        }

        .report-row {
          display: grid;
          grid-template-columns: .7fr 1fr auto;
          align-items: center;
          gap: 5px;
          margin-top: 8px;
          color: rgba(203,213,225,.7);
          font-size: 5px;
        }

        .report-row strong {
          color: white;
          font-weight: 500;
        }

        .report-row b {
          color: rgba(110,231,183,.8);
          font-size: 4px;
        }

        .report-event {
          margin-top: 8px;
          padding-left: 6px;
          border-left: 1px solid rgba(96,165,250,.3);
        }

        .report-event span {
          color: rgba(96,165,250,.75);
          font-size: 5px;
        }

        .report-event p {
          margin: 2px 0 0;
          color: rgba(203,213,225,.65);
          font-size: 5px;
        }

        .report-footer {
          position: absolute;
          bottom: 8px;
          left: 15px;
          right: 15px;
          display: flex;
          gap: 14px;
          align-items: center;
          border-top: 1px solid rgba(255,255,255,.07);
          padding-top: 7px;
          color: rgba(148,163,184,.5);
          font-size: 5px;
        }

        .report-converged {
          margin-left: auto;
          color: rgba(110,231,183,.8);
        }

        /* ---------------------------------------------
           CURSOR
           --------------------------------------------- */

        .wizard-caret {
          display: inline-block;
          width: 3px;
          height: 8px;
          margin-left: 2px;
          vertical-align: middle;
          background: #93c5fd;
          animation: wizard-blink 900ms steps(2,end) infinite;
        }

        @keyframes wizard-blink {
          0%, 45% {
            opacity: 1;
          }

          46%, 100% {
            opacity: 0;
          }
        }

        /* ---------------------------------------------
           SIDE LABEL
           --------------------------------------------- */

        .investigation-label {
          display: flex;
          align-items: center;
          gap: 7px;
          margin-top: 25px;
          color: rgba(219,234,254,.65);
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 7px;
          letter-spacing: .16em;
          text-transform: uppercase;
        }

        .investigation-pulse {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: #86efac;
          box-shadow: 0 0 10px rgba(134,239,172,.6);
        }

        /* ---------------------------------------------
           RESPONSIVE
           --------------------------------------------- */

        @media (max-width: 1100px) {
          .workspace-window {
            left: 3%;
            width: 56%;
          }

          .terminal-window {
            left: 40%;
            width: 57%;
          }

          .browser-window {
            left: 15%;
            width: 82%;
          }

          .report-window {
            left: 8%;
            width: 84%;
          }
        }

        @media (max-width: 900px) {
          .scene-card {
            transform: none !important;
            border-radius: 0 !important;
          }

          .workspace-window {
            left: 3%;
            top: 5%;
            width: 58%;
            height: 52%;
          }

          .terminal-window {
            left: 39%;
            top: 9%;
            width: 58%;
            height: 43%;
          }

          .repository-window {
            left: 3%;
            top: 54%;
            width: 54%;
            height: 39%;
          }

          .knowledge-window {
            right: 3%;
            top: 57%;
            width: 53%;
            height: 35%;
          }

          .browser-window {
            left: 10%;
            top: 15%;
            width: 87%;
            height: 73%;
          }

          .report-window {
            left: 5%;
            top: 6%;
            width: 90%;
            height: 84%;
          }

          .investigation-label {
            margin-top: 18px;
          }
        }

        @media (max-width: 700px) {
          .scene-card {
            min-height: 100vh;
          }

          .workspace-window {
            left: 3%;
            top: 5%;
            width: 94%;
            height: 38%;
          }

          .terminal-window {
            left: 6%;
            top: 28%;
            width: 88%;
            height: 31%;
          }

          .repository-window {
            left: 3%;
            top: 56%;
            width: 94%;
            height: 34%;
          }

          .knowledge-window {
            display: none;
          }

          .browser-window {
            left: 4%;
            top: 12%;
            width: 92%;
            height: 76%;
          }

          .report-window {
            left: 3%;
            top: 5%;
            width: 94%;
            height: 86%;
          }

          .report-columns {
            grid-template-columns: 1fr;
          }

          .report-footer {
            gap: 7px;
          }

          .report-converged {
            display: none;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .scene-card {
            transition: none;
          }

          .wizard-window {
            transition: none;
          }

          .wizard-caret {
            animation: none;
            opacity: 1;
          }
        }
      `}</style>
    </section>
  )
}

export default CinematicHero