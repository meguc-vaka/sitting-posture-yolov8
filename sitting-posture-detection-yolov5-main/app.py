import cv2
from flask import Flask, render_template, Response
from app_models.load_model import Model
from app_controllers.utils import camera_helper
from app_controllers.controller import Controller

app = Flask(__name__)
model = Model("yolov8n-pose.pt")

# 影像產生器
def generate_frames(camera_id):
    cap = cv2.VideoCapture(int(camera_id))
    
    while True:
        success, frame = cap.read()
        if not success:
            break
        
        # --- AI 辨識核心對接 ---
        try:
            # 把畫面交給 Model 進行預測
            results = model.predict(frame)
            
            # 呼叫 Model 的 get_results 來取得座標與算好的角度
            keypoints_dict, angle = model.get_results(results)
            
            # 如果算成功了，就把這些數據交給 Controller
            if keypoints_dict is not None and angle is not None:
                is_good_posture = angle >= 150
                Controller.draw_skeleton_and_angle(frame, keypoints_dict, angle, is_good_posture)
                
        except Exception as e:
            print(f"AI 偵測發生錯誤: {e}")

        # 把畫好骨架的 frame 上傳給網頁
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
            
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    cap.release()

# 網頁主頁面
@app.route('/')
def index():
    # 呼叫 camera_helper 取得清單
    cameras = camera_helper.get_camera_mapping()
    return render_template('index.html', cameras=cameras)

# 4影像串流路由
@app.route('/video_feed/<int:cam_id>')
def video_feed(cam_id):
    print(f"--- 收到連線請求，準備開啟相機 ID: {cam_id} ---")
    return Response(generate_frames(cam_id), 
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)