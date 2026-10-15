import Link from "next/link"
import { ArrowRight } from "lucide-react"
import { CliHeading, CliPreviewNotice, cliPrimaryLink, cliSecondaryLink } from "@/components/cli-authorization"

export default function CliAuthorizePage() {
  return (
    <>
      <CliHeading title="Your Wizard account. Your terminal.">Connect your Wizard CLI to your website account. Start by signing in to Wizard, or create an account using the existing registration page.</CliHeading>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <a href="/login.html?returnTo=%2Fcli%2Fconnect" className={cliPrimaryLink}>Continue to sign in <ArrowRight aria-hidden="true" className="h-4 w-4" /></a>
        <Link href="/" className={cliSecondaryLink}>Cancel and return to website</Link>
      </div>
      <CliPreviewNotice>CLI authorization is coming soon. You can explore the screens, but this preview does not connect your account or issue credentials.</CliPreviewNotice>
    </>
  )
}
