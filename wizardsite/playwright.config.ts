import { defineConfig } from "@playwright/test"
export default defineConfig({
  testDir: "./tests/browser", workers: 1, fullyParallel: false, retries: 0, timeout: 60000,
  reporter: "list", expect: {timeout: 20000},
  use: { baseURL: "http://localhost:3000", browserName: "chromium", channel: "msedge",
    headless: true, trace: "off", screenshot: "off", video: "off" },
})
