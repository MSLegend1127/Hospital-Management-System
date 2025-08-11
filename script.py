import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, scrolledtext
from datetime import datetime
from fpdf import FPDF
import mysql.connector
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import openai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ================= CONFIG =================
load_dotenv()  # Load .env variables

openai.api_key = os.getenv("OPENAI_API_KEY")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "hospital"
}

# ================= DB Connection =================
def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        messagebox.showerror("Database Error", str(e))
        return None

# ================= Loading Animation =================
loading_event = threading.Event()

def animate_loading(label):
    dots = ""
    while not loading_event.is_set():
        dots = (dots + ".") if len(dots) < 3 else ""
        label.config(text="Processing" + dots)
        time.sleep(0.5)
    label.config(text="")

# ================= AI SYMPTOM CHECKER =================
def get_diagnosis_with_animation(symptoms, loading_label):
    loading_event.clear()
    thread = threading.Thread(target=animate_loading, args=(loading_label,), daemon=True)
    thread.start()

    diagnosis = "Error: Unable to get diagnosis"
    try:
        prompt = (
            f"A patient has the following symptoms: {symptoms}.\n"
            "Provide:\n- Likely diagnosis\n- Recommended tests\n"
            "- Specialist to see\n- Home care suggestions"
        )
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250
        )
        diagnosis = response.choices[0].message['content'].strip()
    except Exception as e:
        diagnosis = f"AI Error: {str(e)}"

    loading_event.set()
    thread.join()
    return diagnosis

# ================= EMAIL REMINDER =================
def send_email_reminder(to_email, name, date_str):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        msg['Subject'] = "Appointment Reminder"

        body = f"Dear {name},\n\nThis is a reminder for your appointment on {date_str}.\n\n- Hospital Team"
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"✅ Email sent to {to_email}")
    except Exception as e:
        print("❌ Email error:", e)

# ================= EXPORT TO PDF =================
def export_to_pdf(patient_data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Patient Report", ln=True, align='C')
    for key, value in patient_data.items():
        pdf.multi_cell(0, 10, f"{key}: {value}")
    pdf.output("Patient_Report.pdf")
    messagebox.showinfo("PDF Exported", "Report saved as Patient_Report.pdf")

# ================= PATIENT MANAGEMENT =================
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

    btn_add_patient.config(state=tk.DISABLED)
    diagnosis = get_diagnosis_with_animation(symptoms, loading_label)
    btn_add_patient.config(state=tk.NORMAL)

    notes = simpledialog.askstring("Doctor Notes", "Enter additional doctor notes:")

    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            query = """
            INSERT INTO patients (name, age, gender, symptoms, diagnosis, doctor_notes, appointment_date, email)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (name, int(age), gender, symptoms, diagnosis, notes, appointment_date, email))
        conn.commit()
        conn.close()

    send_email_reminder(email, name, appointment_date)
    messagebox.showinfo("Saved", "Patient data saved with diagnosis.")
    clear_fields()

def view_patients():
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, age, symptoms, diagnosis, doctor_notes, appointment_date FROM patients LIMIT 50")
            rows = cursor.fetchall()
        conn.close()
        text_output.delete("1.0", tk.END)
        for row in rows:
            text_output.insert(tk.END, f"ID: {row[0]}, Name: {row[1]}, Age: {row[2]}\n")
            text_output.insert(tk.END, f"Symptoms: {row[3]}\nDiagnosis: {row[4]}\nNotes: {row[5]}\nDate: {row[6]}\n\n")

# ================= UI HELPERS =================
def clear_fields():
    entry_name.delete(0, tk.END)
    entry_age.delete(0, tk.END)
    entry_email.delete(0, tk.END)
    gender_var.set("Select")
    text_symptoms.delete("1.0", tk.END)
    entry_date.delete(0, tk.END)

# ================= UI =================
root = tk.Tk()
root.title("🏥 Hospital Management System + AI")
root.geometry("900x700")

tk.Label(root, text="Hospital Management System with AI", font=("Helvetica", 16, "bold")).pack(pady=10)
frame = tk.Frame(root)
frame.pack(pady=10)

labels = ["Name", "Age", "Gender", "Symptoms", "Appointment Date (YYYY-MM-DD)", "Email"]
entries = []
for i, text in enumerate(labels):
    tk.Label(frame, text=text).grid(row=i, column=0, sticky="w")
    if text == "Gender":
        gender_var = tk.StringVar(value="Select")
        tk.OptionMenu(frame, gender_var, "Male", "Female", "Other").grid(row=i, column=1)
    elif text == "Symptoms":
        text_symptoms = tk.Text(frame, height=4, width=30)
        text_symptoms.grid(row=i, column=1)
    else:
        e = tk.Entry(frame)
        e.grid(row=i, column=1)
        entries.append(e)

entry_name, entry_age, entry_date, entry_email = entries[0], entries[1], entries[2], entries[3]

loading_label = tk.Label(root, text="", font=("Helvetica", 10, "italic"), fg="green")
loading_label.pack()

btn_add_patient = tk.Button(root, text="Add Patient", command=save_patient)
btn_add_patient.pack(pady=5)

btn_view = tk.Button(root, text="View All Patients", command=view_patients)
btn_view.pack(pady=5)

text_output = scrolledtext.ScrolledText(root, height=15, width=100)
text_output.pack(pady=10)

root.mainloop()
