# Wizard CLI / TUI refactor plan

Date: 2026-10-22

Status: design plan, not an implemented interface. Preserve the working verification runtime while replacing the presentation. No performance or end-to-end success is claimed by this document.

## 1. Purpose

Make Wizard easy for a beginner to understand, responsive while work runs, and clear about what actually passed. Give it a distinct identity through a small animated reaper, readable activity, and inspectable proof.

The interface should answer:

1. What project am I checking?
2. What is happening now?
3. What happened in each step?
4. What passed, failed, or remains unconfirmed?
5. What can I do next?

Do not optimize for more animation than other tools. Optimize for understandable live work, reliable controls, and low overhead.

## 2. Existing components to reuse

- Runtime and its persisted investigation events remain authoritative.
- Reuse runtime clients, submission, account login/logout, usage events, reports, artifacts, cancellation, process cleanup, and browser observations.
- Keep model, provider policy, shared rate gate, validation, evidence requirements, and execution ownership unchanged by this UI project.
- Agents propose; Runtime validates and executes. The UI never creates evidence or independently advances execution.

Current presentation uses Prompt Toolkit, Rich content converted to ANSI, a persistent identity/art area, and an 80 ms refresh interval for animation. These are inspected implementation facts, not proof of a measured bottleneck.

### Framework decision

Start with the installed Prompt Toolkit, Rich, and Pillow. Prototype one complete activity view before committing to a framework migration.

Prompt Toolkit owns terminal input and output. Avoid repeatedly converting the complete Rich screen to ANSI; cache completed content and update affected UI state. Use Rich where it helps report and output formatting.

If expandable history, Markdown navigation, and responsive details require substantial custom machinery, compare a Textual prototype. Textual offers reusable widgets, workers, and reactive updates, but changing frameworks alone does not prove lower CPU or better responsiveness. Do not ship two competing renderers.

Do not add Chromium/Electron, Termium, terminal-browser, or a web server merely to draw the interface or mascot. TermDOM would introduce a JavaScript UI and is not a drop-in Python component.

## 3. What will change

- Replace the large wizard banner with a compact identity and reaper area.
- Replace the dominant violet/gold/ember decoration with a restrained theme.
- Replace deep mandatory menu navigation with an immediately focused input.
- Replace repetitive event text with stable activity entries that update in place.
- Add optional details, browser, and results views instead of permanent crowded panels.
- Integrate reports into the same navigation and language as the live check.
- Remove unnecessary continuous full-screen refresh and raw terminal output.
- Keep existing commands and noninteractive CLI behavior usable.

## 4. Visual language

- Inherit the terminal background where practical; offer explicit light and dark themes.
- Warm off-white primary text, legible secondary text, one muted violet accent.
- Reserve green, amber, and red for meaningful status; also show text labels.
- Prefer spacing, indentation, and occasional thin separators over nested borders.
- No giant welcome art, flashing frames, mandatory Nerd Fonts, emoji, or punctuation-character spinners.
- Real graphical animation is preferred. Do not use keycap graphics as decoration. Ordinary keyboard support remains available and discoverable.
- Font choice belongs to the terminal. Use weight, alignment, spacing, and line length rather than promising custom web fonts.
- Support narrow windows, reduced motion, mouse-optional operation, text selection, and copying.

## 5. Simple wording

Use plain labels in the main interface. Keep exact technical names, codes, IDs, and diagnostic output under Details.

| Internal wording | Main interface |
| --- | --- |
| Investigation | Check |
| Repository | Project |
| Runtime initializing | Getting ready |
| Planner completed | Plan ready |
| Explorer decision | Next step |
| ToolRequest rejected | Couldn't run this step |
| Process readiness unknown | App started; checking whether it is ready |
| Provider capacity | Waiting for AI |
| Missing evidence | Still needs checking |
| Verified | Passed |
| Unverified | Not confirmed |
| Observation | What happened |
| Provenance | How we checked |

Translate for clarity without hiding uncertainty or changing the meaning of states.

## 6. Startup and first use

Show an editable prompt immediately. Do not wait for provider readiness, start every service, force login, or call a model merely to display the welcome screen.

```text
wizard                                      Project: my-app

What would you like to check?                      [reaper]

> Test sign up and log in

Check project       Recent checks       Open report
```

The placeholder above is a layout sketch, not a final mascot asset.

- Resolve and display the selected project.
- Provide a short explanation for first-time users without a mandatory tutorial.
- Returning users see their last check and report.
- Ask for account login only when the chosen feature requires it.
- Show configuration problems beside the action they prevent.
- Before execution, show goal, project, execution scope, and current limits in a compact review. Do not repeat permissions unnecessarily.
- Continue reconnects to persisted work or explicitly resumes supported work; it never silently reruns completed actions.

## 7. Live activity flow

Keep three stable areas: project/current check, activity history, and input/actions.

```text
wizard   my-project                         Checking login

Passed    Read project files
Passed    Started the app
Passed    Opened the browser
Running   Testing the sign-up form
          Entering a value into the observed Email field

> Tell Wizard something...

Details       Browser       Results       Stop
```

This is illustrative. Labels, fields, addresses, commands, and routes must come from the actual check, never sample-project assumptions.

### Stable activities

Associate updates with real operation/decision IDs. One row evolves from requested to executing to completed, rejected, failed, or waiting. Do not merge unrelated events by guessing from text.

Example: Starting the app -> App started; checking whether it is ready -> App ready.

Preserve the complete saved event history while grouping presentation. A completed execution is not automatically a passed goal.

### Details on demand

Each activity can expose:

- Requested action and safe parameters.
- Validation result.
- Actual command and working directory where relevant.
- Session/process identity and current state.
- Relevant stdout/stderr or browser/HTTP result.
- Observation and artifact references.
- Affected goal, what the result proves, and what remains unproven.

Use a temporary inspector on wide terminals and a separate details view on narrow ones. No permanent three-column dashboard.

### Scrolling and input

- Follow new activity while the user is at the bottom.
- Stop auto-follow when the user reads older content.
- Show new-activity availability without moving their view.
- Input stays responsive during output, browser work, and provider waits.
- Acknowledge new instructions and state when they will apply.
- Stop requests cancellation and cleanup. Offer Pause only if Runtime supports safe pause boundaries; freezing the display is not pausing execution.

## 8. Waiting, failures, and progress

Show the actual known reason: Waiting for AI; App running, no working address found yet; Browser waiting for page.

Use provider-capacity countdowns only when the gate supplies the real next eligible time. Do not invent estimated finish times or percentages.

If there has been no update, say how long and offer details/stop. Do not claim a deadlock merely from silence, or generate rotating synonyms for progress.

Rejected actions and failures are visible, linked to their reason, and never styled as successful execution. Keep credentials, cookies, authorization headers, and sensitive URLs out of the visible timeline and safe summaries.

## 9. Browser view and proof

Reuse actual browser observations to display current address/title, last action, observed controls, and capture time.

- Page controls and labels come from real page state.
- Show the latest existing screenshot only when one was actually captured.
- Label screenshot age; a captured image is not live video.
- Do not continuously capture images solely to animate the UI.
- Support concise before/after differences when actual observations support them.
- Redact sensitive values and withhold private captures under existing policy.

Selecting a passed result should answer what operation happened, what it proved, and what it did not prove. A filled field does not prove successful account creation.

Pinning a selected goal, process, or page is optional future work after the core view is stable. Avoid adding it solely for feature count.

## 10. Reaper and actual animation

The requested SaaS is Dead embed is a browser custom element, not terminal-native executable UI. It uses a sprite sheet. Establish artwork redistribution/modification rights before bundling assets; permission to embed a remote widget is not automatically permission to redistribute its art.

### Rendering choices

1. Preferred on verified compatible terminals: actual prepared image frames through supported graphics, integrated with the single UI renderer.
2. Portable optional alternative: coloured block pixel-art frames, not emoji or punctuation spinners.
3. If strictly image-only mode is selected and graphics are unsupported: use plain status text or an available still image. Never emit unsupported escape sequences or silently install a browser.

Windows Terminal stable 1.22 added Sixel support. Kitty has a graphics protocol with animation features. Sixel support alone does not provide automatic GIF playback. Frame replacement, timing, scrolling, resize, SSH/multiplexers, and renderer integration need explicit testing. Shell name is not terminal capability detection.

### Proposed motion library

| State | Proposed movement | Duration |
| --- | --- | --- |
| Welcome | Reaper rises, lifts head, settles | Brief once |
| Reading project | Opens book, turns pages | Small active loop |
| AI request | Soft light around scythe | While request active |
| Starting app | Small mechanism turns and settles | During startup |
| Browser work | Leans toward a window, scanning light | During real work |
| Waiting | Sits, occasional head movement | Quiet, infrequent |
| Needs input | Turns toward user, raises hand | Once, then still |
| Passed | Short glow across completed step | Once |
| Failed | Lowers book, brief accent change | Once |
| Finished | Closes book and bows | Once |

These are proposed poses, not confirmed existing assets. Inspect the permitted sprite sheet first; prefer its available poses over commissioning or creating unnecessary animations.

Use real animation artwork, not emoji, key symbols, fake typing, bouncing text, or ASCII spinner substitutions. The reaper stays out of output and never takes focus. Make it larger at welcome, compact while working.

### Asset preparation and performance

- Bundle a small set of permitted frames locally; no external asset request at startup.
- Prepare, resize, and cache frames before execution; no live browser/Lottie engine just for motion.
- LottieFiles is a possible source for complementary effects, with per-asset licensing checked. Avoid mixing unrelated art styles.
- Start by measuring roughly 8-12 fps for short image animations; use fewer frames for resting motion.
- Animate only the reserved region, and only while needed.
- Full motion, Reduced motion, and Off settings.
- Pause decorative motion when unfocused where detectable.
- Input, cancellation, and scrolling always take priority over animation.
- No animated background, screen shaking, falling particles, constant flashing, or invented progress.

Reaper messages derive from real Runtime state. Do not add a mascot LLM or claim the mascot understands more than saved events show.

## 11. Usage, results, and reports

Update usage as measured provider events arrive. Show request in progress when final usage is unavailable. Never animate invented token counts; label estimates separately.

The Results view grows during execution, then becomes the final report:

- Passed: compatible proof exists.
- Failed: an actual check failed.
- Not confirmed: proof is missing, capability unavailable, or work stopped.

Keep Finished separate from Passed. A completed run can contain unconfirmed outcomes.

Report sections: Outcome, Checks, How to run the project, What happened, Proof, Artifacts.

Actions: See proof, Open screenshot, Copy command, Open saved report, Run this check again. Opening proof never reruns work. Command execution requires deliberate review and the normal Runtime validation/executor path, not direct terminal execution from Markdown links.

On exit, leave a concise summary and saved report path in ordinary terminal history. Preserve plain/noninteractive output for scripts and redirected output.

## 12. Lightweight update architecture

```text
Persisted Runtime events
          |
          v
Existing client/event reader
          |
          v
UI state associated with operation IDs and event sequence
          |
          v
One renderer -> terminal
```

- UI state is a projection, never a second execution state machine.
- Reconnect with existing sequence/cursor support; suppress duplicate presentation without suppressing real operations.
- Coalesce noisy updates for display while retaining full logs.
- Cache completed steps and Markdown sections.
- Render visible history and load older details on demand.
- Avoid rebuilding all history on each event or animation frame.
- Capture service/process output; sanitize terminal control sequences at display boundaries.
- Keep full diagnostics in existing debug logs, with existing secrecy policy.
- No provider calls to format deterministic summaries, explain known waiting states, or animate progress.
- No additional services, brokers, UI event infrastructure, or independent execution controls.

## 13. Implementation order

1. Record a baseline for startup, idle CPU/memory, typing under output, rendering cost, and resize behavior.
2. Prototype welcome and one active timeline view using the current stack. Use local display fixtures only; never present them as real verification.
3. Compare Textual only if the existing stack would require excessive custom widget work.
4. Connect the existing event stream, bounded history, details, input, cancellation, and reconnect behavior.
5. Connect account actions, measured usage, browser state, report navigation, and artifacts.
6. Confirm reaper asset rights and actual terminal capabilities; add the small motion library last.
7. Validate focused UI behavior and representative real-event playback without paid model requests.
8. Run a real user-authorized check only when requested. Do not launch Wizard or consume provider credit merely for UI development.
9. Replace the default UI only after parity and terminal restoration checks. Keep an ordinary plain CLI path, not a second competing interactive UI.

## 14. Acceptance checks

- Welcome/input does not depend on provider or backend startup.
- Typing and Stop remain responsive during heavy output.
- Idle screen has no continuous decorative repaint.
- New received events become visible promptly; distinguish UI latency from network delivery.
- Scrolling never unexpectedly jumps to the bottom.
- No raw logs, ANSI corruption, overlapping writers, or leaked credentials.
- Resize, narrow terminals, light/dark themes, text selection, and reduced motion work.
- Unsupported image protocols safely degrade to agreed fallback behavior.
- Animation does not alter execution ordering, evidence, budgets, or results.
- Reconnect does not duplicate submissions or executions.
- Reports retain accurate Passed/Failed/Not confirmed distinctions and actual evidence links.
- Exit/cancellation restores the terminal and preserves existing resource cleanup.
- Measure improvement; do not claim success from screenshots or unit tests alone.

Numeric CPU/memory/startup targets should be established from the actual baseline and test machines, not invented in advance.

## 15. Research references

- Prompt Toolkit application/layout support: https://python-prompt-toolkit.readthedocs.io/en/stable/pages/full_screen_apps.html
- Prompt Toolkit redraw/application controls: https://python-prompt-toolkit.readthedocs.io/en/stable/pages/reference.html
- Textual widgets: https://textual.textualize.io/widget_gallery/
- Textual workers: https://textual.textualize.io/guide/workers/
- Textual reactive updates: https://textual.textualize.io/guide/reactivity/
- Toad interaction reference: https://github.com/batrachianai/toad
- Elia keyboard/conversation reference: https://github.com/darrenburns/elia
- Comhad contextual inspection reference: https://github.com/Eoin-McMahon/comhad
- Kew visual reference: https://github.com/ravachol/kew
- Bubbles component reference, Go rather than Python: https://github.com/charmbracelet/bubbles
- Kitty graphics and animation: https://sw.kovidgoyal.net/kitty/graphics-protocol/
- Windows Terminal stable Sixel announcement: https://devblogs.microsoft.com/commandline/windows-terminal-preview-1-23-release/
- iTerm2 image support: https://iterm2.com/documentation-images.html
- Reaper embed source: https://saasisdead.si/reaper/v1.js
- Lottie assets: https://lottiefiles.com/free-animations
- LottieFiles license: https://lottiefiles.com/page/license
- Termium limitations: https://github.com/codr1/termium
- terminal-browser architecture: https://github.com/zenbu-labs/terminal-browser
- TermDOM compatibility: https://termdom.org/compatibility/

These references are research, not approved dependencies or licences for copied assets. Toad currently documents Windows limitations and AGPL licensing. Termium/terminal-browser use browser engines and Windows WSL paths. TermDOM does not support all browser CSS, including the sprite background/animation behavior needed to assume the reaper embed works unchanged.

## 16. Decision rule

Does this need to exist? If not, skip it. Reuse existing code first, then stdlib, native platform features, and installed dependencies. Add only the minimum component that provides a necessary capability. Preserve the working Runtime throughout the UI replacement.
