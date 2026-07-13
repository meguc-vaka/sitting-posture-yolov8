import sqlite3
import hashlib

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
        isAdmin INTEGER DEFAULT 0  -- 0 代表一般用戶，1 代表管理員
    )
    ''')
    
    # 建立預設的超級管理員帳號 (密碼為 admin123)
    admin_pw = hashlib.md5("admin123".encode()).hexdigest()
    cursor.execute('''
        INSERT INTO users (email, password, firstName, isAdmin) 
        VALUES (?, ?, ?, ?)
    ''', ("admin@test.com", admin_pw, "SuperAdmin", 1))
    

    # 2. 姿勢紀錄資料表 (細項)
    cursor.execute('DROP TABLE IF EXISTS PoseRecordData')
    cursor.execute('''
        CREATE TABLE PoseRecordData (
        record_id TEXT PRIMARY KEY,           -- 圖片為 varchar(36)，建議儲存 UUID 字串
        user_id TEXT NOT NULL,                -- 紀錄所屬的使用者 ID
        admin_id INTEGER,                     -- 若有管理員審閱，則紀錄管理員 ID
        timestamp TEXT,                       -- SQLite 中 datetime 通常存為 TEXT (ISO8601)
        posture_type TEXT,                    -- 姿勢類型 (如: 駝背)
        angle_deviation REAL,                 -- 浮點數在 SQLite 中使用 REAL
        is_abnormal INTEGER,                  -- 布林值在 SQLite 中使用 INTEGER (0 或 1)
        alert_message TEXT,
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
    
    # 4. 姿勢聚合紀錄表（3分鐘週期統計，保留 IF NOT EXISTS 不被清掉）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS posture_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        good_count INTEGER NOT NULL DEFAULT 0,
        turtle_neck_count INTEGER NOT NULL DEFAULT 0,
        looking_down_count INTEGER NOT NULL DEFAULT 0,
        slouching_count INTEGER NOT NULL DEFAULT 0,
        timestamp TEXT NOT NULL
    )
    ''')

    conn.commit()
    conn.close()
    print("✨ 資料庫地基重建完成！所有權限與資料表已統一。")

# 執行建表函數
init_db()