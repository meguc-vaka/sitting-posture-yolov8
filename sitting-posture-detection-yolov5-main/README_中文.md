# 基於 YOLOv5 的即時側向坐姿檢測

<div align="center">
  <img src="https://raw.githubusercontent.com/itakurah/SittingPostureDetection/main/data/images/posture.webp" width="80%" height="80%" alt="Sitting Posture"> 

  *Source: https://www.youtube.com/watch?v=HNgTLml_Zi4*
</div>


本倉庫提供了一個使用 [YOLOv5](https://github.com/ultralytics/yolov5)（一種尖端的物件偵測演算法）進行 **即時坐姿檢測** 的開源解決方案。該程式旨在分析使用者的坐姿，並針對其是否符合人體工學最佳實踐提供回饋，旨在促進更健康的坐姿習慣。

## 主要功能

* **YOLOv5**: 該程式利用 [YOLOv5]的強大功能（這是一種物件偵測演算法），從網路攝影機準確偵測使用者的坐姿。
* **即時坐姿檢測**: 該程式提供使用者坐姿的即時回饋，使其適用於辦公室人體工學、健身和健康監測等應用。
* **良好與不良坐姿分類**: 該程式使用預訓練模型將偵測到的姿勢分類為良好 (good) 或不良 (bad)，使使用者能夠改善坐姿，並預防與不良坐姿相關的潛在健康問題。
* **開源**: 以開源授權條款發佈，允許使用者存取、修改並為專案做出貢獻。


---

### 開發工具

![Python]

## IEEE 國際會議論文發表

我們很高興地宣布，該專案已發表於一篇 IEEE 研討會論文中，該論文全面介紹了我們應用 YOLOv5 進行側向坐姿偵測的方法論、技術途徑和結果。這篇標題為 **"Lateral Sitting Posture Detection using YOLOv5"** 的論文發表於 2024 年 IEEE 生物機器人與生物機電整合國際會議 (BioRob)。如需更多深入資訊，請參閱發表於 Xplore 上的全文：

**[在 Xplore 上閱讀 IEEE 發表論文](https://doi.org/10.1109/BioRob60516.2024.10719953)**

# 開始使用

### 前提條件

* Python 3.9.X

### 安裝步驟  
如果您擁有 NVIDIA 圖形處理器 (GPU)，可以透過安裝 GPU 需求文件來啟動 GPU 加速。請注意，若無 GPU 加速，推理將在 CPU 上執行，速度可能會非常緩慢。  
#### Windows  
  
1. `git clone https://github.com/itakurah/sitting-posture-detection-yolov5.git`  
2. `python -m venv venv`  
3. `.\venv\scripts\activate.bat`  
##### 預設/NVIDIA GPU 支援:  
4.  `pip install -r ./requirements_windows.txt` **OR** `pip install -r ./requirements_windows_gpu.txt`

#### Linux  
  
1. `git clone https://github.com/itakurah/sitting-posture-detection-yolov5.git`  
2. `python3 -m venv venv`  
3. `source venv/bin/activate`
##### 預設/NVIDIA GPU 支援::  
4. `pip3 install -r requirements_linux.txt` **或** `pip3 install -r requirements_linux_gpu.txt`


### 執行程式

`python application.py <optional: model_file.pt>` **或** `python3 application.py <optional: model_file.pt>`

若未指定模型檔案，則載入預設模型。

# 模型資訊
本專案使用自定義訓練的 [YOLOv5s](https://github.com/ultralytics/yolov5/blob/79af1144c270ac7169553d450b9170f9c60f92e4/models/yolov5s.yaml) 模型
該模型在每個類別 160 張影像上進行了 146 個輪次 (epochs) 的微調。它將姿勢分為兩個類別：
* `sitting_good`
* `sitting_bad`

訓練好的模型檔案位於以下目錄:
`data/inference_models/small640.pt`
# 架構
該模型使用的架構是標準的 YOLOv5s 架構：

<img src="https://raw.githubusercontent.com/itakurah/SittingPostureDetection/main/data/images/architecture.png" width=75% height=75%>



*圖 1: YOLOv5s 網絡架構 (基於 Liu 等人)。CBS 模組由卷積層 (Convolutional)、批次歸一化層 (Batch Normalization) 和 Sigmoid 線性單元 (SiLU) 啟動函數組成。C3 模組由三個 CBS 模組和一個瓶頸區塊 (bottleneck block) 組成。SPPF 模組由兩個 CBS 模組和三個最大池化層 (Max Pooling layers) 組成。*

# Model Results
驗證集包含 80 張影像 (40 張 sitting_good, 40 張 sitting_bad)。結果如下：
|Class|Images|Instances|Precision|Recall|mAP50|mAP50-95|
|--|--|--|--|--|--|--|
|all| 80 | 80 | 0.87 | 0.939 | 0.931 | 0.734 |
|sitting_good| 40 |  40| 0.884 | 0.954 | 0.908 |0.744  |
|sitting_bad| 80 | 40 | 0.855 | 0.925 | 0.953 | 0.724 |

F1、精確率 (Precision)、召回率 (Recall) 和精確率-召回率 (PR) 曲線圖：

<p align="middle">
<img src="https://raw.githubusercontent.com/itakurah/SittingPostureDetection/main/data/images/F1_curve.png" width=40% height=40%>
<img src="https://raw.githubusercontent.com/itakurah/SittingPostureDetection/main/data/images/P_curve.png" width=40% height=40%>
<img src="https://raw.githubusercontent.com/itakurah/SittingPostureDetection/main/data/images/R_curve.png" width=40% height=40%>
<img src="https://raw.githubusercontent.com/itakurah/SittingPostureDetection/main/data/images/PR_curve.png" width=40% height=40%>
</p>

# About

本專案由 [Niklas Hoefflin](https://github.com/itakurah)、[Tim Spulak](https://github.com/T-Lak)、Pascal Gerber 和 Jan Bösch 開發。由 [André Jeworutzki](https://github.com/AndreJeworutzki) 和 Jan Schwarzer 指導，作為漢堡應用科學大學 (HAW Hamburg) [Train Like A Machine](https://csti.haw-hamburg.de/project/TLAM/) 課程模組的一部分。
該專案目前由 Niklas Hoefflin 和 Tim Spulak 維護。

# 來源

 - Jocher, G. (2020). YOLOv5 by Ultralytics (Version 7.0). https://doi.org/10.5281/zenodo.3908559
 - Fig. 1: H. Liu, F. Sun, J. Gu, and L. Deng, “Sf-yolov5: A lightweight small
object detection algorithm based on improved feature fusion mode,”
Sensors (Basel, Switzerland), vol. 22, no. 15, pp. 1–14, 2022. https://doi.org/10.3390/s22155817

# 授權條款

This project is licensed under the MIT License. See the LICENSE file for details.

<!-- 本專案採用 MIT 授權條款。詳情請參閱 LICENSE 檔案。 -->

[Python]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
