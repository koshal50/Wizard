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
    const canvas = canvasRef.current

    if (!canvas) return

    const ctx = canvas.getContext("2d")

    if (!ctx) return

    let width = 0
    let height = 0
    let dpr = 1
    let frame = 0

    const particles = Array.from(
      { length: 150 },
      () => ({
        x: Math.random(),
        y: Math.random(),
        radius:
          0.35 +
          Math.random() * 1.8,
        speed:
          0.00008 +
          Math.random() * 0.00032,
        drift:
          0.00015 +
          Math.random() * 0.00025,
        phase:
          Math.random() *
          Math.PI *
          2,
        opacity:
          0.08 +
          Math.random() * 0.4,
        depth:
          0.25 +
          Math.random() * 0.75,
      })
    )

    const iceShards = Array.from(
      { length: 28 },
      () => ({
        x:
          Math.random() *
            1.15 -
          0.075,
        y:
          Math.random() *
            1.15 -
          0.075,
        length:
          40 +
          Math.random() * 180,
        width:
          2 +
          Math.random() * 8,
        rotation:
          Math.random() *
          Math.PI *
          2,
        opacity:
          0.018 +
          Math.random() * 0.055,
        phase:
          Math.random() *
          Math.PI *
          2,
      })
    )

    const frostBranches =
      Array.from(
        { length: 20 },
        () => ({
          side:
            Math.random() > 0.5
              ? "left"
              : "right",
          y:
            Math.random(),
          length:
            50 +
            Math.random() * 160,
          thickness:
            0.5 +
            Math.random() * 1.4,
          opacity:
            0.025 +
            Math.random() * 0.055,
          phase:
            Math.random() *
            Math.PI *
            2,
        })
      )

    const resize = () => {
      const rect =
        canvas.getBoundingClientRect()

      width = rect.width
      height = rect.height

      dpr = Math.min(
        window.devicePixelRatio || 1,
        2
      )

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

    /*
     * Draw a long translucent shard.
     */
    const drawShard = (
      x: number,
      y: number,
      length: number,
      thickness: number,
      rotation: number,
      opacity: number,
      time: number
    ) => {
      ctx.save()

      ctx.translate(x, y)

      ctx.rotate(
        rotation +
          Math.sin(
            time * 0.00008
          ) *
            0.025
      )

      const gradient =
        ctx.createLinearGradient(
          -length / 2,
          0,
          length / 2,
          0
        )

      gradient.addColorStop(
        0,
        "rgba(234,247,251,0)"
      )

      gradient.addColorStop(
        0.25,
        `rgba(210,242,255,${opacity})`
      )

      gradient.addColorStop(
        0.5,
        `rgba(255,255,255,${opacity * 1.8})`
      )

      gradient.addColorStop(
        0.75,
        `rgba(127,198,230,${opacity})`
      )

      gradient.addColorStop(
        1,
        "rgba(234,247,251,0)"
      )

      ctx.fillStyle = gradient

      ctx.beginPath()

      ctx.moveTo(
        -length / 2,
        0
      )

      ctx.lineTo(
        -length * 0.1,
        -thickness
      )

      ctx.lineTo(
        length / 2,
        0
      )

      ctx.lineTo(
        -length * 0.1,
        thickness
      )

      ctx.closePath()

      ctx.fill()

      ctx.restore()
    }

    /*
     * Draw branching frost.
     */
    const drawFrost = (
      x: number,
      y: number,
      length: number,
      direction: number,
      opacity: number
    ) => {
      ctx.save()

      ctx.translate(x, y)

      ctx.strokeStyle =
        `rgba(220,246,255,${opacity})`

      ctx.lineWidth = 0.7

      ctx.lineCap = "round"

      ctx.beginPath()

      ctx.moveTo(0, 0)

      ctx.lineTo(
        direction * length,
        -length * 0.18
      )

      ctx.stroke()

      for (
        let i = 0;
        i < 5;
        i++
      ) {
        const progress =
          (i + 1) / 6

        const branchX =
          direction *
          length *
          progress

        const branchY =
          -length *
          0.18 *
          progress

        const branchSize =
          length *
          0.12 *
          (1 - progress * 0.5)

        ctx.beginPath()

        ctx.moveTo(
          branchX,
          branchY
        )

        ctx.lineTo(
          branchX -
            direction *
              branchSize,
          branchY -
            branchSize
        )

        ctx.moveTo(
          branchX,
          branchY
        )

        ctx.lineTo(
          branchX -
            direction *
              branchSize,
          branchY +
            branchSize
        )

        ctx.stroke()
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
       * =====================================================
       * 1. DEEP ICE ATMOSPHERE
       * =====================================================
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
        "rgba(225,248,255,0.13)"
      )

      atmosphere.addColorStop(
        0.18,
        "rgba(127,198,230,0.075)"
      )

      atmosphere.addColorStop(
        0.42,
        "rgba(46,124,192,0.035)"
      )

      atmosphere.addColorStop(
        0.72,
        "rgba(18,58,107,0.08)"
      )

      atmosphere.addColorStop(
        1,
        "rgba(1,14,28,0.32)"
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
       * =====================================================
       * 2. MOVING ICE LIGHT
       *
       * Large extremely slow gradients create the feeling
       * of light refracting through thick ice.
       * =====================================================
       */

      const light1X =
        width *
        (0.15 +
          Math.sin(
            time * 0.000045
          ) *
            0.16)

      const light1Y =
        height *
        (0.25 +
          Math.cos(
            time * 0.000035
          ) *
            0.12)

      const light1 =
        ctx.createRadialGradient(
          light1X,
          light1Y,
          0,
          light1X,
          light1Y,
          width * 0.7
        )

      light1.addColorStop(
        0,
        "rgba(234,247,251,0.16)"
      )

      light1.addColorStop(
        0.25,
        "rgba(127,198,230,0.08)"
      )

      light1.addColorStop(
        0.7,
        "rgba(46,124,192,0.025)"
      )

      light1.addColorStop(
        1,
        "rgba(18,58,107,0)"
      )

      ctx.fillStyle = light1

      ctx.fillRect(
        0,
        0,
        width,
        height
      )

      const light2X =
        width *
        (0.78 +
          Math.cos(
            time * 0.000035
          ) *
            0.18)

      const light2Y =
        height *
        (0.72 +
          Math.sin(
            time * 0.00004
          ) *
            0.15)

      const light2 =
        ctx.createRadialGradient(
          light2X,
          light2Y,
          0,
          light2X,
          light2Y,
          width * 0.6
        )

      light2.addColorStop(
        0,
        "rgba(127,198,230,0.075)"
      )

      light2.addColorStop(
        0.5,
        "rgba(46,124,192,0.025)"
      )

      light2.addColorStop(
        1,
        "rgba(18,58,107,0)"
      )

      ctx.fillStyle = light2

      ctx.fillRect(
        0,
        0,
        width,
        height
      )

      /*
       * =====================================================
       * 3. HUGE ICE SHARDS
       *
       * Very transparent.
       *
       * They create the impression that the camera is
       * looking through fractured frozen glass.
       * =====================================================
       */

      for (const shard of iceShards) {
        const pulse =
          0.7 +
          Math.sin(
            time * 0.00012 +
              shard.phase
          ) *
            0.3

        drawShard(
          shard.x * width,
          shard.y * height,
          shard.length,
          shard.width,
          shard.rotation,
          shard.opacity *
            pulse,
          time
        )
      }

      /*
       * =====================================================
       * 4. FLOATING ICE
       * =====================================================
       */

      for (const particle of particles) {
        const y =
          (particle.y +
            time *
              particle.speed *
              particle.depth) %
          1.08

        const drift =
          Math.sin(
            time *
              particle.drift +
              particle.phase
          ) *
          0.045

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
          0.7 +
          Math.sin(
            time * 0.00035 +
              particle.phase
          ) *
            0.3

        const alpha =
          particle.opacity *
          pulse

        ctx.beginPath()

        ctx.arc(
          x * width,
          y * height,
          particle.radius *
            particle.depth,
          0,
          Math.PI * 2
        )

        ctx.fillStyle =
          `rgba(235,250,255,${alpha})`

        ctx.fill()

        /*
         * Occasional tiny glow around
         * larger particles.
         */

        if (
          particle.radius >
          1.5
        ) {
          ctx.beginPath()

          ctx.arc(
            x * width,
            y * height,
            particle.radius * 3,
            0,
            Math.PI * 2
          )

          ctx.fillStyle =
            `rgba(127,198,230,${alpha * 0.12})`

          ctx.fill()
        }
      }

      /*
       * =====================================================
       * 5. FROST CRAWLING IN FROM EDGES
       * =====================================================
       */

      for (
        const frost of frostBranches
      ) {
        const pulse =
          0.65 +
          Math.sin(
            time * 0.0001 +
              frost.phase
          ) *
            0.35

        const x =
          frost.side === "left"
            ? 0
            : width

        drawFrost(
          x,
          frost.y * height,
          frost.length,
          frost.side ===
            "left"
            ? 1
            : -1,
          frost.opacity *
            pulse
        )
      }

      /*
       * =====================================================
       * 6. FROZEN VIGNETTE
       *
       * Dark corners make the centre feel colder and deeper.
       * =====================================================
       */

      const vignette =
        ctx.createRadialGradient(
          width / 2,
          height / 2,
          Math.min(
            width,
            height
          ) *
            0.18,
          width / 2,
          height / 2,
          Math.max(
            width,
            height
          ) *
            0.78
        )

      vignette.addColorStop(
        0,
        "rgba(0,0,0,0)"
      )

      vignette.addColorStop(
        0.55,
        "rgba(2,16,31,0.025)"
      )

      vignette.addColorStop(
        1,
        "rgba(0,8,18,0.38)"
      )

      ctx.fillStyle = vignette

      ctx.fillRect(
        0,
        0,
        width,
        height
      )

      frame =
        window.requestAnimationFrame(
          render
        )
    }

    resize()

    window.addEventListener(
      "resize",
      resize
    )

    frame =
      window.requestAnimationFrame(
        render
      )

    return () => {
      window.removeEventListener(
        "resize",
        resize
      )

      window.cancelAnimationFrame(
        frame
      )
    }
  }, [])

  return (
    <div
      className={`relative overflow-hidden ${
        className ?? ""
      }`}
    >
      {/* =====================================================
          ORIGINAL REDSHIFT
         ===================================================== */}

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

      {/* =====================================================
          ICE AGE OPTICAL LAYER
         ===================================================== */}

      <canvas
        ref={canvasRef}
        className="pointer-events-none absolute inset-0 h-full w-full"
        aria-hidden="true"
      />

      {/* =====================================================
          FROZEN GLASS
         ===================================================== */}

      <div
        className="pointer-events-none absolute inset-0"
        aria-hidden="true"
        style={{
          background: `
            linear-gradient(
              120deg,
              rgba(234,247,251,0.045),
              rgba(127,198,230,0.015) 35%,
              rgba(18,58,107,0.055) 70%,
              rgba(0,8,18,0.18)
            )
          `,
          mixBlendMode: "screen",
        }}
      />

      {/* =====================================================
          VERY FINE FROST FILM
         ===================================================== */}

      <div
        className="pointer-events-none absolute inset-0"
        aria-hidden="true"
        style={{
          opacity: 0.22,
          backgroundImage: `
            radial-gradient(
              circle at 15% 20%,
              rgba(255,255,255,0.12) 0 1px,
              transparent 2px
            ),
            radial-gradient(
              circle at 72% 38%,
              rgba(210,242,255,0.09) 0 1px,
              transparent 2px
            ),
            radial-gradient(
              circle at 42% 78%,
              rgba(234,247,251,0.08) 0 1px,
              transparent 2px
            )
          `,
          backgroundSize:
            "97px 113px, 131px 149px, 173px 157px",
          mixBlendMode: "screen",
        }}
      />
    </div>
  )
}