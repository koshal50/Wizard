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

function jitter(
  point: Point,
  width: number,
  height: number,
  amount = 0.025
): Point {
  return {
    x: clamp(
      point.x + random(-width * amount, width * amount),
      14,
      width - 14
    ),
    y: clamp(
      point.y + random(-height * amount, height * amount),
      14,
      height - 14
    ),
  }
}

function makePoint(
  width: number,
  height: number,
  x: number,
  y: number,
  spread = 0.02
): Point {
  return {
    x: clamp(
      width * x + random(-width * spread, width * spread),
      14,
      width - 14
    ),
    y: clamp(
      height * y + random(-height * spread, height * spread),
      14,
      height - 14
    ),
  }
}

function createPath(
  width: number,
  height: number
): Action[] {
  /*
   * These are semantic regions rather than exact DOM
   * coordinates because the actual website lives inside
   * a cross origin iframe.
   */

  const addressBar = makePoint(
    width,
    height,
    0.52,
    0.075,
    0.025
  )

  const upperPage = makePoint(
    width,
    height,
    0.48,
    0.28,
    0.08
  )

  const leftContent = makePoint(
    width,
    height,
    0.32,
    0.43,
    0.07
  )

  const centerContent = makePoint(
    width,
    height,
    0.54,
    0.47,
    0.09
  )

  const rightContent = makePoint(
    width,
    height,
    0.73,
    0.39,
    0.07
  )

  const lowerContent = makePoint(
    width,
    height,
    0.57,
    0.72,
    0.08
  )

  const bottomContent = makePoint(
    width,
    height,
    0.38,
    0.84,
    0.06
  )

  const paths: Action[][] = [
    [
      {
        type: "move",
        point: addressBar,
        duration: random(650, 950),
        pause: random(350, 700),
      },
      {
        type: "move",
        point: upperPage,
        duration: random(700, 1100),
        pause: random(450, 850),
      },
      {
        type: "move",
        point: leftContent,
        duration: random(500, 800),
        pause: random(250, 600),
      },
      {
        type: "move",
        point: centerContent,
        duration: random(600, 950),
        pause: random(500, 900),
      },
      {
        type: "click",
        point: centerContent,
        duration: random(350, 600),
        pause: random(500, 900),
      },
      {
        type: "scroll",
        point: centerContent,
        distance: random(140, 220),
        duration: random(500, 800),
        pause: random(600, 1000),
      },
      {
        type: "move",
        point: lowerContent,
        duration: random(600, 950),
        pause: random(450, 800),
      },
    ],

    [
      {
        type: "move",
        point: upperPage,
        duration: random(700, 1050),
        pause: random(300, 650),
      },
      {
        type: "move",
        point: rightContent,
        duration: random(550, 900),
        pause: random(450, 850),
      },
      {
        type: "move",
        point: centerContent,
        duration: random(400, 700),
        pause: random(250, 500),
      },
      {
        type: "click",
        point: centerContent,
        duration: random(350, 550),
        pause: random(650, 1000),
      },
      {
        type: "scroll",
        point: lowerContent,
        distance: random(180, 280),
        duration: random(600, 950),
        pause: random(700, 1200),
      },
      {
        type: "move",
        point: bottomContent,
        duration: random(650, 1000),
        pause: random(400, 750),
      },
      {
        type: "move",
        point: rightContent,
        duration: random(500, 800),
        pause: random(300, 650),
      },
    ],

    [
      {
        type: "move",
        point: leftContent,
        duration: random(650, 950),
        pause: random(400, 750),
      },
      {
        type: "move",
        point: centerContent,
        duration: random(450, 750),
        pause: random(250, 550),
      },
      {
        type: "move",
        point: rightContent,
        duration: random(550, 900),
        pause: random(500, 900),
      },
      {
        type: "click",
        point: rightContent,
        duration: random(350, 550),
        pause: random(600, 1000),
      },
      {
        type: "move",
        point: centerContent,
        duration: random(450, 750),
        pause: random(300, 600),
      },
      {
        type: "scroll",
        point: centerContent,
        distance: random(160, 260),
        duration: random(550, 850),
        pause: random(700, 1100),
      },
      {
        type: "move",
        point: bottomContent,
        duration: random(650, 1000),
        pause: random(500, 900),
      },
    ],
  ]

  return paths[
    Math.floor(Math.random() * paths.length)
  ]
}

export function SmoothCursor() {
  const x = useMotionValue(-100)
  const y = useMotionValue(-100)

  const springX = useSpring(x, {
    damping: 30,
    stiffness: 260,
    mass: 0.7,
  })

  const springY = useSpring(y, {
    damping: 30,
    stiffness: 260,
    mass: 0.7,
  })

  const [pressed, setPressed] = useState(false)
  const [visible, setVisible] = useState(false)
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
     * Find the existing browser component.
     *
     * browser.tsx does not need to change.
     */
    const browser = document.querySelector(
      ".screen-panel"
    ) as HTMLElement | null

    if (!browser) {
      return
    }

    cancelled.current = false

    const getBounds = () => {
      const rect = browser.getBoundingClientRect()

      return {
        width: rect.width,
        height: rect.height,
      }
    }

    const move = async (
      target: Point,
      duration: number
    ) => {
      if (cancelled.current) return

      /*
       * First move toward the target.
       */
      x.set(target.x)
      y.set(target.y)

      await sleep(duration)

      if (cancelled.current) return

      /*
       * Real pointer movement rarely stops perfectly.
       * Add a tiny corrective movement after arrival.
       */
      if (Math.random() > 0.35) {
        const { width, height } = getBounds()

        const correction = jitter(
          target,
          width,
          height,
          0.008
        )

        x.set(correction.x)
        y.set(correction.y)

        await sleep(random(90, 180))
      }
    }

    const click = async () => {
      if (cancelled.current) return

      /*
       * Small hesitation before clicking.
       */
      await sleep(random(180, 420))

      setPressed(true)

      await sleep(random(70, 130))

      setPressed(false)

      /*
       * Agent remains near the clicked target briefly.
       */
      await sleep(random(250, 500))
    }

    const scrollGesture = async (
      target: Point,
      distance: number,
      duration: number
    ) => {
      if (cancelled.current) return

      await move(target, duration)

      if (cancelled.current) return

      setScrolling(true)

      /*
       * The actual website is inside a cross origin iframe.
       * We cannot control its internal scroll position here.
       *
       * Instead the cursor performs the gesture visually.
       */
      const steps = Math.floor(
        random(6, 10)
      )

      for (let i = 0; i < steps; i++) {
        if (cancelled.current) return

        const progress =
          (i + 1) / steps

        const nextY =
          target.y +
          distance * progress

        y.set(nextY)

        await sleep(
          random(45, 85)
        )
      }

      setScrolling(false)

      await sleep(random(500, 950))
    }

    const run = async () => {
      while (!cancelled.current) {
        const { width, height } =
          getBounds()

        /*
         * Start from a different position every
         * investigation so the animation never feels
         * like a perfectly repeated recording.
         */
        const start = makePoint(
          width,
          height,
          random(0.22, 0.42),
          random(0.20, 0.40),
          0.04
        )

        x.set(start.x)
        y.set(start.y)

        setVisible(true)

        await sleep(random(500, 1000))

        if (cancelled.current) return

        const actions = createPath(
          width,
          height
        )

        for (const action of actions) {
          if (cancelled.current) return

          if (action.type === "move") {
            await move(
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
            await scrollGesture(
              action.point,
              action.distance,
              action.duration
            )

            await sleep(action.pause)
          }
        }

        /*
         * The agent has finished examining this part
         * of the page.
         */
        await sleep(random(900, 1700))

        /*
         * Sometimes backtrack before starting another
         * investigation cycle.
         */
        if (Math.random() > 0.45) {
          const { width, height } =
            getBounds()

          const backtrack = makePoint(
            width,
            height,
            random(0.25, 0.75),
            random(0.25, 0.55),
            0.06
          )

          await move(
            backtrack,
            random(500, 850)
          )

          await sleep(random(350, 700))
        }

        /*
         * Hide briefly before the next investigation.
         * This makes the loop feel like a new investigation
         * rather than an animation restarting.
         */
        setVisible(false)

        await sleep(random(500, 1100))

        const { width: nextWidth, height: nextHeight } =
          getBounds()

        const nextStart = makePoint(
          nextWidth,
          nextHeight,
          random(0.25, 0.40),
          random(0.22, 0.42),
          0.04
        )

        x.set(nextStart.x)
        y.set(nextStart.y)

        await sleep(random(300, 700))

        setVisible(true)
      }
    }

    run()

    return () => {
      cancelled.current = true

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
      className="pointer-events-none absolute left-0 top-0 z-40 hidden md:block"
      animate={{
        opacity: visible ? 1 : 0,
        scale: pressed
          ? 0.82
          : scrolling
            ? 0.94
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
        x: springX,
        y: springY,
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