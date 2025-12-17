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
        
        st.header("👨‍⚕️ Phase 1: Clinical Entry")
        st.info("Interactive Clerking Form: Enter MyKad to auto-fill DOB/Age.")

        # --- SECTION A: DEMOGRAPHICS ---
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
        
        # Search Box (Variable 7)
        st.caption("Search for address (e.g., 'Taman Tun Sardon'):")
        selected_address = st_searchbox(
            search_address,
            key="map_search_home",
            placeholder="Type to search Google Maps/OSM..."
        )

        # Logic: If user selects from map, use that. If not, use what they typed manually.
        # We use session state to ensure manual edits aren't overwritten accidentally.
        if "addr_final" not in st.session_state: st.session_state.addr_final = ""
        
        if selected_address:
            st.session_state.addr_final = selected_address

        # The actual input field (Variable 7) - Pre-filled by search, but editable
        address = st.text_area("7. Full Address (Auto-filled or Manual Input) *", 
                              value=st.session_state.addr_final, height=100)

        # Auto-Fill Logic for State/Postcode (Simple parsing)
        # Note: Parsing exact postcode from a raw string is tricky, so we let the user confirm.
        auto_postcode = ""
        auto_state = "Pulau Pinang" # Default
        
        if address:
            import re
            # Try find 5 digit postcode
            pc_match = re.search(r'\b\d{5}\b', address)
            if pc_match: auto_postcode = pc_match.group(0)
            
            # Simple State detection
            if "Kedah" in address: auto_state = "Kedah"
            elif "Perak" in address: auto_state = "Perak"

        c8, c9, c10 = st.columns(3)
        postcode = c8.text_input("8. Postcode *", value=auto_postcode)
        district = c9.selectbox("9. District *", ["Timur Laut", "Barat Daya", "Seberang Perai Utara", "Seberang Perai Tengah", "Seberang Perai Selatan", "Lain-lain"])
        state = c10.text_input("10. State *", value=auto_state)

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
        
        # Search Box (Variable 13/14)
        selected_premise = st_searchbox(
            search_address,
            key="map_search_premise",
            placeholder="Search Premise (e.g., 'SMK Penanti')..."
        )
        
        if "premise_final" not in st.session_state: st.session_state.premise_final = ""
        if selected_premise:
            st.session_state.premise_final = selected_premise

        col_prem1, col_prem2 = st.columns(2)
        
        # We split the result: First part is usually Name, rest is Address
        p_name_val = ""
        p_addr_val = ""
        
        if st.session_state.premise_final:
            parts = st.session_state.premise_final.split(",", 1)
            p_name_val = parts[0]
            if len(parts) > 1: p_addr_val = parts[1].strip()

        work_name = col_prem1.text_input("13. Workplace/School Name *", value=p_name_val)
        work_addr = col_prem2.text_area("14. Workplace/School Address *", value=p_addr_val, height=100)

        st.markdown("---")
        
        # --- SAVE BUTTON ---
        if st.button("🚀 Save & Proceed to Phase 2", type="primary"):
            if not name or not mykad or not dob:
                st.error("Please fill in all mandatory (*) fields.")
            else:
                new_id = datetime.now().strftime("%Y%m%d%H%M%S")
                
                # Consolidate Data
                case_data = {
                    "ID": new_id, 
                    "Status": "Pending_Epi", 
                    "Name": name, 
                    "MyKad": mykad,
                    "Nationality": nationality,
                    "Ethnicity": ethnicity,
                    "Gender": gender,
                    "DOB": str(dob),
                    "Age": age_str,
                    "Address": address,
                    "Postcode": postcode,
                    "District": district,
                    "State": state,
                    "Contact": contact,
                    "Occupation": occupation,
                    "Premise_Name": work_name,
                    "Premise_Address": work_addr,
                    "Final_Classification": "Pending"
                }
                
                save_new_case(case_data)
                st.success(f"Case **{name}** created successfully! ID: {new_id}")
                st.balloons()

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