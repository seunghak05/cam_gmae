import sys
import cv2
import numpy as np
import os
import random
import math
from datetime import datetime

from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QHBoxLayout, QSlider, QColorDialog
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor

# --- 설정값 ---
CAM_ID = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

if not os.path.exists('captures'):
    os.makedirs('captures')

class CameraThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)
    
    def __init__(self):
        super().__init__()
        self._run_flag = True
    
    def run(self):
        cap = cv2.VideoCapture(CAM_ID, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print(f"오류: 카메라 ID {CAM_ID}를 열 수 없습니다.")
            return
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        
        while self._run_flag:
            ret, cv_img = cap.read()
            if ret:
                self.change_pixmap_signal.emit(cv2.flip(cv_img, 1))
        
        cap.release()
    
    def stop(self):
        self._run_flag = False
        self.wait()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("피하기 게임")
        self.setGeometry(100, 100, FRAME_WIDTH + 50, FRAME_HEIGHT + 150)
        
        # 심플한 스타일 설정
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: white;
            }
            QLabel {
                color: white;
                font-family: Arial, sans-serif;
            }
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666;
                border-radius: 5px;
                color: white;
                font-size: 12px;
                padding: 8px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
        """)

        self.current_frame = None
        self.is_game_running = False
        self.is_fullscreen = False
        self.capture_timer = None
        self.current_speed = 5.0  # 기본 속도
        
        # 사각형 색상 설정 (BGR 형식)
        self.rectangle_color = (255, 255, 0)  # 기본: 밝은 노란색
        
        # 부드러운 움직임을 위한 상태 변수
        self.roi_pos = [FRAME_WIDTH / 2, FRAME_HEIGHT / 2]
        self.roi_size = [150, 150]
        self.roi_target_pos = [FRAME_WIDTH / 2, FRAME_HEIGHT / 2]
        self.roi_target_size = [150, 150]
        self.roi_speed = self.current_speed
        self.current_roi_coords = None
        self.animation_frame = 0
        
        self.ROI_SHORT_SIDE_RANGE = (80, 150)
        self.ROI_LONG_SIDE_RANGE = (300, 500)

        self.setup_ui()

        # 부드러운 움직임을 위한 타이머
        self.smooth_move_timer = QTimer(self)
        self.smooth_move_timer.timeout.connect(self.update_movement)

        self.thread = CameraThread()
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.start()

    def setup_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 카메라 화면 (더 많은 공간 할당)
        self.image_label = QLabel(self)
        self.image_label.setMinimumSize(FRAME_WIDTH, FRAME_HEIGHT)  # 최소 크기만 설정
        self.image_label.setStyleSheet("""
            background-color: #1a1a1a;
            border: 2px solid #555;
            border-radius: 5px;
        """)
        self.image_label.setAlignment(Qt.AlignCenter)
        # 스트레치 팩터를 크게 설정하여 더 많은 공간 할당
        main_layout.addWidget(self.image_label, stretch=3)
        
        # 캡처된 이미지 표시 (숨김 상태로 시작)
        self.captured_image_label = QLabel(self)
        self.captured_image_label.setMinimumSize(FRAME_WIDTH, FRAME_HEIGHT)  # 최소 크기만 설정
        self.captured_image_label.setStyleSheet("""
            background-color: #1a1a1a;
            border: 2px solid #ff4444;
            border-radius: 5px;
        """)
        self.captured_image_label.setAlignment(Qt.AlignCenter)
        self.captured_image_label.setHidden(True)
        main_layout.addWidget(self.captured_image_label, stretch=3)
        
        # 하단 컨트롤 영역을 별도 레이아웃으로 구성
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setSpacing(10)
        controls_layout.setContentsMargins(0, 10, 0, 0)
        
        # 속도 조절 슬라이더
        speed_layout = QHBoxLayout()
        speed_label = QLabel("속도:", self)
        speed_label.setStyleSheet("color: #ccc; font-size: 12px;")
        speed_layout.addWidget(speed_label)
        
        self.speed_slider = QSlider(Qt.Horizontal, self)
        self.speed_slider.setRange(1, 15)  # 1.0 ~ 15.0 속도
        self.speed_slider.setValue(int(self.current_speed))
        self.speed_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #555;
                height: 6px;
                background: #3a3a3a;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0099ff;
                border: 1px solid #0077cc;
                width: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #33aaff;
            }
        """)
        self.speed_slider.valueChanged.connect(self.update_speed)
        speed_layout.addWidget(self.speed_slider)
        
        self.speed_value_label = QLabel(f"{self.current_speed:.1f}", self)
        self.speed_value_label.setStyleSheet("color: #0099ff; font-size: 12px; font-weight: bold;")
        self.speed_value_label.setMinimumWidth(30)
        speed_layout.addWidget(self.speed_value_label)
        
        controls_layout.addLayout(speed_layout)
        
        # 색상 선택 버튼
        color_layout = QHBoxLayout()
        color_label = QLabel("사각형 색상:", self)
        color_label.setStyleSheet("color: #ccc; font-size: 12px;")
        color_layout.addWidget(color_label)
        
        self.color_button = QPushButton("색상 선택", self)
        self.color_button.setStyleSheet(f"""
            QPushButton {{
                background-color: rgb(255, 255, 0);
                border: 2px solid #666;
                border-radius: 5px;
                color: black;
                font-size: 11px;
                font-weight: bold;
                padding: 5px 10px;
                min-height: 25px;
            }}
            QPushButton:hover {{
                border: 2px solid #888;
            }}
        """)
        self.color_button.clicked.connect(self.choose_color)
        color_layout.addWidget(self.color_button)
        
        color_layout.addStretch()  # 오른쪽에 여백 추가
        controls_layout.addLayout(color_layout)
        
        # 상태 메시지
        self.status_label = QLabel("게임을 시작하려면 '시작' 버튼을 누르세요", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        status_font = QFont('Arial', 12)
        self.status_label.setFont(status_font)
        self.status_label.setStyleSheet("""
            color: #ccc;
            background-color: #3a3a3a;
            border: 1px solid #555;
            border-radius: 5px;
            padding: 10px;
            max-height: 50px;
        """)
        controls_layout.addWidget(self.status_label)
        
        # 버튼들
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # 시작/정지 버튼
        self.btn_start = QPushButton("시작", self)
        self.btn_start.clicked.connect(self.toggle_game)
        button_layout.addWidget(self.btn_start)
        
        # 다음 라운드 버튼 (숨김 상태로 시작)
        self.btn_next_round = QPushButton("다음 라운드", self)
        self.btn_next_round.clicked.connect(self.next_round)
        self.btn_next_round.setHidden(True)
        button_layout.addWidget(self.btn_next_round)
        
        # 전체화면 버튼
        self.btn_fullscreen = QPushButton("전체화면", self)
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        button_layout.addWidget(self.btn_fullscreen)
        
        # 종료 버튼
        self.btn_quit = QPushButton("종료", self)
        self.btn_quit.clicked.connect(self.close)
        button_layout.addWidget(self.btn_quit)
        
        controls_layout.addLayout(button_layout)
        
        # 컨트롤 영역을 메인 레이아웃에 추가 (고정 크기)
        main_layout.addWidget(controls_widget, stretch=0)

    def toggle_fullscreen(self):
        """전체화면 모드 전환"""
        if self.is_fullscreen:
            self.showNormal()
            self.btn_fullscreen.setText("전체화면")
            # 폰트 크기 원래대로
            status_font = QFont('Arial', 12)
            self.status_label.setFont(status_font)
        else:
            self.showFullScreen()
            self.btn_fullscreen.setText("창모드")
            # 전체화면에서는 폰트를 좀 더 크게
            status_font = QFont('Arial', 16)
            self.status_label.setFont(status_font)
        
        self.is_fullscreen = not self.is_fullscreen

    def keyPressEvent(self, event):
        """키보드 이벤트 처리"""
        if event.key() == Qt.Key_Escape:
            if self.is_fullscreen:
                self.toggle_fullscreen()
        elif event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key_Space:
            self.toggle_game()
        super().keyPressEvent(event)

    def choose_color(self):
        """색상 선택 다이얼로그를 열고 사각형 색상을 변경합니다."""
        # 현재 색상을 QColor로 변환 (BGR -> RGB)
        current_color = QColor(self.rectangle_color[2], self.rectangle_color[1], self.rectangle_color[0])
        
        # 색상 선택 다이얼로그 열기
        color = QColorDialog.getColor(current_color, self, "사각형 색상 선택")
        
        if color.isValid():
            # RGB를 BGR로 변환하여 저장 (OpenCV는 BGR 형식 사용)
            self.rectangle_color = (color.blue(), color.green(), color.red())
            
            # 버튼 색상 업데이트
            self.color_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgb({color.red()}, {color.green()}, {color.blue()});
                    border: 2px solid #666;
                    border-radius: 5px;
                    color: {'white' if color.red() + color.green() + color.blue() < 384 else 'black'};
                    font-size: 11px;
                    font-weight: bold;
                    padding: 5px 10px;
                    min-height: 25px;
                }}
                QPushButton:hover {{
                    border: 2px solid #888;
                }}
            """)

    def update_speed(self, value):
        """속도 슬라이더 값이 변경되었을 때 호출"""
        self.current_speed = float(value)
        self.roi_speed = self.current_speed
        self.speed_value_label.setText(f"{self.current_speed:.1f}")

    def get_level_settings(self):
        """현재 레벨에 따른 설정값 반환"""
        settings = {
            1: {'speed': 3.0, 'delay': (4000, 7000), 'size_change': 0.03},
            2: {'speed': 4.5, 'delay': (3500, 6000), 'size_change': 0.04},
            3: {'speed': 6.0, 'delay': (3000, 5500), 'size_change': 0.05},
            4: {'speed': 7.5, 'delay': (2500, 5000), 'size_change': 0.06},
            5: {'speed': 9.0, 'delay': (2000, 4500), 'size_change': 0.08},
        }
        
        # 레벨 5 이후는 계속 최고 난이도 유지
        if self.game_level > 5:
            return settings[5]
        
        return settings.get(self.game_level, settings[1])
    def set_new_roi_target(self):
        """새로운 목표 지점을 설정합니다."""
        # 카메라 원본 해상도 기준으로 계산 (640x480)
        cam_width = FRAME_WIDTH
        cam_height = FRAME_HEIGHT
        
        is_wide = random.choice([True, False])
        if is_wide:
            self.roi_target_size = [
                random.randint(200, 400), 
                random.randint(80, 150)
            ]
        else:
            self.roi_target_size = [
                random.randint(80, 150), 
                random.randint(200, 400)
            ]
        
        # 카메라 화면 범위를 벗어나지 않도록 제한
        max_x = cam_width - self.roi_target_size[0]
        max_y = cam_height - self.roi_target_size[1]
        
        # 최소값이 0보다 작으면 0으로 설정
        max_x = max(0, max_x)
        max_y = max(0, max_y)
        
        self.roi_target_pos = [
            random.randint(0, max_x), 
            random.randint(0, max_y)
        ]
        
        # 현재 속도를 슬라이더 값으로 사용
        self.roi_speed = self.current_speed

    def update_movement(self):
        """부드러운 움직임을 계산하고 적용합니다."""
        self.animation_frame += 1
        
        # 현재 슬라이더 속도 사용
        self.roi_speed = self.current_speed
        
        # 위치 이동
        dx = self.roi_target_pos[0] - self.roi_pos[0]
        dy = self.roi_target_pos[1] - self.roi_pos[1]
        dist = math.sqrt(dx**2 + dy**2)

        if dist < self.roi_speed:
            self.set_new_roi_target()
        else:
            self.roi_pos[0] += (dx / dist) * self.roi_speed
            self.roi_pos[1] += (dy / dist) * self.roi_speed

        # 크기 변경 (고정된 속도)
        dw = self.roi_target_size[0] - self.roi_size[0]
        dh = self.roi_target_size[1] - self.roi_size[1]
        self.roi_size[0] += dw * 0.05
        self.roi_size[1] += dh * 0.05

        # 최종 좌표 업데이트 (카메라 해상도 범위 내로 제한)
        x1 = int(self.roi_pos[0])
        y1 = int(self.roi_pos[1])
        x2 = int(self.roi_pos[0] + self.roi_size[0])
        y2 = int(self.roi_pos[1] + self.roi_size[1])
        
        # 카메라 화면 범위를 벗어나지 않도록 제한
        x1 = max(0, min(x1, FRAME_WIDTH))
        y1 = max(0, min(y1, FRAME_HEIGHT))
        x2 = max(0, min(x2, FRAME_WIDTH))
        y2 = max(0, min(y2, FRAME_HEIGHT))
        
        # x2, y2가 x1, y1보다 작아지지 않도록 보정
        if x2 <= x1:
            x2 = min(x1 + 50, FRAME_WIDTH)
        if y2 <= y1:
            y2 = min(y1 + 50, FRAME_HEIGHT)
        
        self.current_roi_coords = (x1, y1, x2, y2)

    def draw_simple_rectangle(self, img, coords):
        """심플한 점선 사각형을 그립니다."""
        x1, y1, x2, y2 = coords
        
        # 점선 효과
        dash_length = 20
        gap_length = 10
        total_length = dash_length + gap_length
        color = self.rectangle_color  # 사용자가 선택한 색상 사용
        thickness = 3
        
        # 상단 및 하단 라인
        for x in range(x1, x2, total_length):
            if (x - x1) // total_length % 2 == 0:
                cv2.line(img, (x, y1), (min(x + dash_length, x2), y1), color, thickness)
                cv2.line(img, (x, y2), (min(x + dash_length, x2), y2), color, thickness)
        
        # 좌측 및 우측 라인
        for y in range(y1, y2, total_length):
            if (y - y1) // total_length % 2 == 0:
                cv2.line(img, (x1, y), (x1, min(y + dash_length, y2)), color, thickness)
                cv2.line(img, (x2, y), (x2, min(y + dash_length, y2)), color, thickness)

    def toggle_game(self):
        """게임 시작/정지 토글"""
        if self.is_game_running:
            self.stop_game()
        else:
            self.start_game()

    def start_game(self):
        """게임을 시작합니다."""
        self.is_game_running = True
        self.btn_start.setText("정지")
        self.btn_next_round.setHidden(True)
        self.captured_image_label.setHidden(True)
        self.image_label.setHidden(False)
        
        self.status_label.setText(f"게임 진행 중... 속도: {self.current_speed:.1f}")
        
        # 카메라 해상도 기준으로 초기 위치 설정
        self.roi_pos = [FRAME_WIDTH / 2, FRAME_HEIGHT / 2]
        
        self.set_new_roi_target()
        self.smooth_move_timer.start(25)  # 40 FPS
        
        # 랜덤 딜레이로 캡처
        capture_delay = random.randint(2000, 6000)
        self.capture_timer = QTimer()
        self.capture_timer.timeout.connect(self.capture_moment)
        self.capture_timer.setSingleShot(True)
        self.capture_timer.start(capture_delay)

    def stop_game(self):
        """게임을 정지합니다."""
        self.is_game_running = False
        self.smooth_move_timer.stop()
        if self.capture_timer:
            self.capture_timer.stop()
        self.btn_start.setText("시작")
        self.btn_next_round.setHidden(True)
        self.captured_image_label.setHidden(True)
        self.image_label.setHidden(False)
        self.status_label.setText("게임이 정지되었습니다. '시작' 버튼을 눌러 다시 시작하세요.")

    def capture_moment(self):
        """순간을 캡처하고 결과를 표시합니다."""
        if not self.is_game_running or self.current_frame is None or self.current_roi_coords is None:
            return
        
        # 게임 정지
        self.smooth_move_timer.stop()
        
        # 사각형 영역만 잘라내기
        x1, y1, x2, y2 = self.current_roi_coords
        
        # 원본 프레임에서 사각형 영역만 추출 (텍스트 추가 없이 그대로)
        roi_frame = self.current_frame[y1:y2, x1:x2].copy()
        
        if roi_frame.size == 0:  # 빈 영역인 경우 처리
            self.next_round()
            return
        
        # 캡처된 ROI 이미지 표시 (텍스트 추가 없음)
        self.image_label.setHidden(True)
        self.captured_image_label.setHidden(False)
        qt_img = self.convert_cv_qt(roi_frame)
        
        # 캡처된 이미지를 라벨 크기에 맞게 스케일링해서 표시
        label_size = self.captured_image_label.size()
        scaled_img = qt_img.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.captured_image_label.setPixmap(scaled_img)
        
        # 상태 및 버튼 업데이트
        self.status_label.setText("캡처 완료! 사각형 영역이 찍혔습니다. 다음 라운드를 시작하세요.")
        self.btn_start.setText("시작")
        self.btn_next_round.setHidden(False)
        
        # 게임 상태 업데이트
        self.is_game_running = False

    def next_round(self):
        """다음 라운드를 시작합니다."""
        self.start_game()

    def update_image(self, cv_img):
        """이미지를 업데이트합니다."""
        self.current_frame = cv_img
        
        if self.is_game_running and self.current_roi_coords:
            self.draw_simple_rectangle(cv_img, self.current_roi_coords)
        
        qt_img = self.convert_cv_qt(cv_img)
        
        # 라이브 카메라 화면만 업데이트 (캡처된 이미지가 보이지 않을 때만)
        if not self.captured_image_label.isVisible():
            # 이미지를 라벨 크기에 맞게 스케일링해서 표시
            label_size = self.image_label.size()
            scaled_img = qt_img.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled_img)

    def convert_cv_qt(self, cv_img):
        """OpenCV 이미지를 Qt 이미지로 변환합니다."""
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        return QPixmap.fromImage(QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888))

    def closeEvent(self, event):
        """프로그램 종료 시 정리 작업을 수행합니다."""
        self.is_game_running = False
        self.smooth_move_timer.stop()
        if self.capture_timer:
            self.capture_timer.stop()
        self.thread.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec_())
