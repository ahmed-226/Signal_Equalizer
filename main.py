import csv
import sys
import tempfile
import numpy as np
import pandas as pd
import soundfile as sf
from scipy.io import wavfile
from scipy.signal import spectrogram
from matplotlib import pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import QUrl, QTimer, Qt
from PyQt5.QtGui import QPen, QColor
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QRadioButton, QPushButton,
    QComboBox, QFileDialog, QHBoxLayout, QFrame, QSlider, QLabel, QSizePolicy,
    QSpacerItem, QButtonGroup, QLineEdit, QGraphicsScene, QGraphicsLineItem
)
import pyqtgraph as pg


class SignalProcessingWithWienerFilter:
    def __init__(self, plot_widget, audio_data, sample_rate, main_app, alpha=1.0):
        """ Initialize signal processing with Wiener filter. """
        self.plot_widget = plot_widget
        self.audio_data = audio_data
        self.sample_rate = sample_rate
        self.main_app = main_app
        self.alpha = alpha
        duration = len(self.audio_data) / self.sample_rate

        self.noise_data = None
        self.noise_power = 0
        self.blue_region = None

        self.start_index = 0
        self.end_index = duration if audio_data.any() else 100

        self.pen = QPen(Qt.red)
        self.pen.setWidthF(duration / 1000)

        print("Class initialized with red lines")
        self.start_line = self.create_line(self.start_index)
        self.end_line = self.create_line(self.end_index)

        self.view_box = self.plot_widget.getPlotItem().getViewBox()
        self.view_box.addItem(self.start_line)
        self.view_box.addItem(self.end_line)

        self.start_line.sigPositionChanged.connect(self.handle_start_move)
        self.end_line.sigPositionChanged.connect(self.handle_end_move)
        self.last_start_pos = self.start_index
        self.last_end_pos = self.end_index

    def create_line(self, x_pos):
        line = pg.InfiniteLine(pos=x_pos, angle=90, pen=self.pen, movable=True)
        print(f"Line created at position: {x_pos}")
        return line

    def remove_lines(self):
        self.view_box.removeItem(self.start_line)
        self.view_box.removeItem(self.end_line)
        self.remove_blue_region()
        print("Red lines and blue region removed")

    def create_blue_region(self):
        """Create or update the faint blue region between the red lines."""
        if self.blue_region is None:

            self.blue_region = pg.LinearRegionItem(
                values=(self.start_index, self.end_index),
                brush=pg.mkBrush(QColor(0, 0, 255, 50)),
                movable=False,
            )
            self.view_box.addItem(self.blue_region)
            print(f"Blue region created between: {self.start_index} and {self.end_index}")
        else:

            self.blue_region.setRegion((self.start_index, self.end_index))
            print(f"Blue region updated to: {self.start_index} and {self.end_index}")

    def remove_blue_region(self):
        """Remove the blue region if it exists."""
        if self.blue_region is not None:
            self.view_box.removeItem(self.blue_region)
            self.blue_region = None
            print("Blue region removed")

    def handle_start_move(self):
        new_pos = self.start_line.getPos()[0]
        if abs(new_pos - self.last_start_pos) > 0.001:
            self.start_index = new_pos
            self.last_start_pos = new_pos
            print(f"Start line moved to position: {self.start_index}")
            self.create_blue_region()

    def handle_end_move(self):
        """Update end index when the end line moves."""
        new_pos = self.end_line.getPos()[0]
        if abs(new_pos - self.last_end_pos) > 0.001:
            self.end_index = new_pos
            self.last_end_pos = new_pos
            print(f"End line moved to position: {self.end_index}")
            self.create_blue_region()

    def select_noise_range(self):
        """Extract noise data from the selected range."""
        if self.audio_data is not None:
            start_idx = int(self.start_index * self.sample_rate)
            end_idx = int(self.end_index * self.sample_rate)
            noise_data = self.audio_data[start_idx:end_idx]
            print(f"Noise range selected: {start_idx} to {end_idx}")
            return noise_data

    def estimate_noise_power(self):
        noise_data = self.select_noise_range()
        if noise_data is not None and len(noise_data) > 0:
            noise_power = np.var(noise_data)
            print(f"Noise power estimated: {noise_power}")
        else:
            print("No noise data selected yet.")
            noise_power = 0
        return noise_power

    def apply_wiener_filter(self):
        """Apply a custom Wiener filter with an adjustable alpha."""
        self.create_blue_region()
        noise_power_spectrum = self.estimate_noise_power()
        if self.audio_data is not None:
            if noise_power_spectrum > 0:
                print(f"Applying Wiener filter with noise power: {noise_power_spectrum}")

                audio_fft = np.fft.fft(self.audio_data)
                power_spectrum_signal = np.abs(audio_fft) ** 2
                wiener_filter = power_spectrum_signal / (power_spectrum_signal + self.alpha * noise_power_spectrum)

                filtered_fft = wiener_filter * audio_fft

                filtered_audio = np.fft.ifft(filtered_fft).real

                self.main_app.plot_output(filtered_audio)

                fft_freq = np.fft.fftfreq(len(filtered_fft), 1 / self.sample_rate)
                positive_freqs = fft_freq[: len(fft_freq) // 2]
                magnitudes = np.abs(filtered_fft[: len(filtered_fft) // 2])
                self.main_app.freq_plot_item.setData(positive_freqs, magnitudes)

            else:
                print("Noise power not estimated. Please select a noise range first.")
        else:
            print("No audio data available to filter.")


class SignalViewer(QWidget):
    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout()
        self.plot_widget = pg.PlotWidget()
        self.media_player = QMediaPlayer()
        self.needle = pg.InfiniteLine(pos=0, angle=90, movable=False, pen="cyan")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_needle)
        self.plot_item = self.plot_widget.plot(pen=pg.mkPen(color="gray"))
        self.audio_data = None
        self.sample_rate = 0
        self.cine_mode = False
        self.current_position = 0

        self.layout.addWidget(self.plot_widget)
        self.setLayout(self.layout)

    def load_waveform(self, file_path):
        self.audio_data, self.sample_rate = sf.read(file_path, always_2d=False)
        self.audio_data = self.audio_data[:,
                          0] if self.audio_data.ndim > 1 else self.audio_data
        if not self.cine_mode:
            duration = len(self.audio_data) / self.sample_rate
            x = np.linspace(0, duration, len(self.audio_data))
            self.plot_item.setData(x, self.audio_data)
            self.plot_widget.setXRange(x[0], x[-1])
            self.plot_widget.addItem(self.needle)
        else:
            self.plot_item.setData([], [])

    def play_audio(self):
        self.media_player.play()
        self.timer.start(35)
        if self.cine_mode:
            self.current_position = 0
            self.plot_widget.setXRange(0, 5)
            self.plot_item.setData([], [])
        else:
            duration = len(self.audio_data) / self.sample_rate
            x = np.linspace(0, duration, len(self.audio_data))
            self.plot_item.setData(x, self.audio_data)
            self.plot_widget.setXRange(x[0], x[-1])
            self.plot_widget.addItem(self.needle)

    def update_needle(self):
        if self.media_player.state() == QMediaPlayer.State.PlayingState:
            position = self.media_player.position() / 1000.0
            if self.cine_mode:
                self.update_cine_mode(position)
            else:
                self.needle.setPos(position)

    def update_cine_mode(self, position):
        window_size = 3
        start_time = max(0, position - window_size)
        end_time = position
        start_index = int(start_time * self.sample_rate * 2)
        end_index = int(end_time * self.sample_rate * 2)
        y = self.audio_data[start_index:end_index]
        x = np.linspace(start_time, end_time, end_index - start_index)
        self.plot_item.setData(x, y)
        self.update_x_axis(position)

    def update_x_axis(self, position):
        window_size = 3
        start_time = max(0, position - window_size)
        end_time = start_time + window_size
        self.plot_widget.setXRange(start_time, end_time)

    def pause_audio(self):
        self.media_player.pause()
        self.timer.stop()

    def rewind_audio(self):
        self.media_player.setPosition(0)
        self.media_player.play()
        self.needle.setPos(0)
        self.timer.start(35)

    def forward_audio(self):
        current_position = self.media_player.position()
        duration = len(self.audio_data) / self.sample_rate
        print(duration)
        new_position = int(current_position + (100 * duration))
        self.media_player.setPosition(new_position)

        if self.cine_mode:
            position = new_position / 1000.0
            self.update_cine_mode(position)
        else:
            self.needle.setPos(new_position / 1000.0)

    def backward_audio(self):
        current_position = self.media_player.position()
        duration = len(self.audio_data) / self.sample_rate
        new_position = int(max(0, current_position - 100 * duration))
        self.media_player.setPosition(new_position)

        if self.cine_mode:
            position = new_position / 1000.0
            self.update_cine_mode(position)
        else:
            self.needle.setPos(new_position / 1000.0)


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.end_index = None
        self.start_index = None
        self.isCSV = False
        self.audio_data = None
        self.original_magnitudes = None
        self.positive_freqs = None
        self.fft_freq = None
        self.ftt_data = None
        self.setWindowTitle("Simple Signal Viewer")
        self.setGeometry(50, 50, 600, 1000)

        self.current_mode = "Uniform Mode"
        self.freq_data = None
        self.freq_ranges = []
        self.sliders = []
        self.isShown = True
        self.min_freq_input = QLineEdit()
        self.min_freq_input.setPlaceholderText("Min Frequency (Hz)")

        with open("Style/index.qss", "r") as f:
            self.setStyleSheet(f.read())

        playIcon = QtGui.QIcon()
        playIcon.addPixmap(
            QtGui.QPixmap("Style/icons/play.png"),
            QtGui.QIcon.Mode.Normal,
            QtGui.QIcon.State.On,
        )

        pauseIcon = QtGui.QIcon()
        pauseIcon.addPixmap(
            QtGui.QPixmap("Style/icons/pause.png"),
            QtGui.QIcon.Mode.Normal,
            QtGui.QIcon.State.On,
        )

        rewindIcon = QtGui.QIcon()
        rewindIcon.addPixmap(
            QtGui.QPixmap("Style/icons/rewind.png"),
            QtGui.QIcon.Mode.Normal,
            QtGui.QIcon.State.On,
        )

        forwardIcon = QtGui.QIcon()
        forwardIcon.addPixmap(
            QtGui.QPixmap("Style/icons/forward.png"),
            QtGui.QIcon.Mode.Normal,
            QtGui.QIcon.State.On,
        )

        backwardIcon = QtGui.QIcon()
        backwardIcon.addPixmap(
            QtGui.QPixmap("Style/icons/backward.png"),
            QtGui.QIcon.Mode.Normal,
            QtGui.QIcon.State.On,
        )

        loadIcon = QtGui.QIcon()
        loadIcon.addPixmap(
            QtGui.QPixmap("Style/icons/load.png"),
            QtGui.QIcon.Mode.Normal,
            QtGui.QIcon.State.On,
        )

        self.show_hide_button = QPushButton("Hide spectrogram")
        self.show_hide_button.setObjectName("show_hide_button")
        self.show_hide_button.clicked.connect(self.show_hide_spectrogram)

        self.right_frame = QFrame()
        self.right_layout = QVBoxLayout()
        self.right_frame.setLayout(self.right_layout)

        self.left_frame = QFrame()
        self.left_frame.setMaximumWidth(350)
        self.left_layout = QVBoxLayout()
        self.left_frame.setLayout(self.left_layout)

        self.input_viewer = SignalViewer()

        self.output_viewer = SignalViewer()

        self.input_viewer.plot_widget.setXLink(self.output_viewer.plot_widget)
        self.input_viewer.plot_widget.setYLink(self.output_viewer.plot_widget)

        self.input_output_frame = QFrame()
        self.input_output_frame.setObjectName("input_output_frame")
        self.input_output_layout = QHBoxLayout()
        self.input_output_layout.setContentsMargins(0, 0, 0, 0)
        self.input_output_frame.setLayout(self.input_output_layout)
        self.spectrogram_frame = QFrame()
        self.spectrogram_layout = QVBoxLayout()
        self.spectrogram_frame.setLayout(self.spectrogram_layout)

        self.viewer_frame = QFrame()
        self.viewer_frame.setObjectName("viewer_frame")
        self.viewer_frame.setMaximumHeight(500)
        self.viewer_layout = QVBoxLayout()
        self.viewer_layout.setContentsMargins(0, 0, 0, 0)
        self.viewer_frame.setLayout(self.viewer_layout)
        self.viewer_layout.addWidget(self.input_viewer)
        self.viewer_layout.addWidget(self.output_viewer)

        self.input_output_layout.addWidget(self.viewer_frame)
        self.input_output_layout.addWidget(self.spectrogram_frame)

        self.right_layout.addWidget(self.input_output_frame)

        self.load_button = QPushButton()
        self.load_button.setIcon(loadIcon)
        self.load_button.setIconSize(QtCore.QSize(24, 24))

        self.play_button = QPushButton()
        self.play_button.setIcon(playIcon)
        self.play_button.setIconSize(QtCore.QSize(20, 20))

        self.pause_button = QPushButton()
        self.pause_button.setIcon(pauseIcon)
        self.pause_button.setIconSize(QtCore.QSize(20, 20))

        self.rewind_button = QPushButton()
        self.rewind_button.setIcon(rewindIcon)
        self.rewind_button.setIconSize(QtCore.QSize(24, 24))

        self.forward_button = QPushButton()
        self.forward_button.setIcon(forwardIcon)
        self.forward_button.setIconSize(QtCore.QSize(20, 20))

        self.backward_button = QPushButton()
        self.backward_button.setIcon(backwardIcon)
        self.backward_button.setIconSize(QtCore.QSize(20, 20))
        self.linear_scale_button = QRadioButton("Linear")
        self.linear_scale_button.setStyleSheet(
            "QRadioButton {font-size: 15px;font-weight: bold}"
        )
        self.audiogram_scale_button = QRadioButton("Audiogram")
        self.audiogram_scale_button.setStyleSheet(
            "QRadioButton {font-size: 15px;font-weight: bold}"
        )

        self.load_button.clicked.connect(self.load_file)
        self.play_button.clicked.connect(self.play_audio)
        self.pause_button.clicked.connect(self.pause_audio)
        self.rewind_button.clicked.connect(self.rewind_audio)
        self.forward_button.clicked.connect(self.forward_audio)
        self.backward_button.clicked.connect(self.backward_audio)
        self.linear_scale_button.toggled.connect(self.update_frequency_graph)
        self.audiogram_scale_button.toggled.connect(self.update_frequency_graph)

        dummy_H = QHBoxLayout()

        control_frame_left = QFrame()
        control_frame_left.setObjectName("control_frame_left")
        dummy_H.addWidget(control_frame_left)
        control_layout_left = QHBoxLayout()

        self.plot_mode_group = QButtonGroup(self)
        self.freq_mode_group = QButtonGroup(self)

        self.normal_mode_button = QRadioButton("Normal Plot")
        self.cine_mode_button = QRadioButton("Cine Plot")
        self.normal_mode_button.setChecked(True)
        self.freq_mode_group.addButton(self.linear_scale_button)
        self.freq_mode_group.addButton(self.audiogram_scale_button)

        self.normal_mode_button.toggled.connect(self.change_plot_mode)
        self.cine_mode_button.toggled.connect(self.change_plot_mode)
        control_frame_center = QFrame()
        dummy_H.addSpacerItem(
            QSpacerItem(0, 40, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )
        dummy_H.addSpacerItem(
            QSpacerItem(240, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )
        control_frame_center.setObjectName("control_frame_center")

        control_layout_center = QVBoxLayout()
        control_layout_center.setContentsMargins(0, 0, 0, 0)
        control_top = QHBoxLayout()
        control_top.setContentsMargins(0, 0, 0, 0)
        control_bottom = QHBoxLayout()
        control_bottom.setContentsMargins(0, 0, 0, 0)

        control_layout_center.addLayout(control_top)
        control_layout_center.addLayout(control_bottom)

        control_frame_center.setLayout(control_layout_center)
        control_top.addWidget(self.backward_button)
        control_top.addWidget(self.play_button)
        control_top.addWidget(self.forward_button)
        control_bottom.addWidget(self.load_button)
        control_bottom.addWidget(self.pause_button)
        control_bottom.addWidget(self.rewind_button)

        control_frame_right = QFrame()
        control_frame_right.setObjectName("control_frame_right")
        control_layout_right = QVBoxLayout()
        control_layout_right.addSpacerItem(
            QSpacerItem(0, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        )

        control_layout_right.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        control_layout_right.setSpacing(30)

        control_frame_right.setLayout(control_layout_right)

        iamge_frame = QFrame()
        iamge_layout = QHBoxLayout()
        iamge_frame.setLayout(iamge_layout)

        self.image_label = QLabel()
        self.image_label.setPixmap(QtGui.QPixmap("Style/icons/logo.png"))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(True)
        self.image_label.setFixedSize(250, 250)
        iamge_layout.addWidget(self.image_label)

        self.left_layout.addWidget(control_frame_right)
        self.linear_scale_button.setChecked(True)
        self.freq_frame = QFrame()
        self.freq_frame.setMaximumHeight(250)
        self.freq_layout = QHBoxLayout()
        self.freq_layout.setContentsMargins(0, 0, 0, 0)
        self.freq_frame.setLayout(self.freq_layout)

        self.freq_plot_widget = pg.PlotWidget()
        self.freq_plot_item = self.freq_plot_widget.plot(pen=pg.mkPen(color="blue"))
        self.freq_layout.addWidget(self.freq_plot_widget)
        self.right_layout.addWidget(self.freq_frame)

        self.slider_frame = QFrame()
        self.slider_frame.setObjectName("slider_frame")
        self.slider_layout = QHBoxLayout()
        self.slider_frame.setLayout(self.slider_layout)
        self.right_layout.addWidget(self.slider_frame)

        self.update_sliders()

        self.spec_plot_figure_1 = Figure()
        self.spec_plot_figure_2 = Figure()
        self.spec_canvas_1 = FigureCanvas(self.spec_plot_figure_1)
        self.spec_canvas_1.setFixedSize(500, 230)
        self.spec_canvas_2 = FigureCanvas(self.spec_plot_figure_2)
        self.spec_canvas_2.setFixedSize(500, 230)
        axis1 = self.spec_plot_figure_1.add_subplot(111)
        axis1.set_title("Signal Spectrogram")
        axis1.set_xlabel("Time [s]")
        axis1.set_ylabel("Frequency [Hz] (scaled to '$\pi$')")
        cbar1 = self.spec_canvas_1.figure.colorbar(mappable=None, ax=axis1)
        cbar1.set_label("Magnitude [dB]")

        axis2 = self.spec_plot_figure_2.add_subplot(111)
        axis2.set_title("Reconstructed Signal Spectrogram")
        axis2.set_xlabel("Time [s]")
        axis2.set_ylabel("Frequency [Hz] (scaled to '$\pi$')")
        cbar2 = self.spec_canvas_2.figure.colorbar(mappable=None, ax=axis2)
        cbar2.set_label("Magnitude [dB]")
        self.spectrogram_layout.addWidget(self.spec_canvas_1)
        self.spectrogram_layout.addWidget(self.spec_canvas_2)

        self.combo_box = QComboBox()
        self.combo_box.setObjectName("combo_box")
        self.combo_box.setMinimumHeight(40)
        self.combo_box.setStyleSheet("QComboBox {font-size: 15px;}")
        self.combo_box.addItem("Uniform Mode")
        self.combo_box.addItem("Musical Mode")
        self.combo_box.addItem("Animal Song Mode")
        self.combo_box.addItem("Weiner Filter Mode")

        self.combo_box.currentIndexChanged.connect(self.change_mode)

        self.input_radio_button = QRadioButton("Input")
        self.output_radio_button = QRadioButton("Output")
        self.input_radio_button.setChecked(True)
        self.output_radio_button.setChecked(True)

        self.alpha_label = QLabel("Alpha:")
        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setMinimum(1)
        self.alpha_slider.setMaximum(1000000)
        self.alpha_slider.setValue(1)
        self.alpha_slider.setTickPosition(QSlider.TicksBelow)
        self.alpha_slider.setTickInterval(100000)
        self.alpha_slider.valueChanged.connect(self.update_alpha)
        self.alpha_value_label = QLabel(str(self.alpha_slider.value()))

        self.alpha_slider.setVisible(False)
        self.alpha_label.setVisible(False)

        self.wiener_filter_button = QPushButton("Apply Wiener Filter")
        self.wiener_filter_button.setObjectName("wiener_filter_button")
        self.wiener_filter_button.setVisible(False)
        self.wiener_filter_button.clicked.connect(self.apply_wiener_filter)

        self.io_button_group = QButtonGroup(self)
        self.io_button_group.addButton(self.input_radio_button)
        self.io_button_group.addButton(self.output_radio_button)

        control_layout_right.addWidget(self.combo_box)
        control_layout_right.addWidget(self.linear_scale_button)
        control_layout_right.addWidget(self.audiogram_scale_button)
        control_layout_right.addWidget(control_frame_center)
        control_layout_right.addWidget(self.input_radio_button)
        control_layout_right.addWidget(self.output_radio_button)
        control_layout_right.addWidget(self.show_hide_button)
        control_layout_right.addWidget(self.alpha_label)
        control_layout_right.addWidget(self.alpha_slider)

        control_layout_right.addWidget(self.wiener_filter_button)

        control_layout_right.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
        control_layout_right.addWidget(iamge_frame)

        layout = QHBoxLayout()
        layout.addWidget(self.left_frame)
        layout.addWidget(self.right_frame)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def change_plot_mode(self):
        if self.normal_mode_button.isChecked():
            self.input_viewer.cine_mode = False
            self.output_viewer.cine_mode = False
            self.input_viewer.plot_widget.addItem(self.input_viewer.needle)
            self.output_viewer.plot_widget.addItem(self.output_viewer.needle)
            self.input_viewer.play_audio()
            self.output_viewer.play_audio()
        elif self.cine_mode_button.isChecked():
            self.input_viewer.cine_mode = True
            self.output_viewer.cine_mode = True
            self.input_viewer.plot_widget.removeItem(self.input_viewer.needle)
            self.output_viewer.plot_widget.removeItem(self.output_viewer.needle)
            self.input_viewer.play_audio()
            self.output_viewer.play_audio()
        print('cine_mode:', self.input_viewer.cine_mode)

    def show_hide_spectrogram(self):
        if not self.isShown:
            self.show_hide_button.setText("Hide spectrogram")

            if self.input_viewer.audio_data is not None and self.audio_data is not None:
                self.plot_spectrogram(
                    self.input_viewer.audio_data,
                    self.input_viewer.sample_rate,
                    self.spec_canvas_1,
                    self.spec_plot_figure_1.gca(),
                )
                self.plot_spectrogram(
                    self.audio_data,
                    self.input_viewer.sample_rate,
                    self.spec_canvas_2,
                    self.spec_plot_figure_2.gca(),
                )
            self.spectrogram_frame.show()
        else:
            self.show_hide_button.setText("Show spectrogram")
            self.spectrogram_frame.hide()
        self.isShown = not self.isShown

    def create_sliders(self, slider_num):
        slider_layouts = []
        self.sliders = []
        if self.input_viewer.audio_data is not None:
            min_label, max_label = self.update_frequency_graph()
        else:
            min_label, max_label = 0, 0

        if self.current_mode == "Uniform Mode":
            for i in range(slider_num):

                slider_container = QVBoxLayout()
                slider_container.setAlignment(
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
                )

                slider = QSlider(Qt.Orientation.Vertical)
                slider.setMinimum(0)
                slider.setMaximum(10)
                slider.setValue(5)
                slider.setTickPosition(QSlider.TicksBothSides)
                slider.setTickInterval(1)

                if i == 0:
                    label = QLabel(f" ({min_label:.1f}, {max_label * (i + 1):.1f}) Hz")
                else:
                    label = QLabel(
                        f" ({max_label * i:.1f}, {max_label * (i + 1):.1f}) Hz"
                    )

                label.setAlignment(Qt.AlignLeft)
                label.setObjectName("slider_label")
                label.setMaximumWidth(200)

                slider_container.addWidget(slider)
                slider_container.addWidget(label)

                slider_layouts.append(slider_container)
                self.sliders.append(slider)
                slider.valueChanged.connect(
                    lambda value, index=i: self.update_frequency_graph(index)
                )



































        elif self.current_mode == "Musical Mode":

            freq_labels = ["Drums", "Violin", "OOOh", "R", "S", "Xylophone"]
            freq_ranges = [(0, 400), (400, 4000), (200, 800), (1320, 4400), (2200, 13500), (4000, 20000)]

            for i in range(slider_num):
                slider_container = QVBoxLayout()

                slider = QSlider(Qt.Orientation.Vertical)
                slider.setMinimum(0)
                slider.setMaximum(10)
                slider.setValue(5)
                slider.setTickPosition(QSlider.TicksBothSides)
                slider.setTickInterval(1)

                label = QLabel(
                    f"{freq_labels[i]} ({freq_ranges[i][0]:.1f}, {freq_ranges[i][1]:.1f})"
                )
                label.setAlignment(Qt.AlignLeft)
                label.setMaximumWidth(140)
                slider_container.addWidget(slider)
                slider_container.addWidget(label)

                slider_layouts.append(slider_container)
                self.sliders.append(slider)
                slider.valueChanged.connect(
                    lambda value, index=i: self.update_frequency_graph(index)
                )

        elif self.current_mode == "Animal Song Mode":

            freq_labels = ["Trumpet", "Whale", "Piano", "Frog", "Cardinal", "Xylophone"]
            freq_ranges = [[0, 600], [600, 1200], [1200, 1600], [1600, 2800], [2800, 3600], [4000, 20000]]

            for i in range(slider_num):
                slider_container = QVBoxLayout()

                slider = QSlider(Qt.Orientation.Vertical)
                slider.setMinimum(0)
                slider.setMaximum(10)
                slider.setValue(5)
                slider.setTickPosition(QSlider.TicksBothSides)
                slider.setTickInterval(1)

                label = QLabel(
                    f"{freq_labels[i]} ({freq_ranges[i][0]:.1f}, {freq_ranges[i][1]:.1f})"
                )
                label.setAlignment(Qt.AlignLeft)
                label.setMaximumWidth(140)
                slider_container.addWidget(slider)
                slider_container.addWidget(label)

                slider_layouts.append(slider_container)
                self.sliders.append(slider)
                slider.valueChanged.connect(
                    lambda value, index=i: self.update_frequency_graph(index)
                )
        elif self.current_mode == "ECG Abnormalities Mode":

            freq_labels = ["Normal", "AFib", "VT", "VC"]
            freq_ranges = [0, 22000], [200, 450], [80, 864], [0, 1000]

            for i in range(slider_num):
                slider_container = QVBoxLayout()

                slider = QSlider(Qt.Orientation.Vertical)
                slider.setMinimum(0)
                slider.setMaximum(10)
                slider.setValue(5)
                slider.setTickPosition(QSlider.TicksBothSides)
                slider.setTickInterval(1)

                label = QLabel(
                    f"{freq_labels[i]} ({freq_ranges[i][0]:.1f}, {freq_ranges[i][1]:.1f})"
                )
                label.setAlignment(Qt.AlignLeft)
                label.setMaximumWidth(140)
                slider_container.addWidget(slider)
                slider_container.addWidget(label)

                slider_layouts.append(slider_container)
                self.sliders.append(slider)
                slider.valueChanged.connect(
                    lambda value, index=i: self.update_frequency_graph(index)
                )
        return slider_layouts

    def change_mode(self, index):
        self.current_mode = self.combo_box.itemText(index)

        self.update_sliders()
        self.reset_sliders()
        if self.current_mode == "Weiner Filter Mode":

            self.wiener_filter_button.setVisible(True)
            self.alpha_slider.setVisible(True)
            self.alpha_label.setVisible(True)
            self.signal_processor = SignalProcessingWithWienerFilter(self.input_viewer.plot_widget,
                                                                     self.input_viewer.audio_data,
                                                                     self.input_viewer.sample_rate, self)

        else:
            self.alpha_slider.setVisible(False)
            self.alpha_label.setVisible(False)
            self.wiener_filter_button.setVisible(False)
            if hasattr(self, 'signal_processor'):
                self.signal_processor.remove_lines()

        self.update_frequency_graph()

    def update_sliders(self):

        for i in reversed(range(self.slider_layout.count())):
            widget_to_remove = self.slider_layout.itemAt(i).layout()
            if widget_to_remove:
                while widget_to_remove.count():
                    item = widget_to_remove.takeAt(0)
                    widget = item.widget()
                    if widget:
                        widget.deleteLater()
                self.slider_layout.removeItem(widget_to_remove)

        if self.current_mode == "Uniform Mode" or self.current_mode == "Custom Range Mode":
            slider_num = 10
        elif self.current_mode == "Musical Mode":
            slider_num = 6
        else:
            slider_num = 6
        slider_layouts = self.create_sliders(slider_num)
        for slider_layout in slider_layouts:
            self.slider_layout.addLayout(slider_layout)

    def load_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "",
            "WAV Files (*.wav);;CSV Files (*.csv);;All Files (*)",
            options=options,
        )

        if file_path:
            self.reset_viewers()
            if file_path.endswith(".csv"):
                self.isCSV = True
                wav_file_path = self.convert_csv_to_wav(file_path)
                self.input_viewer.load_waveform(wav_file_path)
                self.input_viewer.media_player.setMedia(
                    QMediaContent(QUrl.fromLocalFile(wav_file_path))
                )
            elif file_path.endswith(".wav"):
                self.isCSV = False
                self.input_viewer.load_waveform(file_path)
                self.input_viewer.media_player.setMedia(
                    QMediaContent(QUrl.fromLocalFile(file_path))
                )

            (
                self.ftt_data,
                self.fft_freq,
                self.positive_freqs,
                self.original_magnitudes,
            ) = self.fft()

            if not self.cine_mode_button.isChecked():
                self.output_viewer.plot_widget.addItem(self.output_viewer.needle)
                self.input_viewer.plot_widget.addItem(self.input_viewer.needle)

            self.update_sliders()
            self.update_frequency_graph()
            self.reset_sliders()

            if self.input_viewer.audio_data is not None:
                self.plot_output(self.input_viewer.audio_data)
                if self.isShown:
                    self.plot_spectrogram(
                        self.input_viewer.audio_data,
                        self.input_viewer.sample_rate,
                        self.spec_canvas_1,
                        self.spec_plot_figure_1.gca(),
                    )
            self.play_audio()
            self.change_mode(self.combo_box.currentIndex())
            return (
                self.ftt_data,
                self.fft_freq,
                self.positive_freqs,
                self.original_magnitudes,
            )

    def convert_csv_to_wav(self, file_path, sample_rate=44100):
        data = pd.read_csv(file_path, header=None)

        if data.shape[1] == 2:

            samples = data.iloc[:, 1].values
        else:
            samples = data.values.flatten()

        samples = samples / np.max(np.abs(samples)) * 32767
        samples = samples.astype(np.int16)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            wav_file = temp_file.name
        wavfile.write(wav_file, sample_rate, samples)
        return wav_file

    def plot_output(self, output_data):
        self.output_viewer.audio_data = output_data
        self.output_viewer.sample_rate = self.input_viewer.sample_rate

        if self.cine_mode_button.isChecked():
            self.output_viewer.cine_mode = True
            self.output_viewer.plot_item.setData([], [])
        else:
            self.output_viewer.cine_mode = False
            duration = len(output_data) / self.input_viewer.sample_rate
            x = np.linspace(0, duration, len(output_data))
            self.output_viewer.plot_item.setData(x, output_data)
            self.output_viewer.plot_widget.setXRange(x[0], x[-1])
            self.output_viewer.plot_widget.addItem(self.output_viewer.needle)

        self.output_viewer.media_player.stop()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            output_file_path = temp_file.name
            sf.write(output_file_path, output_data, self.input_viewer.sample_rate)

        self.output_viewer.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(output_file_path)))

        if self.isShown:
            self.plot_spectrogram(
                output_data, self.input_viewer.sample_rate, self.spec_canvas_2, self.spec_plot_figure_2.gca()
            )

    def fft(self):
        self.ftt_data = np.fft.fft(self.input_viewer.audio_data)
        self.fft_freq = np.fft.fftfreq(
            len(self.ftt_data), 1 / self.input_viewer.sample_rate
        )
        self.positive_freqs = self.fft_freq[: len(self.fft_freq) // 2]
        self.original_magnitudes = np.abs(self.ftt_data[: len(self.ftt_data) // 2])
        return (
            self.ftt_data,
            self.fft_freq,
            self.positive_freqs,
            self.original_magnitudes,
        )

    def update_frequency_graph(self, index=None):
        if self.input_viewer.audio_data is not None:
            if not hasattr(self, "original_magnitudes") or index is None:
                if not hasattr(self, "ftt_data") or not hasattr(self, "fft_freq"):
                    (
                        self.ftt_data,
                        self.fft_freq,
                        self.positive_freqs,
                        self.original_magnitudes,
                    ) = self.fft()
                self.modified_magnitudes = self.original_magnitudes.copy()
                self.slider_label_min = self.positive_freqs[0]
                self.slider_label_max = (self.positive_freqs[-1] - self.positive_freqs[0]) / 10

            if index is not None:
                slider = self.sliders[index]
                labels = slider.parent().findChildren(QLabel)
                label_text = labels[index].text()
                freq_range_text = label_text.split("(")[-1].strip(") Hz")
                min_freq, max_freq = map(float, freq_range_text.split(","))
                if self.audiogram_scale_button.isChecked():
                    magnitudes_db = 20 * np.log10(self.modified_magnitudes)
                    self.freq_plot_item.setData(self.positive_freqs, magnitudes_db)
                    self.freq_plot_widget.getPlotItem().invertY(True)
                    self.freq_plot_widget.setLabel("left", "H L (dB)")
                else:
                    self.freq_plot_item.setData(
                        self.positive_freqs, self.modified_magnitudes
                    )
                    self.freq_plot_widget.getPlotItem().invertY(False)
                    self.freq_plot_widget.setLabel("left", "Magnitude")

                if slider.value() != 0:
                    gain = 1 + (slider.value() - 5) * 0.2
                    freq_range = np.where(
                        (self.positive_freqs >= min_freq)
                        & (self.positive_freqs < max_freq)
                    )[0]

                    self.modified_magnitudes[freq_range] = (
                            self.original_magnitudes[freq_range] * gain
                    )

                    temp_ftt_data = self.ftt_data.copy()
                    half_len = len(temp_ftt_data) // 2
                    temp_ftt_data[:half_len] = self.modified_magnitudes * np.exp(
                        1j * np.angle(temp_ftt_data[:half_len])
                    )

                    if len(temp_ftt_data) % 2 == 0:
                        temp_ftt_data[half_len + 1:] = np.conj(temp_ftt_data[1:half_len][::-1])
                    else:
                        temp_ftt_data[half_len + 1:] = np.conj(temp_ftt_data[1:half_len + 1][::-1])

                    reconstructed_signal = np.fft.ifft(temp_ftt_data).real
                    self.plot_output(reconstructed_signal)

                else:

                    freq_range = np.where(
                        (self.positive_freqs >= min_freq)
                        & (self.positive_freqs < max_freq)
                    )[0]
                    self.modified_magnitudes[freq_range] = 0

                    temp_ftt_data = self.ftt_data.copy()
                    half_len = len(temp_ftt_data) // 2
                    temp_ftt_data[:half_len] = self.modified_magnitudes * np.exp(
                        1j * np.angle(temp_ftt_data[:half_len])
                    )

                    if len(temp_ftt_data) % 2 == 0:
                        temp_ftt_data[half_len + 1:] = np.conj(temp_ftt_data[1:half_len][::-1])
                    else:
                        temp_ftt_data[half_len + 1:] = np.conj(temp_ftt_data[1:half_len + 1][::-1])

                    reconstructed_signal = np.fft.ifft(temp_ftt_data).real
                    self.plot_output(reconstructed_signal)

            self.freq_plot_item.setData(self.positive_freqs, self.modified_magnitudes)

            return self.slider_label_min, self.slider_label_max

    def plot_spectrogram(self, amplitude, sample_rate, figure, axis):
        axis.clear()
        frequencies, times, amplitudes = spectrogram(amplitude, sample_rate)
        frequencies = frequencies * np.pi / np.max(frequencies)
        axis.pcolormesh(
            times, frequencies, 10 * np.log10(amplitudes + 1e-10), shading="gouraud"
        )
        figure.draw()

    def clear_spectrogram(self):
        if hasattr(self, 'spec_canvas_1') and self.spec_canvas_1:
            self.spec_canvas_1.figure.clf()
        if hasattr(self, 'spec_canvas_2') and self.spec_canvas_2:
            self.spec_canvas_2.figure.clf()
            self.spec_canvas_2.draw()

    def reset_viewers(self):
        self.input_viewer.plot_item.clear()
        self.output_viewer.plot_item.clear()
        self.input_viewer.media_player.stop()
        self.output_viewer.media_player.stop()
        self.input_viewer.needle.setPos(0)
        self.output_viewer.needle.setPos(0)
        self.input_viewer.audio_data = None
        self.output_viewer.audio_data = None

    def reset_sliders(self):
        for slider in self.sliders:
            slider.setValue(5)

    def csv_exporter(self, file_name, input_file):

        with open(file_name, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow((["Frequency"]))

            for row1 in input_file:
                writer.writerow([row1])

    def play_audio(self):
        if self.input_radio_button.isChecked():
            self.input_viewer.play_audio()
            self.input_viewer.timer.start(35)
        if self.output_radio_button.isChecked():
            self.output_viewer.play_audio()
        self.output_viewer.timer.start(35)

    def pause_audio(self):
        self.input_viewer.pause_audio()
        self.output_viewer.pause_audio()

    def rewind_audio(self):
        if self.input_radio_button.isChecked():
            self.input_viewer.rewind_audio()
            self.input_viewer.timer.start(35)
        if self.output_radio_button.isChecked():
            self.output_viewer.rewind_audio()
        self.output_viewer.timer.start(35)

    def forward_audio(self):
        if self.input_radio_button.isChecked():
            self.input_viewer.forward_audio()
        else:
            self.output_viewer.forward_audio()

    def backward_audio(self):
        self.input_viewer.backward_audio()
        self.output_viewer.backward_audio()

    def apply_wiener_filter(self):
        self.signal_processor.apply_wiener_filter()

    def update_alpha(self):
        new_alpha = self.alpha_slider.value()
        self.signal_processor.alpha = new_alpha
        self.signal_processor.apply_wiener_filter()

    def plot_difference(self):
        if self.input_viewer.audio_data is not None and self.output_viewer.audio_data is not None:
            input_data = self.input_viewer.audio_data
            output_data = self.output_viewer.audio_data

            min_length = min(len(input_data), len(output_data))
            input_data = input_data[:min_length]
            output_data = output_data[:min_length]

            difference = input_data - output_data

            plt.figure(figsize=(10, 5))
            plt.plot(difference, label='Difference')
            plt.title('Difference between Input and Output Data')
            plt.xlabel('Sample Index')
            plt.ylabel('Amplitude Difference')
            plt.legend()
            plt.grid(True)
            plt.show()


def main():
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
