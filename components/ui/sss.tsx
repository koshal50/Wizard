"use client"

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react"

export interface AsciiArtHandle {
  setProgress: (progress: number) => void
}

interface AsciiArtProps {
  className?: string
}

const FRAME_COUNT = 240
const FRAME_PATH = "/cinematic/wizard-frames"
const POSTER_PATH =
  "/cinematic/wizard-frames/frame_0001.webp"

export const AsciiArt = forwardRef<
  AsciiArtHandle,
  AsciiArtProps
>(function AsciiArt({ className }, ref) {
  const canvasRef =
    useRef<HTMLCanvasElement>(null)

  const imagesRef =
    useRef<(HTMLImageElement | null)[]>(
      new Array(FRAME_COUNT).fill(null)
    )

  const loadedRef =
    useRef<boolean[]>(
      new Array(FRAME_COUNT).fill(false)
    )

  const targetProgressRef =
    useRef(0)

  const renderedFrameRef =
    useRef(-1)

  const animationFrameRef =
    useRef<number | null>(null)

  const resizeFrameRef =
    useRef<number | null>(null)

  const [cinematicReady, setCinematicReady] =
    useState(false)

  /*
   * Parent communicates with the renderer
   * without causing React renders.
   */
  useImperativeHandle(
    ref,
    () => ({
      setProgress(progress: number) {
        targetProgressRef.current =
          Math.min(
            1,
            Math.max(0, progress)
          )
      },
    }),
    []
  )

  /*
   * Draw one frame.
   */
  const drawFrame = (
    frameIndex: number
  ) => {
    const canvas =
      canvasRef.current

    const image =
      imagesRef.current[frameIndex]

    if (!canvas || !image) {
      return
    }

    const context =
      canvas.getContext("2d", {
        alpha: false,
        desynchronized: true,
      })

    if (!context) {
      return
    }

    const width =
      canvas.clientWidth

    const height =
      canvas.clientHeight

    if (
      width <= 0 ||
      height <= 0
    ) {
      return
    }

    const devicePixelRatio =
      Math.min(
        window.devicePixelRatio || 1,
        2
      )

    const pixelWidth =
      Math.round(
        width * devicePixelRatio
      )

    const pixelHeight =
      Math.round(
        height * devicePixelRatio
      )

    if (
      canvas.width !== pixelWidth ||
      canvas.height !== pixelHeight
    ) {
      canvas.width = pixelWidth
      canvas.height = pixelHeight

      context.imageSmoothingEnabled =
        true

      context.imageSmoothingQuality =
        "high"
    }

    const sourceWidth =
      image.naturalWidth

    const sourceHeight =
      image.naturalHeight

    const sourceRatio =
      sourceWidth /
      sourceHeight

    const destinationRatio =
      width / height

    let drawWidth: number
    let drawHeight: number
    let offsetX: number
    let offsetY: number

    /*
     * Same visual behavior as
     * object-fit: cover.
     */
    if (
      sourceRatio >
      destinationRatio
    ) {
      drawHeight = height
      drawWidth =
        height *
        sourceRatio

      offsetX =
        (width - drawWidth) / 2

      offsetY = 0
    } else {
      drawWidth = width
      drawHeight =
        width /
        sourceRatio

      offsetX = 0

      offsetY =
        (height - drawHeight) / 2
    }

    context.setTransform(
      devicePixelRatio,
      0,
      0,
      devicePixelRatio,
      0,
      0
    )

    context.clearRect(
      0,
      0,
      width,
      height
    )

    context.drawImage(
      image,
      offsetX,
      offsetY,
      drawWidth,
      drawHeight
    )

    renderedFrameRef.current =
      frameIndex
  }

  /*
   * Load frames progressively.
   *
   * The first frame gets priority so the
   * cinematic can appear immediately.
   */
  useEffect(() => {
    let cancelled = false

    const loadFrame = (
      index: number
    ) => {
      if (cancelled) {
        return
      }

      if (
        imagesRef.current[index]
      ) {
        return
      }

      const image =
        new Image()

      image.decoding = "async"

      image.src =
        `${FRAME_PATH}/frame_${String(
          index + 1
        ).padStart(4, "0")}.webp`

      image.onload = async () => {
        if (cancelled) {
          return
        }

        try {
          if (
            "decode" in image
          ) {
            await image.decode()
          }
        } catch {
          /*
           * The image can still be drawn
           * even if decode() rejects.
           */
        }

        if (cancelled) {
          return
        }

        imagesRef.current[index] =
          image

        loadedRef.current[index] =
          true

        /*
         * The first usable frame means
         * the cinematic can take over.
         */
        if (index === 0) {
          drawFrame(0)
          setCinematicReady(true)
        }
      }

      image.onerror = () => {
        /*
         * Do not break the entire cinematic
         * if one frame fails.
         */
      }
    }

    /*
     * Load the first frame immediately.
     */
    loadFrame(0)

    /*
     * Load nearby frames first.
     */
    for (
      let index = 1;
      index < Math.min(24, FRAME_COUNT);
      index++
    ) {
      loadFrame(index)
    }

    /*
     * Continue loading the rest in small
     * batches so the browser is not flooded
     * with 240 simultaneous requests.
     */
    let nextIndex = 24

    const batchTimer =
      window.setInterval(() => {
        if (cancelled) {
          return
        }

        const batchEnd =
          Math.min(
            nextIndex + 12,
            FRAME_COUNT
          )

        for (
          let index = nextIndex;
          index < batchEnd;
          index++
        ) {
          loadFrame(index)
        }

        nextIndex = batchEnd

        if (
          nextIndex >= FRAME_COUNT
        ) {
          window.clearInterval(
            batchTimer
          )
        }
      }, 80)

    return () => {
      cancelled = true

      window.clearInterval(
        batchTimer
      )
    }
  }, [])

  /*
   * Render loop.
   *
   * React is completely outside the
   * scrolling and frame rendering loop.
   */
  useEffect(() => {
    const render = () => {
      const progress =
        targetProgressRef.current

      const rawFrame =
        progress *
        (FRAME_COUNT - 1)

      const desiredFrame =
        Math.round(rawFrame)

      /*
       * If the exact frame is not ready,
       * find the closest already loaded frame.
       *
       * This prevents black flashes and
       * avoids waiting for network requests.
       */
      let frameToDraw =
        desiredFrame

      if (
        !loadedRef.current[
          frameToDraw
        ]
      ) {
        let found = -1

        /*
         * Search forward first because
         * progressive loading normally means
         * upcoming frames are available.
         */
        for (
          let distance = 1;
          distance < FRAME_COUNT;
          distance++
        ) {
          const forward =
            desiredFrame +
            distance

          if (
            forward <
              FRAME_COUNT &&
            loadedRef.current[
              forward
            ]
          ) {
            found = forward
            break
          }

          const backward =
            desiredFrame -
            distance

          if (
            backward >= 0 &&
            loadedRef.current[
              backward
            ]
          ) {
            found = backward
            break
          }
        }

        if (found >= 0) {
          frameToDraw = found
        } else {
          frameToDraw = 0
        }
      }

      if (
        loadedRef.current[
          frameToDraw
        ] &&
        frameToDraw !==
          renderedFrameRef.current
      ) {
        drawFrame(frameToDraw)
      }

      animationFrameRef.current =
        window.requestAnimationFrame(
          render
        )
    }

    animationFrameRef.current =
      window.requestAnimationFrame(
        render
      )

    return () => {
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
    }
  }, [])

  /*
   * Handle viewport changes without
   * involving React state.
   */
  useEffect(() => {
    const resize =
      () => {
        if (
          resizeFrameRef.current !==
          null
        ) {
          return
        }

        resizeFrameRef.current =
          window.requestAnimationFrame(
            () => {
              resizeFrameRef.current =
                null

              const frame =
                renderedFrameRef.current

              if (
                frame >= 0 &&
                loadedRef.current[
                  frame
                ]
              ) {
                drawFrame(frame)
              }
            }
          )
      }

    window.addEventListener(
      "resize",
      resize,
      {
        passive: true,
      }
    )

    return () => {
      window.removeEventListener(
        "resize",
        resize
      )

      if (
        resizeFrameRef.current !==
        null
      ) {
        window.cancelAnimationFrame(
          resizeFrameRef.current
        )
      }
    }
  }, [])

  return (
    <div
      className={className}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        background: "#000",
      }}
    >
      {/*
       * Cinematic poster.
       *
       * This appears immediately while the
       * real frame renderer is warming up.
       *
       * There is intentionally no text,
       * spinner, loader, or UI.
       */}
      <img
        src={POSTER_PATH}
        alt=""
        aria-hidden="true"
        draggable={false}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          pointerEvents: "none",
          userSelect: "none",

          opacity:
            cinematicReady
              ? 0
              : 1,

          transform:
            cinematicReady
              ? "scale(1)"
              : "scale(1.018)",

          filter:
            cinematicReady
              ? "brightness(1) blur(0)"
              : "brightness(.42) blur(2px)",

          transition:
            cinematicReady
              ? "opacity 900ms ease, transform 1800ms ease, filter 1200ms ease"
              : "opacity 0ms",

          willChange:
            "opacity, transform, filter",
        }}
      />

      {/*
       * Real frame renderer.
       */}
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        style={{
          position: "absolute",
          inset: 0,
          display: "block",
          width: "100%",
          height: "100%",
          pointerEvents: "none",
          background: "#000",
          opacity:
            cinematicReady
              ? 1
              : 0,
          transition:
            "opacity 900ms ease",
          transform:
            "translateZ(0)",
          backfaceVisibility:
            "hidden",
          willChange:
            "opacity",
        }}
      />

      {/*
       * Extremely subtle atmospheric layer.
       *
       * It makes the transition feel like
       * the image is developing rather than
       * simply appearing.
       */}
      <div
        aria-hidden="true"
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",

          background:
            "radial-gradient(circle at 50% 45%, rgba(255,255,255,.055), transparent 48%)",

          opacity:
            cinematicReady
              ? 0
              : 1,

          transition:
            "opacity 1400ms ease",

          mixBlendMode:
            "screen",
        }}
      />
    </div>
  )
})

AsciiArt.displayName =
  "AsciiArt"