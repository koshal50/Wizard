"use client"

import {
  useEffect,
  useRef,
} from "react"

interface AsciiArtProps {
  className?: string
  progress?: number
}

export function AsciiArt({
  className,
  progress = 0,
}: AsciiArtProps) {
  const videoRef =
    useRef<HTMLVideoElement>(null)

  const targetProgress =
    useRef(0)

  const currentProgress =
    useRef(0)

  const animationFrame =
    useRef<number | null>(null)

  const metadataReady =
    useRef(false)

  /*
   * Keep the latest scroll position
   * available without causing React
   * renders.
   */
  useEffect(() => {
    targetProgress.current =
      Math.min(
        1,
        Math.max(
          0,
          progress
        )
      )
  }, [progress])

  /*
   * Prepare the video.
   *
   * This is intentionally NOT autoplay.
   * Scroll controls the timeline.
   */
  useEffect(() => {
    const video =
      videoRef.current

    if (!video) {
      return
    }

    const handleMetadata = () => {
      metadataReady.current =
        true

      video.currentTime = 0
    }

    if (
      video.readyState >= 1
    ) {
      metadataReady.current =
        true
    } else {
      video.addEventListener(
        "loadedmetadata",
        handleMetadata
      )
    }

    return () => {
      video.removeEventListener(
        "loadedmetadata",
        handleMetadata
      )
    }
  }, [])

  /*
   * Smoothly translate scroll progress
   * into video time.
   *
   * We deliberately interpolate instead
   * of directly assigning currentTime on
   * every scroll event.
   *
   * This prevents the cinematic background
   * from looking like it is jumping between
   * frames.
   */
  useEffect(() => {
    const animate = () => {
      const video =
        videoRef.current

      if (
        video &&
        metadataReady.current &&
        Number.isFinite(
          video.duration
        ) &&
        video.duration > 0
      ) {
        const target =
          targetProgress.current

        const current =
          currentProgress.current

        const difference =
          target - current

        if (
          Math.abs(difference) >
          0.00005
        ) {
          const next =
            current +
            difference *
              0.12

          currentProgress.current =
            next

          const safeProgress =
            Math.min(
              0.999,
              Math.max(
                0,
                next
              )
            )

          const targetTime =
            safeProgress *
            video.duration

          /*
           * Avoid unnecessary seeks.
           */
          if (
            Math.abs(
              video.currentTime -
                targetTime
            ) >
            0.012
          ) {
            video.currentTime =
              targetTime
          }
        }
      }

      animationFrame.current =
        window.requestAnimationFrame(
          animate
        )
    }

    animationFrame.current =
      window.requestAnimationFrame(
        animate
      )

    return () => {
      if (
        animationFrame.current !==
        null
      ) {
        window.cancelAnimationFrame(
          animationFrame.current
        )
      }
    }
  }, [])

  /*
   * Keep the video paused forever.
   *
   * It is a visual timeline controlled
   * entirely by the cinematic scroll.
   */
  useEffect(() => {
    const video =
      videoRef.current

    if (!video) {
      return
    }

    video.pause()
  }, [])

  return (
    <video
      ref={videoRef}
      className={className}
      src="/cinematic/wizard-world.mp4"
      muted
      playsInline
      preload="auto"
      controls={false}
      aria-label="Wizard cinematic world"
      style={{
        display: "block",
        width: "100%",
        height: "100%",
        objectFit: "cover",
      }}
    />
  )
}