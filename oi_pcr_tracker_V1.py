#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║       MULTI-INDEX PCR & OI TREND TRACKER  v1.0 (Dashboard Logic)     ║
║       Indices : NIFTY50 | BANKNIFTY | SENSEX | BANKEX                ║
║       Storage : SQLite (oi_analytics.db)                             ║
║       Interval: Every 5 Minutes                                      ║
║       Data    : Fyers API v3                                         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import sqlite3
import logging
import datetime
import warnings
import base64
import urllib.parse
from typing import Optional, Dict, Tuple
from dotenv import load_dotenv
import pyotp

load_dotenv()
warnings.filterwarnings("ignore")

# ════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ════════════════════════════════════════════════════════════════
CONFIG = {
    # ── Fyers API Credentials ──
    "CLIENT_ID":        os.getenv("FYERS_CLIENT_ID", ""),
    "SECRET_KEY":       os.getenv("FYERS_SECRET_KEY", ""),
    "REDIRECT_URI":     "https://trade.fyers.in/api-login/redirect-uri/index.html",
    
    # ── Headless Login Credentials ──
    "FYERS_ID":         os.getenv("FYERS_ID", ""),
    "FYERS_PIN":        os.getenv("FYERS_PIN", ""),
    "TOTP_KEY":         os.getenv("FYERS_TOTP_KEY", ""),

    # ── Tracker Settings ──
    "STRIKE_COUNT":     5,              # ATM ± 5 strikes (total 11 strikes)
    "REFRESH_INTERVAL": 300,            # 5 minutes = 300 seconds
    "DB_FILE":          "oi_analytics.db",
}

# ── Indices Configuration ──
INDICES: Dict[str, dict] = {
    "NIFTY50":   {"symbol": "NSE:NIFTY50-INDEX"},
    "BANKNIFTY": {"symbol": "NSE:NIFTYBANK-INDEX"},
    "SENSEX":    {"symbol": "BSE:SENSEX-INDEX"},
    "BANKEX":    {"symbol": "BSE:BANKEX-INDEX"},
}

# ════════════════════════════════════════════════════════════════
#  LOGGING SETUP
# ════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("oi_pcr_tracker.log", mode="a", encoding="utf-8"),
    ],
)
log = logging.getLogger("PCRTracker")


# ════════════════════════════════════════════════════════════════
#  FYERS AUTHENTICATION
# ════════════════════════════════════════════════════════════════
class FyersAuth:
    TOKEN_FILE = "fyers_token.txt"

    def __init__(self, config: dict):
        self.client_id    = config["CLIENT_ID"]
        self.secret_key   = config["SECRET_KEY"]
        self.redirect_uri = config["REDIRECT_URI"]
        self.fy_id        = config["FYERS_ID"]
        self.pin          = str(config["FYERS_PIN"])
        self.totp_key     = config["TOTP_KEY"]

    def get_model(self):
        try:
            from fyers_apiv3 import fyersModel
        except ImportError:
            log.error("Missing dependency! Run: pip install fyers-apiv3")
            sys.exit(1)

        token = self._load_today_token()
        if token:
            model = fyersModel.FyersModel(
                client_id=self.client_id, token=token,
                log_path=os.getcwd(), is_async=False,
            )
            try:
                if model.get_profile().get("code") == 200:
                    log.info("✅ Token valid")
                    return model
            except Exception:
                pass
            log.warning("Saved token expired. Generating new token automatically...")
        return self._fresh_login(fyersModel)

    def _fresh_login(self, fyersModel):
        try:
            from curl_cffi import requests as tls_requests
        except ImportError:
            log.error("❌ Missing dependency! Run: pip install curl_cffi")
            sys.exit(1)

        try:
            log.info("Starting automated headless login (Bypassing Security)...")
            fy_id_b64 = base64.b64encode(self.fy_id.encode()).decode()
            pin_b64   = base64.b64encode(self.pin.encode()).decode()

            session = tls_requests.Session(impersonate="chrome110")
            base_headers = {
                "Accept":  "application/json",
                "Origin":  "https://trade.fyers.in",
                "Referer": "https://trade.fyers.in/",
            }

            def safe_post(step_name: str, url: str, payload: dict, extra: dict = None) -> dict:
                hdrs = {**base_headers, **(extra or {})}
                res  = session.post(url, json=payload, headers=hdrs)
                try:
                    return res.json()
                except Exception:
                    log.error(f"❌ {step_name} Failed! Server returned HTML. Status: {res.status_code}")
                    log.error(f"Raw: {res.text[:500]}")
                    sys.exit(1)

            r1 = safe_post("Step 1 (Send OTP)", "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2", {"fy_id": fy_id_b64, "app_id": "2"})
            if "request_key" not in r1: log.error(f"❌ Step 1 Error: {r1}"); sys.exit(1)

            totp = pyotp.TOTP(self.totp_key).now()
            r2 = safe_post("Step 2 (Verify TOTP)", "https://api-t2.fyers.in/vagator/v2/verify_otp", {"request_key": r1["request_key"], "otp": totp})
            if "request_key" not in r2: log.error(f"❌ Step 2 Error: {r2}"); sys.exit(1)

            r3 = safe_post("Step 3 (Verify PIN)", "https://api-t2.fyers.in/vagator/v2/verify_pin_v2", {"request_key": r2["request_key"], "identity_type": "pin", "identifier": pin_b64})
            if "data" not in r3 or "access_token" not in r3["data"]: log.error(f"❌ Step 3 Error: {r3}"); sys.exit(1)

            app_id_clean = self.client_id.split("-")[0]
            r4 = safe_post("Step 4 (Auth Code)", "https://api-t1.fyers.in/api/v3/token", {"fyers_id": self.fy_id, "app_id": app_id_clean, "redirect_uri": self.redirect_uri, "appType": "100", "code_challenge": "", "state": "None", "scope": "", "nonce": "", "response_type": "code", "create_cookie": True}, {"Authorization": f"Bearer {r3['data']['access_token']}"})
            if "Url" not in r4: log.error(f"❌ Step 4 Error: {r4}"); sys.exit(1)

            auth_code = urllib.parse.parse_qs(urllib.parse.urlparse(r4["Url"]).query)["auth_code"][0]
            fy_sess = fyersModel.SessionModel(client_id=self.client_id, secret_key=self.secret_key, redirect_uri=self.redirect_uri, response_type="code", grant_type="authorization_code")
            fy_sess.set_token(auth_code)
            token = fy_sess.generate_token()["access_token"]

            self._save_token(token)
            log.info("✅ Automated login successful!")
            return fyersModel.FyersModel(client_id=self.client_id, token=token, log_path=os.getcwd(), is_async=False)
        except SystemExit: raise
        except Exception as e: log.error(f"Headless login failed: {e}"); sys.exit(1)

    def _save_token(self, token: str):
        with open(self.TOKEN_FILE, "w") as f: f.write(f"{datetime.date.today().isoformat()}:{token}")

    def _load_today_token(self) -> Optional[str]:
        if not os.path.exists(self.TOKEN_FILE): return None
        with open(self.TOKEN_FILE) as f: content = f.read().strip()
        if ":" not in content: return None
        saved_date, token = content.split(":", 1)
        return token if saved_date == datetime.date.today().isoformat() else None


# ════════════════════════════════════════════════════════════════
#  DATABASE MANAGER
# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
#  DATABASE MANAGER (UPDATED WITH SPOT PRICE)
# ════════════════════════════════════════════════════════════════
class DatabaseManager:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_file) as conn:
            # Table create karte waqt 'spot' column add kiya
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pcr_trend_data (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_time       TEXT    NOT NULL,
                    index_name      TEXT    NOT NULL,
                    spot            REAL    DEFAULT 0.0,
                    atm_strike      INTEGER NOT NULL,
                    total_ce_chg_oi REAL    NOT NULL,
                    total_pe_chg_oi REAL    NOT NULL,
                    pcr_value       REAL    NOT NULL,
                    pcr_pct_change  REAL    NOT NULL,
                    trend_status    TEXT    NOT NULL
                )
            """)
            # Agar purana database hai, toh usme spot column auto-add karega
            try:
                conn.execute("ALTER TABLE pcr_trend_data ADD COLUMN spot REAL DEFAULT 0.0")
            except sqlite3.OperationalError:
                pass # Column pehle se hai toh ignore karega
            conn.commit()
        log.info(f"✅ Database ready: {self.db_file}")

    def get_last_record(self, index_name: str) -> Optional[dict]:
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM pcr_trend_data WHERE index_name = ? ORDER BY id DESC LIMIT 1", (index_name,))
            row = cur.fetchone()
            return dict(row) if row else None

    def insert_record(self, record: dict):
        with sqlite3.connect(self.db_file) as conn:
            # Insert karte waqt record["spot"] ko bhi save karega
            conn.execute(
                "INSERT INTO pcr_trend_data (date_time, index_name, spot, atm_strike, total_ce_chg_oi, total_pe_chg_oi, pcr_value, pcr_pct_change, trend_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record["date_time"], record["index_name"], record["spot"], record["atm_strike"], record["total_ce_chg_oi"], record["total_pe_chg_oi"], record["pcr_value"], record["pcr_pct_change"], record["trend_status"])
            )
            conn.commit()


# ════════════════════════════════════════════════════════════════
#  PCR CALCULATOR (PORTED FROM DASHBOARD SMART LOGIC)
# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
#  PCR CALCULATOR (FIXED FYERS V3 FLAT JSON PARSING)
# ════════════════════════════════════════════════════════════════
class PCRCalculator:
    def __init__(self, index_name: str, symbol: str, strike_count: int = 5):
        self.index_name   = index_name
        self.symbol       = symbol
        self.strike_count = strike_count

    def calculate(self, fyers) -> Optional[dict]:
        try:
            # Step 1: Fetch Option Chain
            resp = fyers.optionchain(data={"symbol": self.symbol, "strikecount": 50, "timestamp": ""})
            if resp.get("code") != 200 or resp.get("s") != "ok":
                return None
            
            data_dict = resp.get("data", {})
            options_chain = data_dict.get("optionsChain", [])
            if not options_chain:
                return None

            api_atm = float(data_dict.get("atm", 0))

            # 🚀 Prepare data structures for Flat JSON API v3
            ce_data, pe_data, strikes = {}, {}, set()

            for item in options_chain:
                opt_type = item.get("option_type")
                sp = float(item.get("strike_price", -1))
                
                # Ignore invalid strikes or underlying index (jiska strike -1 hota hai)
                if sp <= 0 or opt_type not in ["CE", "PE"]:
                    continue
                    
                strikes.add(sp)
                
                # V3 keys: 'oich' = Change in OI, 'ltp' = Last Traded Price
                chg_oi = float(item.get("oich", 0.0))
                ltp = float(item.get("ltp", 0.0))
                
                if opt_type == "CE":
                    ce_data[sp] = {"chg_oi": chg_oi, "ltp": ltp}
                elif opt_type == "PE":
                    pe_data[sp] = {"chg_oi": chg_oi, "ltp": ltp}

            strikes_list = sorted(list(strikes))
            if not strikes_list: return None

            # Default padding (taaki error na aaye agar kisi strike par CE/PE missing ho)
            for sp in strikes_list:
                if sp not in ce_data: ce_data[sp] = {"chg_oi": 0.0, "ltp": 0.0}
                if sp not in pe_data: pe_data[sp] = {"chg_oi": 0.0, "ltp": 0.0}

            # 🚀 Step 2: SMART ATM LOGIC (LTP Crossover fallback from Dashboard)
            atm_closest = None
            if api_atm <= 0:
                min_diff = float('inf')
                for sp in strikes_list:
                    diff = abs(ce_data[sp]["ltp"] - pe_data[sp]["ltp"])
                    if diff < min_diff:
                        min_diff = diff
                        atm_closest = sp
                if atm_closest is None:
                    atm_closest = strikes_list[len(strikes_list)//2]
            else:
                atm_closest = min(strikes_list, key=lambda x: abs(x - api_atm))

            atm_index = strikes_list.index(atm_closest)

            # Step 3: Select Strikes (-5 to +5)
            start_idx = max(0, atm_index - self.strike_count)
            end_idx = min(len(strikes_list) - 1, atm_index + self.strike_count)

            tc_co = 0.0
            tp_co = 0.0

            for i in range(start_idx, end_idx + 1):
                sp = strikes_list[i]
                tc_co += ce_data[sp]["chg_oi"]
                tp_co += pe_data[sp]["chg_oi"]

            # Step 4: PCR Calculation
            pcr = round(tp_co / tc_co, 4) if tc_co != 0 else 0.0

            return {
                "index_name":      self.index_name,
                "spot":            api_atm if api_atm > 0 else float(atm_closest), 
                "atm_strike":      int(atm_closest),
                "total_ce_chg_oi": round(tc_co, 2),
                "total_pe_chg_oi": round(tp_co, 2),
                "pcr_value":       pcr,
            }

        except Exception as e:
            log.warning(f"[{self.index_name}] Calculation failed: {e}")
            return None


# ════════════════════════════════════════════════════════════════
#  TREND ENGINE
# ════════════════════════════════════════════════════════════════
def determine_trend(pcr_now: float, pcr_prev: Optional[float]) -> Tuple[float, str]:
    if pcr_prev is None or pcr_prev == 0:
        return 0.0, "Equal"
    pct_change = round(((pcr_now - pcr_prev) / abs(pcr_prev)) * 100.0, 4)
    
    if pcr_now > pcr_prev: trend = "Increasing"
    elif pcr_now < pcr_prev: trend = "Decreasing"
    else: trend = "Equal"
    
    return pct_change, trend


# ════════════════════════════════════════════════════════════════
#  DISPLAY
# ════════════════════════════════════════════════════════════════
_TREND_ICON = {"Increasing": "🟢", "Decreasing": "🔴", "Equal": "⚪"}

def display_cycle(results: list, timestamp: str):
    W, sep, dsep = 96, "═" * 96, "─" * 96
    print(f"\n{sep}\n  📊 MULTI-INDEX PCR & OI TREND TRACKER │ {timestamp}\n{sep}")
    print(f"  {'Index':<12} {'Spot':>9} │ {'ATM':>8} │ {'CE Δ OI':>14} │ {'PE Δ OI':>14} │ {'PCR':>7} │ {'% Δ':>9} │ Trend")
    print(dsep)
    for r in results:
        icon = _TREND_ICON.get(r["trend_status"], "  ")
        sign = "+" if r["pcr_pct_change"] >= 0 else ""
        print(
            f"  {r['index_name']:<12} {r['spot']:>9,.2f} │ {r['atm_strike']:>8,} │ "
            f"{r['total_ce_chg_oi']:>14,.0f} │ {r['total_pe_chg_oi']:>14,.0f} │ "
            f"{r['pcr_value']:>7.4f} │ {sign}{r['pcr_pct_change']:>7.2f}% │ {icon} {r['trend_status']}"
        )
    print(f"{sep}\n")


# ════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════
def is_market_hours() -> bool:
    now = datetime.datetime.now()
    if now.weekday() >= 5: return False
    market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════
def main():
    print(
        "\n╔══════════════════════════════════════════════════════════════════════╗\n"
        "║       MULTI-INDEX PCR & OI TREND TRACKER  v1.0 (Dashboard Logic)     ║\n"
        "║       Indices : NIFTY50 | BANKNIFTY | SENSEX | BANKEX                ║\n"
        "║       Strategy: Change in OI Based PCR Analytics                     ║\n"
        "║       Storage : SQLite (oi_analytics.db)                             ║\n"
        "║       Refresh : Every 5 minutes                                      ║\n"
        "╚══════════════════════════════════════════════════════════════════════╝\n"
    )

    log.info("Authenticating with Fyers API...")
    try: fyers = FyersAuth(CONFIG).get_model()
    except Exception as e: log.error(f"Authentication error: {e}"); sys.exit(1)

    db = DatabaseManager(CONFIG["DB_FILE"])

    calculators = {
        name: PCRCalculator(index_name=name, symbol=info["symbol"], strike_count=CONFIG["STRIKE_COUNT"])
        for name, info in INDICES.items()
    }
    log.info(f"✅ Tracking {len(INDICES)} indices with ATM ± {CONFIG['STRIKE_COUNT']} strikes. Refresh every {CONFIG['REFRESH_INTERVAL']}s.")

    while True:
        try:
            if not is_market_hours():
                print(f"\r[{datetime.datetime.now().strftime('%H:%M:%S')}] Market closed. Checking again in 60s...", end="", flush=True)
                time.sleep(60); continue

            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cycle_results = []

            for name, calc in calculators.items():
                try:
                    result = calc.calculate(fyers)
                    if result is None:
                        log.warning(f"[{name}] Data unavailable — skipping this cycle.")
                        continue

                    last_row = db.get_last_record(name)
                    prev_pcr = last_row["pcr_value"] if last_row else None
                    pct_change, trend = determine_trend(result["pcr_value"], prev_pcr)

                    record = {**result, "date_time": now_str, "pcr_pct_change": pct_change, "trend_status": trend}
                    db.insert_record(record)
                    cycle_results.append(record)

                except Exception as e:
                    log.error(f"[{name}] Unexpected error: {e}")

            if cycle_results: display_cycle(cycle_results, now_str)
            else: log.warning("No data received for any index in this cycle.")

            log.info(f"Next cycle in {CONFIG['REFRESH_INTERVAL']}s...")
            time.sleep(CONFIG["REFRESH_INTERVAL"])

        except KeyboardInterrupt:
            print("\n")
            log.info("🛑 Tracker stopped by user (Ctrl+C).")
            break
        except Exception as e:
            log.error(f"Unexpected error in main loop: {e}")
            time.sleep(CONFIG["REFRESH_INTERVAL"])

if __name__ == "__main__":
    main()