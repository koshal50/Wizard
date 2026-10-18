> Historical preview documentation. The live integration now supersedes this document; see [CLI_AUTH_INTEGRATION.md](./CLI_AUTH_INTEGRATION.md).

# Wizard CLI authorization UI

This is a frontend preview only. No CLI authorization requests, authentication
callbacks, codes, timers, credentials, or success detection are implemented.

## Routes and navigation

- `/cli/authorize`: entry page. Continue opens the existing
  `/login.html?returnTo=%2Fcli%2Fconnect` screen.
- Existing `/login.html`, `/register.html`, and `/forgot-password.html` keep the
  fixed `returnTo=/cli/connect` hint when navigating between auth screens.
  Only this exact destination enables the CLI navigation notice. Other values
  are ignored. Ordinary authentication visits keep their existing UI.
- The notice offers **Preview the connection screen**, explicitly independent
  of authentication. It does not intercept form submission or imply sign-in.
- `/cli/connect`: placeholder for the future authorization code and expiration.
  No fake code, countdown, or copy action is shown.
- `/cli/complete`: separately labeled completion preview using the reusable
  `CliCompletionPreview` component. Opening it does not grant access or assert
  that a connection succeeded.
- Cancel and website links return to `/`.

## Existing authentication assets

The original HTML pages, `css/wizard.css`, and `js/auth.js` were relocated to
Next.js's `public` directory so their existing URLs resolve in this app.
The forms, validation, password controls, actions, and original stylesheet are
unchanged. A separate script and stylesheet add navigation only for the fixed
CLI return hint. No additional dependencies were introduced.

The new App Router pages follow the existing policy/footer ocean palette,
Inter Tight and JetBrains Mono fonts, rounded panels, and pill links. Their
layout is shared under `app/cli/layout.tsx`; no homepage changes are required.

## Future integration dependency

The repository's auth HTML forms currently submit to `/login`, `/register`, and
`/forgot-password`; this branch contains no handlers for those actions or OAuth
callback. Automatic navigation after real authentication cannot be completed
here without implementing the excluded authentication work.

The runtime integration must explicitly consume the fixed return hint after
verified authentication, supply a real code and expiration to the connection
UI, and render completion only after a confirmed backend response. The preview
route/link must then be replaced or gated as appropriate. A URL parameter alone
must never establish authentication or authorization.

## Manual checks

1. Open `/cli/authorize`, continue to sign-in, and switch to registration and
   password reset. Confirm the CLI hint and preview navigation persist.
2. Open the auth pages without a query and with an unrelated `returnTo` value.
   Confirm no CLI notice appears and existing form controls still work.
3. Follow the connection and completion preview links and each cancel link.
4. Check narrow mobile, tablet, and desktop widths and keyboard focus visibility.
5. Do not submit credentials or interpret any preview as an authorized session.

## Validation results

- Supabase was removed from the homepage and project dependencies. Development
  startup, production build, and HTTP checks pass without Supabase environment variables. Contact
  form submission now reports that sending is unavailable; it sends no data.
- `npx tsc --noEmit`, navigation-script syntax, and patch whitespace checks passed.
- Local HTTP checks returned 200 for the homepage, all three CLI pages, all
  existing auth pages, their styles/scripts, and privacy/terms navigation.
- Navigation checks passed for the fixed return hint, auth-page links, cancel
  links, and ignoring unrelated return URLs. Original auth files were compared
  against Git and match after removing the two new navigation asset imports.
- Lint could not run: `next lint` prompts to configure ESLint because the
  repository has no ESLint configuration. The build reports ten existing CSS
  warnings in the unchanged `app/globals.css`.
- Browser visual, keyboard, and viewport verification could not be completed:
  no connected browser was available, and the native computer-use pipe was
  unavailable. Responsive utilities and focus styles are implemented, but require
  a browser review at mobile, tablet, and desktop sizes.
- Existing dependencies were installed in this project's ignored `node_modules`
  only. No global package installation or new dependency was needed.
