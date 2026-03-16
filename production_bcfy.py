import streamlit as st
import pandas as pd
import os
import re
from curl_cffi import requests
import time
import json
import plotly.express as px
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- 1. LOCAL CONFIGURATION & CLOUD SIGNER ---
CONFIG_FILE = 'intelhub_config.json'

# This URL is now pointed to your specific Render app
VENDING_MACHINE_URL = "https://intelhub.onrender.com/get_token"

def load_user_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return None

def save_user_config(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f)

def get_cloud_jwt(uid=None, utk=None):
    """
    Calls your Render server to sign a JWT. 
    Added resilience for Render Free Tier 'Cold Starts'.
    """
    payload = {}
    if uid and utk:
        payload = {"uid": uid, "utk": utk}
        
    max_retries = 3
    # 120 second timeout to give Render plenty of time to wake up
    timeout_seconds = 120 

    for attempt in range(max_retries):
        try:
            # We use a unique key for the spinner to prevent Streamlit refresh issues
            with st.spinner(f"Waking up Cloud Signer (Attempt {attempt + 1}/{max_retries})..."):
                response = requests.post(
                    VENDING_MACHINE_URL, 
                    json=payload, 
                    impersonate="chrome",
                    timeout=timeout_seconds
                )
            
            if response.status_code == 200:
                return response.json().get("jwt")
            else:
                st.error(f"Cloud Signer Error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            # If it's a timeout, Render is likely still booting up. Wait 5s and try again.
            if "timeout" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(5)
                continue
            else:
                st.error(f"Cloud Auth Connection Failed: {e}")
                return None
    return None

# --- 2. INITIALIZATION / SETUP SCREEN ---
user_config = load_user_config()

if not user_config:
    st.set_page_config(page_title="Intel Hub Setup", page_icon="📡")
    st.title("📡 Intel Hub - First Time Setup")
    st.markdown("API security is managed via Cloud Signer. Provide local details to begin.")
    
    with st.form("setup_form"):
        dsd_path = st.text_input("DSD+ Folder Path", value=r"C:\Users\HP Elitedesk 800\Downloads\DSDPlusFull")
        sys_id = st.text_input("Broadcastify System ID", value="8384")
        bcfy_user = st.text_input("Broadcastify Username")
        bcfy_pass = st.text_input("Broadcastify Password", type="password")
        
        if st.form_submit_button("Save & Initialize"):
            # Uses the new resilient function
            base_jwt = get_cloud_jwt()
            
            if base_jwt:
                with st.spinner("Authenticating with Broadcastify..."):
                    auth_url = "https://api.bcfy.io/common/v1/auth"
                    auth_resp = requests.post(auth_url, 
                                             headers={"Authorization": f"Bearer {base_jwt}"},
                                             data={"username": bcfy_user, "password": bcfy_pass},
                                             impersonate="chrome")
                
                if auth_resp.status_code == 200:
                    auth_data = auth_resp.json()
                    config_data = {
                        "dsd_path": dsd_path,
                        "sys_id": sys_id,
                        "uid": auth_data['uid'],
                        "token": auth_data['token']
                    }
                    save_user_config(config_data)
                    st.success("Authenticated! Dashboard is ready.")
                    st.rerun()
                else:
                    st.error("Broadcastify Login Failed. Check your credentials.")
            else:
                st.error("Could not reach Cloud Signer after multiple attempts. Is your Render app 'Live'?")
    st.stop()

# --- 3. LOAD SYSTEM PATHS ---
DSD_DIR = user_config['dsd_path']
BCAST_SYS_ID = user_config['sys_id']
BCFY_UID = user_config['uid']
BCFY_TOKEN = user_config['token']

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.txt")
IGNORE_FILE = os.path.join(os.path.dirname(__file__), "ignore_list.txt")
LOG_FILE = os.path.join(DSD_DIR, "CC-DSDPlus.event")
RADIOS_FILE = os.path.join(DSD_DIR, "DSDPlus.radios")
GROUPS_FILE = os.path.join(DSD_DIR, "DSDPlus.groups")

st.set_page_config(page_title="Intel Hub", layout="wide", page_icon="📡")

# --- 4. DATA CORE & CACHING ---
def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE): return {}
    watch = {}
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if ':' in line:
                    rid, reason = line.strip().split(':', 1)
                    watch[rid.strip()] = reason.strip()
    except: pass
    return watch

def load_ignore_list():
    if not os.path.exists(IGNORE_FILE): return {"240"}
    try:
        with open(IGNORE_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            return {line.strip() for line in f if line.strip()}
    except: return {"240"}

@st.cache_data(ttl=60)
def load_metadata():
    rids, tgs = {}, {}
    try:
        if os.path.exists(RADIOS_FILE):
            with open(RADIOS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    parts = line.split(',')
                    if len(parts) >= 9: rids[parts[3].strip()] = parts[8].strip().strip('"')
        if os.path.exists(GROUPS_FILE):
            with open(GROUPS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    parts = line.split(',')
                    if len(parts) >= 8: tgs[parts[2].strip()] = parts[7].strip().strip('"')
    except: pass
    return rids, tgs

def parse_logs():
    rid_aliases, tg_aliases = load_metadata()
    watchlist = load_watchlist()
    ignore_tgs = load_ignore_list()
    all_data = []
    tactical_rids = set()
    pattern = re.compile(r"(\d{4}/\d{2}/\d{2})\s+(\d{2}:\d{2}:\d{2}).*?(Enc Group call|Group call|P-Group call); TG=(\d+).*?RID=(\d+)")

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    date, timestamp, ctype, tg, rid = match.groups()
                    if tg in ignore_tgs: continue 
                    
                    is_enc = "Enc" in ctype
                    if is_enc: tactical_rids.add(rid)
                    
                    all_data.append({
                        'Timestamp': f"{date} {timestamp}",
                        'dt': datetime.strptime(f"{date} {timestamp}", "%Y/%m/%d %H:%M:%S"),
                        'Type': "🔒 ENC" if is_enc else "🔊 CLEAR",
                        'TG': tg,
                        'TG Name': tg_aliases.get(tg, f"TG {tg}"),
                        'RID': str(rid),
                        'Unit Alias': rid_aliases.get(rid, "UNID"),
                        'IsWatched': rid in watchlist
                    })
    return pd.DataFrame(all_data), tactical_rids

def fetch_bcfy_audio_url(target_time_str, target_tg, target_rid):
    """Fetches the direct MP3/M4A URL using Cloud Signer for auth."""
    try:
        target_dt = datetime.strptime(target_time_str, '%Y/%m/%d %H:%M:%S')
        
        # Archive Delay Check
        time_since_call = datetime.now() - target_dt
        if time_since_call.total_seconds() < 1200:
            return None, f"Too recent ({int(time_since_call.total_seconds()/60)} mins ago). Needs 20m delay."
        
        start_ts = int((target_dt - timedelta(minutes=2)).timestamp())
        end_ts = int((target_dt + timedelta(minutes=2)).timestamp())
        group_id = f"{BCAST_SYS_ID}-{str(target_tg).strip()}"
        
        url = f"https://api.bcfy.io/calls/v1/group_archives/{group_id}/{start_ts}/{end_ts}"
        
        # Securely fetch Master JWT from Render using resilient function
        signed_jwt = get_cloud_jwt(BCFY_UID, BCFY_TOKEN)
        
        if not signed_jwt:
            return None, "Cloud Signer timed out. Please try again in 30 seconds."

        headers = {"Authorization": f"Bearer {signed_jwt}", "Accept": "application/json"}
        response = requests.get(url, headers=headers, impersonate="chrome")
        
        if response.status_code == 200:
            data = response.json()
            calls = data.get("calls", [])
            if not calls: return None, "No audio in window."
            
            target_ts = int(target_dt.timestamp())
            target_rid_int = int(str(target_rid).strip())
            
            rid_matches = [c for c in calls if c.get('src') == target_rid_int]
            closest_call = min(rid_matches if rid_matches else calls, key=lambda x: abs(x['ts'] - target_ts))
            return closest_call.get('url'), None
        else:
            return None, f"API Error: {response.status_code}"
            
    except Exception as e:
        return None, f"Script Error: {str(e)}"

# --- 5. UI DASHBOARD ---
rid_map, tg_map = load_metadata()
df, tac_set = parse_logs()
watchlist = load_watchlist()

st.sidebar.header("System Controls")
if st.sidebar.checkbox("Enable Live Tactical Feed", value=False):
    st_autorefresh(interval=15000, key="hub_v16_timer")

st.title("🛰️ Intel Hub Dashboard")

# Tactical Burst Alarm
if not df.empty:
    now = df['dt'].max()
    window = now - timedelta(minutes=5)
    recent_enc = df[(df['Type'] == "🔒 ENC") & (df['dt'] >= window)]
    if not recent_enc.empty:
        bursts = recent_enc.groupby(['TG', 'TG Name'])['RID'].nunique()
        active_bursts = bursts[bursts >= 5]
        for (tg_id, tg_name), count in active_bursts.items():
            st.error(f"🚨 TACTICAL DEPLOYMENT DETECTED: {tg_name} ({count} unique units active)")

tabs = st.tabs(["🔒 Tactical ENC", "👤 Unit Deep-Dive", "🎯 De-Masking", "📊 TGID Intel", "🚨 Watchlist", "📝 Alias Editor", "📜 Live Feed"])

def color_watchlist(val): 
    return 'background-color: #8B0000; color: white' if str(val) in watchlist else ''

# --- TABS LOGIC ---
with tabs[0]:
    st.header("Priority Tactical Feed")
    if not df.empty:
        enc_df = df[df['Type'] == "🔒 ENC"]
        if not enc_df.empty:
            summary_df = enc_df.groupby(['TG', 'TG Name']).agg(
                Total_Calls=('RID', 'count'), Unique_Units=('RID', 'nunique'), Last_Active=('Timestamp', 'max')
            ).reset_index().sort_values('Last_Active', ascending=False)
            st.dataframe(summary_df, hide_index=True, use_container_width=True)
            st.divider()
            st.dataframe(enc_df.sort_values('Timestamp', ascending=False).style.map(color_watchlist, subset=['RID']), width='stretch')

with tabs[1]:
    st.header("Unit Intelligence Profile")
    query = st.text_input("Search RID or Alias")
    if query and not df.empty:
        unit_df = df[df['RID'].str.contains(query, na=False) | df['Unit Alias'].str.contains(query, case=False, na=False)]
        st.dataframe(unit_df.sort_values('Timestamp', ascending=False), width='stretch')

with tabs[2]:
    st.header("🎯 Tactical Correlation & De-Masking")
    if not df.empty:
        df['JustDate'] = df['dt'].dt.date
        enc_tgs = df[df['Type'] == "🔒 ENC"]['TG'].unique().tolist()
        tg_a_opts = ["All Encrypted"] + sorted(enc_tgs)
        clear_tgs = df[df['Type'] == "🔊 CLEAR"]['TG'].unique().tolist()
        tg_b_opts = ["All Clear"] + sorted(clear_tgs)

        with st.form("demask_form"):
            c1, c2 = st.columns(2)
            with c1: tg_a = st.selectbox("Target (Enc Side)", tg_a_opts)
            with c2: tg_b = st.selectbox("Compare (Clear Side)", tg_b_opts)
            submitted = st.form_submit_button("Run Analysis")

        if submitted or True:
            enc_base = df[df['Type'] == "🔒 ENC"] if tg_a == "All Encrypted" else df[(df['Type'] == "🔒 ENC") & (df['TG'] == tg_a)]
            if not enc_base.empty:
                enc_summary = enc_base.sort_values('dt', ascending=False).groupby('RID').first().reset_index()
                enc_summary = enc_summary[['RID', 'Timestamp', 'TG Name']]
                enc_summary.rename(columns={'Timestamp': 'Latest Encrypted Time', 'TG Name': 'Encrypted TG'}, inplace=True)
                
                target_rids = enc_summary['RID'].unique()
                result_mask = (df['Type'] == "🔊 CLEAR") & (df['RID'].isin(target_rids))
                if tg_b != "All Clear": result_mask = result_mask & (df['TG'] == tg_b)
                
                clear_df = df[result_mask]
                if not clear_df.empty:
                    merged_df = pd.merge(clear_df, enc_summary, on='RID', how='left')
                    display_df = merged_df[['Timestamp', 'TG', 'TG Name', 'RID', 'Unit Alias', 'Latest Encrypted Time', 'Encrypted TG']].copy()
                    display_df.rename(columns={'Timestamp': 'Clear Time', 'TG Name': 'Clear TG_Name'}, inplace=True)
                    display_df.sort_values('Clear Time', ascending=False, inplace=True)
                    st.dataframe(display_df.drop(columns=['TG']).style.map(color_watchlist, subset=['RID']), width='stretch')

                    st.divider()
                    st.subheader("📻 Retrieve Transmission Audio")
                    display_df['Select_Label'] = display_df['Clear Time'] + " | TG: " + display_df['Clear TG_Name'] + " | RID: " + display_df['RID'].astype(str)
                    selected_call_label = st.selectbox("Select Target:", display_df['Select_Label'].tolist())

                    if st.button("Fetch Audio"):
                        target_row = display_df[display_df['Select_Label'] == selected_call_label].iloc[0]
                        with st.spinner('Requesting Cloud Signed Audio...'):
                            audio_url, error_msg = fetch_bcfy_audio_url(target_row['Clear Time'], target_row['TG'], target_row['RID'])
                        if audio_url: st.audio(audio_url)
                        else: st.error(error_msg)

with tabs[3]:
    st.header("📊 Talkgroup Traffic Analysis")
    if not df.empty:
        counts = df['TG Name'].value_counts().reset_index().head(10)
        st.plotly_chart(px.pie(counts, values='count', names='TG Name', hole=0.4), use_container_width=True)

with tabs[4]:
    st.header("Target Intelligence Lists")
    c1, c2 = st.columns(2)
    with c1:
        w_rid = st.text_input("Add RID to Watch")
        w_note = st.text_input("Note")
        if st.button("Add Target"):
            with open(WATCHLIST_FILE, 'a') as f: f.write(f"{w_rid}:{w_note}\n")
            st.rerun()
    with c2:
        for rid, note in watchlist.items(): st.write(f"🚩 **{rid}**: {note}")

with tabs[5]:
    st.header("DSDPlus Alias Editor")
    with st.form("alias_form"):
        new_rid, new_alias = st.text_input("Radio ID"), st.text_input("New Alias Name")
        if st.form_submit_button("Write to DSDPlus") and new_rid and new_alias:
            new_line = f'P25, 0, 0, {new_rid}, 50, 40, {datetime.now().strftime("%Y/%m/%d %H:%M")}, "{new_alias}"\n'
            with open(RADIOS_FILE, 'a', encoding='utf-8') as f: f.write(new_line)
            st.success("Updated!")

with tabs[6]:
    st.header("Recent Activity (All Traffic)")
    if not df.empty:
        st.dataframe(df.tail(100).sort_values('Timestamp', ascending=False).style.map(color_watchlist, subset=['RID']), width='stretch')