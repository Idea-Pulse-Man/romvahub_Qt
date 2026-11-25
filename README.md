# romva hub (desktop app)

The Windows desktop app for bidders and admins. It's written in Qt (PySide6) and talks to the romva server (the
backend in `../backend`). It never connects to the database itself.

## What's in it

| Screen | What you do there |
|---|---|
| **Sign in** | Connect with **email and password** (admins also enter an authenticator code), or with **Profile tokens** (`rmv_…`). With tokens you add one per Profile, so one app can work on several Profiles. |
| **Home** | Today's numbers, what needs attention, and the Resume Maker at a glance |
| **Applications** | Every application, with these tabs: Draft · Ready to apply · Applied · Interviews · All. Each row has **↗ Open job**, **▶ Apply**, a clickable status (all statuses, with Undo) and **✓ Ready** links for the Resume and cover letter (a preview window with **PDF** and **Word (DOCX)** downloads). Tick Ready rows to **Apply to all**. Rows are paged: 5 / 10 / 100 per page, set in Settings. |
| **Resume Maker** | Start / Stop the Resume agent (`../resume_agent`) with ChatGPT, Claude or Gemini, see what is being made, and read the log |
| **Profiles** | Edit the Profiles you work on: personal, contact, links, experience, education, job-form and EEO answers, resume and cover letter prompts, template, and Avoid lists |
| **Settings** | Connection (email/password or tokens: add, remove, see "Revoked by admin"), rows per page, theme (light / dark / Windows), Chrome location, start with Windows |

Admins see every Profile, with an **All Profiles** choice and a Profile column. Their admin pages (Users, Tokens, AI
settings, Pipeline, Calendar) open on the website for now.

The app stays in the tray when the window is closed, so the Resume Maker keeps working. Right-click the tray icon and
choose Quit to close it.

## Run

```powershell
cd romvahub
python -m pip install -r requirements.txt
python main.py            # or: run.bat
python main.py --minimized  # start in the tray
```

You need:

- Python 3.10+
- For the Resume Maker: Node.js 20+ and the `resume_agent` folder next to this one. The first time, click
  **Install / Update** on the Resume Maker screen.
- For Apply: Google Chrome with the **Romva Apply (Alt+V)** extension (`../altv`, 3.5.7 or newer), signed in.

## Build for bidders and the VPS (one folder, nothing to install)

```powershell
cd romvahub
powershell -ExecutionPolicy Bypass -File build.ps1
```

It makes `dist\RomvaHub\` and `dist\RomvaHub.zip` (about 85 MB):

| Inside | What it is |
|---|---|
| `RomvaHub.exe` | The app, with Python and Qt inside |
| `agent\node.exe` | Node.js for the Resume Maker |
| `agent\src`, `agent\node_modules` | The Resume agent (`../resume_agent`), already installed |

Copy the folder (or unzip the zip) to any Windows PC and run `RomvaHub.exe`. The bidder only signs in: to romva
in the app, and once to ChatGPT / Claude / Gemini in the agent's Chrome window. The Resume Maker uses the
built-in agent automatically: no folder to choose, no Install / Update. It needs Google Chrome or Microsoft Edge
(Edge comes with Windows 10/11). Rebuild after changing the app or `resume_agent`.

The build PC needs Python, Node.js and npm. `run_pyinstaller.py` works around a bug in Python 3.10.0 that
otherwise stops PyInstaller.

## Where things are kept

| What | Where |
|---|---|
| Sign-in renew token, Profile tokens | Windows **Credential Manager**, encrypted by Windows for your Windows user (service `romvahub`) |
| Settings (theme, rows per page, token names, server) | Registry: `HKCU\Software\Romva\RomvaHub` |
| Resume agent's data and log | `%APPDATA%\RomvaHub\agent\` |

## How the pieces connect

- **Apply** opens `<server>/applications#romva-apply=<ids>` in Chrome. The Alt+V extension picks this up, opens each
  job in its own tab and fills the form. The bidder submits, and the row is marked Applied (with Undo).
- **Resume Maker** runs `node resume_agent/src/agent.js` (in the built app: `agent\node.exe agent\src\agent.js`):
  - In token mode it uses the chosen Profile's token.
  - In account mode it uses the app's 15-minute sign-in, and the app sends it a renewed one on stdin
    (`ROMVA_TOKEN_STDIN=1`).
- **The server must have** the token and Profile updates from backend commit "Desktop app: tokens open their whole
  Profile…":
  - Token mode needs the wider token routes.
  - Bidders saving a Profile need `PUT /api/profiles/:id`.
  - The Draft / Ready tabs need the `hasResume` filter.
