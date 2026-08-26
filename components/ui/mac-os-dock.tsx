"use client"

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react"

interface DockApp {
  id: string
  name: string
  icon: string
}

interface MacOSDockProps {
  apps: DockApp[]
  onAppClick: (appId: string) => void
  openApps?: string[]
  className?: string
}

function VSCodeIcon() {
  return (
    <svg
      width="32"
      height="32"
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

function getResponsiveSize() {
  if (typeof window === "undefined") {
    return {
      icon: 34,
      maxScale: 1.42,
      effectWidth: 180,
      gap: 3,
    }
  }

  const width = window.innerWidth

  if (width < 640) {
    return {
      icon: 26,
      maxScale: 1.3,
      effectWidth: 130,
      gap: 2,
    }
  }

  if (width < 1024) {
    return {
      icon: 30,
      maxScale: 1.36,
      effectWidth: 155,
      gap: 2,
    }
  }

  return {
    icon: 34,
    maxScale: 1.42,
    effectWidth: 180,
    gap: 3,
  }
}

export default function MacOSDock({
  apps,
  onAppClick,
  openApps = [],
  className = "",
}: MacOSDockProps) {
  const dockRef =
    useRef<HTMLDivElement>(null)

  const [mouseX, setMouseX] =
    useState<number | null>(null)

  const [config, setConfig] =
    useState(getResponsiveSize)

  const [scales, setScales] =
    useState<number[]>(
      apps.map(() => 1)
    )

  const animationRef =
    useRef<number | null>(null)

  useEffect(() => {
    const resize = () => {
      setConfig(getResponsiveSize())
    }

    window.addEventListener(
      "resize",
      resize
    )

    return () =>
      window.removeEventListener(
        "resize",
        resize
      )
  }, [])

  const {
    icon,
    maxScale,
    effectWidth,
    gap,
  } = config

  const calculateScales =
    useCallback(
      (x: number | null) => {
        if (x === null) {
          return apps.map(() => 1)
        }

        return apps.map((_, index) => {
          const center =
            index * (icon + gap) +
            icon / 2

          const distance =
            Math.abs(center - x)

          if (
            distance >
            effectWidth / 2
          ) {
            return 1
          }

          const normalized =
            distance /
            (effectWidth / 2)

          const influence =
            Math.cos(
              normalized *
                Math.PI *
                0.5
            )

          return (
            1 +
            influence *
              (maxScale - 1)
          )
        })
      },
      [
        apps,
        icon,
        gap,
        effectWidth,
        maxScale,
      ]
    )

  useEffect(() => {
    const animate = () => {
      const target =
        calculateScales(mouseX)

      setScales(previous =>
        previous.map(
          (value, index) =>
            value +
            (target[index] -
              value) *
              0.18
        )
      )

      animationRef.current =
        window.requestAnimationFrame(
          animate
        )
    }

    animationRef.current =
      window.requestAnimationFrame(
        animate
      )

    return () => {
      if (
        animationRef.current !==
        null
      ) {
        window.cancelAnimationFrame(
          animationRef.current
        )
      }
    }
  }, [
    mouseX,
    calculateScales,
  ])

  const handleMouseMove =
    useCallback(
      (
        event: React.MouseEvent
      ) => {
        const rect =
          dockRef.current?.getBoundingClientRect()

        if (!rect) return

        setMouseX(
          event.clientX -
            rect.left -
            7
        )
      },
      []
    )

  const handleMouseLeave =
    useCallback(() => {
      setMouseX(null)
    }, [])

  const totalWidth =
    apps.length *
      icon +
    Math.max(
      0,
      apps.length - 1
    ) *
      gap

  return (
    <div
      ref={dockRef}
      className={className}
      onMouseMove={
        handleMouseMove
      }
      onMouseLeave={
        handleMouseLeave
      }
      style={{
        width:
          totalWidth + 16,
        height: icon + 12,
        padding:
          "6px 8px",
        borderRadius: 13,
        background:
          "rgba(24, 24, 27, 0.76)",
        border:
          "1px solid rgba(255,255,255,0.13)",
        boxShadow:
          "0 8px 24px rgba(0,0,0,.3), inset 0 1px 0 rgba(255,255,255,.1)",
        backdropFilter:
          "blur(18px)",
        WebkitBackdropFilter:
          "blur(18px)",
      }}
    >
      <div
        className="relative flex items-end"
        style={{
          width: totalWidth,
          height: icon,
          gap,
        }}
      >
        {apps.map(
          (app, index) => {
            const scale =
              scales[index] || 1

            const size =
              icon * scale

            return (
              <button
                key={app.id}
                type="button"
                title={app.name}
                aria-label={
                  app.name
                }
                onClick={() =>
                  onAppClick(
                    app.id
                  )
                }
                className="group relative flex shrink-0 items-end justify-center border-0 bg-transparent p-0 outline-none"
                style={{
                  width: icon,
                  height: icon,
                  transform:
                    `translateY(${
                      -(size -
                        icon) *
                      0.32
                    })`,
                  zIndex:
                    Math.round(
                      scale * 100
                    ),
                  transition:
                    "transform 80ms linear",
                }}
              >
                <div
                  className="flex items-center justify-center overflow-hidden rounded-[8px]"
                  style={{
                    width: size,
                    height: size,
                    transition:
                      "width 80ms linear, height 80ms linear",
                    filter:
                      "drop-shadow(0 3px 5px rgba(0,0,0,.32))",
                  }}
                >
                  {app.id ===
                  "vscode" ? (
                    <VSCodeIcon />
                  ) : (
                    <img
                      src={app.icon}
                      alt=""
                      width={size}
                      height={size}
                      draggable={false}
                      className="h-full w-full object-contain"
                    />
                  )}
                </div>

                {openApps.includes(
                  app.id
                ) && (
                  <span
                    className="absolute bottom-[-4px] left-1/2 -translate-x-1/2 rounded-full bg-white/80"
                    style={{
                      width: 3,
                      height: 3,
                      boxShadow:
                        "0 0 4px rgba(255,255,255,.45)",
                    }}
                  />
                )}
              </button>
            )
          }
        )}
      </div>
    </div>
  )
}