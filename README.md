# 🚀 Brahmastra: Full-Stack Algorithmic Trading Ecosystem

![Version](https://img.shields.io/badge/Version-3.1-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)
![License](https://img.shields.io/badge/License-MIT-orange.svg)

Brahmastra is an advanced, fully automated algorithmic trading ecosystem tailored for **Nifty, BankNifty, Sensex, and Bankex** options. It combines a Quadruple Confirmation signal generator with a real-time data-logging engine and a sleek web dashboard to provide unparalleled market insights.

---

## 🌟 The 3-Engine Architecture

This project is divided into three core components that run simultaneously to power the ecosystem:

1. **🤖 Brahmastra Signal Generator (`option_signal_genrator_V3.1.py`)**
   - Continuously scans the market using SuperTrend, MACD, Session VWAP, and PCR.
   - Pushes high-accuracy entry, partial exit, and full exit alerts directly to Telegram.
   - Features automated headless login (bypassing broker security) for 24/7 cloud deployment.

2. **📊 Deep PCR Data Tracker (`oi_pcr_tracker_V1.py`)**
   - Fetches the Option Chain every 5 minutes for 4 major indices.
   - Uses a **Smart ATM Logic (LTP Crossover)** to accurately pinpoint At-The-Money strikes.
   - Calculates Change in OI (Total CE & PE) for ATM ± 5 strikes and logs the precise PCR trend into a local SQLite database (`oi_analytics.db`).

3. **🌐 Live Web Dashboard (`dashboard/app.py`)**
   - A Flask-powered backend with a professional HTML/CSS/JS frontend.
   - **Real-Time Cards:** Displays the latest Spot Price, ATM, PCR, and % Change trend (Increasing/Decreasing).
   - **Historical Data Table:** Features date and index-specific filters to review the entire day's 5-minute PCR snapshots without reloading the page.

---

## 🛠️ Tech Stack
* **Backend Engine:** Python, Pandas, SQLite3
* **Broker API:** Fyers API v3 (with `curl_cffi` for headless Cloudflare bypass)
* **Web Dashboard:** Flask, HTML5, Vanilla JS, CSS3 (Dark Theme)
* **Alerts:** Telegram Bot API

---

## 🚀 Quick Installation & Setup

### 1. Clone the Repository
```bash
git clone [https://github.com/chandeln16/option_buy_signal.git](https://github.com/chandeln16/option_buy_signal.git)
cd option_buy_signal
```


### 2. Install Dependencies
```
pip install -r requirements.txt
pip install flask flask-cors
```

### 3. Environment Configuration
Create a .env file in the root directory and add your credentials securely:
```
FYERS_CLIENT_ID=YOUR_APP_ID-100
FYERS_SECRET_KEY=YOUR_SECRET_KEY
FYERS_ID=YOUR_CLIENT_ID
FYERS_PIN=YOUR_4_DIGIT_PIN
FYERS_TOTP_KEY=YOUR_32_CHAR_TOTP_KEY
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
```
### 💻 How to Run the Ecosystem
To get the full experience, run these components in separate terminal windows (or using `tmux/screen` on a cloud server):

Terminal 1: Start the Trading Bot
```
python option_signal_genrator_V3.1.py
```
Terminal 2: Start the Data Logger
```
python oi_pcr_tracker_V1.py
```
Terminal 3: Start the Web Dashboard
```
cd dashboard
python app.py
```
Once the server starts, open `http://localhost:5000` in your browser.

## 🛡️ Security & Compliance
- Secure Credentials: Passwords and API tokens are completely hidden via the .env file (ignored in .gitignore).
- Database Management: The SQLite database is lightweight and auto-creates required tables and columns (like Spot Price) on the fly.

## ⚠️ Disclaimer
Trading options involves significant financial risk. This tool is built for educational, analytical, and paper-trading purposes only. Please perform thorough backtesting before deploying with real capital. The author is not responsible for any financial losses.

Developed by Narendra (chandeln16)
