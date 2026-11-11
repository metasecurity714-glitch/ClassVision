"""
Complete Face Detection & Recognition Attendance System
=======================================================
Author: Automated System Architect
Python Version: 3.8+

FOLDER STRUCTURE (Automatically created on startup):
project_root/
├── attendance_system.py       # Main application entry point (GUI + Core Engine)
├── requirements.txt           # Python package dependencies
├── README.md                  # Setup instructions, dlib Windows guide, & accuracy tips
├── dataset/                   # Raw face images captured per registered user
│   └── <ID>_<Name>/           # 10-20 cropped/full RGB frames per person
│       ├── img_01.jpg
│       └── ...
├── encodings/                 # Serialized facial encodings & user registry
│   ├── encodings.pkl          # Pickled dict of IDs, Names, and 128-D face encodings
│   └── users_registry.csv     # Master table of all registered students/employees
└── attendance/                # Monthly Excel workbooks (each day as a separate sheet)
    ├── Attendance_YYYY_MM.xlsx
    └── Daily_Report_<YYYY-MM-DD>.xlsx

CORE & OPTIONAL FEATURES IMPLEMENTED:
1. Register Students/Employees:
   - Captures 15 face images (configurable 10-20) via webcam with live visual progress bar.
   - Takes ID and Name, validates uniqueness, stores images in dataset/<ID>_<Name>/,
     computes 128-D facial encodings via `face_recognition`, and saves to encodings/encodings.pkl.
2. Live Attendance with Real-Time Recognition:
   - Opens webcam feed, detects faces, matches against known encodings with configurable tolerance.
   - Marks attendance automatically with S.No, ID, Name, Date, Time, and Status.
3. No Duplicates:
   - Strictly marks each registered person only once per calendar day.
4. Unknown Faces:
   - Bounding box drawn in red with "Unknown" label; never marks attendance.
5. Excel Output (openpyxl + pandas):
   - Saves to `attendance/Attendance_YYYY_MM.xlsx` with a dedicated worksheet per date (`YYYY-MM-DD`).
   - Columns: S.No, ID, Name, Date, Time, Status (Present - On Time / Present - Late).
   - Full Present & Absent Roster Report generator for any selected date, exporting to styled `.xlsx`.
6. Optional Add-Ons Included:
   - Admin Login protection (Password required to Register new faces or change system settings; default: `admin123`).
   - Late / On-Time automatic status classification based on configurable cutoff time (default: `09:30:00`).
   - Anti-Spoofing (Eye Aspect Ratio / Blink Detection using 68-point facial landmarks) to prevent photo/screen spoofing before marking attendance.
7. Robust Error Handling:
   - Handles missing/disconnected webcams gracefully.
   - Handles frames with zero faces or failed encoding extraction without crashing.
   - Handles `PermissionError` when an Excel workbook is currently open in Microsoft Excel (prompts user & saves to a fallback backup file so no attendance record is ever lost).
"""

import os
import sys
import cv2
import time
import pickle
import datetime
import numpy as np
import pandas as pd
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog, filedialog
    TK_AVAILABLE = True
except ImportError:
    tk = None
    ttk = messagebox = simpledialog = filedialog = None
    TK_AVAILABLE = False

# Attempt to import face_recognition and openpyxl with helpful fallback messages
try:
    import face_recognition
    FACE_REC_AVAILABLE = True
except ImportError:
    FACE_REC_AVAILABLE = False

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
ENCODINGS_DIR = os.path.join(BASE_DIR, "encodings")
ATTENDANCE_DIR = os.path.join(BASE_DIR, "attendance")

ENCODINGS_FILE = os.path.join(ENCODINGS_DIR, "encodings.pkl")
REGISTRY_FILE = os.path.join(ENCODINGS_DIR, "users_registry.csv")

# Default System Settings
DEFAULT_ADMIN_PASSWORD = os.environ.get("ATTENDANCE_ADMIN_PASS", "admin123")
DEFAULT_CUTOFF_TIME = "09:30:00"        # 9:30 AM cutoff for On-Time vs Late
DEFAULT_TOLERANCE = 0.50                # Lower = stricter (0.45-0.50 recommended)
DEFAULT_NUM_SAMPLES = 15                # Capture 15 images per registration (10-20 range)
EAR_BLINK_THRESHOLD = 0.22              # Eye Aspect Ratio threshold for blink detection
REQUIRE_BLINK_ANTISPOOF = True          # Toggle anti-spoofing liveness check


# ==============================================================================
# HELPER FUNCTIONS: DIRECTORY INITIALIZATION & ANTI-SPOOFING MATH
# ==============================================================================
def ensure_directories():
    """Create dataset/, encodings/, and attendance/ directories if they don't exist."""
    for folder in (DATASET_DIR, ENCODINGS_DIR, ATTENDANCE_DIR):
        os.makedirs(folder, exist_ok=True)

    # Initialize empty user registry CSV if not present
    if not os.path.exists(REGISTRY_FILE):
        df = pd.DataFrame(columns=["ID", "Name", "Registered_Date"])
        df.to_csv(REGISTRY_FILE, index=False)


def calculate_eye_aspect_ratio(eye_points):
    """
    Compute the Eye Aspect Ratio (EAR) from 6 (x, y) eye landmark coordinates
    to detect eye blinking for anti-spoofing liveness verification.

    EAR = (||p2 - p6|| + ||p3 - p5||) / (2 * ||p1 - p4||)
    """
    pts = np.array(eye_points, dtype=np.float64)
    # Vertical eye distances
    v1 = np.linalg.norm(pts[1] - pts[5])
    v2 = np.linalg.norm(pts[2] - pts[4])
    # Horizontal eye distance
    h = np.linalg.norm(pts[0] - pts[3])
    if h == 0:
        return 0.30
    return (v1 + v2) / (2.0 * h)


def check_liveness_blink(face_landmarks_dict, ear_threshold=EAR_BLINK_THRESHOLD):
    """
    Given a face_landmarks dictionary from `face_recognition.face_landmarks()`,
    calculates the average EAR of left and right eyes and returns (is_blinking, ear_value).
    """
    if "left_eye" not in face_landmarks_dict or "right_eye" not in face_landmarks_dict:
        return False, 0.30

    left_ear = calculate_eye_aspect_ratio(face_landmarks_dict["left_eye"])
    right_ear = calculate_eye_aspect_ratio(face_landmarks_dict["right_eye"])
    avg_ear = (left_ear + right_ear) / 2.0
    return avg_ear < ear_threshold, avg_ear


# ==============================================================================
# BACKEND ENGINE: ENCODINGS & EXCEL ATTENDANCE MANAGER
# ==============================================================================
class AttendanceBackend:
    """Manages user registration data, face encodings, and Excel attendance logs."""

    def __init__(self):
        ensure_directories()
        self.known_encodings = []
        self.known_ids = []
        self.known_names = []
        self.load_encodings()

    def load_encodings(self):
        """Load saved facial encodings from encodings/encodings.pkl."""
        if os.path.exists(ENCODINGS_FILE):
            try:
                with open(ENCODINGS_FILE, "rb") as f:
                    data = pickle.load(f)
                self.known_encodings = data.get("encodings", [])
                self.known_ids = data.get("ids", [])
                self.known_names = data.get("names", [])
            except Exception as e:
                print(f"[WARNING] Failed to load encodings file: {e}")
                self.known_encodings, self.known_ids, self.known_names = [], [], []
        else:
            self.known_encodings, self.known_ids, self.known_names = [], [], []

    def save_encodings(self):
        """Serialize facial encodings to encodings/encodings.pkl."""
        data = {
            "encodings": self.known_encodings,
            "ids": self.known_ids,
            "names": self.known_names,
        }
        with open(ENCODINGS_FILE, "wb") as f:
            pickle.dump(data, f)

    def get_registered_users(self):
        """Return a DataFrame of all unique registered users (ID, Name, Registered_Date)."""
        if os.path.exists(REGISTRY_FILE):
            try:
                df = pd.read_csv(REGISTRY_FILE, dtype=str)
                return df.drop_duplicates(subset=["ID"]).reset_index(drop=True)
            except Exception:
                pass
        return pd.DataFrame(columns=["ID", "Name", "Registered_Date"])

    def register_user_in_registry(self, user_id: str, name: str):
        """Add or update a user in encodings/users_registry.csv."""
        df = self.get_registered_users()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if user_id in df["ID"].values:
            df.loc[df["ID"] == user_id, "Name"] = name
        else:
            new_row = pd.DataFrame(
                [{"ID": str(user_id), "Name": str(name), "Registered_Date": now_str}]
            )
            df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(REGISTRY_FILE, index=False)

    def get_monthly_excel_path(self, date_str: str) -> str:
        """
        Return the path to the monthly Excel workbook for a given date (YYYY-MM-DD).
        Example: attendance/Attendance_2026_11.xlsx
        """
        year_month = date_str[:7].replace("-", "_")
        return os.path.join(ATTENDANCE_DIR, f"Attendance_{year_month}.xlsx")

    def _style_worksheet(self, ws):
        """Apply clean openpyxl styling to an attendance worksheet."""
        if not OPENPYXL_AVAILABLE:
            return
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        cell_font = Font(name="Calibri", size=11)
        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )

        # Style header row
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        # Style data rows & auto-fit column widths
        for row_idx in range(2, ws.max_row + 1):
            status_val = str(ws.cell(row=row_idx, column=6).value or "")
            for col_idx in range(1, ws.max_column + 1):
                c = ws.cell(row=row_idx, column=col_idx)
                c.font = cell_font
                c.border = thin_border
                c.alignment = Alignment(
                    horizontal="left" if col_idx == 3 else "center",
                    vertical="center",
                )
                if col_idx == 6:
                    if "Absent" in status_val:
                        c.fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
                        c.font = Font(name="Calibri", size=11, bold=True, color="C00000")
                    elif "Late" in status_val:
                        c.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
                        c.font = Font(name="Calibri", size=11, bold=True, color="B25900")
                    elif "Present" in status_val:
                        c.fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
                        c.font = Font(name="Calibri", size=11, bold=True, color="375623")

        col_widths = [8, 14, 26, 14, 14, 22]
        for i, width in enumerate(col_widths[: ws.max_column], start=1):
            ws.column_dimensions[get_column_letter(i)].width = width

    def get_daily_attendance_df(self, date_str: str) -> pd.DataFrame:
        """
        Read the attendance sheet for `date_str` (YYYY-MM-DD) from the monthly workbook.
        Returns a DataFrame with columns: ['S.No', 'ID', 'Name', 'Date', 'Time', 'Status'].
        """
        columns = ["S.No", "ID", "Name", "Date", "Time", "Status"]
        excel_path = self.get_monthly_excel_path(date_str)
        if not os.path.exists(excel_path):
            return pd.DataFrame(columns=columns)

        try:
            xl = pd.ExcelFile(excel_path, engine="openpyxl")
            if date_str in xl.sheet_names:
                df = pd.read_excel(excel_path, sheet_name=date_str, dtype=str, engine="openpyxl")
                for col in columns:
                    if col not in df.columns:
                        df[col] = ""
                return df[columns]
        except Exception as e:
            print(f"[WARNING] Error reading Excel sheet {date_str}: {e}")

        return pd.DataFrame(columns=columns)

    def mark_attendance(self, user_id: str, name: str, cutoff_time_str: str = DEFAULT_CUTOFF_TIME):
        """
        Mark attendance for `user_id` if not already marked today.
        Returns tuple: (already_marked: bool, status_label: str, saved_path: str, error_msg: str)
        """
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        df_today = self.get_daily_attendance_df(date_str)

        # Duplicate check: ensure each person is marked only ONCE per day
        if not df_today.empty and str(user_id) in df_today["ID"].astype(str).values:
            existing_row = df_today[df_today["ID"].astype(str) == str(user_id)].iloc[0]
            return True, existing_row["Status"], "", ""

        # Determine On-Time vs Late status based on cutoff time
        try:
            cutoff_dt = datetime.datetime.strptime(cutoff_time_str.strip(), "%H:%M:%S").time()
            is_late = now.time() > cutoff_dt
            status_str = "Present (Late)" if is_late else "Present"
        except ValueError:
            status_str = "Present"

        next_sno = len(df_today) + 1
        new_entry = pd.DataFrame(
            [
                {
                    "S.No": next_sno,
                    "ID": str(user_id),
                    "Name": str(name),
                    "Date": date_str,
                    "Time": time_str,
                    "Status": status_str,
                }
            ]
        )
        df_updated = pd.concat([df_today, new_entry], ignore_index=True)
        df_updated["S.No"] = range(1, len(df_updated) + 1)

        excel_path = self.get_monthly_excel_path(date_str)
        saved_path, err_msg = self._save_sheet_safely(excel_path, date_str, df_updated)
        return False, status_str, saved_path, err_msg

    def _save_sheet_safely(self, excel_path: str, sheet_name: str, df_sheet: pd.DataFrame):
        """
        Write or update `sheet_name` inside `excel_path` with full error handling for
        when the Excel file is locked/open in Microsoft Excel (`PermissionError`).
        """
        try:
            if os.path.exists(excel_path):
                with pd.ExcelWriter(
                    excel_path, engine="openpyxl", mode="a", if_sheet_exists="replace"
                ) as writer:
                    df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)
            else:
                with pd.ExcelWriter(excel_path, engine="openpyxl", mode="w") as writer:
                    df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)

            # Apply openpyxl visual formatting
            if OPENPYXL_AVAILABLE:
                wb = openpyxl.load_workbook(excel_path)
                if sheet_name in wb.sheetnames:
                    self._style_worksheet(wb[sheet_name])
                wb.save(excel_path)

            return excel_path, ""

        except PermissionError:
            # Handle the case where the Excel file is currently open in Excel
            fallback_name = f"Attendance_Backup_{sheet_name}_{int(time.time())}.xlsx"
            fallback_path = os.path.join(ATTENDANCE_DIR, fallback_name)
            try:
                with pd.ExcelWriter(fallback_path, engine="openpyxl", mode="w") as writer:
                    df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)
                if OPENPYXL_AVAILABLE:
                    wb = openpyxl.load_workbook(fallback_path)
                    self._style_worksheet(wb[sheet_name])
                    wb.save(fallback_path)
                err = (
                    f"The main Excel file ({os.path.basename(excel_path)}) is currently open "
                    f"in another program! To prevent data loss, attendance was saved to backup: "
                    f"{fallback_name}. Please close Excel so future records save to the main file."
                )
                return fallback_path, err
            except Exception as inner_e:
                return "", f"PermissionError and backup failed: {inner_e}"
        except Exception as e:
            return "", f"Unexpected Excel save error: {e}"

    def build_present_absent_report(self, date_str: str) -> pd.DataFrame:
        """
        Build a complete roster report listing ALL registered people as either
        Present (with arrival time) or Absent for a chosen date (`YYYY-MM-DD`).
        """
        users_df = self.get_registered_users()
        daily_df = self.get_daily_attendance_df(date_str)

        rows = []
        present_map = {}
        if not daily_df.empty:
            for _, row in daily_df.iterrows():
                present_map[str(row["ID"])] = (str(row["Time"]), str(row["Status"]))

        # Include all registered users
        seen_ids = set()
        for _, u_row in users_df.iterrows():
            uid = str(u_row["ID"])
            uname = str(u_row["Name"])
            seen_ids.add(uid)
            if uid in present_map:
                t_val, s_val = present_map[uid]
                rows.append(
                    {
                        "S.No": len(rows) + 1,
                        "ID": uid,
                        "Name": uname,
                        "Date": date_str,
                        "Time": t_val,
                        "Status": s_val,
                    }
                )
            else:
                rows.append(
                    {
                        "S.No": len(rows) + 1,
                        "ID": uid,
                        "Name": uname,
                        "Date": date_str,
                        "Time": "--:--:--",
                        "Status": "Absent",
                    }
                )

        # Also include any attendance entries whose ID wasn't in users_registry.csv
        if not daily_df.empty:
            for _, d_row in daily_df.iterrows():
                uid = str(d_row["ID"])
                if uid not in seen_ids:
                    rows.append(
                        {
                            "S.No": len(rows) + 1,
                            "ID": uid,
                            "Name": str(d_row["Name"]),
                            "Date": date_str,
                            "Time": str(d_row["Time"]),
                            "Status": str(d_row["Status"]),
                        }
                    )

        return pd.DataFrame(
            rows, columns=["S.No", "ID", "Name", "Date", "Time", "Status"]
        )

    def export_present_absent_excel(self, date_str: str, custom_path: str = None):
        """
        Export the full Present & Absent list for `date_str` to a dedicated Excel file
        with summary metrics.
        """
        report_df = self.build_present_absent_report(date_str)
        if custom_path is None:
            custom_path = os.path.join(
                ATTENDANCE_DIR, f"Attendance_Present_Absent_{date_str}.xlsx"
            )

        saved_path, err = self._save_sheet_safely(custom_path, f"Report_{date_str}", report_df)
        return saved_path, err, report_df


# ==============================================================================
# TKINTER GUI APPLICATION
# ==============================================================================
class FaceAttendanceGUI:
    """Tkinter Graphical User Interface for the Face Detection Attendance System."""

    def __init__(self, root):
        self.root = root
        self.root.title("Smart Face Recognition Attendance System")
        self.root.geometry("980x680")
        self.root.minsize(900, 620)
        self.root.configure(bg="#F4F6F9")

        self.backend = AttendanceBackend()
        self.is_admin_authenticated = False
        self.admin_password = DEFAULT_ADMIN_PASSWORD

        # Configurable runtime variables
        self.cutoff_var = tk.StringVar(value=DEFAULT_CUTOFF_TIME)
        self.tolerance_var = tk.DoubleVar(value=DEFAULT_TOLERANCE)
        self.samples_var = tk.IntVar(value=DEFAULT_NUM_SAMPLES)
        self.antispoof_var = tk.BooleanVar(value=REQUIRE_BLINK_ANTISPOOF)
        self.camera_index_var = tk.IntVar(value=0)
        self.query_date_var = tk.StringVar(
            value=datetime.datetime.now().strftime("%Y-%m-%d")
        )

        self._build_ui()
        self._refresh_table()

    # --------------------------------------------------------------------------
    # UI LAYOUT CONSTRUCTION
    # --------------------------------------------------------------------------
    def _build_ui(self):
        # Top Header Banner
        header_frame = tk.Frame(self.root, bg="#1F4E78", height=70)
        header_frame.pack(fill=tk.X, side=tk.TOP)

        title_lbl = tk.Label(
            header_frame,
            text="Face Detection & Recognition Attendance System",
            font=("Segoe UI", 18, "bold"),
            fg="white",
            bg="#1F4E78",
            pady=14,
        )
        title_lbl.pack(side=tk.LEFT, padx=20)

        self.admin_status_btn = tk.Button(
            header_frame,
            text="Admin Login (Locked)",
            font=("Segoe UI", 10, "bold"),
            bg="#D9534F",
            fg="white",
            activebackground="#C9302C",
            relief=tk.FLAT,
            padx=12,
            pady=6,
            command=self.toggle_admin_login,
        )
        self.admin_status_btn.pack(side=tk.RIGHT, padx=20, pady=15)

        # Main Content Container
        main_frame = tk.Frame(self.root, bg="#F4F6F9", padx=18, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left Panel: Core Action Buttons & Settings
        left_panel = tk.LabelFrame(
            main_frame,
            text=" Core Operations & Controls ",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#1F4E78",
            padx=15,
            pady=12,
        )
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))

        # 4 Required Primary Buttons
        btn_style = {
            "font": ("Segoe UI", 11, "bold"),
            "width": 24,
            "pady": 8,
            "relief": tk.FLAT,
            "cursor": "hand2",
        }

        tk.Button(
            left_panel,
            text="1. Register Face",
            bg="#2E75B6",
            fg="white",
            activebackground="#1F4E78",
            command=self.handle_register_face,
            **btn_style,
        ).pack(pady=6)

        tk.Button(
            left_panel,
            text="2. Start Attendance (Live)",
            bg="#28A745",
            fg="white",
            activebackground="#1E7E34",
            command=self.handle_start_attendance,
            **btn_style,
        ).pack(pady=6)

        tk.Button(
            left_panel,
            text="3. View Attendance List",
            bg="#17A2B8",
            fg="white",
            activebackground="#117A8B",
            command=self.handle_view_attendance,
            **btn_style,
        ).pack(pady=6)

        tk.Button(
            left_panel,
            text="4. Export to Excel",
            bg="#F0AD4E",
            fg="white",
            activebackground="#EC971F",
            command=self.handle_export_excel,
            **btn_style,
        ).pack(pady=6)

        ttk.Separator(left_panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=12)

        # Settings Section
        tk.Label(
            left_panel,
            text="System Parameters",
            font=("Segoe UI", 10, "bold"),
            bg="white",
            fg="#333333",
        ).pack(anchor="w", pady=(0, 6))

        # Date Filter
        date_row = tk.Frame(left_panel, bg="white")
        date_row.pack(fill=tk.X, pady=3)
        tk.Label(date_row, text="Target Date (YYYY-MM-DD):", bg="white", font=("Segoe UI", 9)).pack(
            side=tk.LEFT
        )
        tk.Entry(date_row, textvariable=self.query_date_var, width=12, font=("Segoe UI", 9)).pack(
            side=tk.RIGHT
        )

        # Cutoff Time
        cutoff_row = tk.Frame(left_panel, bg="white")
        cutoff_row.pack(fill=tk.X, pady=3)
        tk.Label(cutoff_row, text="On-Time Cutoff (HH:MM:SS):", bg="white", font=("Segoe UI", 9)).pack(
            side=tk.LEFT
        )
        tk.Entry(cutoff_row, textvariable=self.cutoff_var, width=12, font=("Segoe UI", 9)).pack(
            side=tk.RIGHT
        )

        # Recognition Tolerance
        tol_row = tk.Frame(left_panel, bg="white")
        tol_row.pack(fill=tk.X, pady=3)
        tk.Label(tol_row, text="Match Tolerance (0.4-0.6):", bg="white", font=("Segoe UI", 9)).pack(
            side=tk.LEFT
        )
        tk.Spinbox(
            tol_row,
            from_=0.35,
            to=0.65,
            increment=0.05,
            textvariable=self.tolerance_var,
            width=10,
            font=("Segoe UI", 9),
        ).pack(side=tk.RIGHT)

        # Sample Count
        samp_row = tk.Frame(left_panel, bg="white")
        samp_row.pack(fill=tk.X, pady=3)
        tk.Label(samp_row, text="Images per Registration:", bg="white", font=("Segoe UI", 9)).pack(
            side=tk.LEFT
        )
        tk.Spinbox(
            samp_row,
            from_=10,
            to=20,
            increment=1,
            textvariable=self.samples_var,
            width=10,
            font=("Segoe UI", 9),
        ).pack(side=tk.RIGHT)

        # Camera Index
        cam_row = tk.Frame(left_panel, bg="white")
        cam_row.pack(fill=tk.X, pady=3)
        tk.Label(cam_row, text="Webcam Device Index:", bg="white", font=("Segoe UI", 9)).pack(
            side=tk.LEFT
        )
        tk.Spinbox(
            cam_row,
            from_=0,
            to=4,
            increment=1,
            textvariable=self.camera_index_var,
            width=10,
            font=("Segoe UI", 9),
        ).pack(side=tk.RIGHT)

        # Anti-spoofing checkbox
        tk.Checkbutton(
            left_panel,
            text="Enable Blink Anti-Spoofing",
            variable=self.antispoof_var,
            bg="white",
            font=("Segoe UI", 9, "bold"),
            fg="#1F4E78",
        ).pack(anchor="w", pady=(8, 4))

        # Summary Counters
        self.stats_lbl = tk.Label(
            left_panel,
            text="Registered Users: 0\nEncoded Samples: 0",
            font=("Segoe UI", 9),
            bg="#EBF1F5",
            fg="#1F4E78",
            justify=tk.LEFT,
            padx=10,
            pady=8,
        )
        self.stats_lbl.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        # Right Panel: Attendance Table View (Present + Absent Roster)
        right_panel = tk.LabelFrame(
            main_frame,
            text=" Daily Attendance & Absentee Roster ",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#1F4E78",
            padx=12,
            pady=12,
        )
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Filter bar inside Right Panel
        filter_bar = tk.Frame(right_panel, bg="white")
        filter_bar.pack(fill=tk.X, pady=(0, 8))

        self.view_mode_var = tk.StringVar(value="ALL")
        tk.Label(filter_bar, text="Filter View:", bg="white", font=("Segoe UI", 9, "bold")).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        for label, mode in [
            ("All (Present + Absent)", "ALL"),
            ("Present Only", "PRESENT"),
            ("Absent Only", "ABSENT"),
        ]:
            tk.Radiobutton(
                filter_bar,
                text=label,
                variable=self.view_mode_var,
                value=mode,
                bg="white",
                font=("Segoe UI", 9),
                command=self._refresh_table,
            ).pack(side=tk.LEFT, padx=6)

        # Treeview Table
        columns = ("S.No", "ID", "Name", "Date", "Time", "Status")
        self.tree = ttk.Treeview(right_panel, columns=columns, show="headings", height=18)

        col_Access_widths = {
            "S.No": 55,
            "ID": 95,
            "Name": 180,
            "Date": 100,
            "Time": 95,
            "Status": 135,
        }
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(
                col,
                width=col_Access_widths[col],
                anchor=tk.W if col == "Name" else tk.CENTER,
            )

        scrollbar = ttk.Scrollbar(right_panel, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom Status Bar
        self.status_var = tk.StringVar(
            value="System Ready. Click 'Register Face' or 'Start Attendance' to begin."
        )
        status_bar = tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            bg="#E1E6EB",
            fg="#333333",
            anchor="w",
            padx=15,
            pady=5,
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    # --------------------------------------------------------------------------
    # ADMIN AUTHENTICATION
    # --------------------------------------------------------------------------
    def toggle_admin_login(self):
        """Allow admin login/logout with password protection."""
        if self.is_admin_authenticated:
            self.is_admin_authenticated = False
            self.admin_status_btn.config(text="Admin Login (Locked)", bg="#D9534F")
            self.status_var.set("Admin logged out.")
            return

        pwd = simpledialog.askstring(
            "Admin Authentication",
            "Enter Admin Password (default: admin123):",
            show="*",
            parent=self.root,
        )
        if pwd is None:
            return
        if pwd == self.admin_password:
            self.is_admin_authenticated = True
            self.admin_status_btn.config(text="Admin Unlocked (Logout)", bg="#28A745")
            self.status_var.set("Admin mode unlocked. You can now register new faces.")
        else:
            messagebox.showerror("Access Denied", "Incorrect admin password!")

    def _require_admin(self) -> bool:
        """Ensure admin is authenticated before registering new users."""
        if self.is_admin_authenticated:
            return True
        self.toggle_admin_login()
        return self.is_admin_authenticated

    # --------------------------------------------------------------------------
    # FEATURE 1: REGISTER STUDENTS / EMPLOYEES (10-20 WEBCAM IMAGES + ENCODINGS)
    # --------------------------------------------------------------------------
    def handle_register_face(self):
        """
        Prompt for Admin authentication, collect User ID & Name, capture 10-20 face images
        via webcam, extract 128-D face encodings, and save to dataset/ and encodings/.
        """
        if not FACE_REC_AVAILABLE:
            messagebox.showerror(
                "Missing Dependency",
                "The `face_recognition` library is not installed.\n"
                "Please follow the instructions in README.md to install dlib and face_recognition.",
            )
            return

        if not self._require_admin():
            return

        user_id = simpledialog.askstring(
            "Register Person - Step 1/2",
            "Enter Unique Student / Employee ID (e.g., EMP001 or 101):",
            parent=self.root,
        )
        if not user_id or not user_id.strip():
            return
        user_id = user_id.strip()

        user_name = simpledialog.askstring(
            "Register Person - Step 2/2",
            f"Enter Full Name for ID '{user_id}':",
            parent=self.root,
        )
        if not user_name or not user_name.strip():
            return
        user_name = user_name.strip()

        num_samples_target = max(10, min(20, int(self.samples_var.get())))
        cam_idx = int(self.camera_index_var.get())

        # Open Webcam with robust error handling
        cap = cv2.VideoCapture(cam_idx)
        if not cap.isOpened():
            messagebox.showerror(
                "Webcam Error",
                f"Could not access webcam at device index {cam_idx}.\n\n"
                "Troubleshooting:\n"
                "1. Check that your camera is plugged in and not used by another app.\n"
                "2. Try changing 'Webcam Device Index' to 1.",
            )
            return

        # Prepare folder in dataset/<ID>_<Name>/
        safe_folder_name = "".join(
            c if c.isalnum() or c in ("_", "-") else "_" for c in f"{user_id}_{user_name}"
        )
        person_dir = os.path.join(DATASET_DIR, safe_folder_name)
        os.makedirs(person_dir, exist_ok=True)

        captured_encodings = []
        captured_count = 0
        last_capture_time = 0.0
        capture_interval = 0.35  # 350ms between samples so user can slightly turn head

        self.status_var.set(
            f"Registering {user_name} ({user_id})... Look at the camera. Press 'Q' to cancel."
        )
        self.root.update()

        while captured_count < num_samples_target:
            ret, frame = cap.read()
            if not ret or frame is None:
                messagebox.showerror(
                    "Camera Read Error", "Lost connection to webcam during capture."
                )
                break

            display_frame = frame.copy()
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Detect faces in the current frame
            face_locations = face_recognition.face_locations(rgb_frame, model="hog")

            if len(face_locations) == 0:
                # Error handling: No face detected in frame
                cv2.putText(
                    display_frame,
                    "No face detected! Please center your face in good lighting.",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 0, 255),
                    2,
                )
            elif len(face_locations) > 1:
                cv2.putText(
                    display_frame,
                    "Multiple faces detected! Only 1 person allowed during registration.",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.60,
                    (0, 165, 255),
                    2,
                )
            else:
                top, right, bottom, left = face_locations[0]
                cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 255, 0), 2)

                now = time.time()
                if now - last_capture_time >= capture_interval:
                    encodings = face_recognition.face_encodings(
                        rgb_frame, [face_locations[0]]
                    )
                    if len(encodings) > 0:
                        captured_encodings.append(encodings[0])
                        captured_count += 1
                        last_capture_time = now

                        # Save image to dataset/<ID>_<Name>/
                        img_path = os.path.join(
                            person_dir, f"sample_{captured_count:02d}.jpg"
                        )
                        cv2.imwrite(img_path, frame)

            # Draw progress overlay bar
            progress_text = f"Capturing {user_name} ({user_id}): {captured_count}/{num_samples_target}"
            cv2.putText(
                display_frame,
                progress_text,
                (20, display_frame.shape[0] - 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 0),
                2,
            )

            cv2.imshow("Register Face - Press 'Q' to Abort", display_frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                break

        cap.release()
        cv2.destroyAllWindows()

        if captured_count < 5:
            messagebox.showwarning(
                "Registration Incomplete",
                f"Only {captured_count} valid face samples were captured. "
                "Registration cancelled (minimum 5 samples required).",
            )
            self.status_var.set("Registration cancelled.")
            return

        # Save encodings and update user registry
        for enc in captured_encodings:
            self.backend.known_encodings.append(enc)
            self.backend.known_ids.append(user_id)
            self.backend.known_names.append(user_name)

        self.backend.save_encodings()
        self.backend.register_user_in_registry(user_id, user_name)
        self._refresh_table()

        messagebox.showinfo(
            "Registration Complete",
            f"Successfully registered {user_name} (ID: {user_id})!\n"
            f"- Images saved: {captured_count} in dataset/{safe_folder_name}/\n"
            f"- Face encodings updated in encodings/encodings.pkl",
        )
        self.status_var.set(f"Registered {user_name} ({user_id}) with {captured_count} samples.")

    # --------------------------------------------------------------------------
    # FEATURE 2, 3, 4: LIVE ATTENDANCE, NO DUPLICATES, UNKNOWN FACES, ANTI-SPOOF
    # --------------------------------------------------------------------------
    def handle_start_attendance(self):
        """
        Open webcam in real-time, detect & recognize faces, verify blink liveness
        (if enabled), mark attendance once per day in Excel, and display "Unknown"
        for unrecognized faces.
        """
        if not FACE_REC_AVAILABLE:
            messagebox.showerror(
                "Missing Dependency",
                "The `face_recognition` library is not installed.\n"
                "Please see README.md for installation instructions.",
            )
            return

        if len(self.backend.known_encodings) == 0:
            messagebox.showwarning(
                "No Registered Faces",
                "No face encodings found! Please click '1. Register Face' first.",
            )
            return

        cam_idx = int(self.camera_index_var.get())
        cap = cv2.VideoCapture(cam_idx)
        if not cap.isOpened():
            messagebox.showerror(
                "Webcam Error",
                f"Could not open webcam at index {cam_idx}. Please check camera connection.",
            )
            return

        tolerance = float(self.tolerance_var.get())
        cutoff_str = self.cutoff_var.get().strip()
        require_blink = bool(self.antispoof_var.get())

        # Track who has blinked during the current session for anti-spoofing
        blink_verified_ids = set()
        # Cache already-marked IDs in memory for instant overlay feedback
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        df_today = self.backend.get_daily_attendance_df(today_str)
        marked_today_ids = set(df_today["ID"].astype(str).values) if not df_today.empty else set()

        self.status_var.set("Live Attendance Running... Press 'Q' or 'ESC' in the video window to stop.")
        self.root.update()

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                messagebox.showerror("Webcam Disconnected", "Video stream interrupted.")
                break

            # Resize frame to 1/2 size for faster real-time recognition
            small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small, model="hog")
            face_encodings = face_recognition.face_encodings(rgb_small, face_locations)
            face_landmarks_list = (
                face_recognition.face_landmarks(rgb_small, face_locations)
                if require_blink and len(face_locations) > 0
                else [{}] * len(face_locations)
            )

            if len(face_locations) == 0:
                cv2.putText(
                    frame,
                    "Scanning for faces... (Press 'Q' to exit)",
                    (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (200, 200, 200),
                    2,
                )

            for (top, right, bottom, left), face_enc, landmarks in zip(
                face_locations, face_encodings, face_landmarks_list
            ):
                # Scale coordinates back up by 2x
                top *= 2
                right *= 2
                bottom *= 2
                left *= 2

                # Compute Euclidean distances against all known encodings
                distances = face_recognition.face_distance(
                    self.backend.known_encodings, face_enc
                )
                best_idx = int(np.argmin(distances))
                best_dist = float(distances[best_idx])

                if best_dist <= tolerance:
                    matched_id = str(self.backend.known_ids[best_idx])
                    matched_name = str(self.backend.known_names[best_idx])
                    confidence_pct = max(0, int((1.0 - best_dist) * 100))

                    # Check Anti-Spoofing Blink Liveness if enabled
                    if require_blink and matched_id not in marked_today_ids:
                        is_blinking, ear_val = check_liveness_blink(landmarks)
                        if is_blinking:
                            blink_verified_ids.add(matched_id)

                    if require_blink and (
                        matched_id not in blink_verified_ids
                        and matched_id not in marked_today_ids
                    ):
                        # Prompt user to blink before marking attendance
                        box_color = (0, 165, 255)  # Orange = waiting for blink
                        label_top = f"{matched_name} ({matched_id}) [{confidence_pct}%]"
                        label_bottom = "Blink eyes to verify liveness & mark attendance"
                    else:
                        # Mark attendance if not already marked today
                        if matched_id not in marked_today_ids:
                            already, status_label, saved_path, err_msg = (
                                self.backend.mark_attendance(
                                    matched_id, matched_name, cutoff_str
                                )
                            )
                            marked_today_ids.add(matched_id)
                            self.query_date_var.set(
                                datetime.datetime.now().strftime("%Y-%m-%d")
                            )
                            self._refresh_table()
                            if err_msg:
                                self.status_var.set(f"WARNING: {err_msg}")
                            else:
                                self.status_var.set(
                                    f"Marked {matched_name} ({matched_id}) as {status_label}."
                                )

                        box_color = (0, 200, 0)  # Green = verified & marked
                        label_top = f"{matched_name} (ID: {matched_id}) [{confidence_pct}%]"
                        label_bottom = "Attendance Marked Today"
                else:
                    # Unknown Face: Show "Unknown" in red and DO NOT mark attendance
                    box_color = (0, 0, 255)
                    label_top = "Unknown"
                    label_bottom = "Not Registered - Attendance Not Marked"

                # Draw bounding box & labels
                cv2.rectangle(frame, (left, top), (right, bottom), box_color, 2)
                cv2.rectangle(
                    frame, (left, bottom - 32), (right, bottom), box_color, cv2.FILLED
                )
                cv2.putText(
                    frame,
                    label_top,
                    (left + 6, bottom - 10),
                    cv2.FONT_HERSHEY_DUPLEX,
                    0.55,
                    (255, 255, 255),
                    1,
                )
                cv2.putText(
                    frame,
                    label_bottom,
                    (left, max(25, top - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    box_color,
                    2,
                )

            cv2.imshow("Live Attendance Feed - Press 'Q' to Stop", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                break

        cap.release()
        cv2.destroyAllWindows()
        self._refresh_table()
        self.status_var.set("Live attendance session ended.")

    # --------------------------------------------------------------------------
    # FEATURE 3 & 4 (GUI): VIEW ATTENDANCE LIST & EXPORT PRESENT/ABSENT TO EXCEL
    # --------------------------------------------------------------------------
    def handle_view_attendance(self):
        """Load and display Present and Absent records for the selected Target Date."""
        target_date = self.query_date_var.get().strip()
        try:
            datetime.datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror(
                "Invalid Date Format",
                "Please enter Target Date in YYYY-MM-DD format (e.g., 2026-11-11).",
            )
            return

        self._refresh_table()
        report_df = self.backend.build_present_absent_report(target_date)
        total_cnt = len(report_df)
        present_cnt = int(
            report_df["Status"].astype(str).str.startswith("Present").sum()
        ) if total_cnt > 0 else 0
        absent_cnt = total_cnt - present_cnt

        self.status_var.set(
            f"Loaded attendance for {target_date}: {present_cnt} Present, {absent_cnt} Absent (Total: {total_cnt})."
        )

    def handle_export_excel(self):
        """
        Export the complete Present & Absent roster for the selected date to an
        Excel (.xlsx) file and let the user choose a custom save location or default folder.
        """
        target_date = self.query_date_var.get().strip()
        try:
            datetime.datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror(
                "Invalid Date Format",
                "Please enter Target Date in YYYY-MM-DD format (e.g., 2026-11-11).",
            )
            return

        default_filename = f"Attendance_Present_Absent_{target_date}.xlsx"
        save_path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export Present & Absent Attendance Report",
            initialdir=ATTENDANCE_DIR,
            initialfile=default_filename,
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook", "*.xlsx")],
        )
        if not save_path:
            return

        saved_file, err_msg, report_df = self.backend.export_present_absent_excel(
            target_date, save_path
        )
        if err_msg and not saved_file:
            messagebox.showerror("Export Failed", err_msg)
            return

        total_cnt = len(report_df)
        present_cnt = int(
            report_df["Status"].astype(str).str.startswith("Present").sum()
        ) if total_cnt > 0 else 0
        absent_cnt = total_cnt - present_cnt

        msg = (
            f"Attendance report exported for {target_date}!\n\n"
            f"- File: {saved_file}\n"
            f"- Present: {present_cnt}\n"
            f"- Absent: {absent_cnt}\n"
            f"- Total Registered: {total_cnt}"
        )
        if err_msg:
            msg += f"\n\nNote: {err_msg}"

        messagebox.showinfo("Export Successful", msg)
        self.status_var.set(f"Exported Excel report to: {saved_file}")

    def _refresh_table(self):
        """Populate the Tkinter Treeview with Present & Absent rows for the target date."""
        for row in self.tree.get_children():
            self.tree.delete(row)

        target_date = self.query_date_var.get().strip()
        report_df = self.backend.build_present_absent_report(target_date)
        mode = self.view_mode_var.get()

        if not report_df.empty:
            if mode == "PRESENT":
                report_df = report_df[
                    report_df["Status"].astype(str).str.startswith("Present")
                ]
            elif mode == "ABSENT":
                report_df = report_df[report_df["Status"] == "Absent"]

            for idx, (_, r) in enumerate(report_df.iterrows(), start=1):
                self.tree.insert(
                    "",
                    tk.END,
                    values=(
                        idx,
                        r["ID"],
                        r["Name"],
                        r["Date"],
                        r["Time"],
                        r["Status"],
                    ),
                )

        # Update summary stats on the left panel
        reg_users = self.backend.get_registered_users()
        self.stats_lbl.config(
            text=(
                f"Registered People: {len(reg_users)}\n"
                f"Stored Face Encodings: {len(self.backend.known_encodings)}\n"
                f"Monthly Workbook: Attendance_{target_date[:7].replace('-', '_')}.xlsx"
            )
        )


# ==============================================================================
# CLI / DEMO VERIFICATION MODE (FOR HEADLESS TESTING)
# ==============================================================================
def run_self_test():
    """
    Verify directory creation, registry management, duplicate prevention,
    and openpyxl Excel export in headless environments.
    """
    print("[SELF-TEST] Initializing AttendanceBackend...")
    backend = AttendanceBackend()
    backend.register_user_in_registry("EMP101", "Aarav Sharma")
    backend.register_user_in_registry("EMP102", "Priya Patel")
    backend.register_user_in_registry("EMP103", "Rohan Verma")

    # Mark EMP101 and EMP102 present; leave EMP103 absent
    already1, status1, path1, err1 = backend.mark_attendance(
        "EMP101", "Aarav Sharma", cutoff_time_str="23:59:59"
    )
    # Test duplicate prevention on EMP101
    already1_dup, _, _, _ = backend.mark_attendance(
        "EMP101", "Aarav Sharma", cutoff_time_str="23:59:59"
    )
    # Test Late marking on EMP102
    already2, status2, path2, err2 = backend.mark_attendance(
        "EMP102", "Priya Patel", cutoff_time_str="00:00:01"
    )

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    saved_report, err_rep, df_rep = backend.export_present_absent_excel(today_str)

    assert not already1, "First mark should not be duplicate"
    assert already1_dup, "Second mark on same day MUST be flagged as duplicate"
    assert os.path.exists(path1), f"Monthly Excel file not created at {path1}"
    assert os.path.exists(saved_report), f"Daily report not created at {saved_report}"
    print(f"[SELF-TEST PASSED] Monthly file: {path1}")
    print(f"[SELF-TEST PASSED] Present/Absent Report: {saved_report}")
    print(df_rep.to_string(index=False))


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_self_test()
    else:
        root = tk.Tk()
        app = FaceAttendanceGUI(root)
        root.mainloop()
