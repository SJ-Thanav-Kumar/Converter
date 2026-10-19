#Small reusable widgets: the drop zone and the preview box (images, animations and video)
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from PySide6.QtCore import QByteArray, QPoint, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStackedLayout, QVBoxLayout, QWidget,
)

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
        self.setMinimumHeight(120)
        self.setToolTip("Click to choose another file")

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
        self._preview = PreviewBox("", inline=True)      #shown instead of the texts once a file is loaded
        self._preview.hide()
        layout.addWidget(self._preview, stretch=1)

    def show_preview(self, path: Path, is_video: bool) -> bool:
        #draw the loaded file inside the box. False = cannot be drawn, the texts stay
        if not self._preview.show_file(path, is_video):
            self.clear_preview()
            return False
        self._title.hide()
        self._subtitle.hide()
        self._preview.show()
        return True

    def clear_preview(self) -> None:
        self._preview.hide()
        self._preview.show_text("")      #also stops any playing animation or video
        self._title.show()
        self._subtitle.show()

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


PREVIEW_MAX_PX = 1200      #frames are shrunk to this before drawing, so a 40 MP photo costs no more than a small one
ANIMATED_FORMATS = ("GIF", "WEBP", "AVIF")    #Pillow format names whose extra frames are a real animation


class _PixmapLabel(QLabel):
    #a label that keeps the full-size picture and redraws it scaled whenever it is resized

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._original = None   #the full-size QPixmap, kept so a resize rescales from the source

    def set_source(self, pixmap) -> None:
        self._original = pixmap
        self._rescale()

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


class PreviewBox(QWidget):
    #shows a file: a still image, an animation (gif/webp/avif), a video, or a line of text.
    #inline=True is the quiet version used inside the drop zone: no border, no buttons, no sound.
    #
    #Pictures are decoded with Pillow, the same library that wrote them, so every format the
    #converter can output can be previewed (Qt itself cannot read AVIF, and its WebP/HEIC support
    #depends on optional plugins). Video goes through Qt's own player.

    def __init__(self, placeholder: str, inline: bool = False) -> None:
        super().__init__()
        self._inline = inline
        self._stack = QStackedLayout(self)              #shows ONE of its pages at a time
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._label = _PixmapLabel(placeholder)         #page 0: text, still picture or animation frame
        self._label.setObjectName("Preview")
        self._label.setProperty("inline", inline)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._stack.addWidget(self._label)
        if inline:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)   #clicks/drops fall through to the drop zone
        else:
            self.setMinimumSize(260, 200)
        #ignored: the box takes whatever the layout gives it, and a big pixmap
        #can never force the window to grow.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self._timer = QTimer(self)                      #one tick per animation frame
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._next_frame)
        self._animation = None                          #the open Pillow image while a gif/webp/avif plays
        self._frame = 0

        self._player = None                             #QMediaPlayer, built the first time a video is shown
        self._video_page = None
        self._play_button = None
        self._sound_button = None

    def minimumSizeHint(self) -> QSize:
        #without this the video widget's own minimum size would make the box refuse to shrink with the window
        return QSize(0, 0)

    # ------------------------------------------------------------------ public
    def show_text(self, text: str) -> None:
        self._stop()
        self._label.clear()
        self._label.setText(text)
        self._stack.setCurrentWidget(self._label)

    def show_file(self, path: Path, is_video: bool) -> bool:
        #True if it is now on screen, False if there is nothing we can draw (the caller shows text)
        self._stop()
        return self._show_video(path) if is_video else self._show_picture(path)

    # ------------------------------------------------------------------ pictures and animations
    def _show_picture(self, path: Path) -> bool:
        try:
            #read the bytes once so no file handle stays open: the staged file is moved or deleted later
            img = Image.open(io.BytesIO(path.read_bytes()))
            animated = img.format in ANIMATED_FORMATS and getattr(img, "is_animated", False)
            if not animated:
                img = ImageOps.exif_transpose(img)      #bake in the camera rotation, like the converter does
            self._draw(img)
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
            return False
        self._stack.setCurrentWidget(self._label)
        if animated:
            self._animation, self._frame = img, 0
            self._timer.start(self._delay(img))
        return True

    @staticmethod
    def _delay(img: Image.Image) -> int:
        return max(20, int(img.info.get("duration", 100)))   #ms; tiny delays are clamped so the UI keeps breathing

    def _draw(self, img: Image.Image) -> None:
        frame = img.convert("RGBA")
        frame.thumbnail((PREVIEW_MAX_PX, PREVIEW_MAX_PX))
        qimage = QImage(frame.tobytes(), frame.width, frame.height, frame.width * 4, QImage.Format.Format_RGBA8888)
        self._label.set_source(QPixmap.fromImage(qimage))    #fromImage copies, so the bytes can go away

    def _next_frame(self) -> None:
        img = self._animation
        if img is None:
            return
        self._frame = (self._frame + 1) % img.n_frames      #wrap around: the preview loops forever
        img.seek(self._frame)
        self._draw(img)
        self._timer.start(self._delay(img))

    # ------------------------------------------------------------------ video
    def _show_video(self, path: Path) -> bool:
        if not self._ensure_player():
            return False
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
        self._stack.setCurrentWidget(self._video_page)
        if self._play_button is not None:
            self._play_button.setText("PAUSE")
        return True

    def _ensure_player(self) -> bool:
        if self._player is not None:
            return True
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget
        except ImportError:                              #a Qt install without multimedia: previews fall back to text
            return False
        self._video_page = QWidget()
        column = QVBoxLayout(self._video_page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        video = QVideoWidget()
        video.setMinimumSize(1, 1)
        column.addWidget(video, stretch=1)

        self._player = QMediaPlayer(self)
        audio = QAudioOutput(self)
        audio.setMuted(True)                             #never start blaring sound when a conversion finishes
        self._player.setAudioOutput(audio)
        self._player.setVideoOutput(video)
        self._player.setLoops(QMediaPlayer.Loops.Infinite)
        self._player.errorOccurred.connect(lambda *_: self.show_text("THIS VIDEO CANNOT BE PREVIEWED"))

        if not self._inline:                             #the output preview gets two small buttons
            row = QHBoxLayout()
            self._play_button = QPushButton("PAUSE")
            self._sound_button = QPushButton("SOUND OFF")
            for button in (self._play_button, self._sound_button):
                button.setObjectName("Flat")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                row.addWidget(button)
            row.addStretch()
            column.addLayout(row)

            def toggle_play() -> None:
                playing = self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
                self._player.pause() if playing else self._player.play()
                self._play_button.setText("PLAY" if playing else "PAUSE")

            def toggle_sound() -> None:
                audio.setMuted(not audio.isMuted())
                self._sound_button.setText("SOUND OFF" if audio.isMuted() else "SOUND ON")

            self._play_button.clicked.connect(toggle_play)
            self._sound_button.clicked.connect(toggle_sound)
        self._stack.addWidget(self._video_page)
        return True

    # ------------------------------------------------------------------ cleanup
    def _stop(self) -> None:
        #let go of everything: the timer, the open animation, and the video file
        self._timer.stop()
        self._animation = None
        self._label.set_source(None)
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())


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
