# Face Detection & Recognition Attendance System

![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)
![OpenCV](https://img.shields.io/badge/OpenCV-4.8%2B-green.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

A real-time **Face Detection & Recognition Attendance System** built in Python using **OpenCV**, **face_recognition (`dlib`)**, **NumPy**, **pandas**, **openpyxl**, and a **Tkinter GUI**. It registers students or employees via webcam, performs real-time facial recognition with blink-based anti-spoofing, prevents duplicate daily entries, and exports styled daily/monthly Excel (`.xlsx`) reports.

## Key Features

- **1-Click Face Registration:** Captures 10–20 face samples via webcam with a live on-screen progress indicator, saves raw images to `dataset/<ID>_<Name>/`, extracts 128-D facial encodings, and stores them in `encodings/encodings.pkl`.
- **Real-Time Live Attendance:** Detects and matches faces in real time, logging **S.No, ID, Name, Date, Time, and Status** automatically.
- **Zero Duplicate Marking:** Ensures each person is marked **only once per calendar day**.
- **Unknown Face Handling:** Displays a red `"Unknown"` bounding box for unregistered individuals without marking attendance.
- **Automated Excel Workbooks (`openpyxl` + `pandas`):**
  - Creates a monthly workbook (`attendance/Attendance_YYYY_MM.xlsx`) with a dedicated sheet for each date (`YYYY-MM-DD`).
  - Generates a complete **Present & Absent Roster Report** for any selected date and exports it to a formatted `.xlsx` file.
- **Built-In Security & Add-Ons:**
  - **Admin Password Protection:** Locks face registration behind an admin login (`admin123` by default, or configurable via `ATTENDANCE_ADMIN_PASS`).
  - **On-Time / Late Cutoff Classification:** Automatically marks arrivals as `Present` or `Present (Late)` based on a configurable cutoff time (default `09:30:00`).
  - **Blink Anti-Spoofing (Liveness Detection):** Computes the Eye Aspect Ratio (EAR) from 68-point facial landmarks to verify eye blinking and block photo/screen spoofing.
- **Production Error Handling:** Gracefully handles missing/busy webcams, frames with zero or multiple faces, and `PermissionError` if the target Excel workbook is open in Microsoft Excel (automatically writes to a timestamped backup `.xlsx` so zero records are lost).

## Repository Structure

```text
face-attendance-system/
├── attendance_system.py       # Main GUI application & recognition/Excel engine
├── requirements.txt           # Python dependencies
├── README.md                  # Documentation, setup guide, & accuracy tips
├── LICENSE                    # MIT License
├── .gitignore                 # Ignores private biometric data & virtualenvs
├── dataset/                   # Captured face images per person (tracked via .gitkeep)
│   └── .gitkeep
├── encodings/                 # Serialized 128-D encodings & user registry CSV
│   └── .gitkeep
└── attendance/                # Monthly Excel logs & exported Present/Absent reports
    └── .gitkeep
```

## Step-by-Step Setup & Installation

### 1. Clone the Repository & Create a Virtual Environment

```bash
git clone https://github.com/<your-username>/face-attendance-system.git
cd face-attendance-system

# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies (Including Windows `dlib` Guide)

Because `face_recognition` depends on `dlib` (C++), Windows users should follow one of the two methods below:

#### Option A: Visual Studio C++ Build Tools + CMake (Recommended on Windows)
1. Install [CMake](https://cmake.org/download/) and select **"Add CMake to the system PATH for all users"**.
2. Install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) and check the **"Desktop development with C++"** workload.
3. Restart your terminal, activate `venv`, and run:
   ```bash
   pip install --upgrade pip setuptools wheel cmake
   pip install -r requirements.txt
   ```

#### Option B: Conda Pre-Built Binary Route (No C++ Compiler Needed)
```bash
conda install -c conda-forge dlib
pip install -r requirements.txt
```

### 3. Run the Application

```bash
python attendance_system.py
```

To run the automated headless verification test (verifies directory creation, duplicate prevention, late cutoff logic, and `.xlsx` generation):

```bash
python attendance_system.py --self-test
```

## How to Use the GUI

1. **Unlock Admin Mode:** Click **Admin Login (Locked)** in the top-right banner and enter `admin123` (or set your own password via the `ATTENDANCE_ADMIN_PASS` environment variable).
2. **1. Register Face:** Enter a unique Student/Employee ID (e.g., `EMP101`) and Full Name. Look at the webcam while it captures 15 samples across slight head movements.
3. **2. Start Attendance (Live):** Starts the real-time recognition feed. Blink once when prompted to verify liveness and log attendance. Press `Q` or `ESC` to close the camera window.
4. **3. View Attendance List:** Enter any `Target Date (YYYY-MM-DD)` and filter the table by **All (Present + Absent)**, **Present Only**, or **Absent Only**.
5. **4. Export to Excel:** Exports a styled `.xlsx` report listing all Present and Absent registered users for the chosen date.

## Error Handling Summary

| Error Condition | System Behavior |
| :--- | :--- |
| **No Webcam / Camera Busy** | Validates `cv2.VideoCapture.isOpened()` prior to capture and displays a troubleshooting dialog to check camera connections or switch the **Webcam Device Index** (`0`–`4`). |
| **No Face / Multiple Faces Detected** | Displays an live overlay banner (`No face detected!` or `Multiple faces detected!`) and pauses sample capture until a single clear face is visible. |
| **Excel File Open While Saving** | Catches `PermissionError` when writing to `.xlsx`, saves the attendance sheet to `attendance/Attendance_Backup_<Date>_<Timestamp>.xlsx`, and notifies the user so no attendance data is ever lost. |

## Tips to Improve Recognition Accuracy

- **Even Frontal Lighting:** Place the webcam where light illuminates the face evenly from the front. Avoid strong backlighting (such as bright windows behind the person), which casts shadows over facial landmarks.
- **Capture 15–20 Varied Registration Samples:** During registration, slowly tilt your head slightly left, right, up, and down, and alternate between a neutral expression and a slight smile. If a person wears glasses intermittently, capture half of the images with glasses and half without.
- **Tune the Match Tolerance (`0.45` – `0.55`):** The system defaults to a Euclidean distance threshold of **`0.50`** (stricter and more accurate than the standard `0.60` default). Lower it to **`0.45`** to eliminate false positives in large rosters, or increase it to **`0.55`** in rooms with variable lighting.

## Publishing to GitHub

If you downloaded these files directly, initialize and push your repository with:

```bash
git init
git add .
git commit -m "Initial commit: Face Detection & Recognition Attendance System"
git branch -M main
git remote add origin https://github.com/<your-username>/face-attendance-system.git
git push -u origin main
```

## License

This project is licensed under the [MIT License](LICENSE).
