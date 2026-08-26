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

    /*
     * The parent communicates with the
     * video imperatively.
     *
     * This does NOT trigger React renders.
     */
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

    /*
     * Prepare the video once.
     */
    useEffect(() => {
      const video =
        videoRef.current

      if (!video) {
        return
      }

      video.pause()
      video.currentTime = 0

      const handleMetadata =
        () => {
          readyRef.current =
            true

          currentTime.current =
            0

          video.currentTime = 0
        }

      if (
        video.readyState >= 1
      ) {
        handleMetadata()
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
     * There is exactly ONE animation
     * loop responsible for scrubbing.
     *
     * React never participates in this loop.
     */
    useEffect(() => {
      const update =
        () => {
          const video =
            videoRef.current

          if (
            video &&
            readyRef.current &&
            Number.isFinite(
              video.duration
            ) &&
            video.duration > 0
          ) {
            const target =
              targetProgress.current

            const nextTime =
              target *
              video.duration

            /*
             * Do not seek repeatedly to
             * effectively identical frames.
             */
            if (
              Math.abs(
                nextTime -
                  currentTime.current
              ) > 0.035
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
        src="/cinematic/wizard-world.mp4"
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
        }}
      />
    )
  })