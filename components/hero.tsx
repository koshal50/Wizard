"use client"

import {
  useEffect,
  useRef,
  useState,
} from "react"

import {
  X,
} from "lucide-react"

import {
  motion,
  AnimatePresence,
} from "framer-motion"

import {
  SafeMeshGradient,
} from "@/components/ui/cinematic-landing-hero"

import {
  AsciiArt,
  AsciiArtHandle,
} from "@/components/ui/sss"

import {
  createClient,
} from "@supabase/supabase-js"

const supabase =
  createClient(
    process.env
      .NEXT_PUBLIC_SUPABASE_URL!,
    process.env
      .NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
      process.env
        .NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  )

export default function Hero() {
  const asciiRef =
    useRef<AsciiArtHandle>(null)

  const scrollFrame =
    useRef<number | null>(null)

  const [isExpanded, setIsExpanded] =
    useState(false)

  const [isSubmitting, setIsSubmitting] =
    useState(false)

  const [
    submissionStatus,
    setSubmissionStatus,
  ] = useState<
    "idle" |
    "success" |
    "error"
  >("idle")

  /*
   * --------------------------------------------------
   * CINEMATIC BACKGROUND
   * --------------------------------------------------
   *
   * This is deliberately not React state.
   *
   * Scrolling only talks directly to
   * AsciiArt through its imperative ref.
   */

  useEffect(() => {
    const updateBackground =
      () => {
        scrollFrame.current =
          null

        const scrollY =
          window.scrollY

        const viewportHeight =
          window.innerHeight

        /*
         * Give the background enough
         * vertical distance to tell its
         * story slowly.
         */
        const cinematicDistance =
          viewportHeight *
          1.75

        const progress =
          Math.min(
            1,
            Math.max(
              0,
              scrollY /
                cinematicDistance
            )
          )

        asciiRef.current?.setProgress(
          progress
        )
      }

    const handleScroll =
      () => {
        /*
         * Never run more than one
         * scroll calculation per frame.
         */
        if (
          scrollFrame.current !==
          null
        ) {
          return
        }

        scrollFrame.current =
          window.requestAnimationFrame(
            updateBackground
          )
      }

    window.addEventListener(
      "scroll",
      handleScroll,
      {
        passive: true,
      }
    )

    /*
     * Establish initial position.
     */
    updateBackground()

    return () => {
      window.removeEventListener(
        "scroll",
        handleScroll
      )

      if (
        scrollFrame.current !==
        null
      ) {
        window.cancelAnimationFrame(
          scrollFrame.current
        )

        scrollFrame.current =
          null
      }
    }
  }, [])

  /*
   * --------------------------------------------------
   * CONTACT FORM
   * --------------------------------------------------
   */

  const handleExpand =
    () => {
      setIsExpanded(true)
    }

  const handleClose =
    () => {
      setIsExpanded(false)
      setSubmissionStatus(
        "idle"
      )
    }

  const handleSubmit =
    async (
      event: React.FormEvent<HTMLFormElement>
    ) => {
      event.preventDefault()

      setIsSubmitting(true)
      setSubmissionStatus(
        "idle"
      )

      const form =
        event.currentTarget

      if (
        !form.reportValidity()
      ) {
        setIsSubmitting(false)
        return
      }

      const formData =
        new FormData(form)

      const {
        error,
      } =
        await supabase
          .from(
            "wizard_contact_submissions"
          )
          .insert({
            name: String(
              formData.get(
                "name"
              ) ?? ""
            ).trim(),

            email: String(
              formData.get(
                "email"
              ) ?? ""
            ).trim(),

            website:
              String(
                formData.get(
                  "website"
                ) ?? ""
              ).trim() ||
              null,

            role:
              String(
                formData.get(
                  "role"
                ) ?? ""
              ).trim() ||
              null,

            message:
              String(
                formData.get(
                  "message"
                ) ?? ""
              ).trim() ||
              null,
          })

      setIsSubmitting(false)

      if (error) {
        setSubmissionStatus(
          "error"
        )

        return
      }

      form.reset()

      setSubmissionStatus(
        "success"
      )

      window.setTimeout(
        () => {
          setIsExpanded(false)

          setSubmissionStatus(
            "idle"
          )
        },
        3000
      )
    }

  /*
   * Prevent background scrolling while
   * the contact experience is open.
   */
  useEffect(() => {
    if (isExpanded) {
      document.body.style.overflow =
        "hidden"
    } else {
      document.body.style.overflow =
        ""
    }

    return () => {
      document.body.style.overflow =
        ""
    }
  }, [isExpanded])

  return (
    <>
      {/* ==================================================
          HERO
          ================================================== */}

      <section
        className="
          relative
          flex
          min-h-screen
          flex-col
          items-center
          justify-center
          overflow-hidden
          px-4
          py-12
          sm:px-6
          sm:py-20
        "
      >
        {/* ==================================================
            CINEMATIC WORLD

            This layer owns the video.

            It does not transform the text.
            It does not transform the CTA.
            It does not participate in their layout.
            ================================================== */}

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
            ref={asciiRef}
            className="
              h-full
              w-full
            "
          />

          <div
            className="
              pointer-events-none
              absolute
              inset-0
              bg-black/[0.035]
            "
          />
        </div>

        {/* ==================================================
            HERO CONTENT
            ================================================== */}

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

          {/* ==================================================
              CTA
              ================================================== */}

          <AnimatePresence
            initial={false}
          >
            {!isExpanded && (
              <motion.div
                className="
                  relative
                  inline-block
                "
              >
                <motion.div
                  layout
                  layoutId="cta-card"
                  style={{
                    borderRadius:
                      "100px",
                  }}
                  className="
                    absolute
                    inset-0
                    border
                    border-[#7FC6E6]/25
                    bg-[#123A6B]
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
                  exit={{
                    opacity: 0,
                    scale: 0.8,
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
      </section>

      {/* ==================================================
          CONTACT MODAL
          ================================================== */}

      <AnimatePresence
        initial={false}
      >
        {isExpanded && (
          <div
            className="
              fixed
              inset-0
              z-50
              flex
              items-center
              justify-center
              p-3
              sm:p-4
            "
          >
            <motion.div
              layout
              layoutId="cta-card"
              style={{
                borderRadius:
                  "24px",
              }}
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
              {/* ==================================================
                  OCEANIC CONTACT BACKGROUND
                  ================================================== */}

              <div
                className="
                  pointer-events-none
                  absolute
                  inset-0
                  z-0
                  overflow-hidden
                "
              >
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
                  className="
                    absolute
                    inset-0
                    h-full
                    w-full
                  "
                />

                <div
                  className="
                    absolute
                    inset-0
                  "
                  style={{
                    background:
                      "linear-gradient(180deg, rgba(18,58,107,0.08) 0%, rgba(18,58,107,0.32) 100%)",
                  }}
                />
              </div>

              {/* ==================================================
                  MODAL CONTENT
                  ================================================== */}

              <div
                className="
                  relative
                  z-10
                  h-full
                  w-full
                  overflow-y-auto
                  overscroll-contain
                  scrollbar-hide
                "
              >
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
                  {/* ==================================================
                      LEFT
                      ================================================== */}

                  <div
                    className="
                      flex
                      w-full
                      flex-1
                      flex-col
                      justify-center
                      space-y-3
                    "
                  >
                    <h2
                      className="
                        text-3xl
                        font-medium
                        leading-none
                        tracking-[-0.03em]
                        text-[#EAF7FB]
                        sm:text-4xl
                        lg:text-5xl
                      "
                    >
                      Talk to the Wizard team
                    </h2>

                    <p
                      className="
                        pt-4
                        text-base
                        leading-[150%]
                        text-[#EAF7FB]/90
                        sm:text-lg
                      "
                    >
                      Whether you're a
                      developer building
                      with AI or a business
                      exploring reliable AI
                      powered software
                      development, we'd love
                      to hear from you.
                    </p>

                    <p
                      className="
                        text-base
                        leading-[150%]
                        text-[#EAF7FB]/90
                        sm:text-lg
                      "
                    >
                      See how Wizard can
                      help you understand,
                      verify, and improve
                      your software with
                      evidence you can trust.
                    </p>

                    <div
                      className="
                        mt-4
                        border-t
                        border-[#EAF7FB]/20
                        pt-6
                        sm:mt-6
                        sm:pt-8
                      "
                    >
                      <p
                        className="
                          mb-3
                          font-mono
                          text-[10px]
                          uppercase
                          tracking-[0.5px]
                          text-[#EAF7FB]/65
                        "
                      >
                        Built with Wizard
                      </p>

                      <p
                        className="
                          text-lg
                          leading-[150%]
                          text-[#EAF7FB]
                          sm:text-xl
                          lg:text-2xl
                        "
                      >
                        “Wizard gives our
                        team confidence that
                        what AI builds
                        actually works.”
                      </p>
                    </div>
                  </div>

                  {/* ==================================================
                      FORM
                      ================================================== */}

                  <div
                    className="
                      w-full
                      flex-1
                    "
                  >
                    <form
                      onSubmit={
                        handleSubmit
                      }
                      className="
                        space-y-4
                        sm:space-y-5
                      "
                    >
                      <div>
                        <label
                          htmlFor="name"
                          className="
                            mb-2
                            block
                            font-mono
                            text-[10px]
                            uppercase
                            tracking-[0.5px]
                            text-[#EAF7FB]
                          "
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

                      <div>
                        <label
                          htmlFor="email"
                          className="
                            mb-2
                            block
                            font-mono
                            text-[10px]
                            uppercase
                            tracking-[0.5px]
                            text-[#EAF7FB]
                          "
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

                      <div
                        className="
                          flex
                          flex-col
                          gap-4
                          sm:flex-row
                        "
                      >
                        <div className="flex-1">
                          <label
                            htmlFor="website"
                            className="
                              mb-2
                              block
                              font-mono
                              text-[10px]
                              uppercase
                              tracking-[0.5px]
                              text-[#EAF7FB]
                            "
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

                        <div
                          className="
                            w-full
                            sm:w-40
                          "
                        >
                          <label
                            htmlFor="role"
                            className="
                              mb-2
                              block
                              font-mono
                              text-[10px]
                              uppercase
                              tracking-[0.5px]
                              text-[#EAF7FB]
                            "
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

                      <div>
                        <label
                          htmlFor="message"
                          className="
                            mb-2
                            block
                            font-mono
                            text-[10px]
                            uppercase
                            tracking-[0.5px]
                            text-[#EAF7FB]
                          "
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
                            className="
                              text-sm
                              text-[#EAF7FB]
                            "
                          >
                            Something went wrong.
                            Please try again.
                          </motion.p>
                        )}
                      </AnimatePresence>

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
                              className="
                                h-6
                                w-7
                              "
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