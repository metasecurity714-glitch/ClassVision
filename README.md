# ClassVision — Face Attendance (adult consent build)

## Important
This demo is intended only for adult students who have explicitly consented to biometric enrollment and face-based attendance. Do not enroll anyone without informed consent. Provide a non-biometric attendance alternative.

No face-recognition system is error-free. Lighting, camera quality, pose, masks, similar-looking faces and enrollment quality can cause missed or incorrect matches. This build uses conservative matching thresholds and requires a stable match across multiple frames, but it can still make mistakes. Review records regularly.

## What it includes
- Adult student registration using name, ID and three face samples.
- In-browser face matching using face-api.js.
- Front/back camera selection.
- Repeated-frame confirmation before attendance is recorded.
- Ambiguous matches are left unmarked.
- Duplicate prevention per student per day.
- Today's and all-records CSV export.
- Student deletion and local data wipe.
- IndexedDB storage on the current browser/device.

## Publish on GitHub Pages
1. Download and extract the ZIP.
2. Upload `index.html`, `style.css`, `app.js`, and `README.md` to the repository root, replacing the old files.
3. In GitHub, open **Settings → Pages** and confirm the deployment source is your main branch and root folder.
4. Open the published `https://...github.io/.../` URL in Chrome.
5. Allow camera permission.

## Requirements and limitations
- HTTPS is required for camera access; GitHub Pages provides HTTPS.
- Internet is required to load face-api.js and its model weights from the CDN.
- This is a static, single-browser prototype. Student records and face descriptors stay in that browser's IndexedDB; they do not sync across devices and are not protected by server-side authentication.
- Clearing browser site data may delete the records. Export attendance regularly.
- The app does not upload camera frames or face descriptors to a server, but anyone with access to the unlocked browser profile may access local app data.
- For production use, obtain appropriate legal/privacy advice, use secure access controls, encryption and audited retention/deletion procedures. Consider a non-biometric option.
