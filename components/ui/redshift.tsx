"use client"

import { useEffect, useRef } from "react"

export function AsciiArt({
  className,
}: {
  className?: string
}) {
  const canvasRef =
    useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas =
      canvasRef.current

    if (!canvas) return

    const ctx =
      canvas.getContext("2d")

    if (!ctx) return

    let animationFrame = 0
    let width = 0
    let height = 0
    let dpr = 1

    const particles = Array.from(
      { length: 95 },
      (_, index) => ({
        x: Math.random(),
        y: Math.random(),
        size:
          0.5 +
          Math.random() * 2.2,
        speed:
          0.00018 +
          Math.random() * 0.00042,
        drift:
          0.00012 +
          Math.random() * 0.00025,
        phase:
          Math.random() *
          Math.PI *
          2,
        opacity:
          0.12 +
          Math.random() * 0.34,
        depth:
          0.3 +
          Math.random() * 0.7,
        index,
      })
    )

    const crystals = Array.from(
      { length: 18 },
      (_, index) => ({
        x:
          Math.random() *
          1.1 -
          0.05,
        y:
          Math.random() *
          1.1 -
          0.05,
        size:
          35 +
          Math.random() * 110,
        rotation:
          Math.random() *
          Math.PI,
        opacity:
          0.025 +
          Math.random() * 0.045,
        phase:
          Math.random() *
          Math.PI *
          2,
        index,
      })
    )

    const resize = () => {
      const rect =
        canvas.getBoundingClientRect()

      dpr = Math.min(
        window.devicePixelRatio || 1,
        2
      )

      width = rect.width
      height = rect.height

      canvas.width =
        width * dpr

      canvas.height =
        height * dpr

      ctx.setTransform(
        dpr,
        0,
        0,
        dpr,
        0,
        0
      )
    }

    const drawCrystal = (
      x: number,
      y: number,
      size: number,
      rotation: number,
      opacity: number,
      time: number
    ) => {
      ctx.save()

      ctx.translate(x, y)
      ctx.rotate(
        rotation +
          Math.sin(
            time * 0.00015
          ) *
            0.03
      )

      ctx.strokeStyle = `rgba(210, 242, 255, ${opacity})`
      ctx.lineWidth = 0.7

      for (
        let branch = 0;
        branch < 6;
        branch++
      ) {
        ctx.save()

        ctx.rotate(
          (Math.PI * 2 * branch) /
            6
        )

        ctx.beginPath()

        ctx.moveTo(
          0,
          -size * 0.5
        )

        ctx.lineTo(
          0,
          size * 0.5
        )

        ctx.stroke()

        for (
          let level = 1;
          level < 4;
          level++
        ) {
          const distance =
            size *
            (0.5 -
              level * 0.11)

          const branchSize =
            size *
            (0.08 -
              level * 0.012)

          ctx.beginPath()

          ctx.moveTo(
            0,
            -distance
          )

          ctx.lineTo(
            -branchSize,
            -distance +
              branchSize
          )

          ctx.moveTo(
            0,
            -distance
          )

          ctx.lineTo(
            branchSize,
            -distance +
              branchSize
          )

          ctx.stroke()
        }

        ctx.restore()
      }

      ctx.restore()
    }

    const render = (
      time: number
    ) => {
      ctx.clearRect(
        0,
        0,
        width,
        height
      )

      /*
       * Cold atmospheric wash.
       *
       * This sits above the Redshift
       * video but remains transparent.
       */

      const atmosphere =
        ctx.createLinearGradient(
          0,
          0,
          0,
          height
        )

      atmosphere.addColorStop(
        0,
        "rgba(225, 248, 255, 0.08)"
      )

      atmosphere.addColorStop(
        0.35,
        "rgba(127, 198, 230, 0.035)"
      )

      atmosphere.addColorStop(
        0.7,
        "rgba(46, 124, 192, 0.025)"
      )

      atmosphere.addColorStop(
        1,
        "rgba(18, 58, 107, 0.16)"
      )

      ctx.fillStyle =
        atmosphere

      ctx.fillRect(
        0,
        0,
        width,
        height
      )

      /*
       * Large moving cold glow.
       *
       * This gives the feeling of light
       * moving through ice rather than
       * simply placing a blue overlay.
       */

      const glowX =
        width *
        (0.5 +
          Math.sin(
            time * 0.00008
          ) *
            0.22)

      const glowY =
        height *
        (0.38 +
          Math.cos(
            time * 0.00006
          ) *
            0.14)

      const glow =
        ctx.createRadialGradient(
          glowX,
          glowY,
          0,
          glowX,
          glowY,
          Math.max(
            width,
            height
          ) *
            0.65
        )

      glow.addColorStop(
        0,
        "rgba(234, 247, 251, 0.11)"
      )

      glow.addColorStop(
        0.25,
        "rgba(127, 198, 230, 0.055)"
      )

      glow.addColorStop(
        0.65,
        "rgba(46, 124, 192, 0.018)"
      )

      glow.addColorStop(
        1,
        "rgba(18, 58, 107, 0)"
      )

      ctx.fillStyle = glow

      ctx.fillRect(
        0,
        0,
        width,
        height
      )

      /*
       * Floating ice particles.
       *
       * Their movement is intentionally
       * slow and imperfect.
       */

      for (const particle of particles) {
        const drift =
          Math.sin(
            time *
              particle.drift +
              particle.phase
          ) *
          0.035

        const y =
          (particle.y +
            time *
              particle.speed *
              particle.depth) %
          1.08

        const x =
          particle.x +
          drift

        if (
          x < -0.05 ||
          x > 1.05
        ) {
          continue
        }

        const pulse =
          0.72 +
          Math.sin(
            time * 0.0005 +
              particle.phase
          ) *
            0.28

        const alpha =
          particle.opacity *
          pulse

        ctx.beginPath()

        ctx.arc(
          x * width,
          y * height,
          particle.size *
            particle.depth,
          0,
          Math.PI * 2
        )

        ctx.fillStyle = `rgba(225, 248, 255, ${alpha})`

        ctx.fill()
      }

      /*
       * Very faint crystalline structures.
       *
       * These should be discovered by
       * the eye rather than immediately seen.
       */

      for (const crystal of crystals) {
        const breathing =
          1 +
          Math.sin(
            time * 0.00012 +
              crystal.phase
          ) *
            0.08

        const alpha =
          crystal.opacity *
          (0.75 +
            Math.sin(
              time * 0.0002 +
                crystal.phase
            ) *
              0.25)

        drawCrystal(
          crystal.x * width,
          crystal.y * height,
          crystal.size *
            breathing,
          crystal.rotation,
          alpha,
          time
        )
      }

      /*
       * Subtle frost at the edges.
       */

      const edge =
        ctx.createRadialGradient(
          width / 2,
          height / 2,
          Math.min(
            width,
            height
          ) *
            0.2,
          width / 2,
          height / 2,
          Math.max(
            width,
            height
          ) *
            0.75
        )

      edge.addColorStop(
        0,
        "rgba(0,0,0,0)"
      )

      edge.addColorStop(
        0.7,
        "rgba(10,38,67,0.015)"
      )

      edge.addColorStop(
        1,
        "rgba(2,14,27,0.28)"
      )

      ctx.fillStyle = edge

      ctx.fillRect(
        0,
        0,
        width,
        height
      )

      animationFrame =
        window.requestAnimationFrame(
          render
        )
    }

    resize()

    window.addEventListener(
      "resize",
      resize
    )

    animationFrame =
      window.requestAnimationFrame(
        render
      )

    return () => {
      window.removeEventListener(
        "resize",
        resize
      )

      window.cancelAnimationFrame(
        animationFrame
      )
    }
  }, [])

  return (
    <div
      className={`relative overflow-hidden ${className ?? ""}`}
    >
      {/* Existing Redshift layer */}
      <video
        className="absolute inset-0 h-full w-full object-cover"
        src="https://assets.21st.dev/ascii-recipes/videos/user_2nElBLvklOKlAURm6W1PTu6yYFh/1783480440186-b7o356.mp4"
        poster="https://assets.21st.dev/ascii-recipes/thumbnails/user_2nElBLvklOKlAURm6W1PTu6yYFh/63f8aa27-cea7-49e0-a6a4-c2dc0954563c.jpg"
        autoPlay
        loop
        muted
        playsInline
        aria-hidden="true"
        style={{
          display: "block",
          width: "100%",
          height: "100%",
          objectFit: "cover",
        }}
      />

      {/* Ice Age atmospheric layer */}
      <canvas
        ref={canvasRef}
        className="pointer-events-none absolute inset-0 h-full w-full"
        aria-hidden="true"
      />

      {/* Final cold glass veil */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "linear-gradient(180deg, rgba(234,247,251,0.025) 0%, rgba(18,58,107,0.06) 48%, rgba(2,14,27,0.18) 100%)",
          mixBlendMode: "screen",
        }}
      />
    </div>
  )
}