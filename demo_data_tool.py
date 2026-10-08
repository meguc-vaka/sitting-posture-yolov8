import json
from db import execute_db, query_db

def update_only_demo_sessions_to_improvement(user_id=1):
    """
    只針對 Demo 注入的 4 個精準時間點更新烏龜頸數值，
    原有的 09-23 與 10-04 等真實紀錄完全保留不受影響。
    """
    # 4 個 Demo 專用時間點與對應的改善數值 (良好%, 烏龜頸%, 低頭%, 駝背%)
    # 烏龜頸前 3 週維持在 ~37%，第 4 週斷崖式降至 8%
    demo_updates = [
        ("2026-09-14 10:00:00", 57.0, 38.0,  5.0, 0.0),  # W37
        ("2026-09-21 14:30:00", 59.0, 36.0,  5.0, 0.0),  # W38
        ("2026-09-28 09:15:00", 56.0, 37.0,  7.0, 0.0),  # W39
        ("2026-10-05 11:00:00", 82.0,  8.0, 10.0, 0.0)   # W40 (大幅改善！)
    ]

    print(f"🔄 開始精確更新 user_id={user_id} 的 4 筆 Demo 紀錄...")

    for start_t, good_pct, turtle_pct, down_pct, slouch_pct in demo_updates:
        # 1. 檢查是否存在該精確時間點的紀錄
        row = query_db(
            "SELECT session_id, good_frames, turtle_frames, down_frames, slouch_frames "
            "FROM monitoring_sessions WHERE user_id = ? AND start_time = ?",
            (user_id, start_t),
            one=True
        )

        if not row:
            print(f"⚠️ 找不到精確時間為 {start_t} 的紀錄，略過。")
            continue

        session_id = row['session_id']
        total_frames = (row['good_frames'] + row['turtle_frames'] + 
                        row['down_frames'] + row['slouch_frames'])

        # 2. 重新換算各幀數
        new_good = int(total_frames * (good_pct / 100.0))
        new_turtle = int(total_frames * (turtle_pct / 100.0))
        new_down = int(total_frames * (down_pct / 100.0))
        new_slouch = total_frames - new_good - new_turtle - new_down

        # 判斷 dominant_posture
        counts = {"良好": new_good, "烏龜頸": new_turtle, "低頭": new_down, "駝背": new_slouch}
        new_dominant = max(counts, key=counts.get)

        new_ratio_json = json.dumps({
            "good": round(good_pct, 1),
            "turtle": round(turtle_pct, 1),
            "down": round(down_pct, 1),
            "slouch": round(slouch_pct, 1)
        })

        # 3. 透過 session_id 直接原地 UPDATE，絕不刪除任何資料
        update_sql = '''
            UPDATE monitoring_sessions
            SET good_frames = ?,
                turtle_frames = ?,
                down_frames = ?,
                slouch_frames = ?,
                dominant_posture = ?,
                posture_ratio = ?
            WHERE session_id = ?
        '''
        execute_db(update_sql, (
            new_good, new_turtle, new_down, new_slouch, 
            new_dominant, new_ratio_json, session_id
        ))
        print(f"✅ 已成功原地修改 {start_t} 紀錄：烏龜頸變為 {turtle_pct}%")

    print("\n🎉 更新完畢！原先的 9/23、10/04 等真實資料毫髮無傷。")

if __name__ == "__main__":
    update_only_demo_sessions_to_improvement(user_id=1)