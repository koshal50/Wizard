"use client"

import React, {
  useState,
  useRef,
  useCallback,
  useEffect,
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

const MacOSDock: React.FC<MacOSDockProps> = ({
  apps,
  onAppClick,
  openApps = [],
  className = "",
}) => {
  const [mouseX, setMouseX] =
    useState<number | null>(null)

  const [currentScales, setCurrentScales] =
    useState<number[]>(
      apps.map(() => 1)
    )

  const [currentPositions, setCurrentPositions] =
    useState<number[]>([])

  const dockRef =
    useRef<HTMLDivElement>(null)

  const iconRefs =
    useRef<(HTMLDivElement | null)[]>([])

  const animationFrameRef =
    useRef<number | undefined>(undefined)

  const lastMouseMoveTime =
    useRef<number>(0)

  const getResponsiveConfig =
    useCallback(() => {
      if (typeof window === "undefined") {
        return {
          baseIconSize: 64,
          maxScale: 1.6,
          effectWidth: 240,
        }
      }

      const smallerDimension =
        Math.min(
          window.innerWidth,
          window.innerHeight
        )

      if (smallerDimension < 480) {
        return {
          baseIconSize: Math.max(
            40,
            smallerDimension * 0.08
          ),
          maxScale: 1.4,
          effectWidth:
            smallerDimension * 0.4,
        }
      }

      if (smallerDimension < 768) {
        return {
          baseIconSize: Math.max(
            48,
            smallerDimension * 0.07
          ),
          maxScale: 1.5,
          effectWidth:
            smallerDimension * 0.35,
        }
      }

      if (smallerDimension < 1024) {
        return {
          baseIconSize: Math.max(
            56,
            smallerDimension * 0.06
          ),
          maxScale: 1.6,
          effectWidth:
            smallerDimension * 0.3,
        }
      }

      return {
        baseIconSize: Math.max(
          64,
          Math.min(
            80,
            smallerDimension * 0.05
          )
        ),
        maxScale: 1.8,
        effectWidth: 300,
      }
    }, [])

  const [config, setConfig] =
    useState(getResponsiveConfig)

  const {
    baseIconSize,
    maxScale,
    effectWidth,
  } = config

  const minScale = 1

  const baseSpacing =
    Math.max(
      4,
      baseIconSize * 0.08
    )

  useEffect(() => {
    const handleResize = () => {
      setConfig(getResponsiveConfig())
    }

    window.addEventListener(
      "resize",
      handleResize
    )

    return () =>
      window.removeEventListener(
        "resize",
        handleResize
      )
  }, [getResponsiveConfig])

  const calculateTargetMagnification =
    useCallback(
      (mousePosition: number | null) => {
        if (mousePosition === null) {
          return apps.map(
            () => minScale
          )
        }

        return apps.map(
          (_, index) => {
            const normalIconCenter =
              index *
                (baseIconSize +
                  baseSpacing) +
              baseIconSize / 2

            const minX =
              mousePosition -
              effectWidth / 2

            const maxX =
              mousePosition +
              effectWidth / 2

            if (
              normalIconCenter < minX ||
              normalIconCenter > maxX
            ) {
              return minScale
            }

            const theta =
              ((normalIconCenter -
                minX) /
                effectWidth) *
              2 *
              Math.PI

            const cappedTheta =
              Math.min(
                Math.max(theta, 0),
                2 * Math.PI
              )

            const scaleFactor =
              (1 -
                Math.cos(
                  cappedTheta
                )) /
              2

            return (
              minScale +
              scaleFactor *
                (maxScale -
                  minScale)
            )
          }
        )
      },
      [
        apps,
        baseIconSize,
        baseSpacing,
        effectWidth,
        maxScale,
      ]
    )

  const calculatePositions =
    useCallback(
      (scales: number[]) => {
        let currentX = 0

        return scales.map(
          scale => {
            const scaledWidth =
              baseIconSize *
              scale

            const centerX =
              currentX +
              scaledWidth / 2

            currentX +=
              scaledWidth +
              baseSpacing

            return centerX
          }
        )
      },
      [
        baseIconSize,
        baseSpacing,
      ]
    )

  useEffect(() => {
    const initialScales =
      apps.map(() => minScale)

    setCurrentScales(
      initialScales
    )

    setCurrentPositions(
      calculatePositions(
        initialScales
      )
    )
  }, [
    apps,
    calculatePositions,
    config,
  ])

  const animateToTarget =
    useCallback(() => {
      const targetScales =
        calculateTargetMagnification(
          mouseX
        )

      const targetPositions =
        calculatePositions(
          targetScales
        )

      const lerpFactor =
        mouseX !== null
          ? 0.2
          : 0.12

      setCurrentScales(
        previous =>
          previous.map(
            (scale, index) =>
              scale +
              (targetScales[index] -
                scale) *
                lerpFactor
          )
      )

      setCurrentPositions(
        previous =>
          previous.map(
            (position, index) =>
              position +
              (targetPositions[index] -
                position) *
                lerpFactor
          )
      )

      animationFrameRef.current =
        requestAnimationFrame(
          animateToTarget
        )
    }, [
      mouseX,
      calculateTargetMagnification,
      calculatePositions,
    ])

  useEffect(() => {
    animationFrameRef.current =
      requestAnimationFrame(
        animateToTarget
      )

    return () => {
      if (
        animationFrameRef.current
      ) {
        cancelAnimationFrame(
          animationFrameRef.current
        )
      }
    }
  }, [animateToTarget])

  const handleMouseMove =
    useCallback(
      (
        event: React.MouseEvent
      ) => {
        const now =
          performance.now()

        if (
          now -
            lastMouseMoveTime.current <
          16
        ) {
          return
        }

        lastMouseMoveTime.current =
          now

        if (!dockRef.current) {
          return
        }

        const rect =
          dockRef.current.getBoundingClientRect()

        const padding =
          Math.max(
            8,
            baseIconSize * 0.12
          )

        setMouseX(
          event.clientX -
            rect.left -
            padding
        )
      },
      [baseIconSize]
    )

  const handleMouseLeave =
    useCallback(() => {
      setMouseX(null)
    }, [])

  const handleAppClick = (
    appId: string,
    index: number
  ) => {
    const element =
      iconRefs.current[index]

    if (element) {
      element.animate(
        [
          {
            transform:
              "translateY(0)",
          },
          {
            transform:
              "translateY(-10px)",
          },
          {
            transform:
              "translateY(0)",
          },
        ],
        {
          duration: 380,
          easing:
            "cubic-bezier(.2,.8,.2,1)",
        }
      )
    }

    onAppClick(appId)
  }

  const contentWidth =
    currentPositions.length > 0
      ? Math.max(
          ...currentPositions.map(
            (position, index) =>
              position +
              (baseIconSize *
                currentScales[index]) /
                2
          )
        )
      : apps.length *
          (baseIconSize +
            baseSpacing)

  const padding =
    Math.max(
      8,
      baseIconSize * 0.12
    )

  return (
    <div
      ref={dockRef}
      className={`backdrop-blur-md ${className}`}
      style={{
        width:
          contentWidth +
          padding * 2,
        background:
          "rgba(30, 30, 32, .78)",
        borderRadius:
          Math.max(
            12,
            baseIconSize * 0.4
          ),
        border:
          "1px solid rgba(255,255,255,.14)",
        boxShadow:
          "0 12px 35px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.12)",
        padding,
      }}
      onMouseMove={
        handleMouseMove
      }
      onMouseLeave={
        handleMouseLeave
      }
    >
      <div
        className="relative"
        style={{
          height: baseIconSize,
          width: "100%",
        }}
      >
        {apps.map(
          (app, index) => {
            const scale =
              currentScales[index] ||
              1

            const position =
              currentPositions[
                index
              ] || 0

            const scaledSize =
              baseIconSize * scale

            return (
              <div
                key={app.id}
                ref={element => {
                  iconRefs.current[
                    index
                  ] = element
                }}
                className="absolute flex cursor-pointer flex-col items-center justify-end"
                title={app.name}
                onClick={() =>
                  handleAppClick(
                    app.id,
                    index
                  )
                }
                style={{
                  left:
                    position -
                    scaledSize / 2,
                  bottom: 0,
                  width:
                    scaledSize,
                  height:
                    scaledSize,
                  transformOrigin:
                    "bottom center",
                  zIndex:
                    Math.round(
                      scale * 10
                    ),
                }}
              >
                <img
                  src={app.icon}
                  alt={app.name}
                  width={scaledSize}
                  height={scaledSize}
                  className="object-contain"
                  draggable={false}
                  style={{
                    filter:
                      `drop-shadow(0 ${Math.max(
                        1,
                        baseIconSize *
                          0.04
                      )}px ${Math.max(
                        2,
                        baseIconSize *
                          0.08
                      )}px rgba(0,0,0,.3))`,
                  }}
                />

                {openApps.includes(
                  app.id
                ) && (
                  <div
                    className="absolute"
                    style={{
                      bottom:
                        Math.max(
                          -2,
                          -baseIconSize *
                            0.05
                        ),
                      left: "50%",
                      transform:
                        "translateX(-50%)",
                      width:
                        Math.max(
                          3,
                          baseIconSize *
                            0.06
                        ),
                      height:
                        Math.max(
                          3,
                          baseIconSize *
                            0.06
                        ),
                      borderRadius:
                        "50%",
                      background:
                        "rgba(255,255,255,.8)",
                    }}
                  />
                )}
              </div>
            )
          }
        )}
      </div>
    </div>
  )
}

export default MacOSDock