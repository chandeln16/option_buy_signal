#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║       BRAHMASTRA OPTIONS SIGNAL GENERATOR  v3.1                    ║
║       Strategy: Quadruple Confirmation (PCR Based)                 ║
║       Features: Dynamic VWAP, Telegram Alerts, Headless Cloud Login║
║       Data    : Fyers API v3                                       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import logging
import datetime
import warnings
import traceback
import requests
import urllib.parse
from dotenv import load_dotenv
import pyotp
import base64
from typing import Optional, Tuple, List, Dict, Any

import numpy as np
import pandas as pd

# Env file se secrets load karein
load_dotenv()

warnings.filterwarnings("ignore")


# ════════════════════════════════════════════════════════════════
#  CONFIGURATION  ── Edit these before running
# ════════════════════════════════════════════════════════════════
CONFIG = {
    # ── Fyers API Credentials ──
    "CLIENT_ID":    os.getenv("FYERS_CLIENT_ID", ""),           
    "SECRET_KEY":   os.getenv("FYERS_SECRET_KEY", ""),             
    "REDIRECT_URI": "https://trade.fyers.in/api-login/redirect-uri/index.html",
    
    # ── Fyers Headless Login (For Cloud) ──
    "FYERS_ID":     os.getenv("FYERS_ID", ""),               
    "FYERS_PIN":    os.getenv("FYERS_PIN", ""),                   
    "TOTP_KEY":     os.getenv("FYERS_TOTP_KEY", ""),  

    # ── Trading Settings ──
    "INDEX":        "NIFTY",                  
    "TIMEFRAME":    "5",                      

    # ── Option Chain Settings ──
    "STRIKE_COUNT": 5,                        

    # ── SuperTrend & MACD Settings ──
    "ST_PERIOD":      20,
    "ST_MULTIPLIER":   2,
    "MACD_FAST":      12,
    "MACD_SLOW":      26,
    "MACD_SIGNAL":     9,

    # ── PCR Thresholds ──
    "PCR_STRONG_BULL": 0.70,                  
    "PCR_BULL":        1.00,                  
    "PCR_BEAR":        1.00,                  
    "PCR_STRONG_BEAR": 1.30,                  

    # ── Loop & VWAP Settings ──
    "REFRESH_INTERVAL": 60,                   
    "CANDLES_REQUIRED": 120,                  
    "VWAP_MAX_DEV_PCT": 0.30,                 
    
    # ── Telegram Alerts ──
    "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""), 
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),     
}
SYMBOL_MAP = {
    "NIFTY": {"index_symbol": "NSE:NIFTY50-INDEX", "option_prefix": "NSE:NIFTY", "strike_gap": 50, "lot_size": 25},
    "BANKNIFTY": {"index_symbol": "NSE:NIFTYBANK-INDEX", "option_prefix": "NSE:BANKNIFTY", "strike_gap": 100, "lot_size": 15},
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("brahmastra.log", mode="a", encoding="utf-8")],
)
log = logging.getLogger("Brahmastra")


# ════════════════════════════════════════════════════════════════
def send_telegram_alert(message: str, config: dict):
    bot_token = config.get("TELEGRAM_BOT_TOKEN")
    chat_id = config.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id or "YOUR_TELEGRAM" in bot_token:
        return 
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=5)
    except Exception as e:
        log.error(f"Telegram alert fail: {e}")


# ════════════════════════════════════════════════════════════════
class SignalOutput:
    def __init__(self, timestamp: str, signal: str, confidence: str, capital_pct: int, entry_price: float, stop_loss: float, exit_rule: str, pcr: float, pcr_sentiment: str, st_status: str, macd_status: str, vwap_status: str, reasons: List[str], ce_conditions: Optional[Dict[str, bool]] = None, pe_conditions: Optional[Dict[str, bool]] = None):
        self.timestamp = timestamp
        self.signal = signal
        self.confidence = confidence
        self.capital_pct = capital_pct
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.exit_rule = exit_rule
        self.pcr = pcr
        self.pcr_sentiment = pcr_sentiment
        self.st_status = st_status
        self.macd_status = macd_status
        self.vwap_status = vwap_status
        self.reasons = reasons
        self.ce_conditions = ce_conditions or {}
        self.pe_conditions = pe_conditions or {}

    def display(self):
        SEP, sep = "═" * 72, "─" * 72
        icon = {"BUY CE": "🟢", "BUY PE": "🔴", "NO TRADE": "⚪"}.get(self.signal, "")
        print(f"\n{SEP}\n  {icon} BRAHMASTRA SIGNAL  │  {self.timestamp}\n{SEP}")
        print(f"  Signal       : {self.signal}\n  Confidence   : {self.confidence}\n  Capital %    : {self.capital_pct}%\n  Entry Price  : ₹{self.entry_price:.2f}")
        print(f"  Stop Loss    : ₹{self.stop_loss:.2f}" if self.stop_loss else "  Stop Loss    : N/A")
        print(f"  Exit Rule    : {self.exit_rule}\n{sep}\n  PCR (Chg OI) : {self.pcr:.4f}  →  {self.pcr_sentiment}\n  SuperTrend   : {self.st_status}\n  MACD         : {self.macd_status}\n  VWAP         : {self.vwap_status}\n{sep}")
        if self.signal != "NO TRADE":
            print("  ✅ Confirmed Conditions:")
            for r in self.reasons: print(f"     ✓ {r}")
        else:
            print("  ❌ Conditions Status (BUY CE):")
            for cond, passed in self.ce_conditions.items(): print(f"     {'✓' if passed else '✗'} {cond}")
            print("  ❌ Conditions Status (BUY PE):")
            for cond, passed in self.pe_conditions.items(): print(f"     {'✓' if passed else '✗'} {cond}")
            if self.reasons:
                print("  ⚠️  Blockers:")
                for r in self.reasons: print(f"     • {r}")
        print(SEP + "\n")

    def log_signal(self):
        row = {"timestamp": self.timestamp, "signal": self.signal, "confidence": self.confidence, "capital_pct": self.capital_pct, "entry_price": self.entry_price, "stop_loss": self.stop_loss, "pcr": round(self.pcr, 4), "pcr_sentiment": self.pcr_sentiment}
        df_row = pd.DataFrame([row])
        df_row.to_csv("brahmastra_signals.csv", mode="a", header=not os.path.exists("brahmastra_signals.csv"), index=False)


# ════════════════════════════════════════════════════════════════
class FyersAuth:
    TOKEN_FILE = "fyers_token.txt"
    def __init__(self, config: dict):
        self.client_id, self.secret_key, self.redirect_uri = config["CLIENT_ID"], config["SECRET_KEY"], config["REDIRECT_URI"]
        self.fy_id, self.pin, self.totp_key = config["FYERS_ID"], str(config["FYERS_PIN"]), config["TOTP_KEY"]

    def get_model(self):
        try: from fyers_apiv3 import fyersModel
        except ImportError: log.error("Run: pip install fyers-apiv3"); sys.exit(1)
        token = self._load_today_token()
        if token:
            model = fyersModel.FyersModel(client_id=self.client_id, token=token, log_path=os.getcwd(), is_async=False)
            try:
                if model.get_profile().get("code") == 200:
                    log.info("✅ Token valid")
                    return model
            except Exception: pass
        return self._fresh_login(fyersModel)
    
    
    

    # ════════════════════════════════════════════════════════════════
#  FYERS AUTHENTICATION (Automated Headless TOTP Login)
# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
#  FYERS AUTHENTICATION (Automated Headless TOTP Login)
# ════════════════════════════════════════════════════════════════
class FyersAuth:
    TOKEN_FILE = "fyers_token.txt"

    def __init__(self, config: dict):
        self.client_id = config["CLIENT_ID"]
        self.secret_key = config["SECRET_KEY"]
        self.redirect_uri = config["REDIRECT_URI"]
        self.fy_id = config["FYERS_ID"]
        self.pin = str(config["FYERS_PIN"])
        self.totp_key = config["TOTP_KEY"]

    def get_model(self):
        try:
            from fyers_apiv3 import fyersModel
        except ImportError:
            log.error("Run: pip install fyers-apiv3"); sys.exit(1)
        
        token = self._load_today_token()
        if token:
            model = fyersModel.FyersModel(client_id=self.client_id, token=token, log_path=os.getcwd(), is_async=False)
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
            log.error("❌ Library Missing! Terminal me chalayein: pip install curl_cffi")
            sys.exit(1)

        try:
            log.info("Starting automated headless login (Bypassing Security)...")
            
            fy_id_b64 = base64.b64encode(self.fy_id.encode()).decode()
            pin_b64 = base64.b64encode(self.pin.encode()).decode()
            
            # Chrome Browser Impersonation
            session = tls_requests.Session(impersonate="chrome110")
            base_headers = {
                "Accept": "application/json",
                "Origin": "https://trade.fyers.in",
                "Referer": "https://trade.fyers.in/"
            }

            # Helper function for safe requests
            def make_request(step_name, url, payload, extra_headers=None):
                req_headers = base_headers.copy()
                if extra_headers: 
                    req_headers.update(extra_headers)
                
                res = session.post(url, json=payload, headers=req_headers)
                
                try:
                    return res.json()
                except Exception:
                    log.error(f"❌ {step_name} Failed! Fyers sent HTML instead of JSON.")
                    log.error(f"Status Code: {res.status_code}")
                    log.error(f"Raw Response: {res.text[:800]}") 
                    sys.exit(1)

            # Step 1: Send OTP
            res1 = make_request("Step 1 (Send OTP)", "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2", {"fy_id": fy_id_b64, "app_id": "2"})
            if "request_key" not in res1:
                log.error(f"❌ Step 1 Error: {res1}"); sys.exit(1)
            
            # Step 2: Verify TOTP 
            totp = pyotp.TOTP(self.totp_key).now()
            res2 = make_request("Step 2 (Verify TOTP)", "https://api-t2.fyers.in/vagator/v2/verify_otp", {"request_key": res1["request_key"], "otp": totp})
            if "request_key" not in res2:
                log.error(f"❌ Step 2 Error: {res2}"); sys.exit(1)
                
            # Step 3: Verify PIN 
            res3 = make_request("Step 3 (Verify PIN)", "https://api-t2.fyers.in/vagator/v2/verify_pin_v2", {"request_key": res2["request_key"], "identity_type": "pin", "identifier": pin_b64})
            if "data" not in res3 or "access_token" not in res3["data"]:
                log.error(f"❌ Step 3 Error: {res3}"); sys.exit(1)
                
            # Step 4: Auth Code (✅ FIXED: 'invalid appId' error sorted)
            app_id_clean = self.client_id.split("-")[0]  # Automatically removes '-100'
            auth_req = {"fyers_id": self.fy_id, "app_id": app_id_clean, "redirect_uri": self.redirect_uri, "appType": "100", "code_challenge": "", "state": "None", "scope": "", "nonce": "", "response_type": "code", "create_cookie": True}
            res4 = make_request("Step 4 (Auth Code)", "https://api-t1.fyers.in/api/v3/token", auth_req, {"Authorization": f"Bearer {res3['data']['access_token']}"})
            
            if "Url" not in res4:
                log.error(f"❌ Step 4 Error: {res4}"); sys.exit(1)
                
            auth_code = urllib.parse.parse_qs(urllib.parse.urlparse(res4["Url"]).query)["auth_code"][0]
            fy_session = fyersModel.SessionModel(client_id=self.client_id, secret_key=self.secret_key, redirect_uri=self.redirect_uri, response_type="code", grant_type="authorization_code")
            fy_session.set_token(auth_code)
            token = fy_session.generate_token()["access_token"]
            
            self._save_token(token)
            log.info("✅ Automated login successful!")
            return fyersModel.FyersModel(client_id=self.client_id, token=token, log_path=os.getcwd(), is_async=False)
            
        except Exception as e:
            log.error(f"Headless login failed: {e}")
            sys.exit(1)

    def _save_token(self, token: str):
        with open(self.TOKEN_FILE, "w") as f: f.write(f"{datetime.date.today().isoformat()}:{token}")

    def _load_today_token(self) -> Optional[str]:
        if not os.path.exists(self.TOKEN_FILE): return None
        with open(self.TOKEN_FILE, "r") as f: content = f.read().strip()
        if ":" not in content: return None
        saved_date, token = content.split(":", 1)
        return token if saved_date == datetime.date.today().isoformat() else None


# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
#  DATA FETCHER (UPDATED FOR DASHBOARD LOGIC)
# ════════════════════════════════════════════════════════════════
class DataFetcher:
    def __init__(self, fyers, config: dict):
        self.fyers, self.config, self.sym = fyers, config, SYMBOL_MAP[config["INDEX"]]

    def get_ohlcv(self, candles: int = 120) -> Tuple[pd.DataFrame, pd.DataFrame]:
        params = {"symbol": self.sym["index_symbol"], "resolution": self.config["TIMEFRAME"], "date_format": "1", "range_from": (datetime.date.today() - datetime.timedelta(days=15)).strftime("%Y-%m-%d"), "range_to": datetime.date.today().strftime("%Y-%m-%d"), "cont_flag": "1"}
        try:
            resp = self.fyers.history(data=params)
            if resp.get("code") != 200: return pd.DataFrame(), pd.DataFrame()
            df = pd.DataFrame(resp["candles"], columns=["ts", "open", "high", "low", "close", "volume"])
            df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
            df = df.sort_values("ts").reset_index(drop=True)
            return df.tail(candles).copy().reset_index(drop=True), df[df["ts"].dt.date == datetime.date.today()].copy()
        except Exception: return pd.DataFrame(), pd.DataFrame()

    def get_option_chain(self, strike_count: int = 5) -> dict:
        try:
            # 🚀 Always fetch 50 strikes to ensure accurate ATM crossover detection
            resp = self.fyers.optionchain(data={"symbol": self.sym["index_symbol"], "strikecount": 50, "timestamp": ""})
            return resp.get("data", {}) if resp.get("code") == 200 else {}
        except Exception: return {}


# ════════════════════════════════════════════════════════════════
class Indicators:
    @staticmethod
    def supertrend(df: pd.DataFrame, period: int = 20, multiplier: float = 2) -> pd.DataFrame:
        hi, lo, cl, n = df["high"].values, df["low"].values, df["close"].values, len(df)
        tr, atr = np.zeros(n), np.zeros(n)
        tr[0] = hi[0] - lo[0]
        for i in range(1, n): tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
        atr[0] = tr[0]
        for i in range(1, n): atr[i] = (1.0 / period) * tr[i] + (1 - (1.0 / period)) * atr[i - 1]
        hl2 = (hi + lo) / 2.0
        upper, lower = hl2 + multiplier * atr, hl2 - multiplier * atr
        fu, fl = upper.copy(), lower.copy()
        for i in range(1, n):
            fu[i] = upper[i] if (upper[i] < fu[i - 1] or cl[i - 1] > fu[i - 1]) else fu[i - 1]
            fl[i] = lower[i] if (lower[i] > fl[i - 1] or cl[i - 1] < fl[i - 1]) else fl[i - 1]
        st_val, st_dir = np.zeros(n), np.zeros(n, dtype=int)
        st_val[0], st_dir[0] = (fu[0], -1) if cl[0] <= fu[0] else (fl[0], 1)
        for i in range(1, n):
            if st_dir[i - 1] == -1: st_dir[i], st_val[i] = (1, fl[i]) if cl[i] > fu[i] else (-1, fu[i])
            else: st_dir[i], st_val[i] = (-1, fu[i]) if cl[i] < fl[i] else (1, fl[i])
        df = df.copy()
        df["st_val"], df["st_dir"] = st_val, st_dir
        df["st_fresh_buy"] = (df["st_dir"] == 1) & (df["st_dir"].shift(1).fillna(0) == -1)
        df["st_fresh_sell"] = (df["st_dir"] == -1) & (df["st_dir"].shift(1).fillna(0) == 1)
        return df

    @staticmethod
    def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        df = df.copy()
        macd_line = df["close"].ewm(span=fast, adjust=False).mean() - df["close"].ewm(span=slow, adjust=False).mean()
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        df["macd_line"], df["signal_line"] = macd_line, signal_line
        df["macd_bull_cross"] = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
        df["macd_bear_cross"] = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))
        return df

    @staticmethod
    def session_vwap(df_today: pd.DataFrame) -> pd.DataFrame:
        if df_today.empty: return df_today
        df = df_today.copy()
        tp = df["high"].astype(float).add(df["low"].astype(float)).add(df["close"].astype(float)) / 3.0
        df["vwap"] = (tp * df["volume"].astype(float)).cumsum() / df["volume"].astype(float).cumsum()
        return df


# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
#  PCR CALCULATOR (FIXED WITH DASHBOARD LOGIC)
# ════════════════════════════════════════════════════════════════
class PCRCalculator:
    def __init__(self, index: str, strike_count: int = 5):
        self.gap, self.strike_count = SYMBOL_MAP[index]["strike_gap"], strike_count

    def parse(self, chain_data: dict, spot: float) -> dict:
        out = {"atm": 0, "spot": spot, "expiry": "", "strikes": [], "ce_total_chg_oi": 0.0, "pe_total_chg_oi": 0.0, "pcr": 1.0, "sentiment": "Neutral", "data_valid": False}
        try:
            options_chain = chain_data.get("optionsChain", [])
            if not options_chain: return out

            api_atm = float(chain_data.get("atm", 0))

            # 🚀 Step 1: Flat JSON Parsing (Dashboard Style)
            ce_data, pe_data, strikes = {}, {}, set()
            for item in options_chain:
                opt_type = item.get("option_type")
                sp = float(item.get("strike_price", -1))
                
                if sp <= 0 or opt_type not in ["CE", "PE"]: continue
                strikes.add(sp)
                
                chg_oi = float(item.get("oich", 0.0))
                ltp = float(item.get("ltp", 0.0))
                
                if opt_type == "CE": ce_data[sp] = {"chg_oi": chg_oi, "ltp": ltp}
                elif opt_type == "PE": pe_data[sp] = {"chg_oi": chg_oi, "ltp": ltp}

            strikes_list = sorted(list(strikes))
            if not strikes_list: return out

            # Padding
            for sp in strikes_list:
                if sp not in ce_data: ce_data[sp] = {"chg_oi": 0.0, "ltp": 0.0}
                if sp not in pe_data: pe_data[sp] = {"chg_oi": 0.0, "ltp": 0.0}

            # 🚀 Step 2: SMART ATM LOGIC (LTP Crossover)
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

            # 🚀 Step 3: Select Strikes (-5 to +5 based on user config)
            start_idx = max(0, atm_index - self.strike_count)
            end_idx = min(len(strikes_list) - 1, atm_index + self.strike_count)

            tc_co, tp_co = 0.0, 0.0
            for i in range(start_idx, end_idx + 1):
                sp = strikes_list[i]
                tc_co += ce_data[sp]["chg_oi"]
                tp_co += pe_data[sp]["chg_oi"]

            # 🚀 Step 4: PCR Calculation
            pcr = round(tp_co / tc_co, 4) if tc_co != 0 else 0.0
            
            # Setup Sentiment mapping for Trading Logic
            sentiment = "Extremely Bullish" if pcr < 0.7 else "Bullish" if pcr < 1.0 else "Bearish" if pcr <= 1.3 else "Extremely Bearish"

            out.update({
                "atm": int(atm_closest),
                "spot": api_atm if api_atm > 0 else float(atm_closest),
                "ce_total_chg_oi": tc_co,
                "pe_total_chg_oi": tp_co,
                "pcr": pcr,
                "sentiment": sentiment,
                "data_valid": True
            })
        except Exception: pass
        return out

    def print_table(self, pcr_data: dict):
        if pcr_data.get("data_valid"): print(f"\n  OPTION CHAIN │ ATM: {pcr_data['atm']} │ PCR: {pcr_data['pcr']:.4f}")


# ════════════════════════════════════════════════════════════════
class SignalGenerator:
    def __init__(self, cfg: dict): self.cfg = cfg

    def generate(self, df: pd.DataFrame, df_today: pd.DataFrame, pcr_data: dict) -> SignalOutput:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if df.empty: return self._no_trade_obj(ts, 0.0, ["Not enough candles"])

        last, close_price = df.iloc[-1], float(df.iloc[-1]["close"])
        st_dir, st_val = int(last.get("st_dir", 0)), float(last.get("st_val", 0))
        st_fresh_buy, st_fresh_sell = bool(last.get("st_fresh_buy")), bool(last.get("st_fresh_sell"))
        macd_line, sig_line = float(last.get("macd_line", 0)), float(last.get("signal_line", 0))
        bull_cross, bear_cross = bool(last.get("macd_bull_cross")), bool(last.get("macd_bear_cross"))
        vwap_val = float(df_today["vwap"].iloc[-1]) if (df_today is not None and not df_today.empty and "vwap" in df_today.columns) else None
        pcr, valid, sentiment = pcr_data.get("pcr", 1.0), pcr_data.get("data_valid", False), pcr_data.get("sentiment", "Unknown")

        blockers = []
        if not valid: blockers.append("PCR data unavailable")
        if vwap_val is None: blockers.append("VWAP not calculable")
        if st_dir == 1 and macd_line < sig_line: blockers.append("SuperTrend Bullish but MACD Bearish")
        if st_dir == -1 and macd_line > sig_line: blockers.append("SuperTrend Bearish but MACD Bullish")
        
        if vwap_val and not (st_fresh_buy or st_fresh_sell):
            dev = abs(close_price - vwap_val) / vwap_val * 100
            max_dev = self.cfg.get("VWAP_MAX_DEV_PCT", 0.30)
            if dev > max_dev: blockers.append(f"Price deviation from VWAP is {dev:.2f}% (>{max_dev}%) without fresh ST signal")

        ce_cond = {"① Fresh ST BUY": st_fresh_buy, "② Bullish MACD Cross": bull_cross, "③ Price >= VWAP": (vwap_val and close_price >= vwap_val), "④ PCR < 1.00": (valid and pcr < self.cfg["PCR_BULL"])}
        pe_cond = {"① Fresh ST SELL": st_fresh_sell, "② Bearish MACD Cross": bear_cross, "③ Price <= VWAP": (vwap_val and close_price <= vwap_val), "④ PCR > 1.00": (valid and pcr > self.cfg["PCR_BEAR"])}

        if all(ce_cond.values()) and not blockers:
            strong = pcr < self.cfg["PCR_STRONG_BULL"]
            return SignalOutput(ts, "BUY CE", "Strong 💪" if strong else "Moderate", 50 if strong else 25, close_price, round(st_val, 2), "Partial Exit on Bearish MACD → Final on SL", pcr, sentiment, "Bullish ST", "Bullish Cross", "Above VWAP", [k for k, v in ce_cond.items() if v], ce_cond, pe_cond)

        if all(pe_cond.values()) and not blockers:
            strong = pcr > self.cfg["PCR_STRONG_BEAR"]
            return SignalOutput(ts, "BUY PE", "Strong 💪" if strong else "Moderate", 50 if strong else 25, close_price, round(st_val, 2), "Partial Exit on Bullish MACD → Final on SL", pcr, sentiment, "Bearish ST", "Bearish Cross", "Below VWAP", [k for k, v in pe_cond.items() if v], ce_cond, pe_cond)

        return self._no_trade_obj(ts, close_price, blockers, "N/A", "N/A", "N/A", pcr, sentiment, ce_cond, pe_cond)

    def _no_trade_obj(self, ts: str, price: float, reasons: List[str], st_str: str = "N/A", macd_str: str = "N/A", vwap_str: str = "N/A", pcr: float = 0.0, sentiment: str = "N/A", ce_cond: Optional[Dict[str, bool]] = None, pe_cond: Optional[Dict[str, bool]] = None) -> SignalOutput:
        return SignalOutput(ts, "NO TRADE", "No Signal", 0, price, 0.0, "Wait for alignment", pcr, sentiment, st_str, macd_str, vwap_str, reasons, ce_cond, pe_cond)


# ════════════════════════════════════════════════════════════════
class ExitMonitor:
    def __init__(self):
        self.active: Optional[SignalOutput] = None
        self.partial_done = False
    def set_position(self, sig: SignalOutput): self.active, self.partial_done = sig, False
    def clear(self): self.active, self.partial_done = None, False
    def check(self, df: pd.DataFrame) -> Optional[str]:
        if not self.active or df.empty: return None
        close, st_val = float(df.iloc[-1]["close"]), float(df.iloc[-1].get("st_val", 0))
        bull_cross, bear_cross = bool(df.iloc[-1].get("macd_bull_cross")), bool(df.iloc[-1].get("macd_bear_cross"))
        if self.active.signal == "BUY CE":
            if close < st_val: self.clear(); return f"🚨 FINAL EXIT │ BUY CE │ SL Hit │ Close: ₹{close:.2f}"
            if bear_cross and not self.partial_done: self.partial_done = True; return f"⚡ PARTIAL EXIT (50%) │ BUY CE │ Bearish MACD │ Price: ₹{close:.2f}"
        elif self.active.signal == "BUY PE":
            if close > st_val: self.clear(); return f"🚨 FINAL EXIT │ BUY PE │ SL Hit │ Close: ₹{close:.2f}"
            if bull_cross and not self.partial_done: self.partial_done = True; return f"⚡ PARTIAL EXIT (50%) │ BUY PE │ Bullish MACD │ Price: ₹{close:.2f}"
        return None

def is_market_hours() -> bool:
    now = datetime.datetime.now()
    return False if now.weekday() >= 5 else (now.replace(hour=9, minute=15, second=0) <= now <= now.replace(hour=15, minute=30, second=0))

# ════════════════════════════════════════════════════════════════
def main():
    # ── YEH RAHI TEST LINE (Isse yahan paste karein) ──
    send_telegram_alert("Brahmastra Bot is Online! 🚀", CONFIG)
    
    auth, fyers = FyersAuth(CONFIG), None
    # ... baki ka code waisa hi rehne dein
    
    print("╔══════════════════════════════════════════════════════════════╗\n║   BRAHMASTRA OPTIONS SIGNAL GENERATOR  v3.1                 ║\n╚══════════════════════════════════════════════════════════════╝")
    
    auth, fyers = FyersAuth(CONFIG), None
    try: fyers = auth.get_model()
    except Exception as e: log.error(f"Failed to auth: {e}"); sys.exit(1)

    fetcher, ind, pcr_calc, sig_gen, exit_mon = DataFetcher(fyers, CONFIG), Indicators(), PCRCalculator(CONFIG["INDEX"], CONFIG["STRIKE_COUNT"]), SignalGenerator(CONFIG), ExitMonitor()
    last_signal = "INIT"

    while True:
        try:
            if not is_market_hours():
                print(f"\r[{datetime.datetime.now().strftime('%H:%M:%S')}] Market closed. Waiting...", end="", flush=True)
                time.sleep(60); continue

            df, df_today = fetcher.get_ohlcv(CONFIG["CANDLES_REQUIRED"])
            if df.empty: time.sleep(CONFIG["REFRESH_INTERVAL"]); continue

            df = ind.macd(ind.supertrend(df, CONFIG["ST_PERIOD"], CONFIG["ST_MULTIPLIER"]), CONFIG["MACD_FAST"], CONFIG["MACD_SLOW"], CONFIG["MACD_SIGNAL"])
            if df_today is not None and not df_today.empty: df_today = ind.session_vwap(df_today)

            pcr_data = pcr_calc.parse(fetcher.get_option_chain(CONFIG["STRIKE_COUNT"]), float(df["close"].iloc[-1]))

            if exit_msg := exit_mon.check(df):
                print(f"\n{'!' * 72}\n  {exit_msg}\n{'!' * 72}\n")
                send_telegram_alert(f"⚠️ <b>EXIT ALERT</b>\n{exit_msg}", CONFIG)

            signal = sig_gen.generate(df, df_today, pcr_data)
            signal.display()
            signal.log_signal()

            if signal.signal in ("BUY CE", "BUY PE") and signal.signal != last_signal:
                exit_mon.set_position(signal)
                send_telegram_alert(f"🚨 <b>BRAHMASTRA: {signal.signal}</b>\n\n<b>Index:</b> {CONFIG['INDEX']}\n<b>Conf:</b> {signal.confidence} ({signal.capital_pct}%)\n<b>Entry:</b> ₹{signal.entry_price:.2f}\n<b>SL:</b> ₹{signal.stop_loss:.2f}\n<b>PCR:</b> {signal.pcr:.4f}", CONFIG)
            last_signal = signal.signal

            time.sleep(CONFIG["REFRESH_INTERVAL"])

        except KeyboardInterrupt: break
        except Exception as e: log.error(f"Loop error: {e}"); time.sleep(CONFIG["REFRESH_INTERVAL"])

if __name__ == "__main__":
    main()