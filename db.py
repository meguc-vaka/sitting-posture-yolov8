import sqlite3

DB_PATH = 'database.db'

# === 資料庫初始化 ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS posture_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            good_count INTEGER,
            turtle_neck_count INTEGER,
            looking_down_count INTEGER,
            slouching_count INTEGER,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

# === 資料庫查詢 / 讀取 ===
def query_db(query, args=(), one=False):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row      # 支援用 key 讀取欄位
        cur = conn.cursor()
        cur.execute(query, args)
        rv = cur.fetchall()
        return (rv[0] if rv else None) if one else rv
    
# === 資料庫執行 / 寫入修改 ===
def execute_db(query, args=()):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(query, args)
        conn.commit()
