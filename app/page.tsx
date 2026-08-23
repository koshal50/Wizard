import Hero from "@/components/hero"
import { CinematicHero } from "@/components/ui/cinematic-landing-hero"

export default function Home() {
  return (
    <main className="min-h-screen">
      <Hero />
      <CinematicHero />
    </main>
  )
}
