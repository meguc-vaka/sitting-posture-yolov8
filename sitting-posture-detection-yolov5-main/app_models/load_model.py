import math
from ultralytics import YOLO

class Model:
    def __init__(self, model_name="yolov8n-pose.pt"):
        self.model_name = model_name
        print('Loading YOLOv8 Pose model...')
        self.model = YOLO(self.model_name) 
        self.conf = 0.50

    def predict(self, image):
        return self.model(image, conf=self.conf, verbose=False)

    @staticmethod
    def calculate_angle_3points(p1, p2, p3):
        """
        p1: 耳朵 (頸椎起點)
        p2: 肩膀 (兩條線的交點)
        p3: 骨盆 (脊椎終點)
        """
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        
        # 計算兩條線在平面上的角度
        angle1 = math.degrees(math.atan2(y1 - y2, x1 - x2)) 
        angle2 = math.degrees(math.atan2(y3 - y2, x3 - x2)) 
        
        # 兩個角度相減取絕對值
        angle = abs(angle1 - angle2)
        
        # 取得內角
        if angle > 180.0:
            angle = 360.0 - angle
            
        return int(angle)

    def get_results(self, results):
        keypoints_dict = None
        angle = None

        if len(results[0].boxes) > 0: 
            keypoints = results[0].keypoints.xy[0].cpu().numpy() 
            
            # 如果座標數量足夠（避免模型沒抓完整而報錯）
            if len(keypoints) > 12:
                r_ear = keypoints[4]      
                r_shoulder = keypoints[6] 
                r_hip = keypoints[12]     

                keypoints_dict = {
                    'ear': (int(r_ear[0]), int(r_ear[1])),
                    'shoulder': (int(r_shoulder[0]), int(r_shoulder[1])),
                    'hip': (int(r_hip[0]), int(r_hip[1]))
                }

                # 將座標回傳計算內角
                angle = self.calculate_angle_3points(
                    keypoints_dict['ear'], 
                    keypoints_dict['shoulder'], 
                    keypoints_dict['hip']
                )

        return keypoints_dict, angle