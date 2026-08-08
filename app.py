import base64, hashlib, math, smtplib, sqlite3, threading, time, traceback
from collections import deque
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import cv2
import numpy as np
from flask import Flask, redirect, render_template, request, session, url_for
from flask_apscheduler import APScheduler
from flask_socketio import SocketIO, emit

from controllers.controller import Controller
from db import init_db, query_db, execute_db
from models.load_model import Model
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'secret_key_for_session' # 設定 Session 的加密金鑰
socketio = SocketIO(app, cors_allowed_origins="*")

record_lock = threading.RLock()     # 全域只宣告一次鎖頭
last_record_time = time.time()      # 紀錄初始時間
posture_counts = {                  # 建立一個用來統計姿勢的字典
    "Good": 0,
    "TurtleNeck": 0,
    "LookingDown": 0,
    "Slouching": 0
}

# 3 分鐘姿勢聚合計數器（全局共享，重連不丟數據）
posture_history = deque(
    maxlen=30                       # 代表這條輸送帶最多只記得過去 30 次的判定結果 (約 3 秒)
) 
last_warning_time = 0               # 記錄上一次發送 AI 警告的時間戳記
COOLDOWN_SECONDS = 60               # 設定冷卻時間為 60 秒

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

# === 寫入並重置坐姿紀錄 ===
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

        query = """
            INSERT INTO posture_records (
                good_count, turtle_neck_count,
                looking_down_count, slouching_count, timestamp
            ) VALUES (?, ?, ?, ?, ?)
        """
        args = (
            posture_counts['Good'],
            posture_counts['TurtleNeck'],
            posture_counts['LookingDown'],
            posture_counts['Slouching'],
            now_ts,
        )
        execute_db(query, args)

        # 清零並刷新時間戳
        for k in posture_counts:
            posture_counts[k] = 0
        last_record_time = time.time()

# 取得坐姿歷史紀錄（含分頁與狀態判斷）並渲染頁面(record.html)
@app.route('/renaissance')
def posture_record():
    # 1. 取得當前頁碼 (預設為第 1 頁) 與每頁顯示筆數
    page = request.args.get('page', 1, type=int)
    per_page = 10 

    # 2. 計算總紀錄數與總頁數 (使用 one=True 取得單一紀錄)
    total_row = query_db("SELECT COUNT(*) FROM posture_records", one=True)
    total_records = total_row[0] if total_row else 0
    total_pages = math.ceil(total_records / per_page)

    # 3. 根據頁碼，計算要「跳過」幾筆資料 (OFFSET)，再撈取該頁資料 (LIMIT)
    offset = (page - 1) * per_page
    db_records = query_db(
        "SELECT * FROM posture_records ORDER BY timestamp DESC LIMIT ? OFFSET ?", 
        (per_page, offset)
    )
    
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
#接收前端影像幀進行 AI 姿勢識別、骨架標記繪製、定期統計落庫與不良姿勢即時警告
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
        
        # 完美接住模型丟出來的 6 個變數
        keypoints_dict, angle, posture_status, shoulder_to_hip_y, shoulder_width, shoulder_height_ratio = pose_model.get_results(results)
        
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
        traceback.print_exc()

#處理 WebSocket 新連線
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

#處理 WebSocket 斷線：
@socketio.on('disconnect')
def handle_disconnect():
    """尾部強制結算：關閉頁面時把未滿 180 秒的累計數據寫入庫。
    觸發條件：距離上次入庫超過 30 秒（避免閃斷刷新就觸發）。"""
    global last_record_time
    with record_lock:
        if time.time() - last_record_time >= 30:
            insert_posture_record_if_any()

#坐姿紀錄整理成圖表
@app.route('/analysis')
def posture_analysis():
    db_records = query_db("SELECT * FROM posture_records ORDER BY timestamp DESC LIMIT 30")
    db_records = db_records[::-1] if db_records else []
    
    # 準備餵給折線圖的資料陣列
    labels = []
    good_data = []
    turtle_data = []
    down_data = []
    slouch_data = []
    
    # 準備餵給圓餅圖的加總變數
    total_good = 0
    total_turtle = 0
    total_down = 0
    total_slouch = 0
    
    for row in db_records:
        time_str = row['timestamp'].split(' ')[1] if ' ' in row['timestamp'] else row['timestamp']
        labels.append(time_str)
        
        good_data.append(row['good_count'])
        turtle_data.append(row['turtle_neck_count'])
        down_data.append(row['looking_down_count'])
        slouch_data.append(row['slouching_count'])
        
        # 順便把這些數字加總起來
        total_good += row['good_count']
        total_turtle += row['turtle_neck_count']
        total_down += row['looking_down_count']
        total_slouch += row['slouching_count']
        
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
    # 這裡未來會替換成「撈取近一週資料庫並計算比例」的真實邏輯
    mock_ranking_data = [
        {
            "rank": 1, 
            "name": "過度低頭", 
            "desc": "頸部前傾超過標準角度，極易造成頸椎壓力與肩頸痠痛。建議將螢幕墊高至視線平齊。", 
            "count": 1250, 
            "percent": 45
        },
        {
            "rank": 2, 
            "name": "烏龜頸頻發", 
            "desc": "耳朵水平位移超出肩膀中線，長期可能導致頸椎提早退化。請試著微收下巴。", 
            "count": 840, 
            "percent": 30
        },
        {
            "rank": 3, 
            "name": "癱坐前滑", 
            "desc": "骨盆過度前傾滑出椅面，腰椎失去支撐，易引發下背痛。請將臀部坐滿椅面。", 
            "count": 420, 
            "percent": 15
        },
        {
            "rank": 4, 
            "name": "端正坐姿", 
            "desc": "脊椎保持自然曲度，肌肉受力平均的優良狀態。請繼續保持這個好習慣！", 
            "count": 280, 
            "percent": 10
        }
    ]
    
    return render_template('rank.html', rankings=mock_ranking_data)

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