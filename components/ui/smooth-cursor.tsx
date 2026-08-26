"use client"

import { motion, useMotionValue, useSpring } from "motion/react"
import { useEffect, useRef, useState } from "react"

type Point = {
  x: number
  y: number
}

type Action =
  | {
      type: "move"
      point: Point
      duration: number
      pause: number
    }
  | {
      type: "click"
      point: Point
      duration: number
      pause: number
    }
  | {
      type: "inspect"
      point: Point
      duration: number
      pause: number
    }
  | {
      type: "scroll"
      point: Point
      distance: number
      duration: number
      pause: number
    }

const sleep = (ms: number) =>
  new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms)
  })

const random = (min: number, max: number) =>
  min + Math.random() * (max - min)

const clamp = (
  value: number,
  min: number,
  max: number
) => Math.max(min, Math.min(max, value))

function point(
  width: number,
  height: number,
  xRatio: number,
  yRatio: number,
  spread = 0.035
): Point {
  return {
    x: clamp(
      width * xRatio +
        random(-width * spread, width * spread),
      10,
      width - 10
    ),
    y: clamp(
      height * yRatio +
        random(-height * spread, height * spread),
      10,
      height - 10
    ),
  }
}

function nearby(
  target: Point,
  width: number,
  height: number,
  spread = 0.012
): Point {
  return {
    x: clamp(
      target.x +
        random(-width * spread, width * spread),
      10,
      width - 10
    ),
    y: clamp(
      target.y +
        random(-height * spread, height * spread),
      10,
      height - 10
    ),
  }
}

function createInvestigation(
  width: number,
  height: number
): Action[] {
  /*
   * These are exploration zones rather than exact elements.
   *
   * The real Wizard website is inside a cross origin iframe,
   * so the parent page cannot inspect its DOM.
   *
   * The agent therefore behaves like an investigator exploring
   * the rendered page rather than following exact coordinates.
   */

  const top = point(
    width,
    height,
    0.52,
    0.16,
    0.04
  )

  const left = point(
    width,
    height,
    0.29,
    0.38,
    0.06
  )

  const center = point(
    width,
    height,
    0.51,
    0.40,
    0.08
  )

  const right = point(
    width,
    height,
    0.73,
    0.38,
    0.07
  )

  const action = point(
    width,
    height,
    0.53,
    0.57,
    0.05
  )

  const lower = point(
    width,
    height,
    0.61,
    0.74,
    0.07
  )

  const bottom = point(
    width,
    height,
    0.39,
    0.84,
    0.06
  )

  const investigations: Action[][] = [
    [
      {
        type: "move",
        point: top,
        duration: random(650, 950),
        pause: random(350, 650),
      },
      {
        type: "inspect",
        point: left,
        duration: random(550, 850),
        pause: random(500, 900),
      },
      {
        type: "move",
        point: center,
        duration: random(600, 950),
        pause: random(350, 700),
      },
      {
        type: "click",
        point: action,
        duration: random(450, 700),
        pause: random(550, 950),
      },
      {
        type: "scroll",
        point: action,
        distance: random(75, 125),
        duration: random(500, 800),
        pause: random(650, 1000),
      },
      {
        type: "inspect",
        point: lower,
        duration: random(550, 850),
        pause: random(500, 850),
      },
    ],

    [
      {
        type: "move",
        point: right,
        duration: random(700, 1050),
        pause: random(400, 750),
      },
      {
        type: "inspect",
        point: center,
        duration: random(450, 750),
        pause: random(450, 850),
      },
      {
        type: "move",
        point: left,
        duration: random(500, 850),
        pause: random(300, 650),
      },
      {
        type: "click",
        point: center,
        duration: random(400, 650),
        pause: random(600, 1000),
      },
      {
        type: "scroll",
        point: lower,
        distance: random(90, 150),
        duration: random(550, 850),
        pause: random(700, 1100),
      },
      {
        type: "move",
        point: bottom,
        duration: random(650, 1000),
        pause: random(450, 850),
      },
    ],

    [
      {
        type: "move",
        point: center,
        duration: random(700, 1050),
        pause: random(450, 800),
      },
      {
        type: "move",
        point: right,
        duration: random(550, 900),
        pause: random(350, 700),
      },
      {
        type: "inspect",
        point: right,
        duration: random(350, 600),
        pause: random(500, 850),
      },
      {
        type: "move",
        point: action,
        duration: random(500, 800),
        pause: random(300, 600),
      },
      {
        type: "click",
        point: action,
        duration: random(400, 650),
        pause: random(600, 1000),
      },
      {
        type: "scroll",
        point: action,
        distance: random(70, 120),
        duration: random(450, 750),
        pause: random(650, 1000),
      },
      {
        type: "move",
        point: bottom,
        duration: random(650, 1000),
        pause: random(450, 800),
      },
    ],

    [
      {
        type: "move",
        point: left,
        duration: random(650, 1000),
        pause: random(300, 650),
      },
      {
        type: "move",
        point: top,
        duration: random(600, 900),
        pause: random(450, 800),
      },
      {
        type: "inspect",
        point: top,
        duration: random(350, 600),
        pause: random(500, 900),
      },
      {
        type: "move",
        point: right,
        duration: random(650, 1000),
        pause: random(350, 700),
      },
      {
        type: "scroll",
        point: right,
        distance: random(80, 135),
        duration: random(500, 800),
        pause: random(650, 1000),
      },
      {
        type: "move",
        point: lower,
        duration: random(600, 950),
        pause: random(450, 800),
      },
    ],
  ]

  return investigations[
    Math.floor(
      Math.random() * investigations.length
    )
  ]
}

export function SmoothCursor() {
  const x = useMotionValue(-100)
  const y = useMotionValue(-100)

  const sx = useSpring(x, {
    damping: 30,
    stiffness: 250,
    mass: 0.7,
  })

  const sy = useSpring(y, {
    damping: 30,
    stiffness: 250,
    mass: 0.7,
  })

  const [visible, setVisible] = useState(false)
  const [pressed, setPressed] = useState(false)
  const [scrolling, setScrolling] = useState(false)

  const cancelled = useRef(false)

  useEffect(() => {
    const media = window.matchMedia(
      "(pointer: coarse), (prefers-reduced-motion: reduce)"
    )

    if (media.matches) {
      return
    }

    /*
     * The browser contains the real Wizard website.
     *
     * We deliberately identify the iframe rather than
     * searching for .screen-panel because the cinematic
     * hero contains other screen panels too.
     */
    const findWizardIframe = () =>
      document.querySelector(
        'iframe[src*="wizardagents.vercel.app"]'
      ) as HTMLIFrameElement | null

    let iframe = findWizardIframe()

    let observer: MutationObserver | null = null
    let retryTimer: number | null = null

    const startWhenReady = () => {
      if (iframe) {
        runAgent(iframe)
        return
      }

      let attempts = 0

      retryTimer = window.setInterval(() => {
        iframe = findWizardIframe()
        attempts++

        if (iframe) {
          if (retryTimer !== null) {
            window.clearInterval(retryTimer)
          }

          runAgent(iframe)
        }

        if (attempts > 40) {
          if (retryTimer !== null) {
            window.clearInterval(retryTimer)
          }
        }
      }, 150)
    }

    const runAgent = (
      target: HTMLIFrameElement
    ) => {
      cancelled.current = false

      const getRect = () =>
        target.getBoundingClientRect()

      const getBounds = () => {
        const rect = getRect()

        return {
          width: rect.width,
          height: rect.height,
        }
      }

      /*
       * Convert coordinates inside the browser viewport
       * into actual page coordinates.
       *
       * This is what keeps the cursor attached to the
       * MacBook browser while the cinematic section moves.
       */
      const viewportPoint = (
        local: Point
      ): Point => {
        const rect = getRect()

        return {
          x: rect.left + local.x,
          y: rect.top + local.y,
        }
      }

      const move = async (
        local: Point,
        duration: number
      ) => {
        if (cancelled.current) return

        const targetPoint =
          viewportPoint(local)

        x.set(targetPoint.x)
        y.set(targetPoint.y)

        await sleep(duration)

        if (cancelled.current) return

        /*
         * Small correction after reaching a target.
         * This avoids perfectly robotic movement.
         */
        if (Math.random() > 0.32) {
          const { width, height } =
            getBounds()

          const correction = nearby(
            local,
            width,
            height,
          )

          const corrected =
            viewportPoint(correction)

          x.set(corrected.x)
          y.set(corrected.y)

          await sleep(random(80, 170))
        }
      }

      const click = async () => {
        if (cancelled.current) return

        /*
         * The agent hesitates before committing an action.
         */
        await sleep(random(180, 420))

        setPressed(true)

        await sleep(random(65, 125))

        setPressed(false)

        await sleep(random(250, 550))
      }

      const inspect = async (
        local: Point,
        duration: number
      ) => {
        await move(local, duration)

        if (cancelled.current) return

        /*
         * Inspection is intentionally not perfectly still.
         * The cursor makes tiny movements as though examining
         * nearby content.
         */
        const { width, height } =
          getBounds()

        const first = nearby(
          local,
          width,
          height,
          0.009
        )

        const second = nearby(
          local,
          width,
          height,
          0.006
        )

        await move(first, random(180, 300))
        await sleep(random(180, 350))

        await move(second, random(150, 260))
        await sleep(random(300, 650))
      }

      const scroll = async (
        local: Point,
        distance: number,
        duration: number
      ) => {
        if (cancelled.current) return

        await move(local, duration)

        if (cancelled.current) return

        setScrolling(true)

        const { height } = getBounds()

        const steps = Math.floor(
          random(6, 10)
        )

        for (let i = 0; i < steps; i++) {
          if (cancelled.current) return

          const progress =
            (i + 1) / steps

          /*
           * Slightly irregular scroll motion.
           */
          const eased =
            progress < 0.5
              ? 2 * progress * progress
              : 1 -
                Math.pow(
                  -2 * progress + 2,
                  2
                ) / 2

          const nextY = clamp(
            local.y + distance * eased,
            10,
            height - 10
          )

          const next =
            viewportPoint({
              x: local.x,
              y: nextY,
            })

          y.set(next.y)

          await sleep(random(45, 85))
        }

        setScrolling(false)

        await sleep(random(550, 1000))
      }

      const investigate = async () => {
        while (!cancelled.current) {
          const rect = getRect()

          /*
           * The iframe may temporarily be outside the viewport
           * while the cinematic section transitions.
           */
          if (
            rect.width < 100 ||
            rect.height < 100 ||
            rect.bottom < 0 ||
            rect.top > window.innerHeight
          ) {
            setVisible(false)

            await sleep(500)

            continue
          }

          const { width, height } =
            getBounds()

          /*
           * Every cycle starts somewhere different.
           */
          const start = point(
            width,
            height,
            random(0.25, 0.65),
            random(0.18, 0.35),
            0.035
          )

          const startPoint =
            viewportPoint(start)

          x.set(startPoint.x)
          y.set(startPoint.y)

          setVisible(true)

          await sleep(random(500, 1000))

          if (cancelled.current) return

          const actions =
            createInvestigation(
              width,
              height
            )

          for (const action of actions) {
            if (cancelled.current) return

            /*
             * The MacBook may have moved since the previous
             * action. Every action recalculates the iframe
             * position through viewportPoint().
             */

            if (action.type === "move") {
              await move(
                action.point,
                action.duration
              )

              await sleep(action.pause)
            }

            if (action.type === "inspect") {
              await inspect(
                action.point,
                action.duration
              )

              await sleep(action.pause)
            }

            if (action.type === "click") {
              await move(
                action.point,
                action.duration
              )

              await click()

              await sleep(action.pause)
            }

            if (action.type === "scroll") {
              await scroll(
                action.point,
                action.distance,
                action.duration
              )

              await sleep(action.pause)
            }
          }

          /*
           * A real agent does not immediately restart.
           * It pauses after completing an investigation step.
           */
          await sleep(random(900, 1700))

          /*
           * Occasional backtracking.
           */
          if (Math.random() > 0.42) {
            const {
              width: currentWidth,
              height: currentHeight,
            } = getBounds()

            const backtrack = point(
              currentWidth,
              currentHeight,
              random(0.30, 0.72),
              random(0.25, 0.58),
              0.05
            )

            await move(
              backtrack,
              random(500, 850)
            )

            await sleep(
              random(300, 700)
            )
          }

          /*
           * Brief disappearance represents the agent
           * moving to another investigation context.
           */
          setVisible(false)

          await sleep(random(500, 1100))
        }
      }

      investigate()
    }

    startWhenReady()

    /*
     * MutationObserver handles the case where the Browser
     * component mounts after SmoothCursor.
     */
    observer = new MutationObserver(() => {
      if (!iframe) {
        iframe = findWizardIframe()

        if (iframe) {
          if (retryTimer !== null) {
            window.clearInterval(retryTimer)
          }

          runAgent(iframe)
        }
      }
    })

    observer.observe(document.body, {
      childList: true,
      subtree: true,
    })

    return () => {
      cancelled.current = true

      if (retryTimer !== null) {
        window.clearInterval(retryTimer)
      }

      observer?.disconnect()

      setVisible(false)
      setPressed(false)
      setScrolling(false)

      x.set(-100)
      y.set(-100)
    }
  }, [x, y])

  return (
    <motion.div
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 z-[120] hidden md:block"
      animate={{
        opacity: visible ? 1 : 0,
        scale: pressed
          ? 0.82
          : scrolling
            ? 0.93
            : 1,
      }}
      transition={{
        opacity: {
          duration: 0.2,
        },
        scale: {
          type: "spring",
          stiffness: 420,
          damping: 24,
        },
      }}
      style={{
        x: sx,
        y: sy,
        translateX: "-7px",
        translateY: "-5px",
        willChange: "transform",
      }}
    >
      <motion.span
        className="absolute -inset-2 rounded-full"
        animate={{
          opacity: pressed ? 1 : 0,
          scale: pressed ? 1 : 0.65,
        }}
        transition={{
          duration: 0.14,
        }}
        style={{
          border:
            "1px solid rgba(127,198,230,.8)",
        }}
      />

      <motion.span
        className="absolute -inset-1 rounded-full"
        animate={{
          opacity: pressed ? 0.65 : 0,
          scale: pressed ? 1.35 : 0.8,
        }}
        transition={{
          duration: 0.28,
        }}
        style={{
          border:
            "1px solid rgba(234,247,251,.45)",
        }}
      />

      <svg
        width="22"
        height="25"
        viewBox="0 0 22 25"
        fill="none"
      >
        <path
          d="M18.8 18.4 12.1 3.2c-.5-1.2-2.2-1.2-2.7 0L2.4 18.4c-.7 1.6.9 3.1 2.5 2.4l5.9-2.2c.2-.1.5-.1.7 0l5.8 2.2c1.6.7 2.3-.9 1.5-2.4Z"
          fill="#071F3A"
          stroke="#EAF7FB"
          strokeWidth="1.4"
        />
      </svg>
    </motion.div>
  )
}

export default SmoothCursor