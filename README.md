# ClassVision — Smart Face Attendance

A browser-based attendance prototype with student registration, live face matching, named bounding boxes, session-wise attendance and CSV export.

## Run it
1. Download and extract this ZIP.
2. Open the folder in VS Code or another editor.
3. Serve the folder over HTTPS or localhost. For example, with Python installed:
   ```bash
   python -m http.server 8000
   ```
4. Open `http://localhost:8000` in Chrome or Edge.
5. Allow camera permission. The face recognition models load from a CDN, so internet is required.

Opening `index.html` directly using `file://` may block camera access. GitHub Pages is also supported because it serves over HTTPS.

## Features
- Student fields: full name, roll number, enrolment number and branch.
- Capture five face descriptor samples per student.
- Live face detection with green recognized, amber uncertain and red unknown boxes.
- Name and roll number appear above confidently matched faces.
- Attendance session name is required before scanning.
- Repeated attendance is prevented for the same student, date and session.
- Student and attendance CSV exports.
- Student face descriptors stored in browser IndexedDB; attendance records stored in browser localStorage.

## Accuracy notes
This is a prototype, not a certified biometric attendance system. Face matching can be affected by lighting, camera quality, pose, occlusion and similar-looking faces. The matching threshold is a configurable heuristic, not a guarantee. Test in your actual classroom and maintain a manual correction/attendance alternative. The app uses face-api.js descriptor matching, not a trained institutional identity model.

## Privacy and security
- Obtain explicit, informed consent before collecting face data.
- Explain purpose, retention period, access, and deletion procedure.
- Do not use this prototype for high-stakes decisions without independent validation and legal/privacy review.
- Data is stored only in the current browser profile on the device. Clearing site data removes it; it does not sync to a server.
- Do not share a browser profile or device containing student biometric data.
- This prototype does not include authentication, encryption at rest, server backup, or an administrator deletion workflow.

## Files
- `index.html` — application layout
- `style.css` — responsive dark UI
- `app.js` — camera, face matching, browser storage and exports
