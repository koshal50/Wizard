import { AccountLink } from "@/components/account-link"
import Hero from "@/components/hero"
import { CinematicHero } from "@/components/ui/cinematic-landing-hero"
import CinematicFooter from "@/components/ui/motion-footer"
import { SmoothCursor } from "@/components/ui/smooth-cursor"

export default function Home() {
  return <main className="min-h-screen bg-black"><AccountLink /><Hero /><CinematicHero /><CinematicFooter /><SmoothCursor /></main>
}
