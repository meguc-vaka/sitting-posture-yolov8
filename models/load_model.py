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

    # 現象分類器 (規則引擎)
    @staticmethod
    def classify_posture(ear, shoulder, hip, angle):
        ear_x, _ = ear
        shoulder_x, _ = shoulder
        hip_x, _ = hip

        # 計算水平位移 (X 座標差值)
        # 正常情況下，從側面看耳朵應該在肩膀正上方 (X差值接近 0)
        neck_offset_x = abs(ear_x - shoulder_x)
        
        # 正常情況下，肩膀應該在骨盆上方 (X差值不會太大)
        torso_offset_x = abs(shoulder_x - hip_x)

        # === 開始進入分類邏輯 ===
        # 註：這裡的數值 (40, 60, 140) 是像素點與角度的「臨界值」
        # 您可以依據報告測量時的攝影機距離，微調這些標準
        
        if neck_offset_x > 40:
            return "TurtleNeck"  # 烏龜頸：耳朵 X 座標遠離肩膀
            
        elif torso_offset_x > 60:
            return "Slouching"   # 癱坐：骨盆往前滑，導致肩膀與骨盆 X 差值變大
            
        elif angle < 140:
            return "LookingDown" # 過度低頭 / 嚴重駝背：內角過小
            
        else:
            return "Good"        # 皆未觸發，判定為良好坐姿

    def get_results(self, results):
        keypoints_dict = None
        angle = None
        posture_status = "Good"
        shoulder_to_hip_y = None
        shoulder_width = None
        shoulder_height_ratio = None

        if len(results[0].boxes) > 0: 
            keypoints = results[0].keypoints.xy[0].cpu().numpy() 
            
            if len(keypoints) > 12:
                r_ear = keypoints[4]      
                r_shoulder = keypoints[6] 
                r_hip = keypoints[12]
                l_shoulder = keypoints[5]

                if r_ear[0] != 0 and r_shoulder[0] != 0 and r_hip[0] != 0:
                    keypoints_dict = {
                        'ear': (int(r_ear[0]), int(r_ear[1])),
                        'shoulder': (int(r_shoulder[0]), int(r_shoulder[1])),
                        'hip': (int(r_hip[0]), int(r_hip[1]))
                    }

                    angle = self.calculate_angle_3points(
                        keypoints_dict['ear'], 
                        keypoints_dict['shoulder'], 
                        keypoints_dict['hip']
                    )

                    posture_status = self.classify_posture(
                        keypoints_dict['ear'], 
                        keypoints_dict['shoulder'], 
                        keypoints_dict['hip'], 
                        angle
                    )

                    # 新增：肩高比相关计算
                    shoulder_to_hip_y = abs(int(r_shoulder[1]) - int(r_hip[1]))

                    if l_shoulder[0] != 0 and l_shoulder[1] != 0:
                        shoulder_width = math.sqrt(
                            (int(r_shoulder[0]) - int(l_shoulder[0])) ** 2 +
                            (int(r_shoulder[1]) - int(l_shoulder[1])) ** 2
                        )
                        if shoulder_width > 0:
                            shoulder_height_ratio = shoulder_to_hip_y / shoulder_width

        return keypoints_dict, angle, posture_status, shoulder_to_hip_y, shoulder_width, shoulder_height_ratio