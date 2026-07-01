from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import sqlite3
import datetime
import os

app = Flask(__name__)
CORS(app)

# Database path (Assumes dashboard folder is inside the main project folder)
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "oi_analytics.db")

def query_db(query, args=(), one=False):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(query, args)
            rv = cur.fetchall()
            return (dict(rv[0]) if rv else None) if one else [dict(row) for row in rv]
    except Exception as e:
        print(f"Database Error: {e}")
        return []

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/latest')
def get_latest():
    indices = ["NIFTY50", "BANKNIFTY", "SENSEX", "BANKEX"]
    result = []
    for index in indices:
        row = query_db("SELECT * FROM pcr_trend_data WHERE index_name = ? ORDER BY id DESC LIMIT 1", (index,), one=True)
        if row:
            result.append(row)
    return jsonify(result)

@app.route('/api/history')
def get_history():
    index_name = request.args.get('index', 'NIFTY50')
    date = request.args.get('date', datetime.datetime.now().strftime("%Y-%m-%d"))
    
    query = "SELECT * FROM pcr_trend_data WHERE index_name = ? AND date_time LIKE ? ORDER BY date_time DESC"
    rows = query_db(query, (index_name, f"{date}%"))
    return jsonify(rows)

@app.route('/api/latest_signal_text')
def get_latest_signal_text():
    try:
        # File folder ke bahar hai, isliye '../'
        with open('../latest_signal.txt', 'r', encoding='utf-8') as f:
            data = f.read()
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": "Waiting for Brahmastra Bot..."})
    
    
from flask import request, jsonify
import sqlite3

@app.route('/api/pcr_trend')
def get_pcr_trend():
    index_name = request.args.get('index', 'NIFTY50')
    # Default: aaj ki date (agar frontend se nahi aayi)
    date = request.args.get('date', datetime.datetime.now().strftime("%Y-%m-%d"))

    try:
        # DB_PATH use karo (consistent with baaki routes)
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Date filter lagao, ORDER BY ASC taaki chart left→right sahi dikhe
            query = """
                SELECT date_time, pcr_value
                FROM pcr_trend_data
                WHERE index_name = ? AND date_time LIKE ?
                ORDER BY id ASC
            """
            cursor.execute(query, (index_name, f"{date}%"))
            data = cursor.fetchall()

        return jsonify({
            "status":     "success",
            "date":       date,
            "index":      index_name,
            "count":      len(data),
            "timestamps": [row[0].split(' ')[1][:5] for row in data],  # HH:MM format
            "pcr_values": [row[1] for row in data]
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
if __name__ == '__main__':
    app.run(debug=True, port=5000)
import sqlite3

@app.route('/api/live_signals')
def get_live_signals():
    try:
        conn = sqlite3.connect('../oi_analytics.db') 
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, index_name, signal_type, price FROM brahmastra_signals ORDER BY id DESC LIMIT 5")
        data = cursor.fetchall()
        conn.close()

        signals = [{"time": r[0], "index": r[1], "type": r[2], "price": r[3]} for r in data]
        return jsonify({"status": "success", "data": signals})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})