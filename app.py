import streamlit as st
import sqlite3
import os, re, hashlib, html
from datetime import datetime
from io import BytesIO
from PIL import Image
import urllib.parse

# Matplotlib (Render-safe)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import google.generativeai as genai

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(page_title="NutriVision", page_icon="🥗", layout="wide")

# --------------------------------------------------
# GEMINI CONFIG (Render-safe)
# --------------------------------------------------
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# --------------------------------------------------
# CONSTANTS
# --------------------------------------------------
DB = "nutrivision.db"
HIGH_CAL_THRESHOLD = 500
APP_URL = "https://nutri-app.onrender.com"   # 🔁 change if needed

# --------------------------------------------------
# DATABASE
# --------------------------------------------------
def db():
    return sqlite3.connect(DB)

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        username TEXT PRIMARY KEY,
        password TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        date TEXT,
        meal TEXT,
        calories INTEGER,
        details TEXT
    )
    """)
    con.commit()
    con.close()

init_db()

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def hash_pass(p):
    return hashlib.sha256(p.encode()).hexdigest()

def extract_calories(text):
    m = re.search(r'(\d+)\s*kcal', text, re.I)
    return int(m.group(1)) if m else 0

def extract_macros(text):
    p = re.search(r'Protein[:\s]+(\d+)', text, re.I)
    c = re.search(r'Carb\w*[:\s]+(\d+)', text, re.I)
    f = re.search(r'Fat\w*[:\s]+(\d+)', text, re.I)
    if not (p and c and f):
        return None, None, None
    return int(p.group(1)), int(c.group(1)), int(f.group(1))

# ---------- PDF CLEANING ----------
def clean_text(text):
    text = html.escape(text)
    text = text.replace("**", "")
    text = text.replace("*", "")
    return text

def generate_pdf(text):
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=50,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "NormalText",
        parent=styles["Normal"],
        fontSize=11,
        leading=14
    )

    story = []
    story.append(Paragraph("NutriVision – Nutrition Report", styles["Title"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Generated on: {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        styles["Normal"]
    ))
    story.append(Spacer(1, 14))

    for line in clean_text(text).split("\n"):
        if line.strip():
            story.append(Paragraph(line, normal))
            story.append(Spacer(1, 6))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Generated using NutriVision App", styles["Italic"]))

    doc.build(story)
    buf.seek(0)
    return buf

def ai_analysis(prompt, image):
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    return model.generate_content([prompt, image]).text

def whatsapp_share(text):
    return "https://wa.me/?text=" + urllib.parse.quote(text)

# --------------------------------------------------
# SESSION
# --------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

# --------------------------------------------------
# DARK UI
# --------------------------------------------------
st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg,#0f2027,#203a43,#2c5364);
}
input, textarea {
    background:#1e1e1e !important;
    color:white !important;
}
.stButton>button {
    background:linear-gradient(90deg,#00c6ff,#0072ff);
    color:white;
    font-weight:bold;
    border-radius:12px;
}
.card {
    background:#121212;
    padding:16px;
    border-radius:10px;
    box-shadow:0 0 20px rgba(0,255,255,.2);
}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# AUTH
# --------------------------------------------------
if not st.session_state.logged_in:
    st.title("🔐 NutriVision Authentication")
    t1, t2 = st.tabs(["Login", "Create Account"])

    with t1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            con = db(); cur = con.cursor()
            cur.execute("SELECT password FROM users WHERE username=?", (u,))
            r = cur.fetchone(); con.close()
            if r and r[0] == hash_pass(p):
                st.session_state.logged_in = True
                st.session_state.username = u
                st.rerun()
            else:
                st.error("Invalid credentials")

    with t2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        if st.button("Create Account"):
            try:
                con = db(); cur = con.cursor()
                cur.execute("INSERT INTO users VALUES (?,?)", (nu, hash_pass(np)))
                con.commit(); con.close()
                st.success("Account created. Login now.")
            except:
                st.error("Username already exists")

    st.stop()

# --------------------------------------------------
# MAIN UI
# --------------------------------------------------
st.title("🥗 NutriVision")
st.write(f"Welcome **{st.session_state.username}**")

uploaded = st.file_uploader("Upload food / beverage image", ["jpg","png","jpeg"])
qty = st.text_input("Quantity", "100g")

if uploaded:
    st.image(Image.open(uploaded), width=300)

prompt = f"""
You are a nutritionist.

Quantity: {qty}

Meal Name:
Ingredients and Calories:
Total Calories: X kcal

Macronutrient Profile:
Protein: X
Carbs: X
Fat: X
Fiber: X grams

Healthiness:
Recommendation:
Kids suitability:
"""

# --------------------------------------------------
# ANALYSIS
# --------------------------------------------------
if st.button("Analyse Food"):
    if not uploaded:
        st.warning("Upload image first")
    else:
        with st.spinner("Analyzing..."):
            image_data = {"mime_type": uploaded.type, "data": uploaded.getvalue()}
            result = ai_analysis(prompt, image_data)

        calories = extract_calories(result)

        con = db(); cur = con.cursor()
        cur.execute("""
        INSERT INTO history(username,date,meal,calories,details)
        VALUES (?,?,?,?,?)
        """, (
            st.session_state.username,
            datetime.now().strftime("%d-%m-%Y %H:%M"),
            result.split("\n")[0],
            calories,
            result
        ))
        con.commit(); con.close()

        st.markdown(f"<div class='card'>{result}</div>", unsafe_allow_html=True)

        # PIE CHART
        p, c, f = extract_macros(result)
        if all(v is not None for v in [p, c, f]) and (p + c + f) > 0:
            fig, ax = plt.subplots(figsize=(4,4))
            ax.pie([p,c,f], labels=["Protein","Carbs","Fat"], autopct="%1.1f%%", startangle=90)
            ax.set_title("Macronutrient Distribution")
            st.pyplot(fig)
            plt.close(fig)

        # PDF
        st.download_button(
            "📄 Download PDF Report",
            generate_pdf(result),
            "nutrivision_report.pdf"
        )

        # WHATSAPP SHARE
        share_text = f"""
NutriVision – Nutrition Report

User: {st.session_state.username}

{result}

Download full PDF:
{APP_URL}
"""
        st.markdown(
            f"""
            <a href="{whatsapp_share(share_text)}" target="_blank"
            style="
                display:inline-block;
                background:#25D366;
                color:white;
                padding:12px 20px;
                border-radius:14px;
                font-size:16px;
                font-weight:700;
                text-decoration:none;
                margin-top:12px;
            ">
            📤 Share Report on WhatsApp
            </a>
            """,
            unsafe_allow_html=True
        )

# --------------------------------------------------
# HISTORY
# --------------------------------------------------
st.markdown("## 📅 Calorie History")
con = db(); cur = con.cursor()
cur.execute("""
SELECT date, meal, calories
FROM history
WHERE username=?
ORDER BY date DESC
""", (st.session_state.username,))
rows = cur.fetchall()
con.close()

for d, meal, cal in rows:
    color = "#FF5252" if cal >= HIGH_CAL_THRESHOLD else "#81C784"
    icon = "🔴" if cal >= HIGH_CAL_THRESHOLD else "🟢"
    st.markdown(
        f"""
        <div class='card' style='border-left:6px solid {color};'>
        {icon} <b>{meal}</b><br>
        Calories: <span style='color:{color}; font-weight:bold;'>{cal} kcal</span>
        </div>
        """,
        unsafe_allow_html=True
    )

# --------------------------------------------------
# FOOTER
# --------------------------------------------------
st.markdown("""
<hr>
<div style="text-align:center; color:#B0BEC5; font-size:14px;">
<b>Developed by</b> Aishwarya Patil · C. G. Balasubramanyam Singh · Madhushree · Pradeep S<br>
Final Year – Information Science & Engineering<br>
PDA College of Engineering © 2025
</div>
""", unsafe_allow_html=True)
