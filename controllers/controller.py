import cv2

class Controller:
    @staticmethod
    def draw_skeleton_and_angle(frame, keypoints_dict, angle, posture_status):
        ear = keypoints_dict['ear']
        shoulder = keypoints_dict['shoulder']
        hip = keypoints_dict['hip']

        # 取得畫面的長寬
        height, width = frame.shape[:2]
        
        # 建立狀態字典，根據 AI 傳來的標籤決定顏色與警告字眼
        status_config = {
            "Good": {"color": (0, 255, 0), "text": ""},                                # 綠色，無警告
            "TurtleNeck": {"color": (0, 0, 255), "text": "Warning: Turtle Neck!"},     # 紅色，烏龜頸
            "Slouching": {"color": (0, 0, 255), "text": "Warning: Slouching!"},        # 紅色，癱坐
            "LookingDown": {"color": (0, 165, 255), "text": "Warning: Looking Down!"}  # 橘色，低頭
        }

        # 取得當前狀態設定，如果是不認識的標籤，預設給紅色警告
        current_config = status_config.get(posture_status, {"color": (0, 0, 255), "text": "Warning: Bad Posture"})
        theme_color = current_config["color"]
        warning_text = current_config["text"]

        # 畫上滿版的邊框(厚度為 8)，顏色跟隨主題色
        cv2.rectangle(frame, (0, 0), (width-1, height-1), theme_color, 8)

        # 頸椎線與脊椎線(黃)
        cv2.line(frame, ear, shoulder, (0, 255, 255), 2) 
        cv2.line(frame, shoulder, hip, (0, 255, 255), 2)

        # 關節點(藍)
        for pt in [ear, shoulder, hip]:
            cv2.circle(frame, pt, 6, (255, 0, 0), -1)

        # 寫出角度，顏色跟隨主題色
        cv2.putText(frame, f"Angle: {angle} deg", (shoulder[0] + 15, shoulder[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, theme_color, 2, cv2.LINE_AA)
        
        # 如果有警告文字 (即不是 Good 狀態)，就印在畫面上
        if warning_text:
            cv2.putText(frame, warning_text, (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, theme_color, 3, cv2.LINE_AA)