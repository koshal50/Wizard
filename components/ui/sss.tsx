"use client"

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react"

export interface AsciiArtHandle {
  setProgress: (
    progress: number
  ) => void
}

interface AsciiArtProps {
  className?: string
}

export const AsciiArt =
  forwardRef<
    AsciiArtHandle,
    AsciiArtProps
  >(function AsciiArt(
    {
      className,
    },
    ref
  ) {
    const videoRef =
      useRef<HTMLVideoElement>(null)

    const targetProgress =
      useRef(0)

    const currentTime =
      useRef(-1)

    const frameRef =
      useRef<number | null>(null)

    const readyRef =
      useRef(false)

    const durationRef =
      useRef(0)

    useImperativeHandle(
      ref,
      () => ({
        setProgress(
          value: number
        ) {
          targetProgress.current =
            Math.min(
              1,
              Math.max(
                0,
                value
              )
            )
        },
      }),
      []
    )

    useEffect(() => {
      const video =
        videoRef.current

      if (!video) {
        return
      }

      video.pause()

      const handleMetadata =
        () => {
          if (
            !Number.isFinite(
              video.duration
            ) ||
            video.duration <= 0
          ) {
            return
          }

          durationRef.current =
            video.duration

          readyRef.current =
            true

          video.currentTime =
            0

          currentTime.current =
            0
        }

      const handleCanPlay =
        () => {
          if (
            Number.isFinite(
              video.duration
            ) &&
            video.duration > 0
          ) {
            durationRef.current =
              video.duration

            readyRef.current =
              true
          }
        }

      video.addEventListener(
        "loadedmetadata",
        handleMetadata
      )

      video.addEventListener(
        "canplay",
        handleCanPlay
      )

      if (
        video.readyState >= 1
      ) {
        handleMetadata()
      }

      video.load()

      return () => {
        video.removeEventListener(
          "loadedmetadata",
          handleMetadata
        )

        video.removeEventListener(
          "canplay",
          handleCanPlay
        )
      }
    }, [])

    useEffect(() => {
      const update =
        () => {
          const video =
            videoRef.current

          if (
            video &&
            readyRef.current &&
            durationRef.current > 0
          ) {
            const target =
              targetProgress.current

            const nextTime =
              target *
              durationRef.current

            /*
             * Roughly one frame at
             * 30fps.
             *
             * This prevents tiny scroll
             * movements from triggering
             * unnecessary seeks.
             */
            const threshold =
              1 / 30

            if (
              Math.abs(
                nextTime -
                  currentTime.current
              ) >=
              threshold
            ) {
              video.currentTime =
                nextTime

              currentTime.current =
                nextTime
            }
          }

          frameRef.current =
            window.requestAnimationFrame(
              update
            )
        }

      frameRef.current =
        window.requestAnimationFrame(
          update
        )

      return () => {
        if (
          frameRef.current !==
          null
        ) {
          window.cancelAnimationFrame(
            frameRef.current
          )

          frameRef.current =
            null
        }
      }
    }, [])

    return (
      <video
        ref={videoRef}
        className={className}
        src="/cinematic/wizard-world-scrub.mp4"
        muted
        playsInline
        preload="auto"
        controls={false}
        disablePictureInPicture
        aria-label="Wizard cinematic world"
        style={{
          display: "block",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          pointerEvents: "none",
          transform:
            "translateZ(0)",
          backfaceVisibility:
            "hidden",
        }}
      />
    )
  })