"use client"

import React, {
  FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  Check,
  Globe,
  Lock,
  Maximize2,
  MoreHorizontal,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  Star,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { SmoothCursor } from "@/components/ui/smooth-cursor"

interface Tab {
  id: string
  title: string
  url: string
  isActive: boolean
  isLoading: boolean
}

interface BrowserProps {
  className?: string
  initialUrl?: string
  initialTabs?: Array<{
    id?: string
    title?: string
    url?: string
  }>
  theme?: "light" | "dark" | "system"
  showWindowControls?: boolean
  showBookmarksBar?: boolean
  showStatusBar?: boolean
  enableTabManagement?: boolean
  enableBookmarks?: boolean
  enableHistory?: boolean
  enableDownloads?: boolean
  enableSettings?: boolean
  maxTabs?: number
  onNavigate?: (url: string, tabId: string) => void
  onTabCreate?: (tab: Tab) => void
  onTabClose?: (tabId: string) => void
  onTabSwitch?: (tabId: string) => void
  onBookmarkToggle?: (
    url: string,
    isBookmarked: boolean
  ) => void
  simulateLoading?: boolean
  loadingDuration?: number
}

const DEFAULT_URL =
  "https://wizardagents.vercel.app"

function normalizeUrl(value: string) {
  const trimmed = value.trim()

  if (!trimmed) {
    return "about:blank"
  }

  if (
    trimmed.startsWith("http://") ||
    trimmed.startsWith("https://") ||
    trimmed.startsWith("about:")
  ) {
    return trimmed
  }

  return `https://www.google.com/search?q=${encodeURIComponent(
    trimmed
  )}`
}

function hostname(url: string) {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

function createTabId() {
  return `tab-${Date.now()}-${Math.random()
    .toString(36)
    .slice(2, 8)}`
}

export function Browser({
  className,
  initialUrl = DEFAULT_URL,
  initialTabs,
  theme = "light",
  showWindowControls = false,
  showBookmarksBar = false,
  showStatusBar = false,
  enableTabManagement = true,
  enableBookmarks = true,
  enableHistory = true,
  enableDownloads = false,
  enableSettings = false,
  maxTabs = 8,
  onNavigate,
  onTabCreate,
  onTabClose,
  onTabSwitch,
  onBookmarkToggle,
  simulateLoading = true,
  loadingDuration = 900,
}: BrowserProps) {
  const viewportRef =
    useRef<HTMLDivElement>(null)

  const [tabs, setTabs] = useState<Tab[]>(() => {
    if (initialTabs?.length) {
      return initialTabs.map((tab, index) => ({
        id:
          tab.id ||
          `tab-${Date.now()}-${index}`,
        title:
          tab.title ||
          hostname(tab.url || initialUrl),
        url: tab.url || initialUrl,
        isActive: index === 0,
        isLoading: false,
      }))
    }

    return [
      {
        id: "wizard",
        title: hostname(initialUrl),
        url: initialUrl,
        isActive: true,
        isLoading: false,
      },
    ]
  })

  const activeTab =
    tabs.find((tab) => tab.isActive) ||
    tabs[0]

  const [inputUrl, setInputUrl] =
    useState(activeTab?.url || initialUrl)

  const [canGoBack, setCanGoBack] =
    useState(false)

  const [canGoForward, setCanGoForward] =
    useState(false)

  const [isBookmarked, setIsBookmarked] =
    useState(false)

  const [showBookmarks, setShowBookmarks] =
    useState(false)

  const [showHistory, setShowHistory] =
    useState(false)

  const [showSettings, setShowSettings] =
    useState(false)

  const [isFullscreen, setIsFullscreen] =
    useState(false)

  const [iframeLoaded, setIframeLoaded] =
    useState(false)

  const [agentActivity, setAgentActivity] =
    useState<
      "connecting" | "observing" | "ready"
    >("connecting")

  const isDark =
    theme === "dark" ||
    (theme === "system" &&
      typeof window !== "undefined" &&
      window.matchMedia(
        "(prefers-color-scheme: dark)"
      ).matches)

  useEffect(() => {
    setInputUrl(activeTab?.url || "")
    setIframeLoaded(false)
    setAgentActivity("connecting")
  }, [
    activeTab?.id,
    activeTab?.url,
  ])

  useEffect(() => {
    if (!iframeLoaded) {
      return
    }

    setAgentActivity("observing")

    const id = window.setTimeout(() => {
      setAgentActivity("ready")
    }, 700)

    return () => {
      window.clearTimeout(id)
    }
  }, [iframeLoaded])

  const bookmarks = useMemo(
    () => [
      {
        title: "Wizard",
        url: "https://wizardagents.vercel.app",
      },
      {
        title: "Dashboard",
        url: "https://wizardagents.vercel.app/dashboard",
      },
      {
        title: "Docs",
        url: "https://wizardagents.vercel.app/docs",
      },
    ],
    []
  )

  const navigate = (value: string) => {
    const url = normalizeUrl(value)
    const tabId = activeTab?.id || ""

    setInputUrl(url)
    setIframeLoaded(false)
    setAgentActivity("connecting")

    setCanGoBack(true)
    setCanGoForward(false)

    setTabs((current) =>
      current.map((tab) =>
        tab.isActive
          ? {
              ...tab,
              url,
              title:
                url === "about:blank"
                  ? "New Tab"
                  : hostname(url),
              isLoading: simulateLoading,
            }
          : tab
      )
    )

    onNavigate?.(url, tabId)

    if (simulateLoading) {
      window.setTimeout(() => {
        setTabs((current) =>
          current.map((tab) =>
            tab.isActive
              ? {
                  ...tab,
                  isLoading: false,
                }
              : tab
          )
        )
      }, loadingDuration)
    }
  }

  const submitAddress = (
    event: FormEvent
  ) => {
    event.preventDefault()
    navigate(inputUrl)
  }

  const createTab = () => {
    if (tabs.length >= maxTabs) {
      return
    }

    const newTab: Tab = {
      id: createTabId(),
      title: "New Tab",
      url: "about:blank",
      isActive: true,
      isLoading: false,
    }

    setTabs((current) =>
      current
        .map((tab) => ({
          ...tab,
          isActive: false,
        }))
        .concat(newTab)
    )

    setInputUrl("")
    setIframeLoaded(false)
    setAgentActivity("ready")

    onTabCreate?.(newTab)
  }

  const closeTab = (
    tabId: string
  ) => {
    if (tabs.length === 1) {
      return
    }

    const index = tabs.findIndex(
      (tab) => tab.id === tabId
    )

    const closingActive =
      tabs[index]?.isActive

    const remaining = tabs.filter(
      (tab) => tab.id !== tabId
    )

    if (closingActive) {
      const nextIndex = Math.min(
        index,
        remaining.length - 1
      )

      remaining.forEach((tab) => {
        tab.isActive = false
      })

      remaining[nextIndex].isActive = true

      setInputUrl(
        remaining[nextIndex].url
      )

      setIframeLoaded(false)
      setAgentActivity("connecting")
    }

    setTabs(remaining)
    onTabClose?.(tabId)
  }

  const switchTab = (
    tabId: string
  ) => {
    setTabs((current) =>
      current.map((tab) => ({
        ...tab,
        isActive:
          tab.id === tabId,
      }))
    )

    const selected = tabs.find(
      (tab) => tab.id === tabId
    )

    if (selected) {
      setInputUrl(selected.url)
    }

    setIframeLoaded(false)
    setAgentActivity("connecting")

    onTabSwitch?.(tabId)
  }

  const refresh = () => {
    if (!activeTab) {
      return
    }

    setIframeLoaded(false)
    setAgentActivity("connecting")

    setTabs((current) =>
      current.map((tab) =>
        tab.isActive
          ? {
              ...tab,
              isLoading: true,
            }
          : tab
      )
    )

    window.setTimeout(() => {
      setTabs((current) =>
        current.map((tab) =>
          tab.isActive
            ? {
                ...tab,
                isLoading: false,
              }
            : tab
        )
      )
    }, loadingDuration)
  }

  const goBack = () => {
    if (!canGoBack) {
      return
    }

    setCanGoBack(false)
    setCanGoForward(true)
  }

  const goForward = () => {
    if (!canGoForward) {
      return
    }

    setCanGoForward(false)
    setCanGoBack(true)
  }

  const toggleBookmark = () => {
    const next = !isBookmarked

    setIsBookmarked(next)

    onBookmarkToggle?.(
      activeTab?.url || "",
      next
    )
  }

  const currentUrl =
    activeTab?.url || initialUrl

  const currentHost =
    hostname(currentUrl)

  const isBlank =
    currentUrl === "about:blank" ||
    currentUrl === ""

  return (
    <div
      data-wizard-browser="true"
      data-wizard-browser-url={currentUrl}
      data-wizard-browser-state={
        agentActivity
      }
      className={cn(
        "relative flex h-full w-full flex-col overflow-hidden rounded-xl border shadow-2xl",
        isDark
          ? "border-slate-700 bg-slate-950 text-slate-100"
          : "border-slate-300 bg-slate-100 text-slate-800",
        isFullscreen &&
          "fixed inset-0 z-50 rounded-none",
        className
      )}
    >
      {showWindowControls && (
        <div className="flex h-7 shrink-0 items-center justify-between border-b border-slate-700 bg-slate-800 px-3">
          <div className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
            <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
            <span className="h-2.5 w-2.5 rounded-full bg-green-400" />
          </div>

          <div className="flex items-center gap-1 text-slate-400">
            <button
              onClick={() =>
                setIsFullscreen(
                  (value) => !value
                )
              }
              className="rounded p-1 hover:bg-white/10"
              aria-label="Toggle fullscreen"
            >
              <Maximize2 className="h-3 w-3" />
            </button>

            <button
              className="rounded p-1 hover:bg-white/10"
              aria-label="Close"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}

      {enableTabManagement && (
        <div className="flex h-9 shrink-0 items-end border-b border-slate-300 bg-slate-200 px-2 dark:border-slate-700 dark:bg-slate-800">
          <div className="flex min-w-0 flex-1 items-end gap-1 overflow-hidden">
            {tabs.map((tab) => (
              <div
                key={tab.id}
                onClick={() =>
                  switchTab(tab.id)
                }
                className={cn(
                  "group flex h-8 min-w-0 max-w-[220px] cursor-pointer items-center gap-2 rounded-t-lg border border-b-0 px-3 text-[9px]",
                  tab.isActive
                    ? "border-slate-300 bg-white text-slate-800 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
                    : "border-transparent text-slate-500 hover:bg-white/50"
                )}
              >
                {tab.isLoading ? (
                  <span className="h-2.5 w-2.5 animate-spin rounded-full border border-blue-500 border-t-transparent" />
                ) : (
                  <Globe className="h-2.5 w-2.5 shrink-0" />
                )}

                <span className="truncate">
                  {tab.title}
                </span>

                {tabs.length > 1 && (
                  <button
                    onClick={(event) => {
                      event.stopPropagation()
                      closeTab(tab.id)
                    }}
                    className="rounded p-0.5 opacity-0 hover:bg-slate-200 group-hover:opacity-100 dark:hover:bg-slate-700"
                    aria-label={`Close ${tab.title}`}
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                )}
              </div>
            ))}
          </div>

          <button
            onClick={createTab}
            disabled={
              tabs.length >= maxTabs
            }
            className="mb-1 ml-1 rounded p-1.5 hover:bg-slate-300 disabled:opacity-30 dark:hover:bg-slate-700"
            aria-label="New tab"
          >
            <Plus className="h-3 w-3" />
          </button>
        </div>
      )}

      <div className="flex h-10 shrink-0 items-center gap-1 border-b border-slate-300 bg-slate-100 px-2 dark:border-slate-700 dark:bg-slate-800">
        <button
          onClick={goBack}
          disabled={!canGoBack}
          className="rounded-md p-1.5 hover:bg-slate-200 disabled:opacity-30 dark:hover:bg-slate-700"
          aria-label="Back"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
        </button>

        <button
          onClick={goForward}
          disabled={!canGoForward}
          className="rounded-md p-1.5 hover:bg-slate-200 disabled:opacity-30 dark:hover:bg-slate-700"
          aria-label="Forward"
        >
          <ArrowRight className="h-3.5 w-3.5" />
        </button>

        <button
          onClick={refresh}
          className="rounded-md p-1.5 hover:bg-slate-200 dark:hover:bg-slate-700"
          aria-label="Reload"
        >
          <RotateCcw
            className={cn(
              "h-3.5 w-3.5",
              activeTab?.isLoading &&
                "animate-spin"
            )}
          />
        </button>

        <form
          onSubmit={submitAddress}
          className="ml-1 flex min-w-0 flex-1"
        >
          <div className="flex min-w-0 flex-1 items-center rounded-lg border border-slate-300 bg-white px-2.5 dark:border-slate-600 dark:bg-slate-900">
            {currentUrl.startsWith(
              "https://"
            ) ? (
              <Lock className="mr-2 h-3 w-3 shrink-0 text-emerald-500" />
            ) : (
              <ShieldCheck className="mr-2 h-3 w-3 shrink-0 text-slate-400" />
            )}

            <input
              value={inputUrl}
              onChange={(event) =>
                setInputUrl(
                  event.target.value
                )
              }
              className="min-w-0 flex-1 bg-transparent py-1 text-[9px] outline-none"
              aria-label="Address"
              placeholder="Search or enter address"
            />

            <Search className="ml-2 h-3 w-3 shrink-0 text-slate-400" />
          </div>
        </form>

        {enableBookmarks && (
          <button
            onClick={toggleBookmark}
            className="rounded-md p-1.5 hover:bg-slate-200 dark:hover:bg-slate-700"
            aria-label={
              isBookmarked
                ? "Remove bookmark"
                : "Bookmark page"
            }
          >
            <Star
              className={cn(
                "h-3.5 w-3.5",
                isBookmarked &&
                  "fill-yellow-400 text-yellow-400"
              )}
            />
          </button>
        )}

        <button
          onClick={() =>
            setShowSettings(
              (value) => !value
            )
          }
          className="rounded-md p-1.5 hover:bg-slate-200 dark:hover:bg-slate-700"
          aria-label="More options"
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </button>
      </div>

      {showBookmarksBar &&
        enableBookmarks && (
          <div className="flex h-7 shrink-0 items-center gap-3 overflow-hidden border-b border-slate-200 bg-white px-3 dark:border-slate-700 dark:bg-slate-900">
            <Bookmark className="h-3 w-3 text-slate-400" />

            {bookmarks.map(
              (bookmark) => (
                <button
                  key={bookmark.url}
                  onClick={() =>
                    navigate(
                      bookmark.url
                    )
                  }
                  className="whitespace-nowrap text-[8px] text-slate-500 hover:text-blue-600"
                >
                  {bookmark.title}
                </button>
              )
            )}
          </div>
        )}

      {showBookmarks && (
        <div className="absolute left-2 top-16 z-50 w-48 rounded-lg border border-slate-200 bg-white p-2 text-slate-800 shadow-xl">
          <p className="px-2 py-1 text-[9px] font-semibold">
            Bookmarks
          </p>

          {bookmarks.map(
            (bookmark) => (
              <button
                key={bookmark.url}
                onClick={() => {
                  navigate(
                    bookmark.url
                  )
                  setShowBookmarks(false)
                }}
                className="block w-full rounded px-2 py-1.5 text-left text-[8px] hover:bg-slate-100"
              >
                {bookmark.title}
              </button>
            )
          )}
        </div>
      )}

      {showHistory &&
        enableHistory && (
          <div className="absolute left-2 top-16 z-50 w-48 rounded-lg border border-slate-200 bg-white p-3 text-slate-800 shadow-xl">
            <p className="text-[9px] font-semibold">
              History
            </p>

            <p className="mt-2 text-[8px] text-slate-400">
              Recent browsing activity
            </p>
          </div>
        )}

      {showSettings &&
        enableSettings && (
          <div className="absolute right-2 top-20 z-50 w-52 rounded-lg border border-slate-200 bg-white p-3 text-slate-800 shadow-xl">
            <p className="text-[9px] font-semibold">
              Browser settings
            </p>

            <div className="mt-3 space-y-2 text-[8px] text-slate-500">
              <div className="flex justify-between">
                <span>
                  Safe browsing
                </span>

                <span className="text-emerald-600">
                  Enhanced
                </span>
              </div>

              <div className="flex justify-between">
                <span>Zoom</span>
                <span>100%</span>
              </div>

              {enableDownloads && (
                <div className="flex justify-between">
                  <span>Downloads</span>
                  <span>Ready</span>
                </div>
              )}
            </div>
          </div>
        )}

      <div
        ref={viewportRef}
        data-wizard-browser-viewport="true"
        data-wizard-browser-content="true"
        className="relative min-h-0 flex-1 overflow-hidden bg-white"
      >
        {isBlank ? (
          <div className="flex h-full items-center justify-center bg-slate-50">
            <div className="text-center">
              <Search className="mx-auto h-8 w-8 text-slate-300" />

              <h2 className="mt-3 text-sm font-semibold text-slate-700">
                New Tab
              </h2>

              <p className="mt-1 text-[8px] text-slate-400">
                Search or enter a web address
              </p>
            </div>
          </div>
        ) : (
          <>
            {!iframeLoaded && (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-white">
                <div className="flex flex-col items-center gap-3">
                  <div className="relative">
                    <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
                  </div>

                  <div className="text-center">
                    <span className="block text-[8px] font-medium text-slate-500">
                      Establishing verification session
                    </span>

                    <span className="mt-1 block text-[7px] text-slate-400">
                      {currentHost}
                    </span>
                  </div>
                </div>
              </div>
            )}

            <iframe
              key={currentUrl}
              data-wizard-browser-iframe="true"
              data-wizard-target="verification-page"
              src={currentUrl}
              title={`Wizard verification browser · ${currentHost}`}
              className={cn(
                "absolute inset-0 h-full w-full border-0 transition-opacity duration-300",
                iframeLoaded
                  ? "opacity-100"
                  : "opacity-0"
              )}
              onLoad={() => {
                setIframeLoaded(true)

                setTabs((current) =>
                  current.map((tab) =>
                    tab.isActive
                      ? {
                          ...tab,
                          isLoading: false,
                        }
                      : tab
                  )
                )
              }}
              allow="fullscreen"
              loading="eager"
            />

            {iframeLoaded && (
              <SmoothCursor
                containerRef={
                  viewportRef
                }
                active={true}
              />
            )}

            {iframeLoaded && (
              <div
                data-wizard-browser-status="true"
                className="pointer-events-none absolute bottom-2 right-3 z-30 flex items-center gap-1.5 rounded-md border border-slate-200/80 bg-white/85 px-2 py-1 text-[7px] text-slate-500 shadow-sm backdrop-blur-md"
              >
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />

                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>

                <span>
                  {agentActivity ===
                  "observing"
                    ? "Agent observing"
                    : "Secure browser session"}
                </span>
              </div>
            )}
          </>
        )}
      </div>

      {showStatusBar && (
        <div className="flex h-6 shrink-0 items-center justify-between border-t border-slate-300 bg-slate-100 px-3 text-[7px] text-slate-400">
          <span className="flex items-center gap-1">
            <Lock className="h-2.5 w-2.5 text-emerald-500" />
            Secure
          </span>

          <span className="flex items-center gap-2">
            {iframeLoaded && (
              <span className="flex items-center gap-1 text-emerald-600">
                <Check className="h-2.5 w-2.5" />
                Connected
              </span>
            )}

            <span>
              {tabs.length} tab
              {tabs.length !== 1
                ? "s"
                : ""}
            </span>
          </span>
        </div>
      )}
    </div>
  )
}

export default Browser