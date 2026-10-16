// GitHub's own cron ("*/5 * * * *") is best-effort and often skips runs,
// so Netlify triggers the monitor workflows every 5 minutes instead.
// Requires a GITHUB_TOKEN env var (fine-grained token with "Actions: Read and write"
// on this repository).

const REPO = "Mattedark10/futgg-monitor"
const WORKFLOWS = ["monitor.yml", "test-trending.yml"]

export default async () => {
  const token = Netlify.env.get("GITHUB_TOKEN")

  if (!token) {
    console.error("GITHUB_TOKEN is not set: cannot trigger the monitor.")
    return
  }

  for (const workflow of WORKFLOWS) {
    const response = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "futgg-monitor-scheduler",
        },
        body: JSON.stringify({ ref: "main" }),
      }
    )

    if (response.ok) {
      console.log(`Triggered ${workflow}`)
    } else {
      console.error(
        `Failed to trigger ${workflow}: ${response.status} ${await response.text()}`
      )
    }
  }
}

export const config = {
  schedule: "*/5 * * * *",
}
