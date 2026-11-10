# ClassVision — Chrome Edition

A small browser-only QR attendance demo. No Python, Flask, server database, or app installation is required.

## Run on Android Chrome

Camera access is blocked on ordinary `file://` pages. Publish these four files to a static HTTPS host to enable camera access.

### Publish with GitHub Pages
1. Create a GitHub repository named `classvision`.
2. Upload `index.html`, `style.css`, `app.js`, and `README.md` to its root.
3. Open **Settings → Pages**.
4. Select **Deploy from a branch**, choose `main` and `/ (root)`, then save.
5. Open the published `https://YOUR-USERNAME.github.io/classvision/` link in Chrome.
6. Register a test student, open their QR pass, and download the QR image.
7. Open QR Scanner → Start camera. Allow camera permission. Show the QR image on another screen or print it.

## Features
- Student registration, search, and deletion
- Individual QR generation, download, and print
- Rear-camera QR scanning
- Unknown QR rejection and duplicate prevention per date
- Daily dashboard and date-filtered records
- CSV export (opens in Excel)

## Storage and privacy
- Student and attendance data are stored in this browser's IndexedDB. It is not uploaded or synced.
- Data may be lost if Chrome site data is cleared, so export backups regularly.
- There is no login, encryption, or access control. This is a personal-testing demo, not a secured institutional system.
- QR passes can be copied/shared; scanning a pass does not prove who is holding it.
- Use fictional test data first. Before using real students, obtain appropriate institutional approval and consent, and provide another attendance option.
- QR content is a random ID, not the student's name or roll number.

## Internet
The QR generator and camera scanner libraries load from CDNs, so the first load needs internet. Camera access requires HTTPS (or localhost) and Chrome camera permission.
