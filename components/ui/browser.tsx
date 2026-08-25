"use client"

import React, { useEffect, useMemo, useState } from "react"
import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  ChevronDown,
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
  const [tabs, setTabs] = useState<Tab[]>(() => {
    if (initialTabs && initialTabs.length > 0) {
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

  const [verificationStep, setVerificationStep] =
    useState(0)

  const isDark =
    theme === "dark" ||
    (theme === "system" &&
      typeof window !== "undefined" &&
      window.matchMedia(
        "(prefers-color-scheme: dark)"
      ).matches)

  useEffect(() => {
    setInputUrl(activeTab?.url || "")
  }, [activeTab?.id, activeTab?.url])

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
    event: React.FormEvent
  ) => {
    event.preventDefault()
    navigate(inputUrl)
  }

  const createTab = () => {
    if (tabs.length >= maxTabs) {
      return
    }

    const newTab: Tab = {
      id: `tab-${Date.now()}`,
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

    onTabCreate?.(newTab)
  }

  const closeTab = (tabId: string) => {
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

      remaining.forEach(
        (tab) => (tab.isActive = false)
      )

      remaining[nextIndex].isActive = true

      setInputUrl(
        remaining[nextIndex].url
      )
    }

    setTabs(remaining)

    onTabClose?.(tabId)
  }

  const switchTab = (tabId: string) => {
    setTabs((current) =>
      current.map((tab) => ({
        ...tab,
        isActive: tab.id === tabId,
      }))
    )

    const selected = tabs.find(
      (tab) => tab.id === tabId
    )

    if (selected) {
      setInputUrl(selected.url)
    }

    onTabSwitch?.(tabId)
  }

  const refresh = () => {
    if (!activeTab) {
      return
    }

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

  const runVerification = () => {
    setVerificationStep(1)

    window.setTimeout(() => {
      setVerificationStep(2)
    }, 500)

    window.setTimeout(() => {
      setVerificationStep(3)
    }, 1100)

    window.setTimeout(() => {
      setVerificationStep(4)
    }, 1700)
  }

  return (
    <div
      className={cn(
        "flex h-full w-full flex-col overflow-hidden rounded-xl border shadow-2xl",
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
                  !isFullscreen
                )
              }
              className="rounded p-1 hover:bg-white/10"
            >
              <Maximize2 className="h-3 w-3" />
            </button>

            <button className="rounded p-1 hover:bg-white/10">
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
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                )}
              </div>
            ))}
          </div>

          <button
            onClick={createTab}
            className="mb-1 ml-1 rounded p-1.5 hover:bg-slate-300 dark:hover:bg-slate-700"
          >
            <Plus className="h-3 w-3" />
          </button>
        </div>
      )}

      <div className="flex h-10 shrink-0 items-center gap-1 border-b border-slate-300 bg-slate-100 px-2 dark:border-slate-700 dark:bg-slate-850">
        <button
          onClick={goBack}
          disabled={!canGoBack}
          className="rounded-md p-1.5 hover:bg-slate-200 disabled:opacity-30 dark:hover:bg-slate-700"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
        </button>

        <button
          onClick={goForward}
          disabled={!canGoForward}
          className="rounded-md p-1.5 hover:bg-slate-200 disabled:opacity-30 dark:hover:bg-slate-700"
        >
          <ArrowRight className="h-3.5 w-3.5" />
        </button>

        <button
          onClick={refresh}
          className="rounded-md p-1.5 hover:bg-slate-200 dark:hover:bg-slate-700"
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
            {activeTab?.url.startsWith(
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
            setShowSettings(!showSettings)
          }
          className="rounded-md p-1.5 hover:bg-slate-200 dark:hover:bg-slate-700"
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </button>
      </div>

      {showBookmarksBar &&
        enableBookmarks && (
          <div className="flex h-7 shrink-0 items-center gap-3 overflow-hidden border-b border-slate-200 bg-white px-3 dark:border-slate-700 dark:bg-slate-900">
            <Bookmark className="h-3 w-3 text-slate-400" />

            {bookmarks.map((bookmark) => (
              <button
                key={bookmark.url}
                onClick={() =>
                  navigate(bookmark.url)
                }
                className="whitespace-nowrap text-[8px] text-slate-500 hover:text-blue-600"
              >
                {bookmark.title}
              </button>
            ))}
          </div>
        )}

      {showBookmarks && (
        <div className="absolute z-40 mt-16 ml-2 w-48 rounded-lg border border-slate-200 bg-white p-2 shadow-xl">
          <p className="px-2 py-1 text-[9px] font-semibold">
            Bookmarks
          </p>

          {bookmarks.map((bookmark) => (
            <button
              key={bookmark.url}
              onClick={() => {
                navigate(bookmark.url)
                setShowBookmarks(false)
              }}
              className="block w-full rounded px-2 py-1.5 text-left text-[8px] hover:bg-slate-100"
            >
              {bookmark.title}
            </button>
          ))}
        </div>
      )}

      {showHistory &&
        enableHistory && (
          <div className="absolute z-40 mt-16 ml-2 w-48 rounded-lg border border-slate-200 bg-white p-3 shadow-xl">
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
                <span>Safe browsing</span>
                <span className="text-emerald-600">
                  Enhanced
                </span>
              </div>

              <div className="flex justify-between">
                <span>Zoom</span>
                <span>100%</span>
              </div>
            </div>
          </div>
        )}

      <div className="relative flex min-h-0 flex-1 overflow-hidden bg-white">
        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
          {activeTab?.isLoading && (
            <div className="absolute left-0 right-0 top-0 z-30 h-0.5 overflow-hidden bg-blue-100">
              <div className="h-full w-1/2 animate-[loading_0.9s_ease-in-out_infinite] bg-blue-600" />
            </div>
          )}

          {activeTab?.url ===
            "about:blank" ||
          !activeTab?.url ? (
            <div className="flex flex-1 items-center justify-center bg-slate-50">
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
            <div className="relative flex flex-1 items-center justify-center overflow-hidden bg-gradient-to-br from-slate-50 via-white to-blue-50 p-5">
              <div className="absolute inset-0 opacity-30">
                <div className="absolute left-1/4 top-1/4 h-32 w-32 rounded-full bg-blue-200 blur-3xl" />
                <div className="absolute bottom-1/4 right-1/4 h-32 w-32 rounded-full bg-indigo-200 blur-3xl" />
              </div>

              <div className="relative w-full max-w-[420px] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
                  <div className="flex items-center gap-2">
                    <div className="flex h-5 w-5 items-center justify-center rounded bg-blue-600 text-[8px] font-bold text-white">
                      W
                    </div>

                    <span className="text-[8px] font-semibold text-slate-700">
                      Wizard
                    </span>
                  </div>

                  <span className="text-[7px] text-slate-400">
                    {hostname(
                      activeTab.url
                    )}
                  </span>
                </div>

                <div className="p-6">
                  <div className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-1 text-[7px] font-semibold text-blue-600">
                    <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                    LIVE VERIFICATION
                  </div>

                  <h2 className="text-xl font-bold tracking-tight text-slate-900">
                    Your build is ready.
                  </h2>

                  <p className="mt-2 text-[9px] leading-relaxed text-slate-500">
                    Wizard is checking the generated
                    application against the requested
                    behavior.
                  </p>

                  <button
                    onClick={runVerification}
                    className="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-[8px] font-semibold text-white shadow-sm transition hover:bg-blue-700"
                  >
                    {verificationStep === 0
                      ? "Run verification"
                      : verificationStep < 4
                        ? "Verifying..."
                        : "Verification complete"}
                  </button>

                  <div className="mt-5 space-y-2 border-t border-slate-100 pt-4">
                    <div className="flex items-center gap-2 text-[8px]">
                      <span
                        className={cn(
                          "flex h-4 w-4 items-center justify-center rounded-full",
                          verificationStep >= 1
                            ? "bg-emerald-100 text-emerald-600"
                            : "bg-slate-100 text-slate-300"
                        )}
                      >
                        {verificationStep >= 1
                          ? "✓"
                          : "1"}
                      </span>

                      <span className="text-slate-600">
                        Open application
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-[8px]">
                      <span
                        className={cn(
                          "flex h-4 w-4 items-center justify-center rounded-full",
                          verificationStep >= 2
                            ? "bg-emerald-100 text-emerald-600"
                            : "bg-slate-100 text-slate-300"
                        )}
                      >
                        {verificationStep >= 2
                          ? "✓"
                          : "2"}
                      </span>

                      <span className="text-slate-600">
                        Execute browser action
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-[8px]">
                      <span
                        className={cn(
                          "flex h-4 w-4 items-center justify-center rounded-full",
                          verificationStep >= 3
                            ? "bg-emerald-100 text-emerald-600"
                            : "bg-slate-100 text-slate-300"
                        )}
                      >
                        {verificationStep >= 3
                          ? "✓"
                          : "3"}
                      </span>

                      <span className="text-slate-600">
                        Capture browser evidence
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-[8px]">
                      <span
                        className={cn(
                          "flex h-4 w-4 items-center justify-center rounded-full",
                          verificationStep >= 4
                            ? "bg-emerald-100 text-emerald-600"
                            : "bg-slate-100 text-slate-300"
                        )}
                      >
                        {verificationStep >= 4
                          ? "✓"
                          : "4"}
                      </span>

                      <span className="text-slate-600">
                        Verification passed
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50 px-4 py-2">
                  <span className="text-[7px] text-slate-400">
                    Wizard Agent
                  </span>

                  <span className="flex items-center gap-1 text-[7px] text-emerald-600">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    {verificationStep >= 4
                      ? "PASS"
                      : "READY"}
                  </span>
                </div>
              </div>

              <div className="absolute bottom-2 right-3 flex items-center gap-1 text-[7px] text-slate-400">
                <Lock className="h-2.5 w-2.5" />
                Secure browser session
              </div>
            </div>
          )}
        </div>
      </div>

      {showStatusBar && (
        <div className="flex h-6 shrink-0 items-center justify-between border-t border-slate-300 bg-slate-100 px-3 text-[7px] text-slate-400">
          <span className="flex items-center gap-1">
            <Lock className="h-2.5 w-2.5 text-emerald-500" />
            Secure
          </span>

          <span>
            {tabs.length} tab
            {tabs.length !== 1 ? "s" : ""}
          </span>
        </div>
      )}

      <style jsx>{`
        @keyframes loading {
          0% {
            transform: translateX(-100%);
          }

          100% {
            transform: translateX(200%);
          }
        }
      `}</style>
    </div>
  )
}
