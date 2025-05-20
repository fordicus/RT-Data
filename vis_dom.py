r"""................................................................................

How to Use:

	python vis_dom.py [optional_path_to_data_file]

	If no argument is provided, a fallback file
	e.g., "2025-05-09_BTCUSDT_ob200.data" can be used.

	The script launches a GUI that replays DOM snapshots and deltas
	from the given data file, mimicking a live trading environment.

................................................................................

Dependency:

	pip install PyQt5 matplotlib

	↪ Ensure your data file is newline-delimited JSON
	  with fields 'type', 'ts', 'data', 'a', 'b'.

................................................................................"""

import json
import time
from PyQt5.QtWidgets import (
	QApplication, QMainWindow, QPushButton, QVBoxLayout,
	QSlider, QWidget, QLabel, QHBoxLayout
)
from PyQt5.QtCore import Qt, QTimer
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas


class OrderBookPlayer(QMainWindow):
	def __init__(self, filename):
		super().__init__()

		self.setWindowTitle("Order Book Player")
		self.setGeometry(100, 100, 800, 600)

		self.data     = self.load_data(filename)
		self.snapshot = {}
		self.index    = 0
		self.speed    = 1.0
		self.is_paused = True

		self.init_ui()
		self.timer = QTimer()
		self.timer.timeout.connect(self.next_tick)

	def init_ui(self):
		
		main_layout = QVBoxLayout()

		# Attach filename label
		self.filename_label = QLabel(f"File: {filename}")
		main_layout.addWidget(self.filename_label)

		# Attach plot canvas
		self.canvas = FigureCanvas(plt.Figure(figsize=(8, 5)))
		main_layout.addWidget(self.canvas)

		# Set up axis
		self.ax = self.canvas.figure.add_subplot(111)
		self.ax.set_title("Order Book Depth")
		self.ax.set_xlabel("Price")
		self.ax.set_ylabel("Cumulative Size")

		# 🩺 Ensure canvas is drawn immediately
		self.canvas.draw()

		btn_layout = QHBoxLayout()

		self.play_button = QPushButton("▶ Play")
		self.play_button.clicked.connect(self.play)
		btn_layout.addWidget(self.play_button)

		self.pause_button = QPushButton("⏸ Pause")
		self.pause_button.clicked.connect(self.pause)
		btn_layout.addWidget(self.pause_button)

		self.speed_label = QLabel("Speed: 1.0x")
		btn_layout.addWidget(self.speed_label)

		self.speed_slider = QSlider(Qt.Horizontal)
		self.speed_slider.setMinimum(1)
		self.speed_slider.setMaximum(100)
		self.speed_slider.setValue(10)
		self.speed_slider.setTickInterval(1)
		self.speed_slider.valueChanged.connect(self.change_speed)
		btn_layout.addWidget(self.speed_slider)

		main_layout.addLayout(btn_layout)

		container = QWidget()
		container.setLayout(main_layout)
		self.setCentralWidget(container)

	def load_data(self, filename):
		with open(filename, "r", encoding="utf-8") as f:
			lines = f.readlines()
		data = [json.loads(line) for line in lines]
		return data

	def play(self):
		if self.index >= len(self.data):
			return
		self.is_paused = False
		self.timer.start(10)

	def pause(self):
		self.is_paused = True
		self.timer.stop()

	def reset(self):
		self.pause()
		self.index = 0
		self.snapshot = {}
		self.ax.clear()
		self.ax.set_title("Order Book Depth")
		self.ax.set_xlabel("Price")
		self.ax.set_ylabel("Cumulative Size")
		self.canvas.draw()

	def change_speed(self, value):
		self.speed = value / 10.0
		self.speed_label.setText(f"Speed: {self.speed:.1f}x")


		# Apply snapshot or delta updates to the current DOM state
	def update_snapshot(self, item):
		if item["type"] == "snapshot":
			# Full reset: replace snapshot with new base state
			self.snapshot = item["data"]
		elif item["type"] == "delta" and self.snapshot:
			# Loop over both bid ('b') and ask ('a') sides
			for side in ['b', 'a']:
				# Convert snapshot entries to price → size dict
				existing = {x[0]: float(x[1]) for x in self.snapshot.get(side, [])}
				for price, size in item["data"].get(side, []):
					# Remove price level if size is zero (cancellation)
					if float(size) == 0:
						existing.pop(price, None)
					# Otherwise, update or insert the price level
					else:
						existing[price] = float(size)
				# sort and store
				if side == 'b':
				# Re-sort updated entries based on price
					new_side = sorted(existing.items(), key=lambda x: -float(x[0]))
				else:
				# Re-sort updated entries based on price
					new_side = sorted(existing.items(), key=lambda x: float(x[0]))
				# Convert dict back to sorted list of [price, size]
				self.snapshot[side] = [[k, v] for k, v in new_side]

	def plot_book(self):
		self.ax.clear()
		self.ax.set_title("Order Book Depth")
		self.ax.set_xlabel("Price")
		self.ax.set_ylabel("Cumulative Size")

		bids = self.snapshot.get("b", [])
		asks = self.snapshot.get("a", [])

		if bids:
			bid_prices = [float(x[0]) for x in bids]
			bid_sizes = [float(x[1]) for x in bids]
			# Calculate cumulative bid sizes for depth chart
			bid_cum = [sum(bid_sizes[:i + 1]) for i in range(len(bid_sizes))]
			self.ax.fill_between(bid_prices, bid_cum, color='green', alpha=0.5)

		if asks:
			ask_prices = [float(x[0]) for x in asks]
			ask_sizes = [float(x[1]) for x in asks]
			# Calculate cumulative ask sizes for depth chart
			ask_cum = [sum(ask_sizes[:i + 1]) for i in range(len(ask_sizes))]
			self.ax.fill_between(ask_prices, ask_cum, color='red', alpha=0.5)

		self.canvas.draw()


		# Advance to the next item in the data stream
		# Handles replay timing and calls plot_book
	def next_tick(self):
		if self.is_paused or self.index >= len(self.data):
			self.timer.stop()
			return

		item = self.data[self.index]
		self.update_snapshot(item)
		if item["type"] == "snapshot" or item["type"] == "delta":
			self.plot_book()

		curr_ts = item["ts"]
		next_ts = self.data[self.index + 1]["ts"] if self.index + 1 < len(self.data) else curr_ts + 1000
			# Compute real-time delay (scaled by speed)
		interval = max((next_ts - curr_ts) / self.speed, 1)
		self.timer.start(int(interval))
		self.index += 1


if __name__ == '__main__':
	import sys
	app = QApplication(sys.argv)
	if len(sys.argv) >= 2:
		filename = sys.argv[1]  # use CLI argument
	else:
		filename = "2025-05-07_AVAXUSDT_ob200.data"  # fallback file
	player = OrderBookPlayer(filename)
	player.show()
	sys.exit(app.exec_())
