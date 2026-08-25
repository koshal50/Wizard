"use client"

import { motion, useMotionValue, useSpring } from "motion/react"
import { useEffect } from "react"

export function SmoothCursor() {
  const x = useMotionValue(-100)
  const y = useMotionValue(-100)
  const sx = useSpring(x, { damping: 38, stiffness: 420, mass: 0.7 })
  const sy = useSpring(y, { damping: 38, stiffness: 420, mass: 0.7 })
  useEffect(() => {
    if (window.matchMedia("(pointer: coarse), (prefers-reduced-motion: reduce)").matches) return
    const move = (event: MouseEvent) => { x.set(event.clientX); y.set(event.clientY) }
    window.addEventListener("mousemove", move, { passive: true })
    document.body.style.cursor = "none"
    return () => { window.removeEventListener("mousemove", move); document.body.style.cursor = "" }
  }, [x, y])
  return <motion.div aria-hidden="true" className="pointer-events-none fixed z-[100] hidden md:block" style={{ x: sx, y: sy, translateX: "-7px", translateY: "-5px", willChange: "transform" }}><svg width="22" height="25" viewBox="0 0 22 25" fill="none"><path d="M18.8 18.4 12.1 3.2c-.5-1.2-2.2-1.2-2.7 0L2.4 18.4c-.7 1.6.9 3.1 2.5 2.4l5.9-2.2c.2-.1.5-.1.7 0l5.8 2.2c1.6.7 2.3-.9 1.5-2.4Z" fill="#111827" stroke="white" strokeWidth="1.4"/></svg></motion.div>
}
