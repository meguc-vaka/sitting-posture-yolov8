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

    # 現象分類器 (規則引擎) — 全角度制
    @staticmethod
    def classify_posture(ear, shoulder, hip, angle, facing):
        """
        facing: "left" 或 "right"，代表靠近鏡頭的一側
        """
        ear_x, ear_y = ear
        shoulder_x, shoulder_y = shoulder
        hip_x, hip_y = hip

        # TurtleNeck：耳肩連線與垂直線的夾角
        neck_angle = abs(math.degrees(math.atan2(ear_x - shoulder_x, shoulder_y - ear_y)))

        # Slouching：肩骨盆連線與垂直線的夾角
        torso_angle = abs(math.degrees(math.atan2(hip_x - shoulder_x, shoulder_y - hip_y)))

        # 判斷耳朵是否在肩前方（前傾）
        if facing == "right":
            ear_in_front = ear_x > shoulder_x
        else:
            ear_in_front = ear_x < shoulder_x

        if neck_angle > 20:
            return "TurtleNeck"
        elif torso_angle > 25:
            return "Slouching"
        elif angle < 145:
            return "LookingDown"
        elif 145 <= angle <= 160 and ear_in_front:
            return "LeaningForward"
        else:
            return "Good"

    def get_results(self, results):
        keypoints_dict = None
        angle = None
        posture_status = "Good"
        shoulder_to_hip_y = None
        shoulder_width = None
        shoulder_height_ratio = None
        facing = "right"  # 預設右側面向鏡頭

        if len(results[0].boxes) > 0: 
            keypoints = results[0].keypoints.xy[0].cpu().numpy()
            confs = results[0].keypoints.conf[0].cpu().numpy() if results[0].keypoints.conf is not None else None
            
            if len(keypoints) > 12:
                # 自動選肩：比對左右肩信心值，高者為靠近鏡頭的一側
                l_shoulder = keypoints[5]
                r_shoulder = keypoints[6]
                l_conf = confs[5] if confs is not None else 0
                r_conf = confs[6] if confs is not None else 0
                
                if l_conf > r_conf and l_shoulder[0] != 0:
                    near_shoulder = l_shoulder
                    far_shoulder = r_shoulder
                    facing = "left"
                else:
                    near_shoulder = r_shoulder
                    far_shoulder = l_shoulder
                    facing = "right"

                r_ear = keypoints[4]
                r_hip = keypoints[12]

                if r_ear[0] != 0 and near_shoulder[0] != 0 and r_hip[0] != 0:
                    keypoints_dict = {
                        'ear': (int(r_ear[0]), int(r_ear[1])),
                        'shoulder': (int(near_shoulder[0]), int(near_shoulder[1])),
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
                        angle,
                        facing
                    )

                    shoulder_to_hip_y = abs(int(near_shoulder[1]) - int(r_hip[1]))

                    if far_shoulder[0] != 0 and far_shoulder[1] != 0:
                        shoulder_width = math.sqrt(
                            (int(near_shoulder[0]) - int(far_shoulder[0])) ** 2 +
                            (int(near_shoulder[1]) - int(far_shoulder[1])) ** 2
                        )
                        if shoulder_width > 0:
                            shoulder_height_ratio = shoulder_to_hip_y / shoulder_width

        return keypoints_dict, angle, posture_status, shoulder_to_hip_y, shoulder_width, shoulder_height_ratio