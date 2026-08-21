"use client"

// AsciiArt — "Redshift", made with the 21st.dev ASCII editor and baked
// to its exact rendered output (looping video + poster).
export function AsciiArt({ className }: { className?: string }) {
  return (
    <video
      className={className}
      src="https://assets.21st.dev/ascii-recipes/videos/user_2nElBLvklOKlAURm6W1PTu6yYFh/1783480440186-b7o356.mp4"
      poster="https://assets.21st.dev/ascii-recipes/thumbnails/user_2nElBLvklOKlAURm6W1PTu6yYFh/63f8aa27-cea7-49e0-a6a4-c2dc0954563c.jpg"
      autoPlay
      loop
      muted
      playsInline
      aria-label="Redshift — animated ASCII art"
      style={{
        display: "block",
        width: "100%",
        height: "100%",
        objectFit: "cover",
      }}
    />
  )
}
