import { expect, test } from "@playwright/test"

test("homepage retains its hero and centers the dashboard CTA below existing actions", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "Build with AI. Verify with Wizard." })).toBeVisible()
  const review = page.getByRole("link", { name: "Review Architectural Diagram" })
  await expect(review).toHaveAttribute("href", "/dashboard")
  const team = await page.getByRole("button", { name: "Talk to the Wizard team" }).boundingBox()
  const login = await page.getByRole("link", { name: "Login", exact: true }).boundingBox()
  const button = await review.boundingBox()
  expect(team && login && button).toBeTruthy()
  expect(button!.y).toBeGreaterThanOrEqual(Math.max(team!.y + team!.height, login!.y + login!.height))
  const left = Math.min(team!.x, login!.x)
  const right = Math.max(team!.x + team!.width, login!.x + login!.width)
  expect(Math.abs(button!.x + button!.width / 2 - (left + right) / 2)).toBeLessThan(2)
  await review.click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole("heading", { name: "Welcome back!" })).toBeVisible()
})

for (const width of [1440, 390, 320]) {
  test(`dashboard direct URL and honest unavailable state at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto("/dashboard")
    await expect(page.getByRole("navigation", { name: "Dashboard navigation" })).toBeVisible()
    await expect(page.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page")
    for (const name of ["Investigations", "Completed", "Connected Devices", "Usage", "Recent investigations", "Your repositories stay private"]) {
      await expect(page.getByRole("heading", { name, exact: true })).toBeVisible()
    }
    await expect(page.getByText("Data unavailable", { exact: true })).toHaveCount(3)
    await expect(page.getByText("Not yet tracked", { exact: true })).toBeVisible()
    await expect(page.getByRole("heading", { name: "Saved diagrams aren’t available yet" })).toBeVisible()
    await expect(page.getByRole("link", { name: /View all/ })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.getByRole("link", { name: "Wizard home" }).click()
    await expect(page).toHaveURL(/\/$/)
  })
}
