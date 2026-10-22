# Wizard CLI / TUI refactor plan

Date: 2026-10-22

Status: the native Textual interface is implemented and is now the default interactive UI. Runtime authority is preserved. No real-provider end-to-end success is claimed by this document.

Current behavior: skippable first-use guidance; existing account authorization with responsive code entry; stacked commands/subcommands; Enter-to-run composer; event-driven activity, sanitized process output and usage; browser observations; Markdown reports and saved-report actions; side conversation; consent-gated connections upload; existing cancellation and owned-service cleanup. Display preferences persist outside project data.

Quit correction: Wizard's `_closing` flag collided with Textual's private message-pump flag and prevented ExitApp from being queued. It is now `_ui_closing`. Regression checks cover welcome/login/active-session exits. Startup is cancellation-aware and retains owned processes for cleanup.

Native UI dependencies are declared in the normal install; the `tui` extra remains a compatibility alias. `WIZARD_UI=classic` explicitly selects the earlier interface. Opening the shell never submits work or opens account authorization. SVGs show local UI playback, not execution evidence or terminal bitmap captures. The user confirmed the cached reaper in VS Code. Historical delivery notes below describe earlier stages and are superseded by this checkpoint.

### Delivery stages and review points

Connected presentation checkpoint: the native shell now handles the registered
`/login`, `/cancel-login`, `/logout`, `/status`, `/exit`, `/btw`, and existing
`/btw main`, `new`, `copy`, `copy all` controls. Status uses the existing usage
transport/formatter; logout uses existing credential revocation. Side questions
reuse SideChat and its bounded HTTP request, starting the existing local services
only after an explicit question if necessary. Opening `/btw` alone makes no
provider request. Main/side drafts survive switching; usage responses and account
callbacks cannot replace a view the user has left. Check submission, streaming,
cancellation and report-family requests still use TuiSession. Live browser controls
come only from its latest page snapshot; Markdown reports come from Runtime's
returned report, not a UI-generated verdict. Local substituted-transport checks
covered slash dispatch, usage, logout, chat, draft switching, browser controls and
report rendering. `cli-textual-connected.svg` is local playback, not real evidence.
Classic remains default until parity/visual review; native can be selected with
`WIZARD_UI=textual` or its module entry point. No real provider calls were made.

Latest interaction revision (supersedes Review/Start below): selecting a check
and pressing Enter in the composer now submits it directly. An empty intent
uses the selected check. Start/Stop buttons were removed; Ctrl+C or `/cancel`
cancels through the existing Runtime session. Repeated Enter while a check is
active cannot submit another one. The submitted request stays in the activity
view; the composer clears for the next draft without discarding edits made
during service startup. New events update activity immediately. A small colour
sweep and actual elapsed seconds indicate pending work, never fabricated progress.
Companion speech reveals the latest message, replacing stale text instead of
queueing it; terminal results show immediately. Reduced motion reveals full text
and freezes the colour sweep. Local substituted-service checks passed for Enter,
duplicate suppression, draft preservation, cancellation and speech. No real
investigation/provider calls were made for this revision.

Stage 3 checkpoint: Start is now a separate explicit action after local Review.
The native shell reuses ServiceSupervisor and TuiSession rather than duplicating
submission, event cursors, usage monitors or cancellation. Notifications post
coalescible Textual messages; the renderer reads the latest thread-safe snapshot.
The bounded activity view offers expandable page/activity details and displays
reported token totals without polling or inventing in-flight token counts.
Terminal status and saved report path come from Runtime/session state. Opening
or reviewing the UI never launches services or calls a model. Stop uses the
existing remote-cancellation path; exit shuts down the session and owned services.
Service startup runs off the UI thread and cancellation before submission prevents
the prepared request from starting. Local event playback checked single dispatch,
usage updates, page details, incomplete status, saved path and cleanup with no
real services/provider calls. `cli-textual-activity.svg` is that playback, not
investigation evidence. Real investigation behavior is not verified in this pass.
Browser/report views and remaining slash-command parity remain later work.

Latest stage 2 checkpoint: the Textual shell now connects `/login` to the existing
LoginWorker, with centred twelve-character code cells, paste/type support,
validation, explicit Connect/Cancel actions and return to the command picker.
The website protocol uses hexadecimal characters, not twelve decimal digits.
Account work stays on the existing worker; callbacks return to Textual's UI
thread and stale callbacks are ignored after cancellation or exit. Codes are
cleared after submission; authorization-ticket URLs are not copied into the UI
transcript. Login remains optional and opening the shell does not start it.
Local headless interaction checks used a substituted worker without network
access; live backend authentication has not been verified in this pass.
`docs/main/cli-textual-login.svg` shows the empty code-entry layout, not an actual
authentication or proof of bitmap display. The user confirmed the real reaper
is visible after enabling VS Code terminal images and creating a fresh terminal.
Runtime submission/live activity remain the next stage; classic UI stays default.

1. Welcome, compact header, open command composer, provisional palette. Show the exported screen for visual review before extending the design.
2. Guided first use and centred account-code input. Reuse existing authentication; review signed-out, waiting, error, and signed-in screens.
3. Live activity rows and expandable execution details. Wire existing events, scrolling, cancellation, usage, and reconnect; review a local event playback.
4. Browser/result/report views and evidence navigation. Review actual saved observations and artifact links without rerunning checks.
5. Permitted reaper assets and motion, with safe terminal fallback and reduced-motion behavior. Review entrance, working, waiting, and attention poses.
6. Focused regression and terminal checks, then switch the default only after visual and behavior review. Real investigations require user authorization; UI development consumes no provider credits.

Each stage changes presentation only unless a specific existing integration requires a documented correction. Do not describe this prototype as a completed end-to-end refactor.

Design revision: the guided reaper entrance, account-code screen, persistent composer, and companion behavior in section 17 refine the earlier sketches. Colour values remain provisional until visual review. This document does not change the authentication protocol.

Latest visual direction: use the user's four-scene storyboard as the reference. Background #08080A; primary text #F3F1EC; secondary text #7E7C88; violet #9B7EDE; amber #E5A93C only as a restrained occasional animation highlight. Hairlines for the composer; a small outlined speech bubble and individual auth-code cells are intentional exceptions to the no-nested-panels rule. JetBrains Mono is a suggested terminal font, not a font the CLI can enforce.

The opt-in welcome now uses this palette, an open canvas, composer hairlines, and an original resting pixel-reaper pose on sufficiently large terminals. No third-party mascot art is copied. The new docs/main/cli-storyboard.svg shows all four proposed scenes; auth/assembly/workspace content there is illustrative, not completed functionality or execution evidence. Animation, code-entry integration, and the modern live timeline remain subsequent stages. Unsupported /check, /browser, and /report aliases in the supplied visual prompt are not advertised as working commands; the storyboard uses existing slash commands.

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
- Introduce account login during the guided first-use flow, with an option to continue locally where supported. Require authentication only for features that actually need it.
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

## 17. Revised experience: the reaper introduces Wizard

### A. Installation to first launch

After successful installation, show a concise next step:

```text
Wizard is installed.
Open your project folder, then run wizard.
```

Possible supporting line: "Find out what works in your project." Avoid claiming a project has been checked during installation.

On first launch, enter a clean fullscreen surface. Dark mode uses a near-black background, with a legible light-mode alternative. Preserve the terminal contents and restore them on exit; do not permanently clear user scrollback. Input becomes usable immediately.

The small reaper enters from the right and settles at the bottom-right, inside a reserved area. A compact speech bubble appears above it. The entrance must not block typing, require an artificial loading delay, or collide with the command area. On narrow screens use a compact companion row instead of overlaying content.

Opening words:

```text
Hi. I'm here to help you check your project.
Tell me what you want to test, and I'll show you what happens.
```

Offer a short guided introduction with Next, Skip tour, and command input available. Present one idea at a time rather than a long mandatory conversation. Explain commands through examples without requiring decorative keycap symbols or emoji.

### B. Introduce login

The reaper explains:

```text
Type /login to connect your Wizard account.
```

The persistent command/intent composer sits at the bottom. Typing / opens existing command suggestions; ordinary text is treated according to the existing command/intent parser. Enter submits, but all controls remain accessible without a mouse.

Offer Continue locally for features that already support it. Login should not become a new prerequisite for unrelated verification. Returning authenticated users skip this introduction. Returning logged-out users can invoke /login directly without replaying the tour.

### C. Browser approval and centred code entry

Use the current LoginFlow and secure credential storage. /login creates the existing authorization request and opens its validated website URL. The website handles sign-in/sign-up and explicit CLI approval, then shows its authorization code.

Confirmed current contract: **12 hexadecimal characters, A-F and 0-9**, not 12 decimal digits. CLI normalization already accepts spaces/hyphens and converts to uppercase. Keep this protocol; changing code entropy or format is outside this design.

Show a centred code form with 12 large outlined character cells, visually grouped in threes or fours for readability. Implement it as one accessible logical input with a styled display, not 12 independently focusable fields. It must support pasting the complete code, backspace, navigation, validation, and reduced-width layouts. Large cells are a layout treatment, not a promise that terminal fonts can be resized.

Reaper message:

```text
Enter the code shown on the website.
You can paste the whole code here.
```

Do not echo the code into activity history, logs, reports, telemetry, or AI context. Clear the transient input after exchange/cancellation. Retain the existing expiry, attempt limits, request binding, approval, and cancellation semantics.

After entry, provide deliberate Connect submission. Do not automatically issue requests on each keystroke or every completed paste. Disable duplicate submissions while the one exchange is pending.

Provide clear failures: Code not accepted; Code expired; Website unavailable; Couldn't save your login. Preserve the existing backend detail safely under Details. Offer cancel and an explicit new login request when appropriate, never repeated background authorization attempts.

If the browser cannot open, offer Open login page and Copy link through the existing validated flow. The code itself remains ephemeral and private.

### D. Transition into the workspace

During the actual exchange, show "Connecting your account..." and a small real animation. After confirmed secure storage, show "You're signed in." Use "Getting your workspace ready..." only while real initialization is running, not as a decorative delay.

Transition to the main workspace without restarting Runtime or submitting a check. Do not hide an error behind an indefinite setup animation. If credentials are already valid, skip browser and code entry.

### E. Main workspace and persistent companion

The main area contains recent checks or the active activity timeline. A compact set of useful commands is available until the user starts work. The command/intent composer remains at the bottom for both ordinary goals and slash commands.

The reaper remains in the bottom-right reserved area with a small bubble above it. Keep it visually secondary to input and results. Users can hide it, reduce motion, or reopen its guidance. On smaller terminals collapse the bubble or relocate the companion instead of shrinking the working area excessively.

Example messages:

- "What would you like to check?"
- "I'm reading your project."
- "The app started. I'm checking whether it is ready."
- "The page opened. I'm checking the form."
- "Waiting for AI."
- "I need your help here."
- "Finished. Open Results to see what passed."

Messages must be grounded in Runtime state. Do not say the browser opened or a form passed merely because an action was requested.

### F. Live text and /btw

Support brief text-reveal animation for new companion messages, following the user's requested typing effect. This refines the earlier blanket exclusion of fake typing: reveal already-known short UI text only. Never use artificial typing to simulate model reasoning, delay errors, or make completed results appear live.

- Make the full message available immediately to accessibility/plain-text modes.
- Finish or skip the reveal immediately when the user interacts.
- Reduced motion shows the complete text instantly.
- Replace obsolete status messages promptly; do not queue a backlog of stale bubbles.
- Failures, questions, and cancellation status appear immediately.

Reuse the existing /btw side-chat where appropriate. A status bubble uses deterministic events and costs no model tokens. Opening /btw is a separate explicit user action and may consume tokens under the existing budgets. Never trigger a side-chat model request for every status update or grant side-chat direct execution authority.

An optional Ask about this step action can send a bounded, safe reference to the existing side-chat. Keep real execution in Runtime and keep login codes, secrets, and full prompts out of companion context.

### G. Colour review

The latest direction uses the exact near-black/off-white/slate/violet values recorded above. Refine contrast through actual terminal previews and retain a light alternative. The old violet/gold palette is not the target. The reaper's artwork colours need not become the colour of every interface element.

### H. Focused acceptance for this journey

- Fresh launch, returning signed-in launch, and returning signed-out launch work without replaying unwanted onboarding.
- Entrance and speech animation never block typing or delay real status.
- Browser login uses the existing approval/code protocol and handles offline/expired/cancelled flows.
- Twelve-character paste, edit, resize, and validation work with no repeated submissions.
- Code entry never reaches logs, persisted events, reports, or models.
- Main workspace appears only after real login success, or an explicit supported local continuation.
- /btw is explicit; status guidance introduces zero AI requests.
- Reaper/bubble/composer do not overlap, including narrow terminals and resize.
- Exit restores the terminal; login cancellation and investigation cleanup keep their existing behavior.

This section updates the design only. No account, UI, renderer, or animation behavior has been implemented by adding it.

## 18. Post-login workspace refinement

Superseded as the main layout by section 19. The six large SVG screens remain detail/report reference studies, not six screens the user must navigate during normal execution.

Review docs/main/cli-workspace-preview.html for six local full-size design screens. Its sample content is explicitly illustrative: it never connects to Runtime or creates observations. The main storyboard's fourth panel now uses the same live-workspace design instead of a separate simplified mockup.

### Screen progression

1. **After login:** editable goal, two understandable starting actions, recent checks when they exist. No artificial check or repository scan is submitted merely because login succeeded.
2. **Live check:** header and three views (Activity, Browser, Results); goal and real elapsed time; settled earlier steps; expanded active action; recent safe result. A small outcome summary is distinct from activity status. Completed setup is labelled Done, not automatically Passed.
3. **Inspect a step:** request, validation, execution, observation, and what the result proves. Opening details does not start another action or model request. The live run continues unless Runtime says otherwise.
4. **Browser proof:** latest saved page/title, capture age, observed controls, safe last-action changes, links to real snapshots and screenshots when available. Do not imply the design preview is an actual browser capture. Missing captures are not synthesized.
5. **Results:** Passed, Failed, and Not confirmed goal outcomes; concise missing-proof explanations; links to report, proof, run instructions, and a deliberate new check. Finished never means everything passed.
6. **Needs help:** actual failure, what remains unconfirmed, safe diagnostic actions, and stop. Do not offer an automatic retry button that bypasses Runtime policy or silently spends credits.

### Spatial layout

- Main work occupies roughly the left 70% on wide terminals. A quiet right-side lane holds a compact current-check summary and the reaper. It is reserved space, not a permanent bordered dashboard.
- One low-profile header identifies project/account. Three text view selectors share one baseline and a short active underline.
- Composer is anchored bottom-left with two violet hairlines. Input does not expand under the reaper or speech bubble.
- Speech bubble sits above the character inside the companion lane, never floating over active output. The bubble remains the intentional small bordered object.
- Details use the main work area rather than adding a third pane. Browser and report views reuse the same shell.
- At narrower widths collapse the outcome summary, then the companion; retain full input, activity, and access to guidance. Do not scale desktop font sizes down to fit.
- No decorative usage sparkline or invented throughput. Show measured usage when available and clear waiting state otherwise.

### What makes it live

The selected active row updates from real operation IDs. Completed rows settle without moving. A new result updates the expanded row, affected goal summary, and relevant browser/process references together. Context changes are not simulated by animated text.

Following stays on until the user scrolls away. A new-activity notice returns to the tail; selecting a completed row preserves selection while background events arrive. Timestamps/capture ages distinguish saved proof from current process state. Disclosure, tab changes, and local history inspection need no AI calls.

During active work, the composer labels guidance as applying to the next decision boundary. During completion it becomes a new-goal composer. Asking about a step can use the explicit existing /btw path, not an automatic request for every event.

The HTML gallery demonstrates changing between views only. Actual streaming, row expansion, proof links, composer actions, and animations still require staged implementation and Runtime integration. Do not describe gallery navigation as a working runtime UI.

### Reaper revision

Replace the first rectangular silhouette with an original 36-by-44 pixel pose: pointed hood, recessed small bone face, violet eye highlights, layered robe folds, clasp, hand on a long staff, and curved edged blade. One canonical pixel grid feeds native half-block display and SVG previews, keeping the artwork consistent. It is a design asset, not a claim of final approved illustration quality.

Keep the character small relative to the task; motion is meaningful and state-driven. Detailed artwork does not justify a background animation engine or persistent full-screen redraw. The resting pose is implemented; entrance, book-turning, attention, and other motion remain planned. The opt-in welcome only displays it where the reserved 27-row region safely fits.

## 19. Latest correction: one compact screen, actual work unfolding

The user rejected the spacious, static-looking gallery. Use docs/main/cli-live-preview.html as the primary interaction study. It is an isolated local sample playback: no model, Runtime, login, process, network, or evidence mutation. Its timers illustrate event arrival; they must never become artificial runtime output delays.

### One screen after login

- Show the existing four commands: investigate, verify, report, explain. Do not replace the command structure with generic onboarding cards.
- Choosing a command reveals its existing subcommands in the same content area, using the canonical registry. Report has no subcommands; do not invent any.
- Keep the selected command/subcommand immediately above a compact composer. An intent is optional where the existing command permits it.
- Use short descriptions. Remove slogans, promotional copy, hero-scale typography, and repeated introductory questions from this workspace.
- The opt-in native welcome now restores the actual four-command menu and its target list, with compact spacing and existing click/navigation behavior.

### Execution takes over the same area

After submission, replace the command picker with activity. Do not open a second dashboard, permanent goals sidebar, three tabs of repeated information, or a separate chat screen merely to show progress.

Use plain action phrases: Reading files; Starting the app; Checking the address; Opening the page; Filling the form; Checking the result. Module names such as Planner, Explorer, Verifier, Context Engine, and Runtime do not belong in the main activity column. Exact technical identities remain in Details.

The current action stays expanded. Show its safe requested command/action followed by real output as available. Append stdout/stderr chunks to that operation, retain order, and distinguish them without requiring a new activity row for every output line. Completed earlier operations settle into compact rows that can be reopened.

Done means the operation completed, not that a verification goal passed. Preserve errors and partial output. Do not collapse an error the user is reading just because a later event arrived.

### Live text and animation

- Start/finish transitions are brief, local, and do not shift the entire history.
- A small graphical light sweep marks actual in-flight work; no ASCII spinner or emoji substitute.
- The reaper changes pose/motion only for real state, with a small reserved area adjacent to the input. Do not make room for a mostly empty permanent side dashboard.
- Companion text can reveal quickly, but interrupts immediately for failures/questions or a newer message. The current complete text is available in reduced-motion mode.
- Execution output appears as soon as received. Never type out a completed command result artificially or hold events so a fast run looks slow.
- If the backend sends only a completion result, display it at completion and say output was received then. Do not claim per-character live stdout without an actual streaming source.
- Display known provider waits plainly; animation is not proof of model activity.
- Stop/cancel stays accessible while animation or output is arriving.

### Dense, coherent geometry

Use one compact project/account header, one working area, and one composer. Approximately one line between related steps; do not space every item like a landing page. Heading sizes stay close to body text. Speech bubble and composer hairlines are the main outlined elements.

Use a small inline command/subcommand selection above input. Show running duration and measured usage only where useful; no always-visible progress metrics column. Browser/proof/report details temporarily replace or expand selected content and can return to activity without stopping the run.

At narrow widths hide or collapse the companion before shrinking the input or obstructing output. User scrolling suspends auto-follow and reveals a New output action. Opening details preserves selection while new data arrives. A reduced-motion mode removes all decorative movement without removing state information.

### Native integration boundary

The local HTML preview currently demonstrates the desired pacing, disclosures, command picker, subcommand selection, compact composer, text reveal, output arrival, stop, and follow-tail interaction. It is a design tool, not a proposed browser-rendered production CLI. Final native implementation uses the existing single terminal renderer and real event associations.

The working native menu has been tightened, but the modern execution projection is not yet implemented. It must consume real event/operation identities and safe output, suppress internal module chatter in the primary view, preserve full diagnostics, and never invent streamed chunks or verification. Keep the existing working execution lifecycle unchanged while wiring presentation.

## 20. Pre-implementation layout corrections and Textual reaper adaptation

Latest missing-image correction: auto mode previously returned no image widget
when the terminal did not report Sixel/TGP support. This was not an occlusion or
black-background issue in that branch: no bitmap was emitted. Auto mode now
always mounts the available library's half-cell image fallback when graphics
are unavailable, with a visible Limited graphics notice; detected native image
support still takes precedence. This fallback is intentionally labelled and is
not advertised as full bitmap fidelity. The older no-fallback decision below is
superseded by the user's request not to leave the reaper absent.

VS Code workspace settings now enable terminal images and GPU rendering. They
apply only to this project, not global user settings. Reload the window/open a
new terminal to pick up renderer changes. VS Code's own source also requires
ConPTY v2 on Windows; enabling a setting cannot create missing OS support. Do
not force Sixel into a terminal that only supports another image protocol.
rendering_status() exposes safe mode/cache/frame/widget/geometry facts for local
diagnosis without prompts, keys, or account information.

Visibility/fixed-composer correction: the previous compact breakpoint hid the
whole companion below 90 columns or 28 rows, including the common 80x24 terminal.
Compact mode now reduces the image lane and hides only the large speech bubble;
narrower screens retain a smaller image. The composer is bottom-docked again.
Activity alone scrolls. Notices and the slash drawer grow above the input, so
neither a selection change nor a multi-line error shifts the input row. A compact
context strip above input provides the next interaction hint. Headless layout
checks at 120x40, 80x24 and 48x22 confirmed a nonzero, unclipped Sixel image region
and stable input coordinates with notices and slash suggestions open. These are
geometry checks, not visual confirmation in the user's terminal. Full bitmap
display still requires actual terminal graphics support.

Rendering correction: the first native adaptation downsampled each 192x208 frame
to just 18x20 source pixels and drew half-block text. That loses detail and is no
longer the default. reaper_widget.py now retains complete RGB frames and passes
them to textual-image's native bitmap widget. Auto mode accepts detected Sixel
or TGP support; it does not silently substitute unreadable text pixels. Explicit
WIZARD_REAPER_RENDERER=halfcell remains a labelled user-selected approximation,
not full rendering. Unsupported/missing graphics produce an explanation.

The optional tui extra includes textual-image 0.14.x on Python 3.12+ (the
library's current Python requirement). Normal core/legacy CLI Python 3.11
support remains unchanged. The library probes before Textual owns input, handles
placement/clipping itself, and receives PIL frames through its supported image
property. No raw bitmap escape sequences are written by Wizard.

WIZARD_REAPER_RENDERER=sixel or tgp is an explicit override only for a terminal
known to support that protocol. Windows Terminal 1.22+ supports Sixel; ordinary
Windows Console is different. Headless SVG screenshots cannot prove bitmap
display quality. Local headless validation mounted a Sixel widget with intact
192x208 frames; final visual quality needs the user's graphics-capable terminal.

Keyboard correction: the initial shell focused input while up/down bindings only
handled slash suggestions. It now focuses the command list initially, then the
subcommand list, then the composer. Arrows move focused menu items and scroll
them into view; Enter selects; normal Tab navigation remains available. Slash
navigation still takes precedence while its drawer is open. Page Up/Page Down
and Ctrl+Home/Ctrl+End scroll the content without changing the input draft.
Command rows are two terminal lines, and content height is bounded by its actual
contents instead of forcing a large gap between the command list and composer.

Latest native revision: the user explicitly requested the supplied reaper rather than the original placeholder. The requested sprite sheet is now downloaded to the local user cache only and rendered by reaper_widget.py. It is not a repository/package asset and is not a claim of redistribution permission. The Textual preview uses the real cached idle/wave frames, at 18 terminal columns by 10 rows, with a source credit. The old placeholder remains only in older design studies, not in the new native shell.

The native menu is now a vertical stack. Selecting a command replaces the family list with that command's subcommands; selecting a subcommand hides the list and explains the selection. Commands returns to the family list. The companion explains both levels. The composer accepts an empty intent for a valid selected check. A real registry-backed slash drawer supports click, up/down, tab/enter completion, and escape dismissal without submitting a project action.

The latest requested palette is now ember + ice rather than the earlier all-violet study: near-black background, #DDEEF3 ice primary, #8CBFCF cool accents, and #E7A168 warm focus. The header shows "Run. Observe. Verify." plus the project name, avoiding wizard · wizard. A small managed colour-pixel animation occupies the identity region; command transitions fade briefly and the actual reaper waves. Motion can be disabled in the UI. These are native local display changes, not simulated verification.

The earlier "no external artwork cached" statement below describes the prior planning pass only. Current explicit asset setup is python -m wizard.cli.tui.reaper_widget; it fetches one fixed official URL, bounds/validates the WebP, and caches it outside the repository. Opening or rendering the UI does not download anything. If missing, it says artwork is not cached rather than inventing another reaper or launching Chromium.

### Layout corrections applied to the local motion study

- Remove the forced 530px minimum canvas height and the assumption that the preview notice is always exactly 33px. Use a flex page with the real remaining height, so short windows scroll activity instead of pushing the composer below the viewport.
- Align header, picker, activity, and composer on one inset. Use a compact header, smaller command spacing, and tighter output line-height.
- Reduce the companion lane to 180px in the browser design reference, with a matching 192px composer reservation including its gap. Final Textual dimensions must use terminal cells, not copy browser pixels.
- Keep one scroll owner for activity. Long titles/output wrap without widening the canvas; the composer remains outside that scroll area.
- At narrower widths reduce picker columns; at the smallest width remove the companion reservation entirely. At short heights shrink the character and hide optional recent-check copy. Do not scale terminal fonts to fit.
- Hide/collapse optional guidance before obstructing actions, output, or input. These CSS corrections are a browser design prototype, not proof of a completed native terminal layout.

### Can the supplied HTML reaper run in Textual?

Not directly. Textual does not execute browser custom elements or arbitrary CSS/JavaScript. Port the small component behavior to a native widget, and render approved image frames rather than embedding a browser.

Inspected 2026-10-22: https://saasisdead.si/reaper/v1.js loads /mascot/spritesheet.webp and a fallback image. The CSS describes 8 columns and 11 rows of frames, with 192:208 frame aspect ratio. Idle, walk, and wave use different sequences; walking uses eight frames over approximately 720ms, waving approximately 840ms, and idle approximately 5.6 seconds. Confirm actual image dimensions before cutting frames; percentages are not enough to guess pixel coordinates.

The story="support" setting selects the website's canned open-source message. It is not an AI agent, does not connect to /btw, and is not an event-stream subscription. Wizard needs its own messages derived from real events. Do not copy a remote website's fixed positioning, 4-second arrival delay, or stock speech into native execution behavior.

### Smallest native design

Use a compound Textual widget with a speech Static, an image/half-cell view, and explicit state: hidden, arriving, idle, working, waiting, attention, leaving. It owns display only. It receives safe messages and pose names from the existing UI event projection and can emit dismiss/open-side-chat requests; it cannot submit tools or change Runtime state.

- Load permitted assets locally, decode once with Pillow, and cache a bounded set of appropriately sized frames.
- Use one managed timer only while an animation/reveal is active. Stop/pause it on hidden, reduced-motion, unmount, and application exit.
- Update only the affected widget region. Do not rebuild the activity transcript for every mascot frame.
- Recreate a small speech border and tail in native layout; no raw HTML interpreter.
- Native offset/visibility changes supply entrance/dismissal. Keep space reserved to avoid output overlap.
- A latest-message-wins reveal prevents stale queued speech. Error/questions appear immediately. Plain output and reduced-motion modes show the full text.
- Dismissal can use the existing local UI preferences, without remote tracking or a new service.
- Do not claim final pixel fidelity on unsupported terminals or invent missing art poses such as a book turn that the actual source does not provide.

### Existing library option

https://github.com/lnqs/textual-image provides Textual widgets and Rich renderables for Kitty/TGP, Sixel, and half-cell/Unicode output. Its documented support matrix includes Windows Terminal (Sixel, version 1.22+) and notes that ordinary Windows Console differs. This is a candidate to reuse instead of building an image-protocol implementation. Its LGPL-3.0 licensing and packaged dependencies need review before selecting it; no package has been installed by this planning pass.

Do not assume the image widget automatically plays the complete reaper animation or is reliable on every terminal. Verify its frame update API, animation cost, resize/scroll behavior, and actual target terminal first. A small half-cell Textual widget reusing Pillow/Rich is the alternative when sufficient, not a second simultaneous terminal renderer.

### Framework decision checkpoint

The existing running UI is Prompt Toolkit. A Textual-native replacement would replace its terminal ownership, not mount Textual inside it. Reuse runtime/account/client logic behind the replacement. Prove a local welcome + picker + input + companion layout without services before making it the default. Do not install or migrate purely because the word "HTML" was used.

### Reuse boundary

The author's page offers a website embed, but no clear licence permitting redistribution of the mascot sprite sheet was established during inspection. A CC0 reference found in the page concerns a separate open-source-alternatives dataset, not permission for the mascot. Do not treat that reference as an artwork licence.

Before bundling exact frames, establish redistribution/modification permission or an explicit applicable licence. Until then keep third-party assets out of committed/package data and use the clearly identified original placeholder, or no mascot. The native adapter can be designed independently of that asset decision.

No third-party artwork, browser widget, Textual package, or image library was installed/bundled during this pass. It updates design feasibility and layout only.

### Current implementation: one execution transcript

The native interface renders actions, bounded actual execution output, browser summaries and the final Markdown report in one scrolling flow. There are no separate activity, terminal or browser-result panels. New events follow the viewport only while the user is already at the bottom. Active action text uses a native colour sweep; reduced motion disables it. This is a terminal animation, not a Lottie player.

Usage reuses `wizard.cli.display.usage.counter(..., compact=True)` without a new accounting format, immediately above the intent input. Provider usage events remain authoritative; animation never fabricates token increments.

The API's active engine is `control/verification.py`. It now emits bounded `tool.observed` previews after real persisted execution, including readiness reads. Fresh process reads are deduplicated within their goal rather than across different goals. Explorer cannot select an evaluation response while the current proof remains unverified. These changes preserve goal-scoped proof instead of treating a model statement as execution evidence.
