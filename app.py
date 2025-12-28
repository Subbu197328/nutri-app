import streamlit as st
import sqlite3
import os, re, hashlib
from datetime import datetime
from io import BytesIO
from PIL import Image
import matplotlib.pyplot as plt

import google.generativeai as genai

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
st.set_page_config("NutriVision", "🥗", layout="wide")

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

DB = "nutrivision.db"
HIGH_CAL_THRESHOLD = 500

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
    m = re.search(r'calorie[s]?\s*[:\-]?\s*(\d+)', text, re.I)
    return int(m.group(1)) if m else 0

def extract_macros(text):
    p = re.search(r'Protein[:\s]+(\d+)', text, re.I)
    c = re.search(r'Carb\w*[:\s]+(\d+)', text, re.I)
    f = re.search(r'Fat\w*[:\s]+(\d+)', text, re.I)
    if not (p and c and f):
        return None, None, None
    return int(p.group(1)), int(c.group(1)), int(f.group(1))

def generate_pdf(text):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    for line in text.split("\n"):
        story.append(Paragraph(line, styles["Normal"]))
        story.append(Spacer(1, 8))

    doc.build(story)
    buf.seek(0)
    return buf

def ai_analysis(prompt, image):
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    return model.generate_content([prompt, image]).text

# --------------------------------------------------
# SESSION
# --------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

# --------------------------------------------------
# THEME (YOUR DARK UI)
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

    tab1, tab2 = st.tabs(["Login", "Create Account"])

    with tab1:
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

    with tab2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        if st.button("Create Account"):
            try:
                con = db(); cur = con.cursor()
                cur.execute("INSERT INTO users VALUES (?,?)",
                            (nu, hash_pass(np)))
                con.commit(); con.close()
                st.success("Account created")
            except:
                st.error("Username exists")

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
Macronutrient Profile:
Protein: X
Carbs: X
Fats: X
Fiber: X grams
Healthiness:
Recommendation:
Kids suitability:
"""

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

        p,c,f = extract_macros(result)
        if all(v is not None for v in [p,c,f]):
            fig, ax = plt.subplots()
            ax.pie([p,c,f], labels=["Protein","Carbs","Fat"], autopct="%1.1f%%")
            st.pyplot(fig)

        pdf = generate_pdf(result)
        st.download_button("📄 Download PDF", pdf, "nutrivision_report.pdf")

        st.markdown(
            "[📤 Share on WhatsApp](https://wa.me/?text=Here%20is%20my%20NutriVision%20nutrition%20report)"
        )

# --------------------------------------------------
# CALENDAR HISTORY
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

current_day = None

for d, meal, cal in rows:
    day = d.split(" ")[0]
    if day != current_day:
        st.subheader(f"📆 {day}")
        current_day = day

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
<div style="text-align:center; color:#B0BEC5;">
📝 Developed by Aishwarya Patil · C. G. Balasubramanyam Singh · Madhushree · Pradeep S<br>
Final Year – Information Science & Engineering<br>
PDA College of Engineering © 2025
</div>
""", unsafe_allow_html=True)
