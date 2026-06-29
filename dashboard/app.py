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

if __name__ == '__main__':
    app.run(debug=True, port=5000)