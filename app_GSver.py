import streamlit as st
import pandas as pd
import gspread
from datetime import datetime

# --- CONNECT TO GOOGLE SHEETS ---
def get_db_connection():
    try:
        # Load credentials securely from secrets
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open("Measles_DB") 
        worksheet = sh.worksheet("Cases")
        return worksheet
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return None

def load_data():
    ws = get_db_connection()
    if ws:
        data = ws.get_all_records()
        # Ensure ID is treated as string to prevent matching errors
        df = pd.DataFrame(data)
        if not df.empty:
            df['ID'] = df['ID'].astype(str)
        return df
    return pd.DataFrame()

def save_new_case(case_dict):
    ws = get_db_connection()
    if ws:
        headers = ws.row_values(1)
        row_to_add = [str(case_dict.get(h, "")) for h in headers]
        ws.append_row(row_to_add)

def update_case(case_id, update_dict):
    ws = get_db_connection()
    if ws:
        cell = ws.find(str(case_id))
        if cell:
            row_num = cell.row
            headers = ws.row_values(1)
            for key, value in update_dict.items():
                if key in headers:
                    col_num = headers.index(key) + 1
                    ws.update_cell(row_num, col_num, str(value))

# --- AUTHENTICATION LOGIC ---
def check_password(role_key):
    """Returns True if the user is logged in for the specific role."""
    
    # Initialize session state for this role if not exists
    if f"auth_{role_key}" not in st.session_state:
        st.session_state[f"auth_{role_key}"] = False

    # If already logged in, return True
    if st.session_state[f"auth_{role_key}"]:
        return True

    # Show Login Form
    st.markdown(f"### 🔒 {role_key.capitalize()} Access Locked")
    password = st.text_input("Enter Password", type="password", key=f"pw_{role_key}")
    
    if st.button("Login", key=f"btn_{role_key}"):
        # Check against secrets
        correct_password = st.secrets["passwords"][role_key]
        if password == correct_password:
            st.session_state[f"auth_{role_key}"] = True
            st.rerun()
        else:
            st.error("❌ Incorrect Password")
    
    return False

def logout(role_key):
    st.session_state[f"auth_{role_key}"] = False
    st.rerun()

# --- APP UI START ---
st.set_page_config(page_title="Measles Cloud System", layout="wide", page_icon="🔐")

st.sidebar.title("🔐 Role Selection")
role = st.sidebar.radio("Select Your Portal:", ["clinician", "epidemiologist", "admin"], format_func=lambda x: x.capitalize())

st.sidebar.markdown("---")

# --- VIEW 1: CLINICIAN ---
if role == "clinician":
    if check_password("clinician"):
        st.sidebar.button("Log Out", on_click=logout, args=("clinician",))
        
        st.header("👨‍⚕️ Phase 1: Clinical Entry")
        st.info("Please clerk the patient and submit for investigation.")
        
        with st.form("entry_form"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Name")
            mykad = c2.text_input("ID / MyKad")
            
            c3, c4 = st.columns(2)
            age = c3.number_input("Age", min_value=0)
            district = c4.selectbox("District", ["Timur Laut", "Barat Daya", "SPU", "SPT", "SPS"])
            
            st.subheader("Clinical Signs")
            fever = st.selectbox("Fever", ["Yes", "No"])
            rash = st.selectbox("Rash", ["Yes", "No"])
            complaint = st.text_area("Presenting Complaint")
            
            if st.form_submit_button("🚀 Submit Case"):
                if not name:
                    st.error("Name is required.")
                else:
                    new_id = datetime.now().strftime("%Y%m%d%H%M%S")
                    data = {
                        "ID": new_id, "Status": "Pending_Epi", "Name": name, "MyKad": mykad,
                        "Age": age, "District": district, "Fever": fever, "Rash": rash,
                        "Complaint": complaint, "Final_Classification": "Pending"
                    }
                    save_new_case(data)
                    st.success(f"Case uploaded successfully! ID: {new_id}")

# --- VIEW 2: EPIDEMIOLOGIST ---
elif role == "epidemiologist":
    if check_password("epidemiologist"):
        st.sidebar.button("Log Out", on_click=logout, args=("epidemiologist",))
        
        st.header("🕵️ Phase 2: Investigation")
        df = load_data()
        
        if df.empty:
            st.warning("No data found in database.")
        else:
            # Filter for pending cases
            pending = df[df["Status"] != "Finalized"]
            
            if pending.empty:
                st.success("No pending cases! Good job.")
            else:
                case_list = pending["ID"].astype(str) + " - " + pending["Name"]
                selection = st.selectbox("Select Case to Investigate", case_list)
                
                if selection:
                    sel_id = selection.split(" - ")[0]
                    case_row = df[df["ID"].astype(str) == sel_id].iloc[0]
                    
                    # Display Read-Only Clinical Data
                    with st.expander("📄 View Clinical Notes (Read-Only)", expanded=True):
                        st.write(f"**Patient:** {case_row['Name']} ({case_row['Age']}yo)")
                        st.write(f"**Complaint:** {case_row['Complaint']}")
                        st.write(f"**Signs:** Fever: {case_row['Fever']}, Rash: {case_row['Rash']}")
                    
                    st.divider()
                    
                    with st.form("epi_form"):
                        st.subheader("Investigation Findings")
                        c1, c2 = st.columns(2)
                        lab_igm = c1.selectbox("IgM Result", ["Pending", "Positive", "Negative"])
                        lab_pcr = c2.selectbox("PCR Result", ["Not Done", "Positive", "Negative"])
                        epi_link = st.selectbox("Epi Link?", ["No", "Yes"])
                        
                        if st.form_submit_button("✅ Finalize & Save"):
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
                            st.balloons()
                            st.success("Case Finalized!")
                            st.rerun()

# --- VIEW 3: ADMIN ---
elif role == "admin":
    if check_password("admin"):
        st.sidebar.button("Log Out", on_click=logout, args=("admin",))
        
        st.header("📊 Phase 3: Master Linelist")
        df = load_data()
        
        if not df.empty:
            # Metrics
            m1, m2, m3 = st.columns(3)
            finalized = df[df["Status"] == "Finalized"]
            m1.metric("Total Cases", len(df))
            m2.metric("Pending Investigation", len(df) - len(finalized))
            m3.metric("Confirmed Measles", len(df[df['Final_Classification'].str.contains("Measles")]))
            
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Database (CSV)", csv, "full_database.csv", "text/csv")
        else:
            st.info("Database is empty.")