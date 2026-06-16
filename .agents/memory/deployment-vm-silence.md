---
name: VM deployment goes silent (diagnosis)
description: How to tell a stopped/suspended VM deployment from a code crash; don't jump to OOM.
---

# VM deployment goes silent — diagnosis

When the published site shows a spinning wheel / 504 / external requests time out, but
`getDeploymentInfo()` reports `isDeployed: true`, `hasSuccessfulBuild: true`:

**Read the deployment logs' tail before theorizing.** The decisive signal is whether there
are **restart/startup logs**.

- If the process *crashed*, the platform auto-restarts a VM and you WILL see fresh
  "Application startup complete" / cycle-start logs shortly after. Crash-loops produce
  repeated startup logs.
- If the logs simply **go silent with no restart attempts** (and stay silent for hours),
  the VM is **not running at all** — i.e. stopped/suspended at the platform level, NOT a
  code crash. Most common cause for an always-on VM: compute/credits exhaustion (or a
  manual stop). This is a billing/account matter → direct the user to Replit support; a
  code change won't fix it. Republishing restarts it; if it goes dark again the same way
  (~clean stop, no restart), that confirms the platform/credits cause.

**Don't assume OOM.** Verify the real memory footprint first: this app's dev process runs
at only ~150 MB RSS and is stable across cycles (no module-level per-cycle accumulators).
That footprint cannot OOM a normal VM. A clean ~30-min run followed by a silent stop with
zero restart logs is the signature of a *stop*, not a memory crash.

**Why:** In this project I wrongly guessed OOM and nearly recommended bumping VM memory.
Checking dev RSS (~150 MB, stable) and the absence of restart logs disproved it and pointed
to a platform-level stop instead.
