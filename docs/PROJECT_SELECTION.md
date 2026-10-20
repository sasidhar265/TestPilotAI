# Sign-in and project selection

After successful sign-in, `/select-project` automatically opens **Choose your project**
as a modal pop-up. The user explicitly chooses an accessible project before entering the
delivery workspace. A single available
project is still an explicit choice. Existing project creation and selection controls are
hidden on the working screens, and the top bar no longer displays project details.
The profile menu provides **Change project**, which opens the same modal over the current
workspace without navigating away. Cancel or Escape closes this switching modal and restores
focus to the profile control without changing the current project or unsaved input.
After a fresh sign-in, choosing a project or signing out is required; Escape and backdrop
clicks cannot bypass that choice.

The selection page shares the application's brand, typography, card styling and form
geometry. Its appearance control uses the same light/dark/system preference as sign-in
and the workspace. The layout adapts to mobile, with focus contained inside the native
modal dialog. Its loading, empty, creation and error states remain inside the pop-up.

Project lists come from the existing authenticated, membership-filtered SDLC API. Before
opening a project, the selection page retrieves its snapshot so the server verifies access
again. Browser storage never grants project membership or changes role permissions.

The active project is stored per account in the browser tab's session storage. Every new
sign-in clears previous project selection and browser draft context. Reloading an existing
workspace preserves its selected project; a new tab requires selection. Choosing another
project clears the previous project's browser draft context before opening the workspace.
The application rechecks project availability when opening or reloading the workspace.

## Empty accounts and creation

Accounts without projects see an explicit empty state. Roles already permitted by the server
to create projects can create one on the selection page. Other users are directed to ask
an administrator or project owner for membership. Creating a project does not change the
user's role or allow access to someone else's projects.

## Error recovery

- Invalid credentials keep the user on sign-in with the existing credential error.
- Expired sessions return to sign-in with an expiration message.
- Connection failures, timeouts, unreadable responses and service errors show an inline
  error and a retry action on project selection.
- Missing projects and revoked access do not open the workspace. Users can reload the
  accessible project list and choose again.
- An unavailable saved project returns to project selection with an explanation.
- Blocked session storage explains how to enable site storage before continuing.
- Requests disable their controls to prevent concurrent submissions. A successfully created
  project remains selectable if opening it fails, so users can retry opening it.
- Delivery-screen save errors remain visible in an alert outside the hidden project controls.
- Failure to load the switching pop-up shows a recoverable workspace alert and leaves the
  selected project intact. Lazy-loaded assets and requests have timeouts.
- Switching projects prevents the departing page from writing its old browser draft into
  the new project's session during navigation.

The selection page and workspace use the existing server authentication and membership
checks. No API contract or approval gate changed. Guest preview remains separate from
project selection and cannot acquire project access through this page.
