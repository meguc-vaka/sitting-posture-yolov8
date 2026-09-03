import base64, hashlib, math, smtplib, threading, time, traceback, os ,sys ,signal, uuid, json
from collections import deque
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import cv2
import numpy as np
from flask import Flask, redirect, render_template, request, session, url_for, request
from flask_socketio import SocketIO, emit
from flask_apscheduler import APScheduler

from controllers.controller import Controller
from collections import defaultdict
from db import init_db, query_db, execute_db
from models.load_model import Model
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'secret_key_for_session' # 設定 Session 的加密金鑰
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

def graceful_exit(sig, frame):
    print("\n正在停止排程器並退出...")
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
    os._exit(0)

# 註冊中斷訊號
signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)

record_lock = threading.RLock()     # 全域只宣告一次鎖頭
last_record_time = time.time()      # 紀錄初始時間
posture_counts = {                  # 建立一個用來統計姿勢的字典
    "Good": 0,
    "TurtleNeck": 0,
    "LookingDown": 0,
    "Slouching": 0
}

# === 15 秒穩定判定機制 ===
stability_pending = None            # 正在等待穩定的姿勢
stability_count = 0                 # 連續相同姿勢的幀數
STABILITY_THRESHOLD = 150           # 15 秒 × 10fps = 150 幀

# 角度累積器（用於 session 彙總時計算平均）
total_angle = 0
angle_count = 0
total_offset = 0
offset_count = 0

# 3 分鐘姿勢聚合計數器（全局共享，重連不丟數據）
posture_history = deque(
    maxlen=30                       # 代表這條輸送帶最多只記得過去 30 次的判定結果 (約 3 秒)
) 
last_warning_time = 0               # 記錄上一次發送 AI 警告的時間戳記
COOLDOWN_SECONDS = 60               # 設定冷卻時間為 60 秒

# === 3 分鐘定時提示系統 ===
last_tip_check = time.time()        # 上次檢查提示的時間
TIP_CHECK_INTERVAL = 120            # 每 2 分鐘檢查一次
bad_posture_sustained = False       # 過去 3 分鐘內是否曾穩定不良姿勢 15 秒
BAD_POSTURE_THRESHOLD = 150         # 15 秒 (150 幀) 才觸發
# 使用動態字典，自動支援任何新加入的姿勢類別
posture_snapshots = {}

DB_PATH = 'database.db'
init_db()  # 啟動伺服器前自動檢查並建表

print("正在初始化 AI 模型...")
pose_model = Model("yolov8n-pose.pt")

@app.route('/')
def index():
    return render_template('front page.html')

@app.route('/ScanPage')
def scanpage():
    return render_template('index.html')

@app.route('/loginForm')
def login_form():
    return render_template('login.html')

def write_session_summary(sid):
    """將本次 session 的累積數據寫入 monitoring_sessions 彙總表"""
    global posture_counts, posture_snapshots, last_frame, total_angle, angle_count, total_offset, offset_count
    
    total = sum(posture_counts.values())
    if total <= 0:
        return
    
    session_data = user_monitoring_sessions.get(sid, {})
    session_id = str(uuid.uuid4())
    user_id = session_data.get('user_id', 0)
    start_time = session_data.get('start_time_iso', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    avg_angle = round(total_angle / angle_count, 1) if angle_count > 0 else 0
    avg_offset = round(total_offset / offset_count, 1) if offset_count > 0 else 0
    
    posture_ratio = json.dumps({
        "good": round(posture_counts["Good"] / total * 100, 1) if total > 0 else 0,
        "turtle": round(posture_counts["TurtleNeck"] / total * 100, 1) if total > 0 else 0,
        "down": round(posture_counts["LookingDown"] / total * 100, 1) if total > 0 else 0,
        "slouch": round(posture_counts["Slouching"] / total * 100, 1) if total > 0 else 0
    })
    
    dominant = max(posture_counts, key=posture_counts.get)
    dominant_map = {"Good": "端正坐姿", "TurtleNeck": "烏龜頸", "LookingDown": "過度低頭", "Slouching": "癱坐"}
    
    # 取最差姿勢的截圖
    bad_postures = {k: v for k, v in posture_counts.items() if k != "Good"}
    worst = min(bad_postures, key=bad_postures.get) if bad_postures else "Good"
    image_path = ""
    if worst in posture_snapshots and posture_snapshots[worst] is not None:
        image_dir = "static/screenshots"
        if not os.path.exists(image_dir):
            os.makedirs(image_dir)
        filename = f"{session_id}.jpg"
        full_path = os.path.join(image_dir, filename).replace('\\', '/')
        cv2.imwrite(full_path, posture_snapshots[worst])
        image_path = full_path
    
    execute_db("""
        INSERT INTO monitoring_sessions 
        (session_id, user_id, start_time, end_time, good_frames, turtle_frames, down_frames, slouch_frames, dominant_posture, image_path, posture_ratio, avg_angle, avg_offset)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, user_id, start_time, end_time,
        posture_counts["Good"], posture_counts["TurtleNeck"],
        posture_counts["LookingDown"], posture_counts["Slouching"],
        dominant_map.get(dominant, dominant),
        image_path, posture_ratio, avg_angle, avg_offset
    ))
    
    # 重置累積器
    total_angle = 0
    angle_count = 0
    total_offset = 0
    offset_count = 0
    
    print(f"[{sid}] Session 彙總寫入完成: {session_id}, 總幀: {total}, 平均角度: {avg_angle}°")

# 取得坐姿會話紀錄（含分頁）並渲染頁面(record.html)
@app.route('/renaissance')
def posture_record():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    user_id = session.get('userId', 0)
    is_admin = session.get('role') == 'admin'

    if is_admin:
        total_row = query_db("SELECT COUNT(*) FROM monitoring_sessions", one=True)
        total_records = total_row[0] if total_row else 0
        total_pages = math.ceil(total_records / per_page) if total_records > 0 else 1
        offset = (page - 1) * per_page
        db_records = query_db(
            "SELECT ms.*, u.firstName, u.lastName FROM monitoring_sessions ms LEFT JOIN users u ON ms.user_id = u.userId ORDER BY ms.start_time DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        )
    elif user_id > 0:
        total_row = query_db("SELECT COUNT(*) FROM monitoring_sessions WHERE user_id = ?", (user_id,), one=True)
        total_records = total_row[0] if total_row else 0
        total_pages = math.ceil(total_records / per_page) if total_records > 0 else 1
        offset = (page - 1) * per_page
        db_records = query_db(
            "SELECT * FROM monitoring_sessions WHERE user_id = ? ORDER BY start_time DESC LIMIT ? OFFSET ?",
            (user_id, per_page, offset)
        )
    else:
        total_row = query_db("SELECT COUNT(*) FROM monitoring_sessions", one=True)
        total_records = total_row[0] if total_row else 0
        total_pages = math.ceil(total_records / per_page) if total_records > 0 else 1
        offset = (page - 1) * per_page
        db_records = query_db(
            "SELECT * FROM monitoring_sessions ORDER BY start_time DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        )
    
    history_data = []
    for row in db_records:
        row_dict = dict(row)
        dominant = row_dict.get('dominant_posture', '未知')
        
        if dominant == '端正坐姿':
            badge = 'badge-good'
        elif '烏龜' in dominant or '低頭' in dominant or '癱坐' in dominant:
            badge = 'badge-danger'
        else:
            badge = 'badge-warning'
        
        import json as _json
        ratio_str = row_dict.get('posture_ratio', '{}')
        try:
            ratio = _json.loads(ratio_str)
        except:
            ratio = {}
        
        history_data.append({
            "id": row_dict.get('session_id', '')[:8],
            "time": row_dict.get('start_time', ''),
            "status": dominant,
            "badge_class": badge,
            "offset": f"{row_dict.get('avg_offset', 0):.0f} px",
            "angle": f"{row_dict.get('avg_angle', 0):.0f}°",
            "note": f"{'👤 ' + (row_dict.get('lastName', '') + row_dict.get('firstName', '') or '未知') + ' | ' if is_admin else ''}烏龜:{row_dict.get('turtle_frames',0)} 低頭:{row_dict.get('down_frames',0)} 癱坐:{row_dict.get('slouch_frames',0)}",
            "image_url": None
        })

    return render_template('record.html',
                           records=history_data,
                           page=page,
                           total_pages=total_pages,
                           total_records=total_records,
                           per_page=per_page)

# 建立一個 WebSocket 接收通道，名稱叫做 'video_frame'
#接收前端影像幀進行 AI 姿勢識別、骨架標記繪製、定期統計落庫與不良姿勢即時警告
last_frame = None
last_bad_frame = None
@socketio.on('video_frame')
def handle_frame(data):
    global last_warning_time, last_frame, posture_snapshots
    global stability_pending, stability_count, total_angle, angle_count, total_offset, offset_count
    global last_tip_check, bad_posture_sustained
    
    try:
        encoded_data = data.split(',')[1]
        nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        results = pose_model.predict(frame)
        keypoints_dict, angle, posture_status, shoulder_to_hip_y, shoulder_width, shoulder_height_ratio = pose_model.get_results(results)
        
        if keypoints_dict is not None and angle is not None:
            Controller.draw_skeleton_and_angle(frame, keypoints_dict, angle, posture_status)

            # 暫存最新畫面與當前姿勢的代表畫面
            last_frame = frame.copy()
            posture_snapshots[posture_status] = frame.copy()

            # === 15 秒穩定判定後才計數 ===
            if posture_status == stability_pending:
                stability_count += 1
                if stability_count >= STABILITY_THRESHOLD:
                    if posture_status != "Good":
                        bad_posture_sustained = True
                    if posture_status in posture_counts:
                        with record_lock:
                            posture_counts[posture_status] += 1
                            if angle is not None:
                                total_angle += angle
                                angle_count += 1
                            if keypoints_dict is not None:
                                offset_x = abs(keypoints_dict['ear'][0] - keypoints_dict['shoulder'][0])
                                total_offset += offset_x
                                offset_count += 1
            else:
                stability_pending = posture_status
                stability_count = 1

            # === 3 分鐘定時提示 ===
            global last_tip_check, last_warning_time
            
            if time.time() - last_tip_check >= TIP_CHECK_INTERVAL:
                last_tip_check = time.time()
                print(f"[TIP CHECK] sustained={bad_posture_sustained}, cooldown_ok={time.time() - last_warning_time >= COOLDOWN_SECONDS}")
                print(f"[TIP CHECK] sustained={bad_posture_sustained}, cooldown_ok={time.time() - last_warning_time >= COOLDOWN_SECONDS}")
                if bad_posture_sustained and time.time() - last_warning_time >= COOLDOWN_SECONDS:
                    bad_posture_sustained = False
                    if stability_pending is not None and stability_pending != "Good":
                        target = stability_pending
                    else:
                        target = "Slouching"
                    advice_message = ""
                    if target == "TurtleNeck":
                        advice_message = "您的頸部似乎有些前傾囉！請試著深呼吸，將肩膀往後放鬆，下巴微收，保護您的頸椎。"
                    elif target == "LookingDown":
                        advice_message = "視線好像太低了！請試著抬起頭平視前方，讓頸椎休息一下吧。"
                    elif target == "Slouching":
                        advice_message = "身體是不是有點往後滑了呢？稍微把骨盆扶正，讓脊椎回到舒服的弧度喔。"
                    else:
                        advice_message = "系統偵測到您的坐姿需要調整囉，稍微伸展一下吧！"
                    
                    emit('ai_alert', {'message': advice_message})
                    last_warning_time = time.time()

        # 壓縮回傳前端
        ret, buffer = cv2.imencode('.jpg', frame)
        if ret:
            encoded_img = base64.b64encode(buffer).decode('utf-8')
            emit('processed_frame', f"data:image/jpeg;base64,{encoded_img}")

    except Exception as e:
        print(f"處理影像時發生錯誤: {e}")
        traceback.print_exc()

#處理 WebSocket 新連線
@socketio.on('connect')
def handle_connect(auth=None):
    """重連時先將舊 session 的累計數據落庫，再重置所有會話狀態，避免跨 session 汙染。"""
    global last_record_time, last_warning_time, last_frame, posture_snapshots, stability_pending, stability_count, last_tip_check, bad_posture_sustained, total_angle, angle_count, total_offset, offset_count
    with record_lock:
        if sum(posture_counts.values()) > 0:
            write_session_summary(sid)
        for k in posture_counts:
            posture_counts[k] = 0
        last_record_time = time.time()
        posture_snapshots.clear()
        last_frame = None
        stability_pending = None
        stability_count = 0
        last_tip_check = time.time()
        bad_posture_sustained = False
        total_angle = 0
        angle_count = 0
        total_offset = 0
        offset_count = 0
    posture_history.clear()
    last_warning_time = 0

#處理 WebSocket 斷線：
# === 斷線處理（配合 30 秒防閃斷機制）===
@socketio.on('disconnect')
def handle_disconnect(*args):
    """尾部強制結算：關閉頁面時把未結算的 session 數據寫入庫。"""
    global last_record_time, last_frame, posture_snapshots, last_tip_check, bad_posture_sustained, total_angle, angle_count, total_offset, offset_count
    sid = request.sid

    with record_lock:
        if sum(posture_counts.values()) > 0:
            write_session_summary(sid)
        
        for k in posture_counts:
            posture_counts[k] = 0
        posture_snapshots.clear()
        last_frame = None
        total_angle = 0
        angle_count = 0
        total_offset = 0
        offset_count = 0

    posture_history.clear()
    last_tip_check = time.time()
    bad_posture_sustained = False
    user_monitoring_sessions.pop(sid, None)
    print(f"[{sid}] 離線結算完成，狀態已重置。")

# 紀錄該連線的監測開始時間與預定時長 (可依 socket id 記錄)
user_monitoring_sessions = {}

@socketio.on('start_monitoring')
def handle_start_monitoring(data):
    """前端點擊確認開始時觸發：初始化/重置狀態"""
    global last_record_time, last_warning_time, last_frame, posture_snapshots, stability_pending, stability_count, last_tip_check, bad_posture_sustained, total_angle, angle_count, total_offset, offset_count
    sid = request.sid
    duration_minutes = data.get('duration', 0)
    
    with record_lock:
        for k in posture_counts:
            posture_counts[k] = 0
        last_record_time = time.time()
        posture_snapshots.clear()
        last_frame = None
        stability_pending = None
        stability_count = 0
        last_tip_check = time.time() - TIP_CHECK_INTERVAL  # 首次立即檢查
        bad_posture_sustained = False
        total_angle = 0
        angle_count = 0
        total_offset = 0
        offset_count = 0

    posture_history.clear()
    last_warning_time = 0
    
    user_monitoring_sessions[sid] = {
        'start_time': time.time(),
        'start_time_iso': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'target_duration': duration_minutes,
        'user_id': data.get('user_id', 0) or session.get('userId', 0)
    }
    print(f"[{sid}] 開始監測，預定時長: {duration_minutes} 分鐘")


# === 手動停止 / 倒數時間到（主動結算）===
@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    """使用者點擊暫停或倒數時間到：直接結算 session"""
    global last_frame, posture_snapshots, last_tip_check, bad_posture_sustained
    sid = request.sid

    with record_lock:
        if sum(posture_counts.values()) > 0:
            write_session_summary(sid)

        for k in posture_counts:
            posture_counts[k] = 0
        posture_snapshots.clear()
        last_frame = None

    posture_history.clear()
    last_tip_check = time.time()
    bad_posture_sustained = False
    user_monitoring_sessions.pop(sid, None)
    print(f"[{sid}] 監測主動停止，session 已結算落庫。")

#坐姿紀錄整理成圖表（個人數據）
@app.route('/analysis')
def posture_analysis():
    user_id = session.get('userId', 0)
    is_admin = session.get('role') == 'admin'
    
    if is_admin:
        db_records = query_db("SELECT * FROM monitoring_sessions ORDER BY start_time DESC LIMIT 30")
    else:
        db_records = query_db(
            "SELECT * FROM monitoring_sessions WHERE user_id = ? ORDER BY start_time DESC LIMIT 30",
            (user_id,)
        )
    db_records = db_records[::-1] if db_records else []
    
    labels = []
    good_data = []
    turtle_data = []
    down_data = []
    slouch_data = []
    
    total_good = 0
    total_turtle = 0
    total_down = 0
    total_slouch = 0
    
    for row in db_records:
        time_str = row['start_time'].split(' ')[1][:5] if ' ' in str(row['start_time']) else str(row['start_time'])
        labels.append(time_str)
        
        good_data.append(row['good_frames'])
        turtle_data.append(row['turtle_frames'])
        down_data.append(row['down_frames'])
        slouch_data.append(row['slouch_frames'])
        
        total_good += row['good_frames']
        total_turtle += row['turtle_frames']
        total_down += row['down_frames']
        total_slouch += row['slouch_frames']
        
    chart_data = {
        "labels": labels,
        "good": good_data,
        "turtle": turtle_data,
        "down": down_data,
        "slouch": slouch_data,
        "pie_totals": [total_good, total_turtle, total_down, total_slouch]
    }
    
    return render_template('analysis.html', chart_data=chart_data)

@app.route('/rank')
def posture_rank():
    rows = query_db("""
        SELECT dominant_posture, COUNT(*) as cnt, SUM(good_frames + turtle_frames + down_frames + slouch_frames) as total
        FROM monitoring_sessions
        WHERE dominant_posture != '端正坐姿'
        GROUP BY dominant_posture
        ORDER BY cnt DESC
        LIMIT 4
    """)
    
    total_all = sum(r['cnt'] for r in rows) if rows else 1
    
    rank_data = []
    desc_map = {
        "烏龜頸": "耳朵水平位移超出肩膀中線，長期可能導致頸椎提早退化。請試著微收下巴。",
        "過度低頭": "頸部前傾超過標準角度，極易造成頸椎壓力與肩頸痠痛。建議將螢幕墊高至視線平齊。",
        "癱坐": "骨盆過度前傾滑出椅面，腰椎失去支撐，易引發下背痛。請將臀部坐滿椅面。"
    }
    
    for i, row in enumerate(rows):
        name = row['dominant_posture']
        rank_data.append({
            "rank": i + 1,
            "name": name,
            "desc": desc_map.get(name, "請注意保持正確坐姿"),
            "count": row['cnt'],
            "percent": round(row['cnt'] / total_all * 100)
        })
    
    if not rank_data:
        rank_data = [{"rank": 1, "name": "尚無數據", "desc": "尚未有足夠的監測紀錄", "count": 0, "percent": 100}]
    
    return render_template('rank.html', rankings=rank_data)

@app.route('/login', methods=['POST'])
def login():
    # 1. 取得使用者在網頁表單輸入的帳號密碼
    email = request.form.get('email')
    password = request.form.get('password')
    
    # 2. 建立資料庫連線、3. 去資料庫尋找這個信箱
    user = query_db("SELECT * FROM users WHERE email = ?", (email,), one=True)
    
    # 4. 密碼驗證 (將輸入的密碼做 MD5 處理後，與資料庫比對)
    if user:
        hashed_input_password = hashlib.md5(password.encode()).hexdigest()
        
        if user['password'] == hashed_input_password:
            # 登入成功！將重要資訊寫入 Session (使用者的通行證)
            session['loggedIn'] = True
            session['userId'] = user['userId']
            session['email'] = user['email']
            session['firstName'] = user['firstName']
            
            # 根據 isAdmin 標籤，發給不同的權限
            if user['isAdmin'] == 1:
                session['role'] = 'admin'
            else:
                session['role'] = 'user'
                
            # 登入成功後，把使用者踢回首頁 (假設首頁的函數名稱為 index)
            return redirect(url_for('index'))
            
    # 如果找不到帳號，或是密碼比對失敗
    return "帳號或密碼錯誤，請回上一頁重新輸入"

@app.route('/logout')
def logout():
    # 清空 session 裡的所有資料 (銷毀通行證)
    session.clear()
    
    # 登出後，把使用者踢回首頁
    return redirect(url_for('index'))

class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())
scheduler = APScheduler()

# ================= 測試設定 =================
SMTP_SERVER = 'smtp.gmail.com'         # 如果是 Gmail 不用改
SMTP_PORT = 465                        # SSL 端口

SENDER_EMAIL = 'startpan070@gmail.com'   # 寄件人 Gmail 帳號
SENDER_PASSWORD = 'mqpp ahrw tbbb ypuu'  # Google 產生的應用程式專用密碼
RECEIVER_EMAIL = 'startpan070@gmail.com' # 收件人 Email
# ===================================================

#取得一般使用者清單
def get_all_users_from_db():
    """從資料庫讀取所有一般用戶的資料"""
    query = "SELECT email, firstName, lastName FROM users WHERE isAdmin = 0"

    return query_db(query)

# 批次發送用戶每週通知信
def send_weekly_email_to_all_users():
    """核心功能：從資料庫抓取名單並逐一發送客製化信件"""
    print("【系統通知】開始執行每週批次發信任務...")
    
    # 從資料庫獲取超過 7 天未更新 BMI 或從未更新過的使用者名單
    users = query_db("""
        'SELECT * FROM users WHERE (updatedBMI < datetime('now', '-7 days') OR updatedBMI IS NULL OR updatedBMI = '')
          AND (last_notified_at < datetime('now', '-7 days') OR last_notified_at IS NULL OR last_notified_at = '')
    """
    )
    
    if not users:
        print("【系統通知】資料庫中沒有找到符合條件（超過7天未更新BMI）的使用者，終止發信。")
        return False

    try:
        # 建立安全 SMTP 連線 (在迴圈外連線一次即可，效率較高)
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            
            # 逐一為每個使用者客製化郵件內容
            for user in users:
                email = user['email']
                # 結合名與姓，若欄位為空則給預設稱呼
                first_name = user['firstName'] if user['firstName'] else ""
                last_name = user['lastName'] if user['lastName'] else "用戶"
                full_name = f"{first_name}{last_name}"
                
                # 建立支援多元格式的郵件容器
                message = MIMEMultipart('alternative')
                message['From'] = Header(f"官方系統通知 <{SENDER_EMAIL}>", 'utf-8')
                message['To'] = Header(email, 'utf-8')
                message['Subject'] = Header(f"【提醒】{full_name}，記得更新您的 BMI 資料以維持準確度", 'utf-8')
                
                # 給該使用者的客製化內文
                content = f"""
                親愛的 {full_name} 您好：
                
                感謝您使用我們的網站！
                系統檢測到您已超過 7 天未更新 BMI 資料。為了使您的坐姿觀測與分析更準確，提醒您記得前往系統更新 BMI 數據。
                
                祝您有美好的一天！
                官方團隊 敬上
                """
                
                part_text = MIMEText(content, 'plain', 'utf-8')
                message.attach(part_text)
                
                # 發送郵件
                server.sendmail(SENDER_EMAIL, [email], message.as_string())
                print(f"成功發送給: {full_name} ({email})")
                
        print("【系統通知】所有符合條件使用者的郵件均已發送完畢！")
        return True
    except Exception as e:
        print(f"【系統錯誤】批次發信過程中發生錯誤: {e}")
        return False

# ================= 定時任務設定 =================
@scheduler.task('cron', id='weekly_test_job', hour=19, minute=30)
def scheduled_job():
    with app.app_context():
        send_weekly_email_to_all_users()

@app.route('/test-send-all')
def test_send_all():
    """手動測試路由：點擊後立刻從資料庫撈資料並發信"""
    success = send_weekly_email_to_all_users()
    if success:
        return "<h3>批次發信順利完成！請確認終端機 (Terminal) 的發送日誌。</h3>"
    else:
        return "<h3>發信失敗，請檢查終端機的錯誤訊息。</h3>"

def getLoginDetails():
    if 'email' not in session:
        return False, ''
    
    user = query_db("SELECT userId, firstName FROM users WHERE email = ?", (session['email'],), one=True)
    if not user:
        return False, ''
    
    userId, firstName = user
    return True, firstName

@app.route("/aboutus")
def aboutus():
    loggedIn, firstName = getLoginDetails()
    return render_template("aboutus.html", loggedIn=loggedIn, firstName=firstName)

@app.route("/profileHome")
def profileHome():
    if 'email' not in session:
        return redirect(url_for('index'))
    loggedIn, firstName = getLoginDetails()
    profileData = query_db("SELECT email, firstName, lastName, address1, phone, weight, height FROM users WHERE email = ?", (session['email'],), one=True)
    return render_template("profileHome.html", profileData=profileData, loggedIn=loggedIn, firstName=firstName)

@app.route("/editProfile")
def editProfile():
    if 'email' not in session:
        return redirect(url_for('index'))
    loggedIn, firstName = getLoginDetails()
    profileData = query_db("SELECT email, firstName, lastName, address1, phone, weight, height FROM users WHERE email = ?", (session['email'],), one=True)
    return render_template("editProfile.html", profileData=profileData, loggedIn=loggedIn, firstName=firstName)

@app.route("/account/profile/changePassword", methods=["GET", "POST"])
def changePassword():
    if 'email' not in session:
        return redirect(url_for('loginForm'))
    if request.method == "POST":
        oldPassword = request.form['oldpassword']
        oldPassword = hashlib.md5(oldPassword.encode()).hexdigest()
        newPassword = request.form['newpassword']
        newPassword = hashlib.md5(newPassword.encode()).hexdigest()
        user = query_db("SELECT userId, password FROM users WHERE email = ?", (session['email'],), one=True)
        if user:
            userId, password = user
            if (password == oldPassword):
                try:
                    execute_db("UPDATE users SET password = ? WHERE userId = ?", (newPassword, userId))
                    msg = "Changed successfully"
                except Exception as e:
                    msg = "Failed"
                return render_template("changePassword.html", msg=msg)
            else:
                msg = "Wrong password"
                return render_template("changePassword.html", msg=msg)
        else:
            msg = "User not found"
            return render_template("changePassword.html", msg=msg)
    else:
        return render_template("changePassword.html")

@app.route("/updateProfile", methods=["GET", "POST"])
def updateProfile():
    if request.method == 'POST':
        email = request.form['email']
        firstName = request.form['firstName']
        lastName = request.form['lastName']
        address1 = request.form['address1']
        phone = request.form['phone']
        weight = request.form['weight']
        height = request.form['height']
        try:
            execute_db(
                '''UPDATE users 
                   SET firstName = ?, lastName = ?, address1 = ?, phone = ?, weight = ?, height = ? 
                   WHERE email = ?''',
                (firstName, lastName, address1, phone, weight, height, email)
            )
            msg = "Saved Successfully"
        except Exception as e:
            msg = "Error occured"
        return redirect(url_for('editProfile'))

if __name__ == '__main__':
    scheduler.init_app(app)
    scheduler.start()

    print("伺服器啟動中... 請前往 http://127.0.0.1:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False)