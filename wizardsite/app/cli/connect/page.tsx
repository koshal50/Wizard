import Link from "next/link"
import { CliCodePlaceholder, CliHeading, CliPreviewNotice, cliPrimaryLink, cliSecondaryLink } from "@/components/cli-authorization"

export default function CliConnectPage() {
  return (
    <>
      <CliHeading title="Connect your Wizard CLI">Your website account and your terminal will meet here. The final connection step will be completed in Wizard CLI.</CliHeading>
      <CliCodePlaceholder />
      <CliPreviewNotice>No authorization code has been issued. Code and expiration details will be supplied by the future authorization service.</CliPreviewNotice>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Link href="/" className={cliPrimaryLink}>Cancel and return to website</Link>
        <Link href="/cli/complete" className={cliSecondaryLink}>Preview completion screen</Link>
      </div>
    </>
  )
}
