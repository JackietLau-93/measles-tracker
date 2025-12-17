import streamlit as st
import pandas as pd
import gspread
from datetime import datetime

# --- CONNECT TO GOOGLE SHEETS ---
def get_db_connection():
    # Load credentials from Streamlit Secrets (Secure Cloud Storage)
    # When running locally, you need a .streamlit/secrets.toml file
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open("Measles_DB") # Name of your Google Sheet
        worksheet = sh.worksheet("Cases")
        return worksheet
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return None

def load_data():
    ws = get_db_connection()
    if ws:
        data = ws.get_all_records()
        return pd.DataFrame(data)
    return pd.DataFrame()

def save_new_case(case_dict):
    ws = get_db_connection()
    if ws:
        # Convert dict values to a list in the right order (matching headers)
        headers = ws.row_values(1)
        row_to_add = [str(case_dict.get(h, "")) for h in headers]
        ws.append_row(row_to_add)

def update_case(case_id, update_dict):
    ws = get_db_connection()
    if ws:
        # Find the row number
        cell = ws.find(str(case_id))
        if cell:
            row_num = cell.row
            headers = ws.row_values(1)
            # Update specific cells
            for key, value in update_dict.items():
                if key in headers:
                    col_num = headers.index(key) + 1
                    ws.update_cell(row_num, col_num, str(value))

# --- APP UI START ---
st.set_page_config(page_title="Measles Cloud System", layout="wide", page_icon="☁️")
st.sidebar.title("☁️ Measles System")
role = st.sidebar.radio("Role:", ["👨‍⚕️ Clinician", "🕵️ Epidemiologist", "📊 Admin"])

# 1. CLINICIAN VIEW
if role == "👨‍⚕️ Clinician":
    st.header("Phase 1: Clinical Entry")
    with st.form("entry_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name")
        mykad = c2.text_input("ID / MyKad")
        
        c3, c4 = st.columns(2)
        age = c3.number_input("Age", min_value=0)
        district = c4.selectbox("District", ["Timur Laut", "Barat Daya", "SPU", "SPT", "SPS"])
        
        st.subheader("Clinical")
        fever = st.selectbox("Fever", ["Yes", "No"])
        rash = st.selectbox("Rash", ["Yes", "No"])
        complaint = st.text_area("Notes")
        
        if st.form_submit_button("🚀 Submit Case"):
            new_id = datetime.now().strftime("%Y%m%d%H%M%S")
            data = {
                "ID": new_id, "Status": "Pending_Epi", "Name": name, "MyKad": mykad,
                "Age": age, "District": district, "Fever": fever, "Rash": rash,
                "Complaint": complaint, "Final_Classification": "Pending"
            }
            save_new_case(data)
            st.success(f"Case {name} uploaded to Cloud Database!")

# 2. EPIDEMIOLOGIST VIEW
elif role == "🕵️ Epidemiologist":
    st.header("Phase 2: Investigation")
    df = load_data()
    
    # Show cases that are NOT finalized
    if not df.empty:
        pending = df[df["Status"] != "Finalized"]
        case_list = pending["ID"].astype(str) + " - " + pending["Name"]
        selection = st.selectbox("Select Case", case_list)
        
        if selection:
            sel_id = selection.split(" - ")[0]
            # Get current data for this case
            case_row = df[df["ID"].astype(str) == sel_id].iloc[0]
            
            st.info(f"Reviewing: **{case_row['Name']}** (District: {case_row['District']})")
            
            with st.form("epi_form"):
                c1, c2 = st.columns(2)
                lab_igm = c1.selectbox("IgM Result", ["Pending", "Positive", "Negative"])
                lab_pcr = c2.selectbox("PCR Result", ["Not Done", "Positive", "Negative"])
                epi_link = st.selectbox("Epi Link?", ["No", "Yes"])
                
                if st.form_submit_button("✅ Finalize & Save"):
                    # Logic
                    final_class = "Discarded"
                    if lab_pcr == "Positive" or lab_igm == "Positive": final_class = "Lab Confirmed Measles"
                    elif epi_link == "Yes": final_class = "Epi Linked Measles"
                    
                    updates = {
                        "Status": "Finalized",
                        "Lab_IgM": lab_igm,
                        "Lab_PCR": lab_pcr,
                        "Epi_Link": epi_link,
                        "Final_Classification": final_class
                    }
                    update_case(sel_id, updates)
                    st.success("Database Updated Successfully!")
                    st.rerun()

# 3. ADMIN VIEW
elif role == "📊 Admin":
    st.header("Master Linelist (Live from Google Sheets)")
    df = load_data()
    if not df.empty:
        st.dataframe(df)
        st.download_button("Download CSV", df.to_csv().encode('utf-8'), "linelist.csv")