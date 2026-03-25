import os

import cv2
import psutil
from IPython.external.qt_for_kernel import QtCore
from PyQt5.QtCore import QDateTime, Qt, QTimer
from PyQt5.QtGui import QIcon, QImage, QPixmap
from PyQt5.QtWidgets import QColorDialog, QDesktopWidget

from app_controllers.utils import camera_helper
from app_views.fullscreen_view import FullscreenView
from app_views.threads.worker_thread_frame import WorkerThreadFrame
from app_views.threads.worker_thread_pause_screen import WorkerThreadPauseScreen


class Controller:
    def __init__(self, model, view):
        super().__init__()
        self.model = model
        self.view = view
        model.fullscreen_window = FullscreenView()
        model.fullscreen_window.fullscreen_closed.connect(lambda: Controller.on_fullscreen_closed(model))
        view.timer_statusbar_idle = QTimer()
        view.timer_statusbar_idle.start(2000)
        view.timer_statusbar_idle.timeout.connect(lambda: self.check_idle_time(view, model))
        view.status_bar.messageChanged.connect(lambda: self.update_last_update_time(model))
        self.set_start_button_visibility(view, model)

    @staticmethod
    def show_about_view(view):
        view.view_about.show()

    @staticmethod
    def show_fullscreen(model):
        model.is_fullscreen = True
        model.fullscreen_window.showFullScreen()

    @staticmethod
    def on_fullscreen_closed(model):
        model.is_fullscreen = False

    @staticmethod
    def on_button_pressed(button, path):
        button.setIcon(QIcon(path))

    @staticmethod
    def on_button_released(button, path):
        button.setIcon(QIcon(path))

    @staticmethod
    def update_last_update_time(model):
        model.last_update_time = QDateTime.currentDateTime()

    @staticmethod
    def check_idle_time(view, model):
        if view.status_bar.currentMessage() == "Idle":
            return
        current_time = QDateTime.currentDateTime()
        if model.last_update_time.msecsTo(current_time) >= 2000:
            view.status_bar.showMessage('Idle')

    # update color for frame and buttons
    @staticmethod
    def show_color_picker(model, id, button):
        """
        Shows the color picker menu

        Args:
            button: The button which the color is applied.
            view:
        """
        color = QColorDialog.getColor()
        if color.isValid():
            # update the color tuple with the new RGB values
            color_tuple = (color.red(), color.green(), color.blue())
            # set the background color of the button using stylesheet
            button.setStyleSheet(f'background-color: rgb({color.red()}, {color.green()}, {color.blue()});border: none')
            # update the original color tuple with the new RGB values
            if id == 'color_box':
                model.box_color = color_tuple
            elif id == 'color_class':
                model.text_color_class = color_tuple
            elif id == 'color_conf':
                model.text_color_conf = color_tuple
            elif id == 'color_bg':
                model.text_color_bg = color_tuple

    # on timeout stop button
    @staticmethod
    def timer_timeout_stop(view):
        """
        Stops the timeout timer
        """
        # stop timer and toggle button state
        view.timer_stop.stop()
        if not view.button_stop.isEnabled():
            view.button_refresh.setEnabled(True)
            view.button_start.setEnabled(True)
            view.combobox_camera_list.setEnabled(True)

    # on timeout start button
    @staticmethod
    def timer_timeout_start(view):
        """
        Starts the timeout timer

        """
        # stop timer and toggle button state
        view.timer_start.stop()
        if not view.button_start.isEnabled():
            view.button_stop.setEnabled(True)

    # update combobox items with current available cameras
    @staticmethod
    def on_combobox_camera_list_changed(view, model):
        view.combobox_camera_list.setEnabled(False)
        view.button_start.setEnabled(False)
        view.button_stop.setEnabled(False)
        view.button_refresh.setEnabled(False)
        # workaround to process the stack otherwise it will ignore the statements above
        QtCore.QCoreApplication.processEvents()
        Controller.set_start_button_visibility(view, model)

    @staticmethod
    def set_start_button_visibility(view, model):
        if camera_helper.is_camera_connected():
            Controller.update_combobox_camera_list_items(view, model)
            view.button_start.setEnabled(True)
            view.combobox_camera_list.setEnabled(True)
        else:
            view.button_start.setEnabled(False)
            view.combobox_camera_list.setEnabled(False)
        view.button_stop.setEnabled(False)

    # update combobox items
    @staticmethod
    def update_combobox_camera_list_items(view, model):
        view.button_start.setEnabled(False)
        view.button_refresh.setEnabled(False)
        view.combobox_camera_list.setEnabled(False)
        view.status_bar.showMessage('Updating camera list..')
        QtCore.QCoreApplication.processEvents()
        view.combobox_camera_list.currentTextChanged.disconnect()
        text = view.combobox_camera_list.currentText()
        model.camera_mapping = camera_helper.get_camera_mapping(camera_helper.get_connected_camera_alias(),
                                                                camera_helper.get_connected_camera_ids())
        view.combobox_camera_list.clear()
        view.combobox_camera_list.addItems(model.camera_mapping.keys())
        index = view.combobox_camera_list.findText(text, QtCore.Qt.MatchFixedString)
        if index >= 0:
            view.combobox_camera_list.setCurrentIndex(index)
        view.combobox_camera_list.currentTextChanged.connect(
            lambda: Controller.on_combobox_camera_list_changed(view, model))
        view.button_refresh.setEnabled(True)
        view.button_start.setEnabled(True)
        view.combobox_camera_list.setEnabled(True)

    # update memory and cpu usage in statusbar
    @staticmethod
    def update_system_resource(model, view):
        model.memory_usage = psutil.Process(os.getpid()).memory_info().rss / 1024 ** 2
        view.label_memory_usage.setText('Memory: {:.0f} MB'.format(model.memory_usage))
        model.cpu_usage = psutil.cpu_percent(interval=None, percpu=False)
        view.label_cpu_usage.setText('CPU: {:.0f} %'.format(model.cpu_usage))

    @staticmethod
    def update_slider_text(control, label):
        """
        Updates the text of the QLabel besides the slider

        Args:
            control: the control object to read from.
            label: the label to be updated.
        """
        label.setText(str(control.value()) + '%')

    @staticmethod
    def center_window(view):
        """
        Centers the main window

        """
        qr = view.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        view.move(qr.topLeft())

    @staticmethod
    def draw_border(label, size, color):
        label.setStyleSheet('border: {}px solid {};background-color: black;'.format(size, color))

    @staticmethod
    def set_bbox_mode(view, model):
        if view.checkbox_switch_bbox_mode.isChecked():
            model.bbox_mode = 1
        else:
            model.bbox_mode = 0

    # show or hide debug features
    @staticmethod
    def set_debug_mode(view):
        if view.checkbox_enable_debug.isChecked():
            view.label_fps.setHidden(False)
            view.label_class_info.setHidden(False)
            view.label_conf.setHidden(False)
            view.label_dim.setHidden(False)
            view.label_memory_usage.setHidden(False)
            view.label_cpu_usage.setHidden(False)
        else:
            view.label_fps.setHidden(True)
            view.label_class_info.setHidden(True)
            view.label_conf.setHidden(True)
            view.label_dim.setHidden(True)
            view.label_memory_usage.setHidden(True)
            view.label_cpu_usage.setHidden(True)

    @staticmethod
    def start_worker_thread_camera(view, model):
        current_item = view.combobox_camera_list.currentText()
        model.work_thread_camera = WorkerThreadFrame(model, view)
        model.work_thread_camera.update_camera.connect(Controller.draw_frame)
        model.work_thread_camera.start()

    @staticmethod
    def stop_worker_thread_pause_screen(model):
        model.worker_thread_pause_screen.stop()

    # stop camera worker thread
    @staticmethod
    def stop_worker_thread_camera(model):
        if model.work_thread_camera is not None:
            model.work_thread_camera.stop()
            model.work_thread_camera.wait()
            model.work_thread_camera = None
        if model.camera is not None:
            model.camera.release()
            model.camera = None
        cv2.destroyAllWindows()
        model.flag_is_camera_thread_running = False

    @staticmethod
    def on_button_start_clicked(view, model):
        model.flag_is_camera_thread_running = True
        # disable gui elements
        view.label_stream.setHidden(False)
        view.button_start.setEnabled(False)
        view.button_refresh.setEnabled(False)
        view.combobox_camera_list.setEnabled(False)
        # start timer
        view.timer_start.start(2000)
        # set current text from cbox

        # start worker thread
        Controller.start_worker_thread_camera(view, model)
        # stop worker thread
        Controller.stop_worker_thread_pause_screen(model)
        view.label_no_camera.setHidden(True)

    @staticmethod
    def on_button_stop_clicked(view, model):
        view.status_bar.showMessage('Stream stopped..')
        # enable gui elements
        view.label_no_camera.setHidden(False)
        view.label_stream.setHidden(True)
        view.button_stop.setEnabled(False)
        model.frame_rotation = 0
        model.frame_orientation_vertical = 0
        model.frame_orientation_horizontal = 0
        view.slider_brightness.setValue(100)
        view.slider_contrast.setValue(100)
        QtCore.QCoreApplication.processEvents()
        view.timer_stop.start(2000)
        # stop camera thread
        Controller.stop_worker_thread_camera(model)
        Controller.start_worker_thread_pause_screen(model, view)

   
    @staticmethod
    def draw_frame(model, view, img, fps, results):
        if model.flag_is_camera_thread_running:
            view.status_bar.showMessage('Getting camera stream..')
            
        frame = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        height, width = frame.shape[:2]
        
        is_good_posture = True 
        
        if results is not None and len(results[0].boxes) > 0:
            # 拿取座標與角度
            keypoints_dict, angle = model.inference_model.get_results(results)
            
            if keypoints_dict is not None and angle is not None:
                # 角度小於150就偵錯
                is_good_posture = angle >= 150
                Controller.draw_skeleton_and_angle(frame, keypoints_dict, angle, is_good_posture)

        ### 把畫面轉換成PyQt可以顯示的格式(現作廢)
        """
        bytes_per_line = 3 * width
        q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        if model.flag_is_camera_thread_running:
            Controller.update_statusbar(view, height, width, fps, None, None)
        else:
            Controller.update_statusbar(view)
            
        if model.is_fullscreen:
            model.fullscreen_window.set_central_widget_content(pixmap)
        else:
            pixmap = pixmap.scaled(view.label_stream.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.SmoothTransformation)
            view.label_stream.setPixmap(pixmap)
        view.label_stream.update()
        """

    # 畫出骨架連線與角度
    @staticmethod
    def draw_skeleton_and_angle(frame, keypoints_dict, angle, is_good_posture):
        ear = keypoints_dict['ear']
        shoulder = keypoints_dict['shoulder']
        hip = keypoints_dict['hip']

        # 取得畫面的長寬
        height, width = frame.shape[:2]
        
        # 決定邊框顏色(好:綠色, 壞:紅色)
        border_color_cv = (0, 255, 0) if is_good_posture else (0, 0, 255)
        
        # 畫上滿版的邊框(厚度為 8)
        cv2.rectangle(frame, (0, 0), (width-1, height-1), border_color_cv, 8)

        # 頸椎線與脊椎線(黃)
        cv2.line(frame, ear, shoulder, (0, 255, 255), 2) 
        cv2.line(frame, shoulder, hip, (0, 255, 255), 2)

        # 關節點(藍)
        for pt in [ear, shoulder, hip]:
            cv2.circle(frame, pt, 6, (255, 0, 0), -1)

        # 寫出角度(好:綠色, 壞:紅色) 
        text_color = (0, 255, 0) if is_good_posture else (0, 0, 255)
        cv2.putText(frame, f"Angle: {angle} deg", (shoulder[0] + 15, shoulder[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2, cv2.LINE_AA)
        
        # 如果坐姿不良，在畫面上給出提示 (之後改具體調整建議)
        if not is_good_posture:
            cv2.putText(frame, "Warning: Adjust Posture!", (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3, cv2.LINE_AA)

    # update the statusbar while streaming
    @staticmethod
    def update_statusbar(view, height=None, width=None, fps=None, class_name=None, confidence=None):
        # update image size label
        if (height is None) & (width is None):
            view.label_dim.setText("Image size: -")
        else:
            view.label_dim.setText("Image size: " + str(width) + "x" + str(height))
        # update fps label
        if fps is None:
            view.label_fps.setText("FPS: 0.00")
        else:
            view.label_fps.setText("FPS: {:.2f}".format(fps))
        # update detected class
        if class_name is None:
            view.label_class_info.setText("Class: -")
        elif class_name == 0:
            view.label_class_info.setText("Class: 0")
        else:
            view.label_class_info.setText("Class: 1")
        # update confidence
        if confidence is None:
            view.label_conf.setText('Confidence: 0.00')
        else:
            view.label_conf.setText('Confidence: {:.2f}'.format(confidence))

    # start camera worker thread
    @staticmethod
    def start_worker_thread_pause_screen(model, view):
        model.worker_thread_pause_screen = None
        model.worker_thread_pause_screen = WorkerThreadPauseScreen(view, view.label_stream_width,
                                                                   view.label_stream_height)
        model.worker_thread_pause_screen.update_pause_screen.connect(Controller.update_pause_frame)
        model.worker_thread_pause_screen.start()

    @staticmethod
    def update_pause_frame(view, pixmap):
        view.label_no_camera.adjustSize()
        view.label_no_camera.setPixmap(pixmap)
        view.label_no_camera.update()

    @staticmethod
    def update_frame_rotation_degrees(model):
        if model.frame_rotation == 270:
            model.frame_rotation = 0
        else:
            model.frame_rotation += 90

    @staticmethod
    def update_frame_flip_vertical(model):
        if model.frame_orientation_vertical == 0:
            model.frame_orientation_vertical = 1
        else:
            model.frame_orientation_vertical = 0

    @staticmethod
    def update_frame_flip_horizontal(model):
        if model.frame_orientation_horizontal == 0:
            model.frame_orientation_horizontal = 1
        else:
            model.frame_orientation_horizontal = 0
