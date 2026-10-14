"use client"

import {
  motion,
  useMotionValue,
  useSpring,
} from "motion/react"
import {
  RefObject,
  useEffect,
  useRef,
  useState,
} from "react"

interface SmoothCursorProps {
  containerRef?: RefObject<HTMLDivElement | null>
  active?: boolean
}

interface Point {
  x: number
  y: number
  pause?: number
  click?: boolean
  scroll?: number
}

export function SmoothCursor({
  containerRef,
  active = true,
}: SmoothCursorProps) {
  const x = useMotionValue(80)
  const y = useMotionValue(80)

  const sx = useSpring(x, {
    damping: 28,
    stiffness: 220,
    mass: 0.7,
  })

  const sy = useSpring(y, {
    damping: 28,
    stiffness: 220,
    mass: 0.7,
  })

  const [pressed, setPressed] =
    useState(false)

  const [visible, setVisible] =
    useState(false)

  const [scrolling, setScrolling] =
    useState(false)

  const cancelled =
    useRef(false)

  const timerRef =
    useRef<number | null>(null)

  const scrollTimerRef =
    useRef<number | null>(null)

  const randomBetween = (
    min: number,
    max: number
  ) =>
    Math.random() *
      (max - min) +
    min

  const clamp = (
    value: number,
    min: number,
    max: number
  ) =>
    Math.max(
      min,
      Math.min(max, value)
    )

  const getViewport = () =>
    containerRef?.current || null

  const createMovement = (): Point => {
    const viewport = getViewport()

    if (!viewport) {
      return {
        x: 100,
        y: 100,
      }
    }

    const width =
      viewport.clientWidth

    const height =
      viewport.clientHeight

    const horizontalPadding =
      Math.max(
        28,
        width * 0.08
      )

    const verticalPadding =
      Math.max(
        24,
        height * 0.08
      )

    const zones = [
      {
        x: randomBetween(
          horizontalPadding,
          width * 0.38
        ),
        y: randomBetween(
          verticalPadding,
          height * 0.42
        ),
      },
      {
        x: randomBetween(
          width * 0.42,
          width * 0.82
        ),
        y: randomBetween(
          verticalPadding,
          height * 0.46
        ),
      },
      {
        x: randomBetween(
          width * 0.22,
          width * 0.72
        ),
        y: randomBetween(
          height * 0.42,
          height * 0.78
        ),
      },
      {
        x: randomBetween(
          width * 0.65,
          width -
            horizontalPadding
        ),
        y: randomBetween(
          height * 0.5,
          height -
            verticalPadding
        ),
      },
    ]

    const target =
      zones[
        Math.floor(
          Math.random() *
            zones.length
        )
      ]

    const shouldClick =
      Math.random() < 0.2

    const shouldScroll =
      Math.random() < 0.22

    return {
      x: clamp(
        target.x,
        18,
        width - 18
      ),
      y: clamp(
        target.y,
        18,
        height - 18
      ),
      pause: randomBetween(
        350,
        1100
      ),
      click: shouldClick,
      scroll: shouldScroll
        ? Math.random() > 0.5
          ? 260
          : -180
        : undefined,
    }
  }

  const moveTo = (
    point: Point
  ) => {
    if (cancelled.current) {
      return
    }

    x.set(point.x)
    y.set(point.y)

    if (point.click) {
      window.setTimeout(() => {
        if (cancelled.current) {
          return
        }

        setPressed(true)

        window.setTimeout(() => {
          if (!cancelled.current) {
            setPressed(false)
          }
        }, 110)
      }, 260)
    }

    if (
      point.scroll &&
      getViewport()
    ) {
      setScrolling(true)

      const viewport =
        getViewport()

      if (viewport) {
        viewport.scrollBy({
          top: point.scroll,
          behavior: "smooth",
        })
      }

      if (
        scrollTimerRef.current
      ) {
        window.clearTimeout(
          scrollTimerRef.current
        )
      }

      scrollTimerRef.current =
        window.setTimeout(() => {
          if (!cancelled.current) {
            setScrolling(false)
          }
        }, 700)
    }
  }

  const scheduleNext = () => {
    if (cancelled.current) {
      return
    }

    const next =
      createMovement()

    moveTo(next)

    timerRef.current =
      window.setTimeout(
        scheduleNext,
        next.pause || 700
      )
  }

  useEffect(() => {
    cancelled.current = false

    if (!active) {
      setVisible(false)
      return
    }

    const viewport =
      getViewport()

    if (!viewport) {
      return
    }

    if (
      window.matchMedia(
        "(pointer: coarse)"
      ).matches
    ) {
      return
    }

    if (
      window.matchMedia(
        "(prefers-reduced-motion: reduce)"
      ).matches
    ) {
      return
    }

    setVisible(true)

    const width =
      viewport.clientWidth

    const height =
      viewport.clientHeight

    x.set(
      Math.max(
        30,
        width * 0.18
      )
    )

    y.set(
      Math.max(
        30,
        height * 0.2
      )
    )

    timerRef.current =
      window.setTimeout(
        scheduleNext,
        850
      )

    const resizeObserver =
      new ResizeObserver(() => {
        if (
          cancelled.current
        ) {
          return
        }

        const current =
          getViewport()

        if (!current) {
          return
        }

        const nextX =
          clamp(
            x.get(),
            18,
            current.clientWidth -
              18
          )

        const nextY =
          clamp(
            y.get(),
            18,
            current.clientHeight -
              18
          )

        x.set(nextX)
        y.set(nextY)
      })

    resizeObserver.observe(
      viewport
    )

    return () => {
      cancelled.current = true

      if (timerRef.current) {
        window.clearTimeout(
          timerRef.current
        )
      }

      if (
        scrollTimerRef.current
      ) {
        window.clearTimeout(
          scrollTimerRef.current
        )
      }

      resizeObserver.disconnect()

      setVisible(false)
      setPressed(false)
      setScrolling(false)
    }
  }, [active])

  if (!visible) {
    return null
  }

  return (
    <motion.div
      aria-hidden="true"
      data-wizard-agent-cursor="true"
      className="pointer-events-none absolute left-0 top-0 z-[100] hidden md:block"
      style={{
        x: sx,
        y: sy,
        willChange: "transform",
      }}
    >
      <motion.div
        animate={{
          scale: pressed
            ? 0.82
            : scrolling
              ? 0.94
              : 1,
        }}
        transition={{
          type: "spring",
          damping: 20,
          stiffness: 360,
        }}
        className="relative"
      >
        <span
          className="absolute -inset-3 rounded-full border"
          style={{
            borderColor:
              pressed
                ? "rgba(59,130,246,.75)"
                : scrolling
                  ? "rgba(96,165,250,.45)"
                  : "rgba(147,197,253,0)",
          }}
        />

        {scrolling && (
          <motion.span
            initial={{
              opacity: 0,
              scale: 0.5,
            }}
            animate={{
              opacity: 0.65,
              scale: 1.4,
            }}
            transition={{
              duration: 0.5,
              repeat: Infinity,
              repeatType:
                "reverse",
            }}
            className="absolute -inset-1 rounded-full border border-blue-300/30"
          />
        )}

        <svg
          width="22"
          height="25"
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

        <motion.span
          initial={{
            opacity: 0,
            x: 5,
          }}
          animate={{
            opacity: 1,
            x: 0,
          }}
          className="absolute left-5 top-4 whitespace-nowrap rounded bg-slate-950/90 px-1.5 py-0.5 font-mono text-[6px] tracking-wide text-blue-200 shadow-lg backdrop-blur"
        >
          {scrolling
            ? "SCROLL"
            : pressed
              ? "VERIFY"
              : "AGENT"}
        </motion.span>
      </motion.div>
    </motion.div>
  )
}

export default SmoothCursor