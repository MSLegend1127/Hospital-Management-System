import tkinter as tk
from tkinter import messagebox, simpledialog
import mysql.connector
import openai
import matplotlib.pyplot as plt
from fpdf import FPDF
from datetime import datetime, date
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time

# ============ CONFIGS ============
openai.api_key = "your-openai-api-key"  # Replace with your actual key

EMAIL_ADDRESS = "your-email@gmail.com"
EMAIL_PASSWORD = "your-email-password"  # Enable App Password in Gmail

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",  # Change if needed
    database="hospital"
)
cursor = conn.cursor()

# ============ Loading Animation Setup ============
loading = False
def animate_loading(label):
    dots = ""
    while loading:
        dots += "."
        if len(dots) > 3:
            dots = ""
        label.config(text="Processing" + dots)
        time.sleep(0.5)
    label.config(text="")  # Clear loading text when done

# ============ AI SYMPTOM CHECKER with Animation ============
def get_diagnosis_with_animation(symptoms, loading_label):
    global loading
    loading = True
    thread = threading.Thread(target=animate_loading, args=(loading_label,))
    thread.start()

    try:
        prompt = f"""
        A patient has the following symptoms: {symptoms}.
        - What could be the most likely diagnosis?
        - What tests should be conducted?
        - What type of specialist should they see?
        - Provide home care suggestions if applicable.
        """
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250
        )
        diagnosis = response.choices[0].message['content'].strip()
    except Exception as e:
        diagnosis = f"AI error: {str(e)}"
    
    loading = False
    thread.join()
    return diagnosis

# ============ EMAIL REMINDER ============
def send_email_reminder(to_email, name, date_str):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        msg['Subject'] = "Appointment Reminder"

        body = f"Dear {name},\n\nThis is a reminder for your appointment scheduled on {date_str}.\n\n- Hospital Team"
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print("✅ Email sent to", to_email)
    except Exception as e:
        print("❌ Email error:", e)

# ============ EXPORT TO PDF ============
def export_to_pdf(patient_data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Patient Report", ln=True, align='C')
    for key, value in patient_data.items():
        pdf.cell(200, 10, txt=f"{key}: {value}", ln=True)
    pdf.output("Patient_Report.pdf")
    messagebox.showinfo("PDF Exported", "Report saved as Patient_Report.pdf")

# ============ SAVE PATIENT ============
def save_patient():
    name = entry_name.get()
    age = entry_age.get()
    gender = gender_var.get()
    symptoms = text_symptoms.get("1.0", tk.END).strip()
    appointment_date = entry_date.get()
    email = entry_email.get()

    if not (name and age and gender and symptoms and appointment_date and email):
        messagebox.showerror("Input Error", "All fields are required.")
        return
    
    # Disable Add button while processing
    btn_add_patient.config(state=tk.DISABLED)
    diagnosis = get_diagnosis_with_animation(symptoms, loading_label)
    btn_add_patient.config(state=tk.NORMAL)

    notes = simpledialog.askstring("Doctor Notes", "Enter additional doctor notes:")

    query = """
    INSERT INTO patients (name, age, gender, symptoms, diagnosis, doctor_notes, appointment_date, email)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (name, int(age), gender, symptoms, diagnosis, notes, appointment_date, email)
    cursor.execute(query, values)
    conn.commit()

    send_email_reminder(email, name, appointment_date)

    messagebox.showinfo("Saved", "Patient data saved with diagnosis.")
    clear_fields()

# ============ VIEW ALL PATIENTS ============
def view_patients():
    cursor.execute("SELECT id, name, age, symptoms, diagnosis, doctor_notes, appointment_date FROM patients")
    rows = cursor.fetchall()
    text_output.delete("1.0", tk.END)
    for row in rows:
        text_output.insert(tk.END, f"ID: {row[0]}, Name: {row[1]}, Age: {row[2]}\n")
        text_output.insert(tk.END, f"Symptoms: {row[3]}\nDiagnosis: {row[4]}\nNotes: {row[5]}\nDate: {row[6]}\n\n")

# ============ SEARCH ============
def search_patients():
    key = simpledialog.askstring("Search", "Enter name, date (YYYY-MM-DD), or symptom:")
    cursor.execute("SELECT name, age, symptoms, diagnosis, appointment_date FROM patients WHERE name LIKE %s OR symptoms LIKE %s OR appointment_date LIKE %s",
                   (f"%{key}%", f"%{key}%", f"%{key}%"))
    rows = cursor.fetchall()
    text_output.delete("1.0", tk.END)
    for row in rows:
        text_output.insert(tk.END, f"{row}\n")

# ============ ANALYTICS ============
def show_analytics():
    cursor.execute("SELECT appointment_date FROM patients")
    rows = cursor.fetchall()
    count_by_date = {}
    for row in rows:
        date_str = row[0].strftime("%Y-%m-%d")
        count_by_date[date_str] = count_by_date.get(date_str, 0) + 1
    dates = list(count_by_date.keys())
    counts = list(count_by_date.values())
    plt.figure(figsize=(8, 4))
    plt.bar(dates, counts, color='teal')
    plt.title("Patients per Date")
    plt.xlabel("Date")
    plt.ylabel("Number of Patients")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

# ============ PDF Export UI ============
def export_selected_patient():
    patient_id = simpledialog.askinteger("Export", "Enter Patient ID to export:")
    cursor.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
    row = cursor.fetchone()
    if row:
        keys = ["ID", "Name", "Age", "Gender", "Symptoms", "Diagnosis", "Doctor Notes", "Appointment Date", "Email"]
        patient_data = dict(zip(keys, row))
        export_to_pdf(patient_data)
    else:
        messagebox.showerror("Not Found", "No patient with that ID.")

# ============ CLEAR ============
def clear_fields():
    entry_name.delete(0, tk.END)
    entry_age.delete(0, tk.END)
    entry_email.delete(0, tk.END)
    gender_var.set("Select")
    text_symptoms.delete("1.0", tk.END)
    entry_date.delete(0, tk.END)

# ============ BUTTON HOVER EFFECTS ============
def on_enter(e):
    e.widget['background'] = 'lightblue'

def on_leave(e):
    e.widget['background'] = 'SystemButtonFace'

# ============ UI ============
root = tk.Tk()
root.title("🏥 Hospital Management System + AI")
root.geometry("900x700")

tk.Label(root, text="Hospital Management System with AI", font=("Helvetica", 16, "bold")).pack(pady=10)

frame = tk.Frame(root)
frame.pack(pady=10)

tk.Label(frame, text="Name").grid(row=0, column=0)
entry_name = tk.Entry(frame)
entry_name.grid(row=0, column=1)

tk.Label(frame, text="Age").grid(row=1, column=0)
entry_age = tk.Entry(frame)
entry_age.grid(row=1, column=1)

tk.Label(frame, text="Gender").grid(row=2, column=0)
gender_var = tk.StringVar(value="Select")
tk.OptionMenu(frame, gender_var, "Male", "Female", "Other").grid(row=2, column=1)

tk.Label(frame, text="Symptoms").grid(row=3, column=0)
text_symptoms = tk.Text(frame, height=4, width=30)
text_symptoms.grid(row=3, column=1)

tk.Label(frame, text="Appointment Date (YYYY-MM-DD)").grid(row=4, column=0)
entry_date = tk.Entry(frame)
entry_date.grid(row=4, column=1)

tk.Label(frame, text="Email").grid(row=5, column=0)
entry_email = tk.Entry(frame)
entry_email.grid(row=5, column=1)

loading_label = tk.Label(root, text="", font=("Helvetica", 10, "italic"), fg="green")
loading_label.pack()

# Buttons
btn_add_patient = tk.Button(root, text="Add Patient", command=save_patient)
btn_add_patient.pack(pady=5)

btn_view = tk.Button(root, text="View All Patients", command=view_patients)
btn_view.pack(pady=5)

btn_search = tk.Button(root, text="Search Patients", command=search_patients)
btn_search.pack(pady=5)

btn_export = tk.Button(root, text="Export to PDF", command=export_selected_patient)
btn_export.pack(pady=5)

btn_analytics = tk.Button(root, text="Show Analytics", command=show_analytics)
btn_analytics.pack(pady=5)

# Add hover effects to all buttons
for btn in [btn_add_patient, btn_view, btn_search, btn_export, btn_analytics]:
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)

text_output = tk.Text(root, height=15, width=100)
text_output.pack(pady=10)

root.mainloop()
cursor.close()
conn.close()
