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

export default function Hero() {
  const heroRef =
    useRef<HTMLElement>(null)

  const asciiRef =
    useRef<AsciiArtHandle>(null)

  const scrollFrame =
    useRef<number | null>(null)

  const cinematicStart =
    useRef(0)

  const cinematicDistance =
    useRef(1)

  const cinematicVisible =
    useRef(true)

  const [isExpanded, setIsExpanded] =
    useState(false)

  const [showContactNotice, setShowContactNotice] = useState(false)

  /*
   * --------------------------------------------------
   * CINEMATIC BACKGROUND
   * --------------------------------------------------
   *
   * The video is controlled entirely outside React.
   *
   * React does not receive scroll progress.
   *
   * Scroll
   * ↓
   * requestAnimationFrame
   * ↓
   * calculate local cinematic progress
   * ↓
   * AsciiArt.setProgress()
   *
   * No React render happens during this process.
   */

  useEffect(() => {
    const element =
      heroRef.current

    if (!element) {
      return
    }

    const calculateGeometry =
      () => {
        const rect =
          element.getBoundingClientRect()

        cinematicStart.current =
          window.scrollY +
          rect.top

        /*
         * The cinematic deliberately
         * occupies more scroll distance
         * than one viewport.
         *
         * Increase this number if the
         * cinematic should move even slower.
         */
        cinematicDistance.current =
          Math.max(
            window.innerHeight * 1.75,
            1
          )
      }

    const updateBackground =
      () => {
        scrollFrame.current =
          null

        if (
          !cinematicVisible.current
        ) {
          return
        }

        const start =
          cinematicStart.current

        const distance =
          cinematicDistance.current

        const progress =
          Math.min(
            1,
            Math.max(
              0,
              (
                window.scrollY -
                start
              ) /
                distance
            )
          )

        asciiRef.current?.setProgress(
          progress
        )
      }

    const scheduleUpdate =
      () => {
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

    const handleResize =
      () => {
        calculateGeometry()
        scheduleUpdate()
      }

    /*
     * Only run the cinematic
     * controller while this Hero is
     * actually visible.
     */
    const observer =
      new IntersectionObserver(
        entries => {
          const entry =
            entries[0]

          cinematicVisible.current =
            Boolean(
              entry?.isIntersecting
            )

          if (
            cinematicVisible.current
          ) {
            calculateGeometry()
            scheduleUpdate()
          }
        },
        {
          threshold: 0,
          rootMargin:
            "100px 0px 100px 0px",
        }
      )

    observer.observe(element)

    calculateGeometry()

    window.addEventListener(
      "scroll",
      scheduleUpdate,
      {
        passive: true,
      }
    )

    window.addEventListener(
      "resize",
      handleResize,
      {
        passive: true,
      }
    )

    scheduleUpdate()

    return () => {
      observer.disconnect()

      window.removeEventListener(
        "scroll",
        scheduleUpdate
      )

      window.removeEventListener(
        "resize",
        handleResize
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

      setShowContactNotice(false)
    }

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!event.currentTarget.reportValidity()) return
    // Sending is unavailable until a contact service is connected.
    setShowContactNotice(true)
  }

  /*
   * --------------------------------------------------
   * CONTACT MODAL SCROLL LOCK
   * --------------------------------------------------
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
        ref={heroRef}
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

            The video is completely independent
            from the text and CTA.

            Nothing inside the content below
            transforms because of video progress.
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
                  flex
                  flex-col
                  items-stretch
                  gap-3
                  sm:flex-row
                  sm:items-center
                "
              >
                <div className="relative">
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
                    rounded-full
                    focus-visible:outline-2
                    focus-visible:outline-offset-4
                    focus-visible:outline-[#7FC6E6]
                    sm:px-8
                    sm:text-xl
                  "
                >
                  Talk to the Wizard team
                </motion.button>
                </div>
                <a
                  href="/login.html"
                  className="inline-flex h-15 items-center justify-center rounded-full border border-[#7FC6E6]/25 bg-[#123A6B] px-6 py-3 text-lg font-normal tracking-[-0.01em] text-[#EAF7FB] shadow-[0_8px_30px_rgba(18,58,107,0.35)] transition-colors hover:bg-[#1b4a8c] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#7FC6E6] sm:px-8 sm:text-xl"
                >
                  Login
                </a>
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
                        Built to make
                        AI-assisted work
                        easier to inspect,
                        execute, and verify.
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

                      <label className="flex items-start gap-3 text-xs leading-5 text-[#B7CEDD]">
                        <input type="checkbox" name="consent" required className="mt-1 h-4 w-4 rounded border-[#7FC6E6]/30 bg-[#001F63] accent-[#EAF7FB] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7FC6E6]" />
                        <span>I agree that Wizard may use the information I submit to respond to my request. I have read the <a href="/privacy" className="text-[#EAF7FB] underline underline-offset-4">Privacy Policy</a>.</span>
                      </label>

                      <AnimatePresence
                        mode="wait"
                        initial={false}
                      >
                        {showContactNotice && (
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
                            Contact form sending is currently unavailable. Your message has not been sent.
                          </motion.p>
                        )}
                      </AnimatePresence>

                      <motion.button
                        type="submit"
                        animate={{ backgroundColor: "#EAF7FB" }}
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
                        Submit
                      </motion.button>
                    </form>
                  </div>
                </motion.div>
              </div>

              {/* Close */}

              <motion.button
                onClick={
                  handleClose
                }
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
