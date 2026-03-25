import cv2

def get_connected_camera_ids():
    """
    掃描系統中的攝影機索引 (0-4)
    """
    available_ports = []
    for x in range(5):
        camera = cv2.VideoCapture(x)
        if camera.isOpened():
            ret, frame = camera.read()
            if ret:
                available_ports.append(x)
            camera.release() 
        else:
            camera.release()
    return available_ports

def get_connected_camera_alias():
    """
    獲取攝影機名稱。
    如果你在 Windows 且一定要真實名稱，建議安裝 pygrabber。
    """
    ids = get_connected_camera_ids()
    return [f"Camera {i}" for i in ids]

def is_camera_connected():
    """
    檢查是否有任何攝影機連線
    """
    ids = get_connected_camera_ids()
    return len(ids) > 0

def get_camera_mapping():
    """
    直接生成名稱與 ID 的對應字典
    回傳範例: {"Camera 0": 0, "Camera 1": 1}
    """
    ids = get_connected_camera_ids()
    names = [f"Camera {i}" for i in ids]
    return dict(zip(names, ids))