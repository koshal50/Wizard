import type React from "react"
import type { Metadata } from "next"
import { Suspense } from "react"
import { Inter_Tight, JetBrains_Mono } from "next/font/google"
import "./globals.css"
import { AccountProvider } from "@/components/account-session"
import { PrivacyConsent } from "@/components/privacy-consent"

const instrumentSans = Inter_Tight({
  variable: "--font-sans",
  subsets: ["latin"],
})

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  weight: ["400", "700"],
})

export const metadata: Metadata = {
  title: "Wizard — Verify the reality",
  description: "Wizard investigates, executes, browses, and verifies your work with evidence.",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="bg-black">
      <body className={`font-sans ${instrumentSans.variable} ${jetbrainsMono.variable}`}>
        <AccountProvider><Suspense fallback={null}>{children}</Suspense></AccountProvider>
        <PrivacyConsent />
      </body>
    </html>
  )
}
