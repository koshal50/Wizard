import { PolicyPage, PolicySection, policyContact, policyDisclaimer } from "@/components/policy-page"

export const metadata = { title: "Refund Policy — Wizard", description: "Wizard pre-launch refund information." }

export default function RefundsPage() {
  return <PolicyPage title="Refund policy" eyebrow="Wizard / refunds" updated="September 6, 2026"><PolicySection title="Pre-launch status"><p>{policyContact}</p><p>{policyDisclaimer}</p><p>Wizard is currently under development and does not offer paid subscriptions, purchases, trials, or downloadable products through this website. There are therefore no current charges to refund.</p></PolicySection><PolicySection title="When payments launch"><p>Before accepting payment, Wizard will publish a complete commercial refund and cancellation policy describing eligibility, statutory withdrawal rights, billing timing, renewal, taxes, support, and the process for requesting a refund. Any mandatory consumer rights will apply regardless of this policy.</p></PolicySection><PolicySection title="Questions"><p>For pre-launch questions, contact <a href="mailto:shivamgawali585@gmail.com">shivamgawali585@gmail.com</a>. Do not send payment details by email.</p></PolicySection></PolicyPage>
}
