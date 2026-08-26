"use client"

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react"

export interface AsciiArtHandle {
  setProgress: (progress: number) => void
}

interface AsciiArtProps {
  className?: string
}

const FRAME_COUNT = 240
const FRAME_PATH = "/cinematic/wizard-frames"

const INITIAL_FRAMES = 12
const LOAD_BATCH_SIZE = 12
const MAX_CACHED_FRAMES = 48

export const AsciiArt = forwardRef<
  AsciiArtHandle,
  AsciiArtProps
>(function AsciiArt({ className }, ref) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const targetProgressRef = useRef(0)
  const currentFrameRef = useRef(0)

  const imagesRef = useRef<
    Map<number, HTMLImageElement>
  >(new Map())

  const loadingRef = useRef<
    Set<number>
  >(new Set())

  const loadedRef = useRef<
    Set<number>
  >(new Set())

  const frameRequestRef =
    useRef<number | null>(null)

  const renderRequestRef =
    useRef<number | null>(null)

  const destroyedRef =
    useRef(false)

  const lastWidthRef =
    useRef(0)

  const lastHeightRef =
    useRef(0)

  const dprRef =
    useRef(1)

  const lastRenderedFrameRef =
    useRef(-1)

  const drawFrame = (
    frameNumber: number
  ) => {
    const canvas =
      canvasRef.current

    if (!canvas) return

    const image =
      imagesRef.current.get(
        frameNumber
      )

    if (!image || !image.complete) {
      return
    }

    const context =
      canvas.getContext("2d", {
        alpha: false,
        desynchronized: true,
      })

    if (!context) return

    const rect =
      canvas.getBoundingClientRect()

    const width =
      Math.max(
        1,
        Math.round(rect.width)
      )

    const height =
      Math.max(
        1,
        Math.round(rect.height)
      )

    const dpr =
      Math.min(
        window.devicePixelRatio || 1,
        2
      )

    if (
      lastWidthRef.current !==
        width ||
      lastHeightRef.current !==
        height ||
      dprRef.current !== dpr
    ) {
      canvas.width =
        Math.round(width * dpr)

      canvas.height =
        Math.round(height * dpr)

      lastWidthRef.current =
        width

      lastHeightRef.current =
        height

      dprRef.current = dpr

      context.setTransform(
        dpr,
        0,
        0,
        dpr,
        0,
        0
      )
    }

    context.clearRect(
      0,
      0,
      width,
      height
    )

    const imageWidth =
      image.naturalWidth

    const imageHeight =
      image.naturalHeight

    if (
      !imageWidth ||
      !imageHeight
    ) {
      return
    }

    /*
     * Equivalent to object-fit: cover.
     *
     * The image itself scales.
     * Nothing outside the cinematic
     * background is transformed here.
     */
    const scale =
      Math.max(
        width / imageWidth,
        height / imageHeight
      )

    const drawWidth =
      imageWidth * scale

    const drawHeight =
      imageHeight * scale

    const x =
      (width - drawWidth) / 2

    const y =
      (height - drawHeight) / 2

    context.drawImage(
      image,
      x,
      y,
      drawWidth,
      drawHeight
    )

    lastRenderedFrameRef.current =
      frameNumber
  }

  const loadFrame = (
    frameNumber: number
  ) => {
    if (
      frameNumber < 0 ||
      frameNumber >= FRAME_COUNT
    ) {
      return
    }

    if (
      loadedRef.current.has(
        frameNumber
      )
    ) {
      return
    }

    if (
      loadingRef.current.has(
        frameNumber
      )
    ) {
      return
    }

    loadingRef.current.add(
      frameNumber
    )

    const image =
      new Image()

    image.decoding = "async"

    image.onload = () => {
      if (
        destroyedRef.current
      ) {
        return
      }

      imagesRef.current.set(
        frameNumber,
        image
      )

      loadedRef.current.add(
        frameNumber
      )

      loadingRef.current.delete(
        frameNumber
      )

      /*
       * If this is currently requested,
       * render it immediately.
       */
      const targetFrame =
        Math.round(
          targetProgressRef.current *
            (FRAME_COUNT - 1)
        )

      if (
        targetFrame ===
        frameNumber
      ) {
        drawFrame(frameNumber)
      }
    }

    image.onerror = () => {
      loadingRef.current.delete(
        frameNumber
      )
    }

    image.src =
      `${FRAME_PATH}/frame_${String(
        frameNumber + 1
      ).padStart(4, "0")}.webp`
  }

  const maintainCache = (
    centerFrame: number
  ) => {
    if (
      imagesRef.current.size <=
      MAX_CACHED_FRAMES
    ) {
      return
    }

    const entries =
      Array.from(
        imagesRef.current.keys()
      )

    entries.sort(
      (a, b) =>
        Math.abs(
          a - centerFrame
        ) -
        Math.abs(
          b - centerFrame
        )
    )

    const keep =
      new Set(
        entries.slice(
          0,
          MAX_CACHED_FRAMES
        )
      )

    for (
      const frame of entries
    ) {
      if (!keep.has(frame)) {
        imagesRef.current.delete(
          frame
        )

        loadedRef.current.delete(
          frame
        )
      }
    }
  }

  const preloadAround =
    (centerFrame: number) => {
      /*
       * Load slightly ahead and behind.
       *
       * This means fast scrolling does
       * not immediately hit an unloaded
       * frame.
       */
      const radius =
        LOAD_BATCH_SIZE

      for (
        let offset = -radius;
        offset <= radius;
        offset++
      ) {
        const frame =
          centerFrame + offset

        loadFrame(frame)
      }

      maintainCache(
        centerFrame
      )
    }

  useImperativeHandle(
    ref,
    () => ({
      setProgress(progress) {
        const value =
          Math.min(
            1,
            Math.max(
              0,
              progress
            )
          )

        targetProgressRef.current =
          value

        if (
          frameRequestRef.current ===
          null
        ) {
          frameRequestRef.current =
            window.requestAnimationFrame(
              () => {
                frameRequestRef.current =
                  null

                const frame =
                  Math.round(
                    targetProgressRef.current *
                      (FRAME_COUNT - 1)
                  )

                if (
                  frame ===
                  currentFrameRef.current
                ) {
                  return
                }

                currentFrameRef.current =
                  frame

                preloadAround(
                  frame
                )

                const image =
                  imagesRef.current.get(
                    frame
                  )

                if (image) {
                  if (
                    renderRequestRef.current ===
                    null
                  ) {
                    renderRequestRef.current =
                      window.requestAnimationFrame(
                        () => {
                          renderRequestRef.current =
                            null

                          drawFrame(
                            frame
                          )
                        }
                      )
                  }
                } else {
                  /*
                   * If the exact frame is
                   * not ready, find the closest
                   * already decoded frame.
                   */
                  let closest =
                    -1

                  let distance =
                    Infinity

                  for (
                    const loadedFrame of
                      loadedRef.current
                  ) {
                    const nextDistance =
                      Math.abs(
                        loadedFrame -
                          frame
                      )

                    if (
                      nextDistance <
                      distance
                    ) {
                      distance =
                        nextDistance

                      closest =
                        loadedFrame
                    }
                  }

                  if (
                    closest >= 0 &&
                    renderRequestRef.current ===
                      null
                  ) {
                    renderRequestRef.current =
                      window.requestAnimationFrame(
                        () => {
                          renderRequestRef.current =
                            null

                          drawFrame(
                            closest
                          )
                        }
                      )
                  }
                }
              }
            )
        }
      },
    }),
    []
  )

  useEffect(() => {
    destroyedRef.current =
      false

    /*
     * Load the first small group.
     *
     * We deliberately do not load all
     * 240 images on mount.
     */
    for (
      let frame = 0;
      frame < INITIAL_FRAMES;
      frame++
    ) {
      loadFrame(frame)
    }

    const resizeObserver =
      new ResizeObserver(() => {
        lastWidthRef.current = 0
        lastHeightRef.current = 0

        const frame =
          currentFrameRef.current

        const image =
          imagesRef.current.get(
            frame
          )

        if (image) {
          drawFrame(frame)
        }
      })

    const canvas =
      canvasRef.current

    if (canvas) {
      resizeObserver.observe(
        canvas
      )
    }

    return () => {
      destroyedRef.current =
        true

      resizeObserver.disconnect()

      if (
        frameRequestRef.current !==
        null
      ) {
        cancelAnimationFrame(
          frameRequestRef.current
        )

        frameRequestRef.current =
          null
      }

      if (
        renderRequestRef.current !==
        null
      ) {
        cancelAnimationFrame(
          renderRequestRef.current
        )

        renderRequestRef.current =
          null
      }

      imagesRef.current.clear()
      loadedRef.current.clear()
      loadingRef.current.clear()
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className={className}
      aria-label="Wizard cinematic world"
      style={{
        display: "block",
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        background:
          "#07131a",
        transform:
          "translateZ(0)",
        backfaceVisibility:
          "hidden",
      }}
    />
  )
})