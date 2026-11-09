"""A small dependency-free plot for historical speed test measurements."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget


class HistoryChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = []
        self.setMinimumHeight(190)

    def set_records(self, records: list[dict]):
        self.records = records
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self.rect().adjusted(48, 18, -18, -34)
        painter.setPen(QPen(Qt.GlobalColor.lightGray, 1))
        painter.drawRect(area)
        painter.setPen(Qt.GlobalColor.darkGray)
        painter.drawText(8, 18, "Mbps")
        downloads = [row.get("download_mbps") for row in self.records if row.get("download_mbps") is not None]
        uploads = [row.get("upload_mbps") for row in self.records if row.get("upload_mbps") is not None]
        values = downloads + uploads
        if not values:
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, "No speed-test history in this range")
            return
        maximum = max(values) or 1
        painter.setPen(QPen(Qt.GlobalColor.lightGray, 1, Qt.PenStyle.DashLine))
        for index in range(1, 4):
            y = area.bottom() - area.height() * index / 4
            painter.drawLine(area.left(), int(y), area.right(), int(y))
            painter.drawText(5, int(y + 4), f"{maximum * index / 4:.1f}")
        ordered = list(reversed(self.records))
        for key, color in (("download_mbps", Qt.GlobalColor.blue), ("upload_mbps", Qt.GlobalColor.darkGreen)):
            painter.setPen(QPen(color, 2))
            points = []
            if len(ordered) == 1:
                indices = [(0, ordered[0])]
            else:
                indices = list(enumerate(ordered))
            for index, row in indices:
                value = row.get(key)
                if value is None:
                    points.append(None)
                    continue
                x = area.left() + index * area.width() / max(1, len(ordered) - 1)
                y = area.bottom() - (value / maximum) * area.height()
                points.append((int(x), int(y)))
                painter.drawEllipse(int(x) - 3, int(y) - 3, 6, 6)
            for first, second in zip(points, points[1:]):
                if first and second:
                    painter.drawLine(*first, *second)
        painter.setPen(Qt.GlobalColor.blue)
        painter.drawText(area.left(), self.height() - 8, "Download")
        painter.setPen(Qt.GlobalColor.darkGreen)
        painter.drawText(area.left() + 100, self.height() - 8, "Upload")
