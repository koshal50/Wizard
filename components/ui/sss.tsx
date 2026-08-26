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

const FRAME_PATH = (index: number) =>
  `/cinematic/wizard-frames/frame_${String(
    index + 1
  ).padStart(4, "0")}.webp`

const MAX_DPR = 1

const PRELOAD_AHEAD = 24

const INITIAL_PRELOAD = 48

const FRAME_EPSILON = 0.002

type FrameImage = HTMLImageElement | null

export const AsciiArt = forwardRef<
  AsciiArtHandle,
  AsciiArtProps
>(function AsciiArt({ className }, ref) {
  const canvasRef =
    useRef<HTMLCanvasElement>(null)

  const containerRef =
    useRef<HTMLDivElement>(null)

  const framesRef =
    useRef<FrameImage[]>(
      new Array(FRAME_COUNT).fill(null)
    )

  const loadingRef =
    useRef<boolean[]>(
      new Array(FRAME_COUNT).fill(false)
    )

  const loadedRef =
    useRef<boolean[]>(
      new Array(FRAME_COUNT).fill(false)
    )

  const targetProgressRef =
    useRef(0)

  const renderedFrameRef =
    useRef(-1)

  const requestedFrameRef =
    useRef(0)

  const animationFrameRef =
    useRef<number | null>(null)

  const preloadCursorRef =
    useRef(0)

  const resizeFrameRef =
    useRef<number | null>(null)

  const readyRef =
    useRef(false)

  const destroyedRef =
    useRef(false)

  const canvasWidthRef =
    useRef(0)

  const canvasHeightRef =
    useRef(0)

  const drawFrame =
    (frameIndex: number) => {
      const canvas =
        canvasRef.current

      if (!canvas) {
        return
      }

      const image =
        framesRef.current[
          frameIndex
        ]

      if (!image) {
        return
      }

      const ctx =
        canvas.getContext("2d", {
          alpha: false,
          desynchronized: true,
        })

      if (!ctx) {
        return
      }

      const canvasWidth =
        canvasWidthRef.current

      const canvasHeight =
        canvasHeightRef.current

      if (
        canvasWidth <= 0 ||
        canvasHeight <= 0
      ) {
        return
      }

      /*
       * Cover calculation.
       *
       * The source is 16:9.
       * The canvas follows the viewport.
       */
      const imageWidth =
        image.naturalWidth

      const imageHeight =
        image.naturalHeight

      if (
        imageWidth <= 0 ||
        imageHeight <= 0
      ) {
        return
      }

      const scale =
        Math.max(
          canvasWidth /
            imageWidth,
          canvasHeight /
            imageHeight
        )

      const drawWidth =
        imageWidth * scale

      const drawHeight =
        imageHeight * scale

      const x =
        (canvasWidth -
          drawWidth) /
        2

      const y =
        (canvasHeight -
          drawHeight) /
        2

      ctx.drawImage(
        image,
        x,
        y,
        drawWidth,
        drawHeight
      )

      renderedFrameRef.current =
        frameIndex
    }

  const loadFrame =
    (index: number) => {
      if (
        index < 0 ||
        index >= FRAME_COUNT
      ) {
        return
      }

      if (
        loadedRef.current[index] ||
        loadingRef.current[index]
      ) {
        return
      }

      loadingRef.current[index] =
        true

      const image =
        new Image()

      image.decoding = "async"

      image.loading = "eager"

      image.src =
        FRAME_PATH(index)

      image.onload = () => {
        if (destroyedRef.current) {
          return
        }

        framesRef.current[index] =
          image

        loadedRef.current[index] =
          true

        loadingRef.current[index] =
          false

        /*
         * If this is the frame currently
         * requested by scroll, render it
         * immediately on the next RAF.
         */
        if (
          requestedFrameRef.current ===
          index
        ) {
          if (
            animationFrameRef.current ===
            null
          ) {
            animationFrameRef.current =
              window.requestAnimationFrame(
                render
              )
          }
        }
      }

      image.onerror = () => {
        loadingRef.current[index] =
          false
      }
    }

  const preloadAround =
    (centerFrame: number) => {
      const start =
        Math.max(
          0,
          centerFrame
        )

      const end =
        Math.min(
          FRAME_COUNT - 1,
          centerFrame +
            PRELOAD_AHEAD
        )

      /*
       * Load the current frame first.
       */
      loadFrame(centerFrame)

      /*
       * Then load frames in both
       * directions around the current
       * position.
       */
      for (
        let distance = 1;
        distance <=
        PRELOAD_AHEAD;
        distance++
      ) {
        loadFrame(
          centerFrame +
            distance
        )

        loadFrame(
          centerFrame -
            distance
        )
      }

      /*
       * Keep the variables explicit so
       * this function remains easy to
       * tune later.
       */
      void start
      void end
    }

  const render =
    () => {
      animationFrameRef.current =
        null

      if (destroyedRef.current) {
        return
      }

      const targetFrame =
        requestedFrameRef.current

      if (
        targetFrame ===
        renderedFrameRef.current
      ) {
        return
      }

      const image =
        framesRef.current[
          targetFrame
        ]

      if (!image) {
        /*
         * Never synchronously decode here.
         *
         * The frame loader will render
         * once the image becomes available.
         */
        return
      }

      drawFrame(targetFrame)
    }

  const scheduleRender =
    () => {
      if (
        animationFrameRef.current !==
        null
      ) {
        return
      }

      animationFrameRef.current =
        window.requestAnimationFrame(
          render
        )
    }

  useImperativeHandle(
    ref,
    () => ({
      setProgress(
        progress: number
      ) {
        const clamped =
          Math.max(
            0,
            Math.min(
              1,
              progress
            )
          )

        /*
         * Ignore microscopic scroll
         * changes that map to the same
         * cinematic frame.
         */
        if (
          Math.abs(
            clamped -
              targetProgressRef.current
          ) <
          FRAME_EPSILON
        ) {
          return
        }

        targetProgressRef.current =
          clamped

        const frame =
          Math.min(
            FRAME_COUNT - 1,
            Math.max(
              0,
              Math.round(
                clamped *
                  (FRAME_COUNT -
                    1)
              )
            )
          )

        requestedFrameRef.current =
          frame

        /*
         * Start preparing frames around
         * the user's current position.
         */
        preloadAround(frame)

        scheduleRender()
      },
    }),
    []
  )

  useEffect(() => {
    const canvas =
      canvasRef.current

    const container =
      containerRef.current

    if (
      !canvas ||
      !container
    ) {
      return
    }

    destroyedRef.current =
      false

    const ctx =
      canvas.getContext("2d", {
        alpha: false,
        desynchronized: true,
      })

    if (!ctx) {
      return
    }

    const resize =
      () => {
        resizeFrameRef.current =
          null

        const rect =
          container.getBoundingClientRect()

        const width =
          Math.max(
            1,
            Math.round(
              rect.width
            )
          )

        const height =
          Math.max(
            1,
            Math.round(
              rect.height
            )
          )

        const dpr =
          Math.min(
            window.devicePixelRatio ||
              1,
            MAX_DPR
          )

        canvasWidthRef.current =
          width

        canvasHeightRef.current =
          height

        canvas.width =
          Math.round(
            width * dpr
          )

        canvas.height =
          Math.round(
            height * dpr
          )

        canvas.style.width =
          `${width}px`

        canvas.style.height =
          `${height}px`

        /*
         * We intentionally render at
         * a maximum DPR of 1.
         */
        ctx.setTransform(
          dpr,
          0,
          0,
          dpr,
          0,
          0
        )

        /*
         * Repaint the current frame
         * after resize.
         */
        const current =
          renderedFrameRef.current

        if (
          current >= 0 &&
          framesRef.current[
            current
          ]
        ) {
          drawFrame(current)
        }
      }

    const scheduleResize =
      () => {
        if (
          resizeFrameRef.current !==
          null
        ) {
          return
        }

        resizeFrameRef.current =
          window.requestAnimationFrame(
            resize
          )
      }

    const resizeObserver =
      new ResizeObserver(
        scheduleResize
      )

    resizeObserver.observe(
      container
    )

    window.addEventListener(
      "resize",
      scheduleResize,
      {
        passive: true,
      }
    )

    resize()

    /*
     * Load the first chunk immediately.
     *
     * This means the cinematic is
     * already populated before the
     * user starts interacting with it.
     */
    const initialCount =
      Math.min(
        INITIAL_PRELOAD,
        FRAME_COUNT
      )

    for (
      let index = 0;
      index < initialCount;
      index++
    ) {
      loadFrame(index)
    }

    /*
     * Continue loading the remaining
     * frames gradually.
     *
     * This avoids decoding 240 images
     * in one giant blocking operation.
     */
    const preloadRemaining =
      () => {
        if (
          destroyedRef.current
        ) {
          return
        }

        const batchSize = 8

        const start =
          preloadCursorRef.current

        const end =
          Math.min(
            FRAME_COUNT,
            start +
              batchSize
          )

        for (
          let index = start;
          index < end;
          index++
        ) {
          loadFrame(index)
        }

        preloadCursorRef.current =
          end

        if (
          end < FRAME_COUNT
        ) {
          window.setTimeout(
            preloadRemaining,
            50
          )
        }
      }

    preloadCursorRef.current =
      initialCount

    window.setTimeout(
      preloadRemaining,
      100
    )

    readyRef.current =
      true

    return () => {
      destroyedRef.current =
        true

      readyRef.current =
        false

      resizeObserver.disconnect()

      window.removeEventListener(
        "resize",
        scheduleResize
      )

      if (
        animationFrameRef.current !==
        null
      ) {
        window.cancelAnimationFrame(
          animationFrameRef.current
        )

        animationFrameRef.current =
          null
      }

      if (
        resizeFrameRef.current !==
        null
      ) {
        window.cancelAnimationFrame(
          resizeFrameRef.current
        )

        resizeFrameRef.current =
          null
      }

      /*
       * Release image references so
       * the browser can reclaim memory
       * when this component unmounts.
       */
      framesRef.current =
        new Array(
          FRAME_COUNT
        ).fill(null)

      loadedRef.current =
        new Array(
          FRAME_COUNT
        ).fill(false)

      loadingRef.current =
        new Array(
          FRAME_COUNT
        ).fill(false)
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        background: "#000",
        contain:
          "layout paint size",
        transform:
          "translateZ(0)",
      }}
    >
      <canvas
        ref={canvasRef}
        aria-label="Wizard cinematic world"
        role="img"
        style={{
          display: "block",
          width: "100%",
          height: "100%",
          pointerEvents: "none",
          transform:
            "translateZ(0)",
          backfaceVisibility:
            "hidden",
        }}
      />
    </div>
  )
})

AsciiArt.displayName =
  "AsciiArt"