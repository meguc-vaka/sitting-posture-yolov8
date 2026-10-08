import sqlite3

# 1. 請替換成你專案中實際的資料庫檔案名稱 (例如 database.db 或 sitting.db)
db_path = "database.db" 

# 2. 建立連線與游標
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 3. 執行刪除資料表
cursor.execute("DROP TABLE IF EXISTS posture_records;")

cursor.execute('''
    CREATE TABLE IF NOT EXISTS weekly_posture_summaries (
        summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        week_key TEXT NOT NULL,                -- 格式例如: '2026-W37'
        week_start_date TEXT NOT NULL,         -- 該週週一日期，如 '2026-09-14'
        week_end_date TEXT NOT NULL,           -- 該週週日日期，如 '2026-09-20'
        total_sessions INTEGER DEFAULT 0,
        total_frames INTEGER DEFAULT 0,
        turtle_rate REAL DEFAULT 0,            -- 烏龜頸佔比 (%)
        down_rate REAL DEFAULT 0,              -- 低頭佔比 (%)
        slouch_rate REAL DEFAULT 0,            -- 駝背佔比 (%)
        status TEXT NOT NULL,                  -- 'EVALUATED' (已評估), 'DATA_TOO_SHORT' (數據不足)
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        UNIQUE(user_id, week_key),
        FOREIGN KEY (user_id) REFERENCES users (userId)
    )
    ''')

# 7. 退步與警示紀錄表（專門存要推播或前端顯示的警示）
cursor.execute('''
CREATE TABLE IF NOT EXISTS weekly_alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    week_key TEXT NOT NULL,
    alert_type TEXT NOT NULL,              -- 'REGRESSION' (退步), 'STAGNATION' (持續未改善)
    posture_type TEXT NOT NULL,            -- 'turtle', 'down', 'slouch'
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,             -- 前端使用者是否已點擊已讀 (0/1)
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (user_id) REFERENCES users (userId)
)
''')

# 4. 提交變更並關閉連線
conn.commit()
conn.close()

print("成功刪除 posture_records 資料表！")