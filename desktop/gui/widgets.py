#Small reusable widgets: the drop zone and the preview box
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QPoint, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QComboBox, QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout

from desktop.gui.theme import repolish

class DropZone(QFrame):
    #box that accepts dropped files
    #also click to choose button

    files_dropped = Signal(list)
    clicked = Signal()

    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("dragging", False)
        self.setProperty("loaded", False)
        self.setMinimumHeight(150)

        self._title = QLabel(title)
        self._title.setProperty("role", "dropTitle")
        self._subtitle = QLabel(subtitle)
        self._subtitle.setProperty("role", "muted")
        layout = QVBoxLayout(self)
        layout.addStretch()
        for label in (self._title, self._subtitle):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # let mouse events fall through the label to the frame underneath
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(label)
        layout.addStretch()

    def set_texts(self, title: str, subtitle: str) -> None:
        self._title.setText(title)
        self._subtitle.setText(subtitle)

    def set_loaded(self, loaded: bool) -> None:
        #a file is in, the dashed border cals down
        self.setProperty("loaded", loaded)
        repolish(self)

    def _set_dragging(self, value: bool) -> None:
        self.setProperty("dragging", value)
        repolish(self)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():     #files dragged from files(like the app) arrive as URLs
            event.acceptProposedAction()
            self._set_dragging(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_dragging(False)

    def dropEvent(self, event) -> None:
        self._set_dragging(False)
        urls = event.mimeData().urls()
        paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
        event.acceptProposedAction()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.clicked.emit()


class PreviewBox(QLabel):
    #shows an image scaled to fit, or a line of text when there is nothing to draw

    def __init__(self, placeholder: str) -> None:
        super().__init__(placeholder)
        self.setObjectName("Preview")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumSize(260, 200)
        #ignored: the box takes whatever the layout gives it, and a big pixmap
        #can never force the window to grow.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._original = None   #the full-size QPixmap, kept so a resize rescales from the source

    def show_text(self, text: str) -> None:
        self._original = None
        self.clear()
        self.setText(text)

    def show_image(self, path: Path) -> bool:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():     #Qt has no reader for this format, so return false
            return False
        self._original = pixmap
        self._rescale()
        return True

    def _rescale(self) -> None:
        if self._original is None:
            return
        fitted = self._original.scaled(
            self.contentsRect().size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(fitted)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()

# Logos as SVG text so no image files are needed. The fill colour is filled in at draw time.
GITHUB_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path fill="{c}" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>'
)
LINKEDIN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" fill="{c}"/>'
    '<g fill="{bg}"><rect x="2.6" y="6.2" width="2.2" height="7.2"/><circle cx="3.7" cy="3.8" r="1.35"/>'
    '<path d="M6.5 6.2h2.1v1c.4-.7 1.2-1.2 2.3-1.2 2.1 0 2.7 1.3 2.7 3.2v4.2h-2.2v-3.7c0-.9-.2-1.6-1.1-1.6-1 0-1.4.7-1.4 1.7v3.6H6.5z"/></g></svg>'
)


class LogoButton(QPushButton):
    #flat square button showing a logo; clicking opens a web address in the default browser

    def __init__(self, svg: str, url: str, tooltip: str, color: str, background: str, size: int = 20) -> None:
        super().__init__()
        self.setObjectName("Logo")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setFixedSize(size + 12, size + 12)
        self.setIconSize(QSize(size, size))
        renderer = QSvgRenderer(QByteArray(svg.format(c=color, bg=background).encode()))
        pixmap = QPixmap(size * 2, size * 2)           # drawn at 2x so it stays sharp on retina
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        self.setIcon(QIcon(pixmap))
        self.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))


class BelowComboBox(QComboBox):
    #macOS opens a combo's list on top of the box, centred on the current item. This one
    #always opens straight under the box, as wide as the box. Clicking elsewhere or choosing
    #an item closes it (Qt's normal popup behaviour).

    def showPopup(self) -> None:
        super().showPopup()
        popup = self.view().window()          # the floating frame that holds the list
        popup.setFixedWidth(self.width())
        popup.move(self.mapToGlobal(QPoint(0, self.height())))
