import { RepositoryScanner } from "./RepositoryScanner.js";

async function main() {
  console.log("Starting scanner...");

  const scanner = new RepositoryScanner();

  const result = await scanner.scan(
    "C:/Users/yashb/OneDrive/Desktop/New/Projectss/Krushifriendly-main"
  );

  console.log("Scan Result:");
  console.log(JSON.stringify(result, null, 2));
}

main();