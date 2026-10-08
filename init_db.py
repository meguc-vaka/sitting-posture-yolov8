import sqlite3
import hashlib
from werkzeug.security import generate_password_hash

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # 1. 統一的使用者資料表 (包含一般用戶與管理員)
    cursor.execute('DROP TABLE IF EXISTS users')
    cursor.execute('''
    CREATE TABLE users (
        userId INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        firstName TEXT,
        lastName TEXT,
        address1 TEXT,
        phone TEXT,
        height REAL,             -- 身高 (cm)，SQLite 的浮點數使用 REAL
        weight REAL,            -- 體重 (kg)
        updatedBMI TEXT DEFAULT CURRENT_TIMESTAMP,
        last_notified_at TEXT DEFAULT CURRENT_TIMESTAMP,
        isAdmin INTEGER DEFAULT 0  -- 0 代表一般用戶，1 代表管理員
    )
    ''')

    # ★★★ 當 height 或 weight 有被 UPDATE 時，自動更新 updatedBMI ★★★
    cursor.execute("DROP TRIGGER IF EXISTS update_bmi_time")
    cursor.execute("""
    CREATE TRIGGER update_bmi_time
    AFTER UPDATE OF height, weight ON users
    BEGIN
        UPDATE users 
        SET updatedBMI = CURRENT_TIMESTAMP 
        WHERE userId = OLD.userId;
    END;
    """)
    
    # 建立預設的管理員帳號 (密碼為 admin123)
    admin_pw = hashlib.md5("admin123".encode()).hexdigest()
    cursor.execute('''
        INSERT INTO users (email, password, firstName, isAdmin) 
        VALUES (?, ?, ?, ?)
    ''', ("admin@test.com", admin_pw, "SuperAdmin", 1))

    user_pw = hashlib.md5("12345678".encode()).hexdigest()
    cursor.execute('''
        INSERT INTO users (email, password, firstName, lastName, isAdmin, height, weight) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', ("startpan070@gmail.com", user_pw, "Test", "User", 0, 175.5, 68.0))
    

    # 2. 姿勢紀錄資料表 (細項)
    cursor.execute('DROP TABLE IF EXISTS PoseRecordData')
    cursor.execute('''
        CREATE TABLE PoseRecordData (
        record_id TEXT PRIMARY KEY,           -- 單筆紀錄 ID
        user_id TEXT NOT NULL,                -- 紀錄所屬的使用者 ID
        admin_id INTEGER,                     -- 審閱管理員 ID
        timestamp TEXT,                       -- 事件發生時間
        posture_type TEXT,                    -- 姿勢類型 (如: 駝背、烏龜頸、挺直)
        angle_deviation REAL,                 -- 角度偏離值(浮點數在 SQLite 中使用 REAL)
        is_abnormal INTEGER,                  -- 是否異常(布林值在 SQLite 中使用 INTEGER (0 或 1))
        alert_message TEXT,                   -- 警示訊息：系統發出的提醒文字
        image_path TEXT NULL,                 -- 坐姿截圖
        FOREIGN KEY (admin_id) REFERENCES users (userId) -- ★ 關聯已更新到 users 表
    )
    ''')
    
    # 3. 健康知識資料表 
    cursor.execute('DROP TABLE IF EXISTS HealthKnowledgeData')
    cursor.execute('''
    CREATE TABLE HealthKnowledgeData (
        doc_id TEXT PRIMARY KEY,              -- 文件 ID
        admin_id INTEGER,                     -- 上傳的管理員 ID
        title TEXT NOT NULL,                  -- 標題
        content TEXT,                         -- 內文
        keywords TEXT,                        -- 關鍵字
        vector_index BLOB,                    -- 向量索引，使用 BLOB 儲存二進位資料
        updated_at TEXT,                      -- 更新時間
        FOREIGN KEY (admin_id) REFERENCES users (userId) -- ★ 關聯已更新到 users 表
    )
    ''')

    # 5. 監測會話彙總表（每次監測 session 一筆）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS monitoring_sessions (
        session_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        good_frames INTEGER NOT NULL DEFAULT 0,
        turtle_frames INTEGER NOT NULL DEFAULT 0,
        down_frames INTEGER NOT NULL DEFAULT 0,
        slouch_frames INTEGER NOT NULL DEFAULT 0,
        lean_frames INTEGER NOT NULL DEFAULT 0,
        dominant_posture TEXT,
        image_path TEXT,
        posture_ratio TEXT,
        avg_angle REAL DEFAULT 0,
        avg_offset REAL DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (userId)
    )
    ''')

    # 6. 每週姿勢聚合數據表（紀錄每週標準化後的統計指標）
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

    conn.commit()
    conn.close()
    print("✨ 資料庫地基重建完成！所有權限與資料表已統一。")

# 執行建表函數
init_db()