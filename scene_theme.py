"""Decorated scenic surfaces based on the user's character UI references."""

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QMenu


class SceneSurface:
    def __init__(self, profile, kind="panel"):
        self.kind = kind
        self.set_profile(profile)

    def set_profile(self, profile):
        self.profile = profile
        name = "waguri" if profile.id == "waguri_kaoruko" else profile.id
        path = Path(__file__).resolve().parent / "assets/generated/production" / f"{name}_scene.png"
        self.source = QPixmap(str(path)) if path.is_file() else QPixmap()
        self.scaled = QPixmap()
        self.size = None

    def paint(self, painter, rect):
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(rect).adjusted(1,1,-1,-1)
        clip = QPainterPath()
        clip.addRoundedRect(area,17,17)
        painter.setClipPath(clip)
        colour = QColor(self.profile.colours["background"])
        painter.fillRect(area,colour)
        if not self.source.isNull():
            if self.size != rect.size():
                self.size = rect.size()
                self.scaled = self.source.scaled(self.size,Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                  Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((rect.width()-self.scaled.width())//2,(rect.height()-self.scaled.height())//2,self.scaled)
            colour.setAlpha(60 if self.kind == "companion" else (223 if self.kind == "menu" else 216))
            painter.fillRect(area,colour)
        painter.setClipping(False)
        border = QColor(self.profile.colours["border"])
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border,2.0))
        painter.drawRoundedRect(area.adjusted(1,1,-1,-1),17,17)
        painter.setPen(QPen(border,0.8))
        painter.drawRoundedRect(area.adjusted(5,5,-5,-5),12,12)
        # Mirrored filigree stays crisp at arbitrary form sizes.
        for x,y,sx,sy in ((11,11,1,1),(rect.width()-11,11,-1,1),
                          (11,rect.height()-11,1,-1),(rect.width()-11,rect.height()-11,-1,-1)):
            painter.save()
            painter.translate(x,y)
            painter.scale(sx,sy)
            vine = QPainterPath()
            vine.moveTo(0,30)
            vine.cubicTo(1,9,10,1,31,0)
            vine.cubicTo(20,0,16,6,18,11)
            vine.cubicTo(21,15,29,9,24,6)
            painter.setPen(QPen(border,1.15))
            painter.drawPath(vine)
            painter.setBrush(border)
            painter.drawEllipse(QRectF(7,10,3,6))
            painter.restore()
        painter.restore()


class SceneMenu(QMenu):
    def __init__(self, profile, parent=None, title=""):
        super().__init__(title,parent)
        self.setObjectName("ornateMenu")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.surface = SceneSurface(profile,"menu")

    def addMenu(self, title):
        if isinstance(title,QMenu):
            return super().addMenu(title)
        menu = SceneMenu(self.surface.profile,self,title)
        super().addMenu(menu)
        return menu

    def apply_profile(self, profile):
        self.surface.set_profile(profile)
        for child in self.findChildren(SceneMenu):
            child.surface.set_profile(profile)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.surface.paint(painter,self.rect())
        painter.end()
        super().paintEvent(event)
