import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
import requests
from streamlit_searchbox import st_searchbox

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
# --- LOGIC HELPERS ---
def clean_id(id_str):
    """Removes hyphens and spaces."""
    if id_str:
        return id_str.replace("-", "").replace(" ", "")
    return ""

def parse_mykad_dob(mykad):
    """Extracts DOB date object from 12-digit MyKad."""
    clean = clean_id(mykad)
    if len(clean) == 12 and clean.isdigit():
        try:
            year_prefix = clean[:2]
            month = clean[2:4]
            day = clean[4:6]
            
            # Simple 1900 vs 2000 logic (Adjust threshold as needed)
            current_year_short = int(datetime.now().strftime("%y"))
            full_year = f"20{year_prefix}" if int(year_prefix) <= current_year_short else f"19{year_prefix}"
            
            return datetime.strptime(f"{full_year}-{month}-{day}", "%Y-%m-%d").date()
        except ValueError:
            return None
    return None

def calculate_age_display(dob):
    """Returns string 'X years Y months'."""
    if not dob: return ""
    today = datetime.now().date()
    years = today.year - dob.year
    months = today.month - dob.month
    if today.day < dob.day:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    return f"{years} years, {months} months"

# --- MAP SEARCH FUNCTION (OpenStreetMap) ---
def search_address(search_term):
    if not search_term: return []
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": search_term,
            "format": "json",
            "countrycodes": "my",  # Limit to Malaysia
            "limit": 5,
            "addressdetails": 1
        }
        # User-Agent is required by OSM policy
        headers = {'User-Agent': 'MeaslesApp/1.0'}
        response = requests.get(url, params=params, headers=headers)
        data = response.json()
        # Return format: List of (Label, Value) tuples
        return [(item['display_name'], item['display_name']) for item in data]
    except Exception as e:
        print(f"Map Error: {e}")
        return []

# --- APP UI START ---
st.set_page_config(page_title="Measles Cloud System", layout="wide", page_icon="🔐")

st.sidebar.title("🔐 Role Selection")
role = st.sidebar.radio("Select Your Portal:", ["clinician", "epidemiologist", "admin"], format_func=lambda x: x.capitalize())

st.sidebar.markdown("---")


# --- VIEW 1: CLINICIAN ---
if role == "clinician":
    if check_password("clinician"):
        st.sidebar.button("Log Out", on_click=logout, args=("clinician",))
        
        st.header("👨‍⚕️ Phase 1: Clinical Clerking")
        st.info("Complete Sections A & B to submit for investigation.")

        # ==========================================
        # SECTION A: DEMOGRAPHICS
        # ==========================================
        st.subheader("Section A: Demographics")
        
        # 1. Patient Name (Auto-Uppercase)
        name_input = st.text_input("1. Patient Name *")
        name = name_input.upper() if name_input else ""

        # 2. MyKad & Auto-Logic
        col_id1, col_id2 = st.columns(2)
        mykad_raw = col_id1.text_input("2. MyKad / ID Number *", help="Enter without hyphens for auto-calculation")
        mykad = clean_id(mykad_raw)
        
        # Auto-detect DOB from MyKad if possible
        auto_dob = parse_mykad_dob(mykad)
        
        # 3. Nationality
        nat_choice = col_id2.selectbox("3. Nationality *", ["Malaysia", "Foreigner"])
        nationality = nat_choice
        if nat_choice == "Foreigner":
            nationality = st.text_input("Specify Nationality *")

        # 4. Ethnicity
        eth_choice = st.selectbox("4. Ethnicity *", ["Malay", "Chinese", "Indian", "Indigenous", "Others"])
        ethnicity = eth_choice
        if eth_choice == "Others":
            ethnicity = st.text_input("Specify Ethnicity *")

        # 5 & 6. Gender & DOB
        c5, c6 = st.columns(2)
        gender = c5.selectbox("5. Gender *", ["Male", "Female"])
        
        # Logic: Use Auto-DOB if valid, otherwise allow manual pick
        dob = c6.date_input("6. Date of Birth *", value=auto_dob if auto_dob else None)
        
        # Auto-Calculate Age
        age_str = calculate_age_display(dob)
        if dob:
            st.caption(f"📅 Calculated Age: **{age_str}**")
            # 12. Occupation Logic (Auto-fill if under 18)
            years_old = int(age_str.split(" ")[0])
            is_underage = years_old < 18
        else:
            is_underage = False

        # 7-10. SMART ADDRESS SEARCH
        st.markdown("---")
        st.markdown("##### 📍 Location Details")
        
        st.caption("Search for address (e.g., 'Taman Tun Sardon'):")
        selected_address = st_searchbox(
            search_address,
            key="map_search_home",
            placeholder="Type to search Google Maps/OSM..."
        )

        if "addr_final" not in st.session_state: st.session_state.addr_final = ""
        if selected_address:
            st.session_state.addr_final = selected_address

        address = st.text_area("7. Full Address (Auto-filled or Manual Input) *", 
                              value=st.session_state.addr_final, height=100)

        auto_postcode = ""
        if address:
            import re
            pc_match = re.search(r'\b\d{5}\b', address)
            if pc_match: auto_postcode = pc_match.group(0)

        c8, c9, c10 = st.columns(3)
        postcode = c8.text_input("8. Postcode *", value=auto_postcode)
        district = c9.selectbox("9. District *", ["Timur Laut", "Barat Daya", "Seberang Perai Utara", "Seberang Perai Tengah", "Seberang Perai Selatan", "Lain-lain"])
        
        # 10. State (Updated List)
        MALAYSIA_STATES = [
            "Pulau Pinang", "Johor", "Kedah", "Kelantan", "Kuala Lumpur", "Labuan", 
            "Melaka", "Negeri Sembilan", "Pahang", "Perak", "Perlis", "Putrajaya", 
            "Sabah", "Sarawak", "Selangor", "Terengganu"
        ]
        state = c10.selectbox("10. State *", MALAYSIA_STATES)

        # 11 & 12. Contact & Occupation
        c11, c12 = st.columns(2)
        contact_raw = c11.text_input("11. Contact No. *")
        contact = clean_id(contact_raw)
        
        if is_underage:
            occupation = c12.text_input("12. Occupation *", value="Underage / Student")
        else:
            occupation = c12.text_input("12. Occupation *")

        # 13 & 14. WORKPLACE / SCHOOL SEARCH
        st.markdown("##### 🏫 Premise Details")
        st.caption("Search School / Workplace Name:")
        
        selected_premise = st_searchbox(
            search_address,
            key="map_search_premise",
            placeholder="Search Premise (e.g., 'SMK Penanti')..."
        )
        
        if "premise_final" not in st.session_state: st.session_state.premise_final = ""
        if selected_premise:
            st.session_state.premise_final = selected_premise

        p_name_val = ""
        p_addr_val = ""
        if st.session_state.premise_final:
            parts = st.session_state.premise_final.split(",", 1)
            p_name_val = parts[0]
            if len(parts) > 1: p_addr_val = parts[1].strip()

        col_prem1, col_prem2 = st.columns(2)
        work_name = col_prem1.text_input("13. Workplace/School Name *", value=p_name_val)
        work_addr = col_prem2.text_area("14. Workplace/School Address *", value=p_addr_val, height=100)

        st.divider()

        # ==========================================
        # SECTION B: CLINICAL INFORMATION
        # ==========================================
        st.subheader("Section B: Clinical Information")
        st.caption("The 'Anchor' Dates below are crucial for the algorithm to determine Measles probability.")
        
        # --- B.1 HISTORY TAKING ---
        st.markdown("##### 📜 B.1 History Taking")

        # 15. FEVER
        c1, c2 = st.columns([1, 3])
        fever = c1.radio("15. Fever *", ["Yes", "No"], horizontal=True, index=1)
        
        fever_onset = None
        fever_subside = None
        fever_temp = 0.0

        if fever == "Yes":
            c2_1, c2_2, c2_3 = c2.columns(3)
            fever_onset = c2_1.date_input("15a. Onset Date *", value=None, key="f_onset")
            fever_subside = c2_2.date_input("15b. Subside Date (Optional)", value=None, key="f_sub")
            fever_temp = c2_3.number_input("15c. Max Temp (°C)", min_value=35.0, max_value=45.0, step=0.1, format="%.1f")

        # 16. RASH (The Critical Anchor)
        st.markdown("---")
        c3, c4 = st.columns([1, 3])
        rash = c3.radio("16. Rash *", ["Yes", "No"], horizontal=True, index=1)
        
        rash_onset = None
        rash_subside = None
        rash_type = "N/A"
        rash_prog = "N/A"

        if rash == "Yes":
            r1, r2 = c4.columns(2)
            rash_onset = r1.date_input("16a. Rash Onset (CRITICAL) *", value=None, key="r_onset")
            rash_subside = r2.date_input("16b. Subside Date (Optional)", value=None, key="r_sub")
            
            r3, r4 = c4.columns(2)
            rash_type_opt = r3.selectbox("16c. Type of Rash", 
                ["Maculopapular", "Vesicles/Bullae", "Pustules", "Plaques", "Nodules", "Others"])
            if rash_type_opt == "Others":
                rash_type = r3.text_input("Specify Rash Type")
            else:
                rash_type = rash_type_opt
            
            prog_opt = r4.radio("16d. Progression: Head/Face → Body?", ["Yes", "No"], horizontal=True)
            if prog_opt == "No":
                rash_prog = r4.text_input("Describe Progression")
            else:
                rash_prog = "Cephalocaudal (Head to Body)"

        # 17-20. THE 3 Cs & LYMPH
        st.markdown("---")
        st.caption("Symptoms (Leave 'No' if absent)")
        
        col_s1, col_s2 = st.columns(2)
        
        def symptom_block(label, key_prefix, col):
            with col:
                has_sym = st.checkbox(label, key=f"{key_prefix}_check")
                s_onset, s_sub = None, None
                if has_sym:
                    sc1, sc2 = st.columns(2)
                    s_onset = sc1.date_input("Onset", key=f"{key_prefix}_on")
                    s_sub = sc2.date_input("Subside", key=f"{key_prefix}_sub")
                return "Yes" if has_sym else "No", s_onset, s_sub

        cough, cough_on, cough_sub = symptom_block("17. Cough", "cough", col_s1)
        coryza, cory_on, cory_sub = symptom_block("18. Coryza (Runny Nose)", "coryza", col_s2)
        conj, conj_on, conj_sub = symptom_block("19. Conjunctivitis (Red Eye)", "conj", col_s1)
        lymph, lymph_on, lymph_sub = symptom_block("20. Lymphadenopathy", "lymph", col_s2)

        # 21. COMPLICATIONS
        st.markdown("---")
        comp_opts = st.multiselect("21. Complications", 
            ["None", "Diarrhoea", "Otitis Media", "Encephalitis/SSPE", "Pneumonia", "Others"])
        
        complications = ", ".join(comp_opts)
        if "Others" in comp_opts:
            other_comp_text = st.text_input("Specify Other Complications")
            complications += f" ({other_comp_text})"

        # 22. OTHER SYMPTOMS
        other_sx = st.text_input("22. Other Symptoms (Optional)")

        # --- B.2 PHYSICAL EXAMINATION ---
        st.divider()
        st.markdown("##### 🩺 B.2 Physical Examination")

        # 23. BLOOD PRESSURE
        c_bp1, c_bp2, c_bp3 = st.columns([1, 1, 2])
        no_cuff = st.checkbox("23a. Paediatric BP Cuff Not Available")
        
        if no_cuff:
            bp_sys, bp_dia = "N/A", "N/A"
            c_bp1.text_input("Systolic", value="N/A", disabled=True)
            c_bp2.text_input("Diastolic", value="N/A", disabled=True)
        else:
            bp_sys = c_bp1.number_input("23b. Systolic (mmHg)", min_value=0, max_value=300)
            bp_dia = c_bp2.number_input("23c. Diastolic (mmHg)", min_value=0, max_value=200)

        # 24-26. VITALS
        c_v1, c_v2, c_v3 = st.columns(3)
        pulse = c_v1.number_input("24. Pulse Rate (bpm) *", min_value=0)
        rr = c_v2.number_input("25. Resp. Rate (min) *", min_value=0)
        
        # 26. SpO2 Logic
        spo2_val = c_v3.number_input("26a. SpO2 (%) *", min_value=0, max_value=100, step=1)
        spo2_mode = c_v3.selectbox("26b. Oxygen Support", ["Room Air", "Nasal Prong", "Face Mask", "Others"])
        
        spo2_flow = "N/A"
        if spo2_mode in ["Nasal Prong", "Face Mask"]:
            spo2_flow = c_v3.number_input("Flow Rate (L/min)", min_value=0.0)
        elif spo2_mode == "Others":
            spo2_flow = c_v3.text_input("Specify Support")

        # 27. TEMPERATURE (Auto-fill Logic)
        default_temp = float(fever_temp) if (fever == "Yes" and fever_temp) else 0.0
        temp_curr = st.number_input("27. Current Temperature (°C) *", value=default_temp, step=0.1, format="%.1f")

        # 28-30. SCORES & EXAM
        c_ex1, c_ex2 = st.columns(2)
        pain_score = c_ex1.slider("28. Pain Score", 0, 10, 0)
        gcs = c_ex2.slider("29. GCS", 3, 15, 15)
        
        systemic_exam = st.text_area("30. Systemic Examination Findings (Optional)")

        st.markdown("---")
        
        # --- SUBMIT BUTTON ---
        if st.button("🚀 Save & Submit Case", type="primary"):
            # Mandatory Check
            missing = []
            if not fever: missing.append("Fever History")
            if not rash: missing.append("Rash History")
            if fever == "Yes" and not fever_onset: missing.append("Fever Onset Date")
            if rash == "Yes" and not rash_onset: missing.append("Rash Onset Date")
            
            if missing:
                st.error(f"Missing mandatory fields: {', '.join(missing)}")
            else:
                new_id = datetime.now().strftime("%Y%m%d%H%M%S")
                
                # Consolidate Data
                case_data = {
                    "ID": new_id,
                    "Status": "Pending_Epi",
                    # SECTION A
                    "Name": name, "MyKad": mykad, "Nationality": nationality, "Ethnicity": ethnicity,
                    "Gender": gender, "DOB": str(dob), "Age": age_str,
                    "Address": address, "Postcode": postcode, "District": district, "State": state,
                    "Contact": contact, "Occupation": occupation,
                    "Premise_Name": work_name, "Premise_Address": work_addr,
                    
                    # SECTION B
                    "Fever": fever, "Fever_Onset": str(fever_onset), "Fever_Subside": str(fever_subside), "Fever_Max_Temp": fever_temp,
                    "Rash": rash, "Rash_Onset": str(rash_onset), "Rash_Subside": str(rash_subside), 
                    "Rash_Type": rash_type, "Rash_Progression": rash_prog,
                    "Cough": cough, "Cough_Onset": str(cough_on), "Cough_Subside": str(cough_sub),
                    "Coryza": coryza, "Coryza_Onset": str(cory_on), "Coryza_Subside": str(cory_sub),
                    "Conjunctivitis": conj, "Conj_Onset": str(conj_on), "Conj_Subside": str(conj_sub),
                    "Lymphadenopathy": lymph, "Lymph_Onset": str(lymph_on), "Lymph_Subside": str(lymph_sub),
                    "Complications": complications, "Other_Symptoms": other_sx,
                    "BP_Systolic": bp_sys, "BP_Diastolic": bp_dia,
                    "Pulse": pulse, "RR": rr,
                    "SpO2_Val": spo2_val, "SpO2_Mode": spo2_mode, "SpO2_Flow": spo2_flow,
                    "Temp_Current": temp_curr, "Pain_Score": pain_score, "GCS": gcs,
                    "Systemic_Exam": systemic_exam,
                    
                    "Final_Classification": "Pending"
                }
                
                save_new_case(case_data)
                st.success("Case Submitted Successfully!")

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