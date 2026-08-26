"use client"

import { useState, useEffect } from "react"
import { X } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import { SafeMeshGradient } from "@/components/ui/cinematic-landing-hero"
import { AsciiArt } from "@/components/ui/sss"
import { createClient } from "@supabase/supabase-js"

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
)

export default function Hero() {
  const [isExpanded, setIsExpanded] =
    useState(false)

  const [isSubmitting, setIsSubmitting] =
    useState(false)

  const [submissionStatus, setSubmissionStatus] =
    useState<"idle" | "success" | "error">("idle")

  /*
   * Background cinematic progress.
   *
   * The hero background is now controlled
   * by scroll instead of autoplay.
   *
   * This page is intentionally independent
   * from the MacBook cinematic section.
   */
  const [backgroundProgress, setBackgroundProgress] =
    useState(0)

  useEffect(() => {
    let frame = 0

    const updateProgress = () => {
      if (frame) {
        return
      }

      frame = window.requestAnimationFrame(() => {
        frame = 0

        /*
         * The hero occupies the first viewport.
         *
         * We use a slightly longer scroll window
         * so the background does not race through
         * its 10 second cinematic sequence.
         */
        const scrollY =
          window.scrollY

        const viewportHeight =
          window.innerHeight

        const cinematicDistance =
          viewportHeight * 1.35

        const progress =
          Math.min(
            1,
            Math.max(
              0,
              scrollY /
                cinematicDistance
            )
          )

        setBackgroundProgress(
          progress
        )
      })
    }

    window.addEventListener(
      "scroll",
      updateProgress,
      { passive: true }
    )

    updateProgress()

    return () => {
      window.removeEventListener(
        "scroll",
        updateProgress
      )

      if (frame) {
        window.cancelAnimationFrame(
          frame
        )
      }
    }
  }, [])

  const handleExpand = () => {
    setIsExpanded(true)
  }

  const handleClose = () => {
    setIsExpanded(false)
    setSubmissionStatus("idle")
  }

  const handleSubmit = async (
    event: React.FormEvent<HTMLFormElement>
  ) => {
    event.preventDefault()

    setIsSubmitting(true)
    setSubmissionStatus("idle")

    const form =
      event.currentTarget

    if (!form.reportValidity()) {
      setIsSubmitting(false)
      return
    }

    const formData =
      new FormData(form)

    const { error } =
      await supabase
        .from(
          "wizard_contact_submissions"
        )
        .insert({
          name: String(
            formData.get("name") ?? ""
          ).trim(),

          email: String(
            formData.get("email") ?? ""
          ).trim(),

          website:
            String(
              formData.get("website") ?? ""
            ).trim() || null,

          role:
            String(
              formData.get("role") ?? ""
            ).trim() || null,

          message:
            String(
              formData.get("message") ?? ""
            ).trim() || null,
        })

    setIsSubmitting(false)

    if (error) {
      setSubmissionStatus("error")
      return
    }

    form.reset()
    setSubmissionStatus("success")

    window.setTimeout(() => {
      setIsExpanded(false)
      setSubmissionStatus("idle")
    }, 3000)
  }

  useEffect(() => {
    if (isExpanded) {
      document.body.style.overflow =
        "hidden"
    } else {
      document.body.style.overflow =
        "unset"
    }

    return () => {
      document.body.style.overflow =
        "unset"
    }
  }, [isExpanded])

  return (
    <>
      <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-12 sm:px-6 sm:py-20">

        {/* 
         * Cinematic background.
         *
         * This is no longer an autoplaying loop.
         * AsciiArt receives scroll progress and
         * scrubs through wizard-world.mp4.
         *
         * The background itself owns the cinematic
         * movement. The hero content does not inherit
         * any transform from it.
         */}
        <div
          className="
            pointer-events-none
            fixed
            inset-0
            z-0
            overflow-hidden
            bg-black
          "
        >
          <AsciiArt
            progress={
              backgroundProgress
            }
            className="
              h-full
              w-full
            "
          />

          {/* 
           * Very subtle readability layer.
           *
           * This does not animate independently.
           * It simply keeps the typography readable
           * over brighter frames of the video.
           */}
          <div
            className="
              pointer-events-none
              absolute
              inset-0
              bg-black/[0.04]
            "
          />
        </div>

        {/* Hero content */}
        <div
          className="
            relative
            z-10
            isolate
            flex
            flex-col
            items-center
            gap-4
            px-5
            py-6
            text-center
            sm:gap-6
          "
        >
          <h1
            className="
              max-w-2xl
              text-balance
              text-4xl
              font-normal
              leading-[90%]
              tracking-[-0.03em]
              text-black
              mix-blend-exclusion
              sm:text-5xl
              md:text-6xl
              lg:text-7xl
            "
          >
            Build with AI.
            Verify with Wizard.
          </h1>

          <p
            className="
              max-w-2xl
              px-4
              text-base
              leading-[160%]
              text-black
              sm:text-lg
              md:text-xl
            "
          >
            Let Wizard investigate,
            execute, and verify your
            software automatically so
            you can build faster with
            confidence.
          </p>

          {/* CTA */}
          <AnimatePresence
            initial={false}
          >
            {!isExpanded && (
              <motion.div
                className="relative inline-block"
              >
                <motion.div
                  style={{
                    borderRadius:
                      "100px",
                  }}
                  layout
                  layoutId="cta-card"
                  className="
                    absolute
                    inset-0
                    bg-[#123A6B]
                    border
                    border-[#7FC6E6]/25
                    shadow-[0_8px_30px_rgba(18,58,107,0.35)]
                    transform-gpu
                    will-change-transform
                  "
                />

                <motion.button
                  initial={{
                    opacity: 0,
                    scale: 0.8,
                  }}
                  animate={{
                    opacity: 1,
                    scale: 1,
                  }}
                  transition={{
                    delay: 0.2,
                    duration: 0.45,
                    ease: [
                      0.22,
                      1,
                      0.36,
                      1,
                    ],
                  }}
                  exit={{
                    opacity: 0,
                    scale: 0.8,
                  }}
                  layout={false}
                  onClick={
                    handleExpand
                  }
                  className="
                    relative
                    h-15
                    px-6
                    py-3
                    text-lg
                    font-normal
                    tracking-[-0.01em]
                    text-[#EAF7FB]
                    sm:px-8
                    sm:text-xl
                  "
                >
                  Talk to the Wizard team
                </motion.button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Expanded contact experience */}
      <AnimatePresence
        initial={false}
      >
        {isExpanded && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4">
            <motion.div
              layoutId="cta-card"
              style={{
                borderRadius: "24px",
              }}
              layout
              className="
                relative
                flex
                h-full
                w-full
                overflow-hidden
                border
                border-[#7FC6E6]/20
                bg-[#123A6B]
                shadow-[0_24px_80px_rgba(0,0,0,0.35)]
                transform-gpu
                will-change-transform
              "
            >
              {/* Oceanic background */}
              <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
                <SafeMeshGradient
                  speed={1}
                  colors={[
                    "#EAF7FB",
                    "#7FC6E6",
                    "#2E7CC0",
                    "#123A6B",
                  ]}
                  distortion={0.8}
                  swirl={0.1}
                  grainMixer={0}
                  grainOverlay={0}
                  className="absolute inset-0 h-full w-full"
                  style={{
                    height: "100%",
                    width: "100%",
                  }}
                />

                <div
                  className="absolute inset-0"
                  style={{
                    background:
                      "linear-gradient(180deg, rgba(18,58,107,0.08) 0%, rgba(18,58,107,0.32) 100%)",
                  }}
                />
              </div>

              {/* Content */}
              <div className="relative z-10 h-full w-full overflow-y-auto overscroll-contain scrollbar-hide">
                <motion.div
                  initial={{
                    opacity: 0,
                    y: 10,
                  }}
                  animate={{
                    opacity: 1,
                    y: 0,
                  }}
                  transition={{
                    duration: 0.45,
                    ease: [
                      0.22,
                      1,
                      0.36,
                      1,
                    ],
                  }}
                  className="
                    mx-auto
                    flex
                    min-h-full
                    w-full
                    max-w-[1100px]
                    flex-col
                    items-start
                    gap-8
                    px-6
                    py-10
                    pb-24
                    sm:p-10
                    lg:flex-row
                    lg:items-center
                    lg:gap-16
                    lg:p-16
                  "
                >
                  {/* Left side */}
                  <div className="flex w-full flex-1 flex-col justify-center space-y-3">
                    <h2 className="text-3xl font-medium leading-none tracking-[-0.03em] text-[#EAF7FB] sm:text-4xl lg:text-5xl">
                      Talk to the Wizard team
                    </h2>

                    <p className="pt-4 text-base leading-[150%] text-[#EAF7FB]/90 sm:text-lg">
                      Whether you're a
                      developer building
                      with AI or a business
                      exploring reliable AI
                      powered software
                      development, we'd love
                      to hear from you.
                    </p>

                    <p className="text-base leading-[150%] text-[#EAF7FB]/90 sm:text-lg">
                      See how Wizard can
                      help you understand,
                      verify, and improve
                      your software with
                      evidence you can trust.
                    </p>

                    <div className="mt-4 border-t border-[#EAF7FB]/20 pt-6 sm:mt-6 sm:pt-8">
                      <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.5px] text-[#EAF7FB]/65">
                        Built with Wizard
                      </p>

                      <p className="text-lg leading-[150%] text-[#EAF7FB] sm:text-xl lg:text-2xl">
                        “Wizard gives our
                        team confidence that
                        what AI builds
                        actually works.”
                      </p>
                    </div>
                  </div>

                  {/* Form */}
                  <div className="w-full flex-1">
                    <form
                      onSubmit={
                        handleSubmit
                      }
                      className="space-y-4 sm:space-y-5"
                    >
                      {/* Name */}
                      <div>
                        <label
                          htmlFor="name"
                          className="mb-2 block font-mono text-[10px] font-normal uppercase tracking-[0.5px] text-[#EAF7FB]"
                        >
                          FULL NAME *
                        </label>

                        <input
                          type="text"
                          id="name"
                          name="name"
                          required
                          className="
                            h-10
                            w-full
                            rounded-lg
                            border
                            border-[#7FC6E6]/10
                            bg-[#001F63]/70
                            px-4
                            py-2.5
                            text-sm
                            text-[#EAF7FB]
                            placeholder:text-[#EAF7FB]/45
                            outline-none
                            transition-all
                            focus:border-[#7FC6E6]/40
                            focus:ring-2
                            focus:ring-[#7FC6E6]/15
                          "
                        />
                      </div>

                      {/* Email */}
                      <div>
                        <label
                          htmlFor="email"
                          className="mb-2 block font-mono text-[10px] font-normal uppercase tracking-[0.5px] text-[#EAF7FB]"
                        >
                          WORK EMAIL *
                        </label>

                        <input
                          type="email"
                          id="email"
                          name="email"
                          required
                          className="
                            h-10
                            w-full
                            rounded-lg
                            border
                            border-[#7FC6E6]/10
                            bg-[#001F63]/70
                            px-4
                            py-2.5
                            text-sm
                            text-[#EAF7FB]
                            placeholder:text-[#EAF7FB]/45
                            outline-none
                            transition-all
                            focus:border-[#7FC6E6]/40
                            focus:ring-2
                            focus:ring-[#7FC6E6]/15
                          "
                        />
                      </div>

                      {/* Website + Role */}
                      <div className="flex flex-col gap-4 sm:flex-row">
                        <div className="flex-1">
                          <label
                            htmlFor="website"
                            className="mb-2 block font-mono text-[10px] font-normal uppercase tracking-[0.5px] text-[#EAF7FB]"
                          >
                            COMPANY / PROJECT WEBSITE
                          </label>

                          <input
                            type="url"
                            id="website"
                            name="website"
                            className="
                              h-10
                              w-full
                              rounded-lg
                              border
                              border-[#7FC6E6]/10
                              bg-[#001F63]/70
                              px-4
                              py-2.5
                              text-sm
                              text-[#EAF7FB]
                              placeholder:text-[#EAF7FB]/45
                              outline-none
                              transition-all
                              focus:border-[#7FC6E6]/40
                              focus:ring-2
                              focus:ring-[#7FC6E6]/15
                            "
                          />
                        </div>

                        <div className="w-full sm:w-40">
                          <label
                            htmlFor="role"
                            className="mb-2 block font-mono text-[10px] font-normal uppercase tracking-[0.5px] text-[#EAF7FB]"
                          >
                            YOUR ROLE
                          </label>

                          <select
                            id="role"
                            name="role"
                            defaultValue=""
                            className="
                              h-10
                              w-full
                              cursor-pointer
                              appearance-none
                              rounded-lg
                              border
                              border-[#7FC6E6]/10
                              bg-[#001F63]/70
                              px-4
                              py-2.5
                              text-sm
                              text-[#EAF7FB]
                              outline-none
                              transition-all
                              focus:border-[#7FC6E6]/40
                              focus:ring-2
                              focus:ring-[#7FC6E6]/15
                            "
                          >
                            <option
                              value=""
                              disabled
                            >
                              Select your role
                            </option>

                            <option value="Developer">
                              Developer
                            </option>

                            <option value="Founder">
                              Founder
                            </option>

                            <option value="Engineering Leader">
                              Engineering Leader
                            </option>

                            <option value="Other">
                              Other
                            </option>
                          </select>
                        </div>
                      </div>

                      {/* Message */}
                      <div>
                        <label
                          htmlFor="message"
                          className="mb-2 block font-mono text-[10px] font-normal uppercase tracking-[0.5px] text-[#EAF7FB]"
                        >
                          ANYTHING ELSE?
                        </label>

                        <textarea
                          id="message"
                          name="message"
                          rows={3}
                          className="
                            w-full
                            resize-none
                            rounded-lg
                            border
                            border-[#7FC6E6]/10
                            bg-[#001F63]/70
                            px-4
                            py-3
                            text-sm
                            text-[#EAF7FB]
                            placeholder:text-[#EAF7FB]/45
                            outline-none
                            transition-all
                            focus:border-[#7FC6E6]/40
                            focus:ring-2
                            focus:ring-[#7FC6E6]/15
                          "
                        />
                      </div>

                      {/* Error */}
                      <AnimatePresence
                        mode="wait"
                        initial={false}
                      >
                        {submissionStatus ===
                          "error" && (
                          <motion.p
                            key="error"
                            role="alert"
                            initial={{
                              opacity: 0,
                            }}
                            animate={{
                              opacity: 1,
                            }}
                            className="text-sm text-[#EAF7FB]"
                          >
                            Something went wrong.
                            Please try again.
                          </motion.p>
                        )}
                      </AnimatePresence>

                      {/* Submit */}
                      <motion.button
                        type="submit"
                        disabled={
                          isSubmitting ||
                          submissionStatus ===
                            "success"
                        }
                        animate={{
                          backgroundColor:
                            submissionStatus ===
                            "success"
                              ? "#19D66B"
                              : "#EAF7FB",
                        }}
                        transition={{
                          duration: 0.45,
                          ease: [
                            0.22,
                            1,
                            0.36,
                            1,
                          ],
                        }}
                        className="
                          relative
                          flex
                          h-10
                          w-full
                          items-center
                          justify-center
                          overflow-hidden
                          rounded-full
                          px-8
                          py-2.5
                          font-medium
                          tracking-[-0.03em]
                          text-[#123A6B]
                          transition-colors
                          disabled:cursor-default
                        "
                        aria-label={
                          submissionStatus ===
                          "success"
                            ? "Form submitted"
                            : "Submit form"
                        }
                      >
                        <AnimatePresence
                          mode="wait"
                          initial={false}
                        >
                          {submissionStatus ===
                          "success" ? (
                            <motion.svg
                              key="check"
                              viewBox="0 0 28 20"
                              className="h-6 w-7"
                              aria-hidden="true"
                            >
                              <motion.path
                                d="M2 10.5 9.5 18 26 2"
                                fill="none"
                                stroke="#FFFFFF"
                                strokeWidth="3.5"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                initial={{
                                  pathLength: 0,
                                }}
                                animate={{
                                  pathLength: 1,
                                }}
                                transition={{
                                  duration: 0.65,
                                  ease: [
                                    0.65,
                                    0,
                                    0.35,
                                    1,
                                  ],
                                }}
                              />
                            </motion.svg>
                          ) : (
                            <motion.span
                              key="label"
                              initial={{
                                opacity: 0,
                              }}
                              animate={{
                                opacity: 1,
                              }}
                            >
                              {isSubmitting
                                ? "Sending…"
                                : "Submit"}
                            </motion.span>
                          )}
                        </AnimatePresence>
                      </motion.button>
                    </form>
                  </div>
                </motion.div>
              </div>

              {/* Close */}
              <motion.button
                onClick={handleClose}
                className="
                  absolute
                  right-6
                  top-6
                  z-20
                  flex
                  h-10
                  w-10
                  items-center
                  justify-center
                  rounded-full
                  bg-transparent
                  text-[#EAF7FB]
                  transition-colors
                  hover:bg-[#EAF7FB]/10
                "
                aria-label="Close"
              >
                <X className="h-5 w-5" />
              </motion.button>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  )
}