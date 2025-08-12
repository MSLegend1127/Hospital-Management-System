import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, scrolledtext
from datetime import datetime
from fpdf import FPDF
import mysql.connector
from dotenv import load_dotenv
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ===================== CONFIG & INITIALIZATION =====================
load_dotenv()  # loads .env variables into environmentimport os
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, scrolledtext
from datetime import datetime
from fpdf import FPDF
import mysql.connector
from dotenv import load_dotenv
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tkcalendar import DateEntry  # <-- Added

# ===================== CONFIG & INITIALIZATION =====================
load_dotenv()

# Gemini API
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        print("Warning: Failed to configure Gemini API:", e)
else:
    print("Warning: GOOGLE_API_KEY not found. Gemini AI disabled.")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# DB Config
DB_CONFIG = {
    "host": "localhost",
    "user": "matthew",
    "password": "matthewantony122",
    "database": "hospital"
}

# ===================== DATABASE UTIL =====================
def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as e:
        messagebox.showerror("Database Error", f"Could not connect to DB:\n{e}")
        return None

# ===================== AI CALL (Gemini) =====================
def call_gemini(symptoms: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini API key not configured.")
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = (
        f"A patient presents with the following symptoms: {symptoms}.\n\n"
        "Provide a structured analysis in Markdown format with headings:\n"
        "### Likely Diagnosis\n"
        "### Recommended Tests\n"
        "### Specialist to See\n"
        "### Home Care Suggestions\n"
    )
    resp = model.generate_content(prompt)
    if hasattr(resp, "text"):
        return resp.text.strip()
    elif isinstance(resp, dict) and "candidates" in resp:
        return resp["candidates"][0].get("content", "").strip()
    else:
        return str(resp).strip()

# ===================== EMAIL REMINDER =====================
def send_email_reminder(to_email: str, name: str, date_str: str) -> bool:
    """
    Send a reminder email using Brevo (Sendinblue) SMTP.
    Returns True on success, False on failure.
    """
    # Load credentials from environment variables
    EMAIL_HOST = "smtp-relay.brevo.com"
    EMAIL_PORT = 587
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")  # This is your Brevo SMTP login
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # This is your Brevo SMTP password

    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("❌ Brevo SMTP credentials not set — skipping email send.")
        return False

    subject = "Appointment Reminder"
    body = f"Dear {name},\n\nThis is a reminder for your appointment on {date_str}.\n\nRegards,\nHospital Team"

    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=15) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"✅ Reminder sent to {to_email} via Brevo SMTP.")
        return True

    except smtplib.SMTPAuthenticationError:
        print("❌ SMTP Authentication failed — check Brevo username/password.")
        try:
            messagebox.showerror("Email Error", "Authentication failed. Check Brevo credentials.")
        except:
            pass
        return False
    except Exception as e:
        print("❌ Email send error:", e)
        try:
            messagebox.showerror("Email Error", f"Failed to send email: {e}")
        except:
            pass
        return False

# ===================== BACKGROUND WORKER HELPERS =====================
_loading_running = False
def set_loading(flag: bool):
    global _loading_running
    _loading_running = flag

def start_loading(label_widget: ttk.Label):
    def loader():
        dots = ""
        while _loading_running:
            dots = (dots + ".") if len(dots) < 3 else ""
            label_widget.after(0, lambda d=dots: label_widget.config(text="AI is thinking" + d))
            time.sleep(0.45)
        label_widget.after(0, lambda: label_widget.config(text=""))
    t = threading.Thread(target=loader, daemon=True)
    t.start()
    return t

# ===================== SAVE/AI FLOW =====================
def perform_save_thread(name, age, gender, symptoms, appointment_date, email, notes):
    diagnosis = "AI not available."
    ai_error = None
    try:
        diagnosis = call_gemini(symptoms)
    except Exception as e:
        ai_error = str(e)
        diagnosis = f"[AI Error] {ai_error}"

    def after_ai():
        set_loading(False)
        if ai_error:
            proceed = messagebox.askyesno("AI Error", f"AI failed: {ai_error}\n\nSave without AI analysis?")
            if not proceed:
                btn_add_patient.config(state=tk.NORMAL)
                return
        else:
            proceed = messagebox.askokcancel("AI Diagnosis Review", f"AI Generated Analysis:\n\n{diagnosis}\n\nSave record?")
            if not proceed:
                btn_add_patient.config(state=tk.NORMAL)
                return

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                query = """
                INSERT INTO patients
                (name, age, gender, symptoms, diagnosis, doctor_notes, appointment_date, email)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """
                cursor.execute(query, (name, int(age), gender, symptoms, diagnosis, notes, appointment_date, email))
                conn.commit()
                messagebox.showinfo("Saved", "Patient data saved.")
                threading.Thread(target=send_email_reminder, args=(email, name, appointment_date), daemon=True).start()
            except mysql.connector.Error as e:
                messagebox.showerror("DB Save Error", f"Failed to save record: {e}")
            finally:
                cursor.close()
                conn.close()
        btn_add_patient.config(state=tk.NORMAL)
        clear_fields()
        view_patients()

    root.after(0, after_ai)

# ===================== UI ACTIONS =====================
def save_patient():
    name = entry_name.get().strip()
    age = entry_age.get().strip()
    gender = gender_var.get()
    symptoms = text_symptoms.get("1.0", tk.END).strip()
    appointment_date = entry_date.get().strip()
    email = entry_email.get().strip()

    if not (name and age and gender != "Select" and symptoms and appointment_date and email):
        messagebox.showerror("Input Error", "All fields are required.")
        return
    try:
        age_i = int(age)
        if age_i <= 0 or age_i > 130:
            raise ValueError
    except Exception:
        messagebox.showerror("Input Error", "Enter a valid numeric age.")
        return

    notes = simpledialog.askstring("Doctor Notes", "Enter any additional notes (optional):") or "N/A"

    btn_add_patient.config(state=tk.DISABLED)
    set_loading(True)
    start_loading(loading_label)
    worker = threading.Thread(target=perform_save_thread,
                              args=(name, age, gender, symptoms, appointment_date, email, notes),
                              daemon=True)
    worker.start()

def view_patients():
    for item in tree_output.get_children():
        tree_output.delete(item)
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, name, age, gender, appointment_date, email FROM patients ORDER BY id DESC LIMIT 100")
            rows = cursor.fetchall()
            for r in rows:
                tree_output.insert("", tk.END, values=(r["id"], r["name"], r["age"], r["gender"], r["appointment_date"], r["email"]))
        except mysql.connector.Error as e:
            messagebox.showerror("DB Error", f"Failed to fetch patients: {e}")
        finally:
            cursor.close()
            conn.close()

def show_full_details(event):
    sel = tree_output.selection()
    if not sel:
        return
    item = tree_output.item(sel)
    if not item or "values" not in item:
        return
    patient_id = item["values"][0]
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
            pdata = cursor.fetchone()
            if pdata:
                details_window = tk.Toplevel(root)
                details_window.title(f"Details - {pdata['name']}")
                details_window.geometry("700x520")

                txt = scrolledtext.ScrolledText(details_window, wrap=tk.WORD, font=("Helvetica", 11))
                txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                content = (
                    f"ID: {pdata.get('id')}\n"
                    f"Name: {pdata.get('name')}\n"
                    f"Age: {pdata.get('age')}\n"
                    f"Gender: {pdata.get('gender')}\n"
                    f"Email: {pdata.get('email')}\n"
                    f"Appointment Date: {pdata.get('appointment_date')}\n\n"
                    f"--- Symptoms ---\n{pdata.get('symptoms')}\n\n"
                    f"--- AI Diagnosis & Recommendations ---\n{pdata.get('diagnosis')}\n\n"
                    f"--- Doctor Notes ---\n{pdata.get('doctor_notes')}\n"
                )
                txt.insert(tk.END, content)
                txt.config(state=tk.DISABLED)
                btn_pdf = ttk.Button(details_window, text="Export to PDF", command=lambda: export_to_pdf(pdata))
                btn_pdf.pack(pady=6)
        except mysql.connector.Error as e:
            messagebox.showerror("DB Error", f"Failed to fetch details: {e}")
        finally:
            cursor.close()
            conn.close()

# ===================== UI HELPERS =====================
def clear_fields():
    entry_name.delete(0, tk.END)
    entry_age.delete(0, tk.END)
    entry_email.delete(0, tk.END)
    gender_var.set("Select")
    text_symptoms.delete("1.0", tk.END)
    entry_date.set_date(datetime.today())

# ===================== MAIN UI =====================
root = tk.Tk()
root.title("🏥 Hospital Management System")
root.geometry("1000x750")

try:
    if os.path.exists("azure.tcl"):
        root.tk.call("source", "azure.tcl")
        try:
            root.tk.call("set_theme", "dark")
        except Exception:
            pass
except Exception as e:
    print("Azure theme not loaded:", e)

style = ttk.Style(root)
style.configure("TLabel", font=("Helvetica", 11))
style.configure("TButton", font=("Helvetica", 11, "bold"))
style.configure("Treeview.Heading", font=("Helvetica", 12, "bold"))

main_frame = ttk.Frame(root, padding=10)
main_frame.pack(fill=tk.BOTH, expand=True)

lbl_title = tk.Label(main_frame, text="Gemini Hospital Management System", font=("Helvetica", 20, "bold"))
lbl_title.pack(pady=8)

input_frame = ttk.LabelFrame(main_frame, text="Patient Registration", padding=10)
input_frame.pack(fill="x", pady=10)

labels = ["Name", "Age", "Gender", "Symptoms", "Appointment Date", "Email"]

entry_name = ttk.Entry(input_frame, width=40)
entry_age = ttk.Entry(input_frame, width=40)

gender_var = tk.StringVar(value="Select")
gender_menu = ttk.OptionMenu(input_frame, gender_var, "Select", "Male", "Female", "Other")

text_symptoms = tk.Text(input_frame, height=5, width=40)

# ---- New Date Picker ----
entry_date = DateEntry(input_frame, width=37, date_pattern="yyyy-mm-dd", background="darkblue", foreground="white", borderwidth=2)

entry_email = ttk.Entry(input_frame, width=40)

for i, txt in enumerate(labels):
    lbl = ttk.Label(input_frame, text=txt)
    lbl.grid(row=i, column=0, sticky="w", padx=6, pady=6)

entry_name.grid(row=0, column=1, padx=6, pady=6, sticky="ew")
entry_age.grid(row=1, column=1, padx=6, pady=6, sticky="ew")
gender_menu.grid(row=2, column=1, padx=6, pady=6, sticky="ew")
text_symptoms.grid(row=3, column=1, padx=6, pady=6, sticky="ew")
entry_date.grid(row=4, column=1, padx=6, pady=6, sticky="ew")
entry_email.grid(row=5, column=1, padx=6, pady=6, sticky="ew")

input_frame.columnconfigure(1, weight=1)

loading_label = ttk.Label(main_frame, text="", font=("Helvetica", 11, "italic"), foreground="green")
loading_label.pack(pady=5)

button_frame = ttk.Frame(main_frame)
button_frame.pack(pady=6)

btn_add_patient = ttk.Button(button_frame, text="Register Patient & Get AI Analysis", command=save_patient)
btn_add_patient.pack(side=tk.LEFT, padx=6)

btn_view = ttk.Button(button_frame, text="Refresh Patient List", command=view_patients)
btn_view.pack(side=tk.LEFT, padx=6)

output_frame = ttk.LabelFrame(main_frame, text="Patient Records (Double-click to see details)", padding=10)
output_frame.pack(fill=tk.BOTH, expand=True, pady=8)

columns = ("id", "name", "age", "gender", "appointment_date", "email")
tree_output = ttk.Treeview(output_frame, columns=columns, show="headings")
for col in columns:
    tree_output.heading(col, text=col.replace("_", " ").title())
    tree_output.column(col, width=120)
tree_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=tree_output.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
tree_output.configure(yscrollcommand=scrollbar.set)

tree_output.bind("<Double-1>", show_full_details)

view_patients()

root.mainloop()


# Gemini / Google Generative AI key (optional)
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        # If configure fails, we'll handle when calling
        print("Warning: Failed to configure Gemini API:", e)
else:
    print("Warning: GOOGLE_API_KEY not found in .env. Gemini AI disabled.")

# Email credentials (optional, used for reminders)
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Database config - change these to match your DB
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "hospital"
}

# ===================== DATABASE UTIL =====================
def get_db_connection():
    """Return a mysql.connector connection or None (shows error)."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as e:
        messagebox.showerror("Database Error", f"Could not connect to DB:\n{e}")
        return None

# ===================== AI CALL (Gemini) =====================
def call_gemini(symptoms: str) -> str:
    """
    Call Gemini and return text response.
    Raises RuntimeError if key missing or API fails.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini API key not configured.")
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = (
        f"A patient presents with the following symptoms: {symptoms}.\n\n"
        "Provide a structured analysis in Markdown format with headings:\n"
        "### Likely Diagnosis\n"
        "### Recommended Tests\n"
        "### Specialist to See\n"
        "### Home Care Suggestions\n"
    )
    resp = model.generate_content(prompt)
    # Defensive handling of SDK return shapes
    if hasattr(resp, "text"):
        return resp.text.strip()
    elif isinstance(resp, dict) and "candidates" in resp:
        return resp["candidates"][0].get("content", "").strip()
    else:
        return str(resp).strip()

# ===================== EMAIL REMINDER =====================
def send_email_reminder(to_email: str, name: str, date_str: str) -> bool:
    """
    Send a reminder email using Outlook SMTP.
    Returns True on success, False on failure.
    """
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("Email credentials not set — skipping email send.")
        return False

    subject = "Appointment Reminder"
    body = f"Dear {name},\n\nThis is a reminder for your appointment on {date_str}.\n\nRegards,\nHospital Team"

    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        # Outlook SMTP settings (STARTTLS)
        with smtplib.SMTP("smtp.office365.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"Reminder sent to {to_email} via Outlook SMTP.")
        return True

    except smtplib.SMTPAuthenticationError:
        print("SMTP Authentication failed. Check your Outlook username/password.")
        try:
            messagebox.showerror("Email Error", "Authentication failed. Check Outlook credentials.")
        except:
            pass
        return False
    except Exception as e:
        print("Email send error:", e)
        try:
            messagebox.showerror("Email Error", f"Failed to send email: {e}")
        except:
            pass
        return False

# ===================== PDF EXPORT =====================
def export_to_pdf(patient_data: dict):
    """Export patient_data dict to a simple PDF file in ./reports/"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Patient Medical Report", ln=True, align="C")
    pdf.ln(6)
    for key, value in patient_data.items():
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, f"{key.replace('_', ' ').title()}:", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.multi_cell(0, 7, str(value))
        pdf.ln(2)
    os.makedirs("reports", exist_ok=True)
    fname = f"reports/Patient_Report_{patient_data.get('name','unknown').replace(' ','_')}.pdf"
    pdf.output(fname)
    messagebox.showinfo("Exported", f"Saved PDF: {fname}")

# ===================== BACKGROUND WORKER HELPERS =====================
_loading_running = False

def set_loading(flag: bool):
    """Set the global loading flag used by the loader thread."""
    global _loading_running
    _loading_running = flag

def start_loading(label_widget: ttk.Label):
    """Start loader thread to animate `label_widget` text. Non-blocking."""
    def loader():
        dots = ""
        while _loading_running:
            dots = (dots + ".") if len(dots) < 3 else ""
            # schedule text update on main thread
            label_widget.after(0, lambda d=dots: label_widget.config(text="AI is thinking" + d))
            time.sleep(0.45)
        label_widget.after(0, lambda: label_widget.config(text=""))
    t = threading.Thread(target=loader, daemon=True)
    t.start()
    return t

# ===================== SAVE/AI FLOW (worker thread) =====================
def perform_save_thread(name, age, gender, symptoms, appointment_date, email, notes):
    """
    Worker thread:
     - Calls Gemini (if available)
     - Schedules database save on main thread with results (diagnosis)
    """
    diagnosis = "AI not available."
    ai_error = None
    try:
        diagnosis = call_gemini(symptoms)
    except Exception as e:
        ai_error = str(e)
        diagnosis = f"[AI Error] {ai_error}"

    # Continuation runs on main thread
    def after_ai():
        set_loading(False)
        # If AI errored, ask user whether to continue saving.
        if ai_error:
            proceed = messagebox.askyesno("AI Error",
                                          f"AI failed: {ai_error}\n\nSave record without AI analysis?")
            if not proceed:
                btn_add_patient.config(state=tk.NORMAL)
                return
        else:
            proceed = messagebox.askokcancel("AI Diagnosis Review",
                                             f"AI Generated Analysis:\n\n{diagnosis}\n\nSave this patient record?")
            if not proceed:
                btn_add_patient.config(state=tk.NORMAL)
                return

        # Save to DB
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                query = """
                INSERT INTO patients
                (name, age, gender, symptoms, diagnosis, doctor_notes, appointment_date, email)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """
                cursor.execute(query, (name, int(age), gender, symptoms, diagnosis, notes, appointment_date, email))
                conn.commit()
                messagebox.showinfo("Saved", "Patient data saved.")
                # send email reminder in background (non-blocking)
                threading.Thread(target=send_email_reminder, args=(email, name, appointment_date), daemon=True).start()
            except mysql.connector.Error as e:
                messagebox.showerror("DB Save Error", f"Failed to save record: {e}")
            finally:
                cursor.close()
                conn.close()
        else:
            messagebox.showerror("DB Error", "Could not connect to database. Record not saved.")

        btn_add_patient.config(state=tk.NORMAL)
        clear_fields()
        view_patients()

    root.after(0, after_ai)

# ===================== UI ACTIONS =====================
def save_patient():
    """Collect UI entries, validate, then call background worker to call AI and save."""
    name = entry_name.get().strip()
    age = entry_age.get().strip()
    gender = gender_var.get()
    symptoms = text_symptoms.get("1.0", tk.END).strip()
    appointment_date = entry_date.get().strip()
    email = entry_email.get().strip()

    # Basic validation
    if not (name and age and gender != "Select" and symptoms and appointment_date and email):
        messagebox.showerror("Input Error", "All fields are required.")
        return
    try:
        age_i = int(age)
        if age_i <= 0 or age_i > 130:
            raise ValueError
    except Exception:
        messagebox.showerror("Input Error", "Enter a valid numeric age.")
        return
    try:
        # Expect YYYY-MM-DD
        datetime.strptime(appointment_date, "%Y-%m-%d")
    except Exception:
        messagebox.showerror("Input Error", "Appointment date must be YYYY-MM-DD.")
        return

    # Optional doctor notes
    notes = simpledialog.askstring("Doctor Notes", "Enter any additional notes (optional):") or "N/A"

    # Start worker thread
    btn_add_patient.config(state=tk.DISABLED)
    set_loading(True)
    start_loading(loading_label)
    worker = threading.Thread(target=perform_save_thread,
                              args=(name, age, gender, symptoms, appointment_date, email, notes),
                              daemon=True)
    worker.start()

def view_patients():
    """Fetch last 100 patients and populate the treeview."""
    for item in tree_output.get_children():
        tree_output.delete(item)
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, name, age, gender, appointment_date, email FROM patients ORDER BY id DESC LIMIT 100")
            rows = cursor.fetchall()
            for r in rows:
                tree_output.insert("", tk.END, values=(r["id"], r["name"], r["age"], r["gender"], r["appointment_date"], r["email"]))
        except mysql.connector.Error as e:
            messagebox.showerror("DB Error", f"Failed to fetch patients: {e}")
        finally:
            cursor.close()
            conn.close()

def show_full_details(event):
    """Open a details window when a patient row is double-clicked."""
    sel = tree_output.selection()
    if not sel:
        return
    item = tree_output.item(sel)
    if not item or "values" not in item:
        return
    patient_id = item["values"][0]
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
            pdata = cursor.fetchone()
            if pdata:
                details_window = tk.Toplevel(root)
                details_window.title(f"Details - {pdata['name']}")
                details_window.geometry("700x520")

                # Details text widget: shows symptoms, AI diagnosis, doctor notes
                txt = scrolledtext.ScrolledText(details_window, wrap=tk.WORD, font=("Helvetica", 11))
                txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                content = (
                    f"ID: {pdata.get('id')}\n"
                    f"Name: {pdata.get('name')}\n"
                    f"Age: {pdata.get('age')}\n"
                    f"Gender: {pdata.get('gender')}\n"
                    f"Email: {pdata.get('email')}\n"
                    f"Appointment Date: {pdata.get('appointment_date')}\n\n"
                    f"--- Symptoms ---\n{pdata.get('symptoms')}\n\n"
                    f"--- AI Diagnosis & Recommendations ---\n{pdata.get('diagnosis')}\n\n"
                    f"--- Doctor Notes ---\n{pdata.get('doctor_notes')}\n"
                )
                txt.insert(tk.END, content)
                txt.config(state=tk.DISABLED)

                # Export-to-PDF button in the details window
                btn_pdf = ttk.Button(details_window, text="Export to PDF", command=lambda: export_to_pdf(pdata))
                btn_pdf.pack(pady=6)
        except mysql.connector.Error as e:
            messagebox.showerror("DB Error", f"Failed to fetch details: {e}")
        finally:
            cursor.close()
            conn.close()

# ===================== UI HELPERS =====================
def clear_fields():
    """Clear all data-entry widgets (used after successful save)."""
    entry_name.delete(0, tk.END)
    entry_age.delete(0, tk.END)
    entry_email.delete(0, tk.END)
    gender_var.set("Select")
    text_symptoms.delete("1.0", tk.END)
    entry_date.delete(0, tk.END)

# ===================== MAIN UI BUILD (all widgets commented) =====================
root = tk.Tk()
root.title("🏥 Hospital Management System")
root.geometry("1366×768")

# Optional Azure theme loader - safe fallback if missing
try:
    if os.path.exists("azure.tcl"):
        root.tk.call("source", "azure.tcl")
        # set_theme may be "light" or "dark" depending on file; adjust if needed
        try:
            root.tk.call("set_theme", "dark")
        except Exception:
            pass
except Exception as e:
    print("Azure theme not loaded (continuing with default):", e)

style = ttk.Style(root)
style.configure("TLabel", font=("Helvetica", 11))
style.configure("TButton", font=("Helvetica", 11, "bold"))
style.configure("Treeview.Heading", font=("Helvetica", 12, "bold"))

# ---------- Main Frame ----------
# main_frame: container for the whole app area
main_frame = ttk.Frame(root, padding=10)
main_frame.pack(fill=tk.BOTH, expand=True)

# ---------- Title ----------
# lbl_title: big app title at the top
lbl_title = tk.Label(main_frame, text="Gemini Hospital Management System", font=("Helvetica", 20, "bold"))
lbl_title.pack(pady=8)

# ---------- Input Frame ----------
# input_frame: holds all patient registration controls
input_frame = ttk.LabelFrame(main_frame, text="Patient Registration", padding=10)
input_frame.pack(fill="x", pady=10)

# labels list - used to lay out fields (you can change text here)
labels = ["Name", "Age", "Gender", "Symptoms", "Appointment (YYYY-MM-DD)", "Email"]

# entry_name: text entry for patient name (customize font/width/placeholder)
entry_name = ttk.Entry(input_frame, width=40)

# entry_age: text entry for age (validate in save_patient)
entry_age = ttk.Entry(input_frame, width=40)

# gender_var + gender_menu: dropdown for gender selection
gender_var = tk.StringVar(value="Select")
gender_menu = ttk.OptionMenu(input_frame, gender_var, "Select", "Male", "Female", "Other")

# text_symptoms: multi-line text box to enter patient symptoms
text_symptoms = tk.Text(input_frame, height=5, width=40)

# entry_date: text entry for appointment date in YYYY-MM-DD (you can replace with a datepicker)
entry_date = ttk.Entry(input_frame, width=40)

# entry_email: text entry for patient's email (used for reminders)
entry_email = ttk.Entry(input_frame, width=40)

# Layout the labels and inputs in a grid - change grid padding if you want spacing
for i, txt in enumerate(labels):
    lbl = ttk.Label(input_frame, text=txt)  # label widget for each field
    lbl.grid(row=i, column=0, sticky="w", padx=6, pady=6)

entry_name.grid(row=0, column=1, padx=6, pady=6, sticky="ew")
entry_age.grid(row=1, column=1, padx=6, pady=6, sticky="ew")
gender_menu.grid(row=2, column=1, padx=6, pady=6, sticky="ew")
text_symptoms.grid(row=3, column=1, padx=6, pady=6, sticky="ew")
entry_date.grid(row=4, column=1, padx=6, pady=6, sticky="ew")
entry_email.grid(row=5, column=1, padx=6, pady=6, sticky="ew")

input_frame.columnconfigure(1, weight=1)  # make second column expand

# ---------- Loading label ----------
# loading_label: shows the "AI is thinking..." animation text while AI runs
loading_label = ttk.Label(main_frame, text="", font=("Helvetica", 11, "italic"), foreground="green")
loading_label.pack(pady=5)

# ---------- Button Frame ----------
# button_frame: contains primary action buttons (Register, Refresh)
button_frame = ttk.Frame(main_frame)
button_frame.pack(pady=6)

# btn_add_patient: triggers save_patient flow (AI + DB save)
btn_add_patient = ttk.Button(button_frame, text="Register Patient & Get AI Analysis", command=save_patient)
btn_add_patient.pack(side=tk.LEFT, padx=6)

# btn_view: refreshes the patient list (calls view_patients)
btn_view = ttk.Button(button_frame, text="Refresh Patient List", command=view_patients)
btn_view.pack(side=tk.LEFT, padx=6)

# ---------- Output Frame (Treeview) ----------
# output_frame: holds treeview and scrollbar for patient list
output_frame = ttk.LabelFrame(main_frame, text="Patient Records (Double-click to see details)", padding=10)
output_frame.pack(fill=tk.BOTH, expand=True, pady=8)

# Columns for the treeview (you can change what to show)
columns = ("id", "name", "age", "gender", "appointment_date", "email")

# tree_output: table-like widget showing recent patients (customize column widths / headings)
tree_output = ttk.Treeview(output_frame, columns=columns, show="headings")
for col in columns:
    tree_output.heading(col, text=col.replace("_", " ").title())
    tree_output.column(col, width=120)  # adjust width as you like
tree_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

# scrollbar: vertical scrollbar for the treeview (attach to tree_output)
scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=tree_output.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
tree_output.configure(yscrollcommand=scrollbar.set)

# Bind double-click on a row to show_full_details
tree_output.bind("<Double-1>", show_full_details)

# ---------- Initial load ----------
# Populate patient list at startup
view_patients()

# ---------- Start main loop ----------
root.mainloop()
