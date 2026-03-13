# 📡 Intel Hub: SIGINT & Tactical Awareness nerve center

**Intel Hub** is a professional-grade intelligence platform for P25 radio systems. It bridges the gap between local Software Defined Radio (SDR) hardware and cloud-based archives to provide a centralized dashboard for real-time tactical monitoring, unit de-masking, and audio verification.

## 🚀 Core Intelligence Features

* **🔒 Tactical Burst Alarm:** Real-time monitoring that triggers a high-priority alert when multiple unique units (5+) active on an encrypted talkgroup within a 5-minute window.
* **🎯 Tactical De-Masking:** Correlates Radio IDs (RIDs) seen on encrypted channels with their activity on clear dispatch talkgroups to identify "hidden" tactical units.
* **📻 Cloud-Signed Audio Retrieval:** Select any correlated transmission to pull the specific audio clip directly from the Broadcastify vault. 
* **📊 Talkgroup Intel:** Dynamic visualizations of traffic share and system usage across clear and encrypted talkgroups.
* **🚩 Watchlist Management:** Maintain a high-priority "Target List" with custom notes and automatic visual highlighting in all live feeds.

## 🛠️ How It Works

Intel Hub runs locally on your PC to monitor your **DSD+** logs in real-time. To ensure security without requiring every user to have a developer account, it uses a remote **Cloud Signer** (hosted by the developer) to manage cryptographic handshakes with the Broadcastify API.

## 🏁 Getting Started

### 1. Prerequisites
* **DSD+:** A working installation monitoring a P25 system.
* **Python 3.10+:** Installed on your Windows/Linux machine.
* **Broadcastify Premium:** An active subscription is required for audio archive access.

### 2. Installation
Clone the repository and install the necessary libraries:

```powershell
git clone [https://github.com/your-username/intel-hub.git](https://github.com/your-username/intel-hub.git)
cd intel-hub
pip install streamlit pandas curl_cffi pyjwt plotly streamlit-autorefresh
