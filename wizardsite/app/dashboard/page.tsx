import { SavedArchitectures } from "@/components/architecture-viewer"
import type { Metadata } from "next"
import Link from "next/link"
import { CheckCircle2, GitBranch, LayoutDashboard, Monitor, ShieldCheck, Workflow, Activity } from "lucide-react"
import styles from "./dashboard.module.css"

export const metadata: Metadata = {
  title: "Dashboard | Wizard",
  description: "Your codebase investigations, all in one place.",
}

// Saved diagrams use the authenticated backend; device and usage summaries remain unavailable.
// Keep unavailable values distinct from a verified empty account (zero).
const summaries = [
  { title: "Investigations", label: "Saved analyses", icon: Workflow },
  { title: "Completed", label: "Ready to explore", icon: CheckCircle2 },
  { title: "Connected Devices", label: "Registered CLI devices", icon: Monitor },
  { title: "Usage", label: "When usage tracking is available", icon: Activity },
]

export default function Dashboard() {
  return (
    <div className={styles.dashboard}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link href="/" className={styles.brand} aria-label="Wizard home">
            <span className={styles.logo}><GitBranch size={30} aria-hidden="true" /></span>
            <span><span className={styles.brandName}>Wizard</span><span className={styles.subtitle}>Developer Intelligence Platform</span></span>
          </Link>
          <nav aria-label="Dashboard navigation"><Link href="/dashboard" aria-current="page" className={styles.overview}><LayoutDashboard size={15} aria-hidden="true" />Overview</Link></nav>
          <span className={styles.indicator}>Dashboard</span>
        </div>
      </header>
      <main className={styles.main}>
        <section aria-labelledby="welcome-heading" className={styles.welcome}>
          <p className={styles.eyebrow}>Your workspace</p>
          <h1 id="welcome-heading">Welcome back!</h1>
          <p>Your codebase investigations, all in one place.</p>
        </section>
        <section aria-label="Investigation summary" className={styles.grid}>
          {summaries.map(({ title, label, icon: Icon }) => (
            <article key={title} className={styles.card}>
              <div className={styles.cardTop}><h2>{title}</h2><Icon size={18} aria-hidden="true" /></div>
              <p className={styles.metric}><span aria-hidden="true">—</span><span className={styles.srOnly}>Unavailable</span></p>
              <p className={styles.cardLabel}>{label}</p>
              <span className={styles.availability}>{title === "Usage" ? "Not yet tracked" : "Data unavailable"}</span>
            </article>
          ))}
        </section>
        <section aria-labelledby="recent-heading" className={styles.recent}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>Architecture diagrams</p><h2 id="recent-heading">Recent investigations</h2></div></div>
          <SavedArchitectures />
        </section>
        <aside className={styles.privacy} aria-labelledby="privacy-heading">
          <ShieldCheck size={21} aria-hidden="true" />
          <div><h2 id="privacy-heading">Your repositories stay private</h2><p>Manage connected devices, saved evidence, and data retention from your account settings.</p><p className={styles.privacyNote}>Informational only. Account settings and retention controls are not available in this release.</p></div>
        </aside>
      </main>
    </div>
  )
}
