// 取得 HTML 元素
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const confirmStartBtn = document.getElementById('confirmStartBtn');
const durationSelect = document.getElementById('durationSelect');
const durationModal = document.getElementById('durationModal');

const videoImg = document.getElementById('videoStream');
const placeholder = document.getElementById('placeholder');
const cameraSelect = document.getElementById('cameraSelect');

const socket = io(); // 啟動 Socket.IO 連線
let sedentaryTimer = null; 
let sessionTimeout = null; // 本次監測設定的倒數計時器
const SEDENTARY_TIME_MS = 90 * 60 * 1000; 

let isWaitingForServer = false;

// 捕捉本地攝影機畫面的隱藏元件
let videoElement = document.createElement('video');
videoElement.autoplay = true;
videoElement.muted = true;
videoElement.playsInline = true;

let canvasElement = document.createElement('canvas');
let ctx = canvasElement.getContext('2d');
let stream = null;
let sendFrameInterval = null;

// === 核心：啟動監測流程 ===
async function startMonitoring(selectedMinutes) {
    placeholder.style.display = "none";
    videoImg.style.display = "block";

    try {
        // 1. 請求開啟攝影機
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        videoElement.srcObject = stream;

        // 2. 攝影機準備完成後開始串流截圖
        videoElement.onloadedmetadata = () => {
            videoElement.play();
            
            // 縮小解析度減輕傳輸負擔
            canvasElement.width = 640;
            canvasElement.height = 480;
            
            sendFrameInterval = setInterval(() => {
                if (videoElement.readyState >= 2 && !isWaitingForServer) { 
                    isWaitingForServer = true; // 等待伺服器回應

                    ctx.drawImage(videoElement, 0, 0, canvasElement.width, canvasElement.height);
                    let imageData = canvasElement.toDataURL('image/jpeg', 0.6); 
                    socket.emit('video_frame', imageData); 
                }
            }, 100);
        };

        // 3. 啟動久坐計時器
        if (sedentaryTimer) clearInterval(sedentaryTimer);
        sedentaryTimer = setInterval(() => {
            document.getElementById('aiMessageText').innerText = "您已經坐了一個半小時囉！建議您起身喝口水、伸展一下筋骨，保護腰椎與眼睛！";
            document.querySelector('.ai-prompt-box strong').innerText = "⏰ 貼心久坐提醒";
            document.querySelector('.ai-prompt-box strong').className = "d-block mb-1 text-info";
            
            appendLogItem("久坐提醒", "已連續監測 1.5 小時，請起身活動！", "#0dcaf0", "text-info");
        }, SEDENTARY_TIME_MS);

        // 4. 設定監測時間限制 (若選擇 0 代表無限制手動關閉)
        if (sessionTimeout) clearTimeout(sessionTimeout);
        if (selectedMinutes > 0) {
            const durationMs = selectedMinutes * 60 * 1000;
            sessionTimeout = setTimeout(() => {
                stopBtn.click(); // 自動觸發停止
                alert(`⏱️ ${selectedMinutes} 分鐘監測時間已到！記得起身放鬆一下。`);
            }, durationMs);
        }

    } catch (err) {
        alert("無法存取攝影機！請確認您已允許瀏覽器使用鏡頭權限。\n錯誤：" + err.message);
        placeholder.style.display = "flex";
        videoImg.style.display = "none";
    }
}

// === Modal 確認開始按鈕點擊 ===
confirmStartBtn.addEventListener('click', function() {
    const selectedMinutes = parseInt(durationSelect.value, 10);
    
    // 強制清除 modal 殘留
    const modalInstance = bootstrap.Modal.getInstance(durationModal);
    if (modalInstance) {
        modalInstance.hide();
        modalInstance.dispose();
    }
    document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
    document.body.classList.remove('modal-open');
    document.body.style.overflow = '';
    document.body.style.paddingRight = '';
    document.documentElement.style.overflow = '';
    
    // 通知後端開始監測
    socket.emit('start_monitoring', { duration: selectedMinutes });
    
    startMonitoring(selectedMinutes);
});

// === 暫停按鈕 ===
stopBtn.onclick = function() {
    videoImg.style.display = "none";
    placeholder.style.display = "flex";

    // 通知後端停止監測
    socket.emit('stop_monitoring');
    
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }
    if (sendFrameInterval) {
        clearInterval(sendFrameInterval);
        sendFrameInterval = null;
    }
    if (sedentaryTimer) {
        clearInterval(sedentaryTimer);
        sedentaryTimer = null;
    }
    if (sessionTimeout) {
        clearTimeout(sessionTimeout);
        sessionTimeout = null;
    }
};

// === 輔助函式：新增動態紀錄 ===
function appendLogItem(title, content, borderColor, textClass) {
    const logContainer = document.getElementById('logContainer');
    const now = new Date();
    const timeString = now.getHours().toString().padStart(2, '0') + ':' + 
                       now.getMinutes().toString().padStart(2, '0') + ':' + 
                       now.getSeconds().toString().padStart(2, '0');
                       
    const newLog = document.createElement('div');
    newLog.className = "alert-item";
    newLog.style.borderLeftColor = borderColor;
    newLog.innerHTML = `
        <div class="d-flex w-100 justify-content-between">
            <strong class="${textClass}">${title}</strong>
            <small class="text-white-50">${timeString}</small>
        </div>
        <p class="mb-0 small text-white-50">${content}</p>
    `;
    logContainer.insertBefore(newLog, logContainer.firstChild);
}

// === 接收後端繪製好的骨架畫面 ===
socket.on('processed_frame', function(imgData) {
    videoImg.src = imgData;
    isWaitingForServer = false;
});

// === 接收後端 AI 姿勢警示 ===
socket.on('ai_alert', function(data) {
    document.getElementById('aiMessageText').innerText = data.message;
    document.querySelector('.ai-prompt-box strong').innerText = "⚠️ 偵測到不良姿勢";
    document.querySelector('.ai-prompt-box strong').className = "d-block mb-1 text-warning";
    
    appendLogItem("姿勢警告", `${data.message.substring(0, 20)}...`, "#f59e0b", "text-warning");
});