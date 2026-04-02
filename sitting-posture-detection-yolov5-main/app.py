import cv2
import numpy as np
import base64
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

from app_models.load_model import Model
from app_controllers.controller import Controller

app = Flask(__name__)
# 啟用 SocketIO，允許跨域請求
socketio = SocketIO(app, cors_allowed_origins="*")

# 在程式啟動時就先載入模型，避免每次連線都重新讀取，提升效能
print("正在初始化 AI 模型...")
pose_model = Model("yolov8n-pose.pt")

@app.route('/')
def index():
    # 這裡會去專案資料夾下的 templates 資料夾中尋找 index.html 顯示給使用者
    return render_template('index.html')

# 建立一個 WebSocket 接收通道，名稱叫做 'video_frame'
@socketio.on('video_frame')
def handle_frame(data):
    try:
        # ==========================================
        # 步驟一：接收前端傳來的圖片並「解碼」成 OpenCV 格式
        # ==========================================
        # 前端傳來的是 Base64 字串 (例如 data:image/jpeg;base64,/9j/4AAQ...)
        # 我們需要把逗號後面的純資料切出來
        encoded_data = data.split(',')[1]
        # 解碼成二進位資料
        nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        # 轉換成 OpenCV 看得懂的圖片陣列 (frame)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # ==========================================
        # 步驟二：交給您的 Model 算數字，交給 Controller 畫圖
        # ==========================================
        results = pose_model.predict(frame)
        keypoints_dict, angle = pose_model.get_results(results)
        
        if keypoints_dict is not None and angle is not None:
            is_good_posture = angle >= 150
            # 這裡就是我們剛才完美綁定了邊框與骨架的那個函式！
            Controller.draw_skeleton_and_angle(frame, keypoints_dict, angle, is_good_posture)

        # ==========================================
        # 步驟三：把畫好骨架的圖片「編碼」回字串，丟回給前端網頁
        # ==========================================
        # 將處理後的 frame 壓縮成 JPG
        ret, buffer = cv2.imencode('.jpg', frame)
        if ret:
            # 再轉回 Base64 字串
            encoded_img = base64.b64encode(buffer).decode('utf-8')
            # 透過 WebSocket 傳回給前端，通道名稱叫做 'processed_frame'
            emit('processed_frame', f"data:image/jpeg;base64,{encoded_img}")

    except Exception as e:
        print(f"處理影像時發生錯誤: {e}")

if __name__ == '__main__':
    # 雲端版必須使用 socketio.run 來啟動伺服器，取代原本的 app.run
    print("伺服器啟動中... 請前往 http://127.0.0.1:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
