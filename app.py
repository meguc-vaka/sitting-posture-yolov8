import cv2
import numpy as np
import base64
import time
import sqlite3
import threading
import math
from collections import deque
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from flask import render_template, request

from models.load_model import Model
from controllers.controller import Controller

app = Flask(__name__)
# 啟用 SocketIO，允許跨域請求
socketio = SocketIO(app, cors_allowed_origins="*")

print("正在初始化 AI 模型...")
pose_model = Model("yolov8n-pose.pt")


# 系統短期記憶與冷卻設定區
# maxlen=30 代表這條輸送帶最多只記得過去 30 次的判定結果 (約 3 秒)
posture_history = deque(maxlen=30) 
last_warning_time = 0               # 記錄上一次發送 AI 警告的時間戳記
COOLDOWN_SECONDS = 60               # 設定冷卻時間為 60 秒


# 3 分鐘姿勢聚合計數器（全局共享，重連不丟數據）
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

init_db()  # 啟動伺服器前自動檢查並建表


def insert_posture_record_if_any():
    """把當前聚合計數寫入 posture_records 表，寫完後清零並重置計時器。
    若 total <= 0 則直接 return，不寫空記錄。
    注意：調用方應持有 record_lock（RLock，允許重入）。"""
    global posture_counts, last_record_time

    total = sum(posture_counts.values())
    if total <= 0:
        return

    now_ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    with record_lock:
        # 持鎖後再算一次，避免並發競態
        total2 = sum(posture_counts.values())
        if total2 <= 0:
            return

        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                """
                INSERT INTO posture_records (
                    good_count, turtle_neck_count,
                    looking_down_count, slouching_count, timestamp
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    posture_counts["Good"],
                    posture_counts["TurtleNeck"],
                    posture_counts["LookingDown"],
                    posture_counts["Slouching"],
                    now_ts,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        # 清零並刷新時間戳
        for k in posture_counts:
            posture_counts[k] = 0
        last_record_time = time.time()


@app.route('/renaissance')
def posture_record():
    # 1. 取得當前頁碼 (預設為第 1 頁) 與每頁顯示筆數
    page = request.args.get('page', 1, type=int)
    per_page = 10 

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2. 計算總紀錄數與總頁數
    cursor.execute("SELECT COUNT(*) FROM posture_records")
    total_records = cursor.fetchone()[0]
    total_pages = math.ceil(total_records / per_page)

    # 3. 根據頁碼，計算要「跳過」幾筆資料 (OFFSET)，再撈取該頁資料 (LIMIT)
    offset = (page - 1) * per_page
    cursor.execute("SELECT * FROM posture_records ORDER BY timestamp DESC LIMIT ? OFFSET ?", (per_page, offset))
    db_records = cursor.fetchall()
    conn.close()
    
    history_data = []
    for row in db_records:
        status = "端正坐姿"
        badge = "badge-good"
        if row['turtle_neck_count'] > 50:
            status = "烏龜頸頻發"
            badge = "badge-warning"
        elif row['looking_down_count'] > 50:
            status = "過度低頭"
            badge = "badge-danger"
        elif row['slouching_count'] > 50:
            status = "癱坐前滑"
            badge = "badge-warning"
            
        history_data.append({
            "id": row['id'],
            "time": row['timestamp'],
            "status": status,
            "badge_class": badge,
            "offset": f"烏龜頸: {row['turtle_neck_count']} 幀", 
            "angle": f"低頭: {row['looking_down_count']} 幀",
            "note": f"良好姿勢共維持 {row['good_count']} 幀"
        })
        
    # 4. 將分頁所需的數據打包，一併傳給網頁
    return render_template('record.html', 
                           records=history_data,
                           page=page,
                           total_pages=total_pages,
                           total_records=total_records,
                           per_page=per_page)


# 建立一個 WebSocket 接收通道，名稱叫做 'video_frame'
@socketio.on('video_frame')
def handle_frame(data):
    global last_warning_time # 宣告我們要修改全域的冷卻時間變數
    
    try:
        # 前端傳來的是 Base64 字串，把逗號後面的純資料切出來並解碼
        encoded_data = data.split(',')[1]
        nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # 交給 Model 算數字與分類
        results = pose_model.predict(frame)
        
        # 接收第三個參數 posture_status
        keypoints_dict, angle, posture_status = pose_model.get_results(results)
        
        if keypoints_dict is not None and angle is not None:
            # 將大腦的判斷結果交給 Controller 畫圖
            Controller.draw_skeleton_and_angle(frame, keypoints_dict, angle, posture_status)

            # === 3 分鐘聚合計數（與 AI 警告邏輯平行，互不干擾） ===
            if posture_status in posture_counts:
                with record_lock:
                    posture_counts[posture_status] += 1
                    if time.time() - last_record_time >= 180:
                        insert_posture_record_if_any()

            # 狀態追蹤與 AI 通報機制
            # 判斷當下是否為不良姿勢 (非 Good 即為 True)
            is_bad_posture = (posture_status != "Good")
            posture_history.append(is_bad_posture)
            
            # 如果記憶帶收集滿 30 幀，且其中有 25 幀以上都是不良姿勢 (確認是長期習慣，非偶然)
            if len(posture_history) == 30 and posture_history.count(True) >= 25:
                current_time = time.time()
                
                # 檢查是否已經過了 60 秒的冷卻時間
                if current_time - last_warning_time > COOLDOWN_SECONDS:
                    
                    # 根據不同的問題，準備對應的提示訊息 
                    # (未來這裡可以改成把 posture_status 傳給 Gemini API 生成動態文本)
                    advice_message = ""
                    if posture_status == "TurtleNeck":
                        advice_message = "您的頸部似乎有些前傾囉！請試著深呼吸，將肩膀往後放鬆，下巴微收，保護您的頸椎。"
                    elif posture_status == "LookingDown":
                        advice_message = "視線好像太低了！請試著抬起頭平視前方，讓頸椎休息一下吧。"
                    elif posture_status == "Slouching":
                        advice_message = "身體是不是有點往後滑了呢？稍微把骨盆扶正，讓脊椎回到舒服的弧度喔。"
                    else:
                        advice_message = "系統偵測到您的坐姿需要調整囉，稍微伸展一下吧！"
                    
                    # 透過 WebSocket 廣播給網頁，通道名稱為 'ai_alert'
                    emit('ai_alert', {'message': advice_message})
                    
                    # 刷新冷卻時間，並清空記憶帶重新計算
                    last_warning_time = current_time
                    posture_history.clear()


        # 把畫好骨架的圖片壓縮並轉回 Base64，丟回前端
        ret, buffer = cv2.imencode('.jpg', frame)
        if ret:
            encoded_img = base64.b64encode(buffer).decode('utf-8')
            emit('processed_frame', f"data:image/jpeg;base64,{encoded_img}")

    except Exception as e:
        print(f"處理影像時發生錯誤: {e}")


@socketio.on('connect')
def handle_connect():
    """重連時先將舊 session 的累計數據落庫，再重置所有會話狀態，避免跨 session 汙染。"""
    global last_record_time, last_warning_time
    with record_lock:
        insert_posture_record_if_any()
        for k in posture_counts:
            posture_counts[k] = 0
        last_record_time = time.time()
    # 清空 AI 警告的滑動窗口與冷卻計時器，新 session 從零開始
    posture_history.clear()
    last_warning_time = 0


@socketio.on('disconnect')
def handle_disconnect():
    """尾部強制結算：關閉頁面時把未滿 180 秒的累計數據寫入庫。
    觸發條件：距離上次入庫超過 30 秒（避免閃斷刷新就觸發）。"""
    global last_record_time
    with record_lock:
        if time.time() - last_record_time >= 30:
            insert_posture_record_if_any()

@app.route('/analysis')
def posture_analysis():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 撈取最近的 30 筆紀錄來畫圖，並按時間由舊到新排序 (趨勢圖由左至右)
    cursor.execute("SELECT * FROM posture_records ORDER BY timestamp DESC LIMIT 30")
    db_records = cursor.fetchall()[::-1] 
    conn.close()
    
    # 準備餵給圖表的資料陣列
    labels = []
    good_data = []
    turtle_data = []
    down_data = []
    slouch_data = []
    
    for row in db_records:
        # 只擷取時間部分 (例如 22:36:06)，讓 X 軸不會太擠
        time_str = row['timestamp'].split(' ')[1] if ' ' in row['timestamp'] else row['timestamp']
        labels.append(time_str)
        good_data.append(row['good_count'])
        turtle_data.append(row['turtle_neck_count'])
        down_data.append(row['looking_down_count'])
        slouch_data.append(row['slouching_count'])
        
    chart_data = {
        "labels": labels,
        "good": good_data,
        "turtle": turtle_data,
        "down": down_data,
        "slouch": slouch_data
    }
    
    return render_template('analysis.html', chart_data=chart_data)

if __name__ == '__main__':
    print("伺服器啟動中... 請前往 http://127.0.0.1:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
