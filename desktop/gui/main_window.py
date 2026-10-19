#main window. It knows about widgets and about ConversionManager, nothing else
from __future__ import annotations
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt
from PIL import Image
from PySide6.QtWidgets import (
    QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QSlider, QVBoxLayout, QWidget,
)
from core.conversion import CancellationToken, ConversionManager, ConversionResult, Status
from core.detection import detect_file, get_format
from desktop.gui import theme
from desktop.gui.widgets import GITHUB_SVG, LINKEDIN_SVG, BelowComboBox, DropZone, LogoButton, PreviewBox
from desktop.settings.store import AppSettings
from desktop.workers.conversion_worker import ConversionWorker

# >>> ELEMENT: every piece of visible text. Uppercase is typed in because QSS cannot do it
APP_NAME = "QUARRY"
FOOTER_NAME = "SJ THANAV KUMAR"      # centre of the footer
GITHUB_URL = "https://github.com/SJ-Thanav-Kumar"
LINKEDIN_URL = "www.linkedin.com/in/thanav-kumar-s-j-6025692b5"
ARROW_TEXT = "→"
DROP_TITLE = "DRAG & DROP YOUR FILE"
DROP_SUBTITLE = "OR CLICK TO CHOOSE"
PREVIEW_PLACEHOLDER = "NO OUTPUT YET"
BUTTON_TEXT = {"cancel": "CANCEL", "save": "SAVE OUTPUT", "discard": "DISCARD", "remove": "×", "default": "DEFAULT"}

# >>> ELEMENT: the main tabs: (mode id, label, text of the run button, hint under ADDITIONAL OPTIONS)
MODES = [
    ("convert", "CONVERT", "CONVERT FILE", "Keep default settings for best quality."),
    ("compress", "COMPRESS", "COMPRESS FILE", "Smaller file, lower quality. Image: JPEG, WebP, AVIF or HEIC. Video: re-encoded."),
]
# >>> ELEMENT: the secondary tabs: (kind id, label)
KINDS = [("image", "IMAGE"), ("video", "VIDEO")]

LOSSY_TARGETS = {"jpeg", "webp", "avif", "heic"}     # formats with a quality slider (same list as core.image.pillow_backend.LOSSY)
CODEC_CONVERT = [("KEEP", "keep"), ("H.264", "h264"), ("H.265", "h265")]
CODEC_COMPRESS = [("H.264", "h264"), ("H.265", "h265")]   # compressing always re-encodes
CRF_RANGE = (18, 40)       #FFmpeg CRF: lower = better quality and a bigger file
CRF_DEFAULT = 28
QUALITY_DEFAULT = 90       # JPEG / WebP / AVIF / HEIC quality slider (same as core.image.pillow_backend.JPEG_QUALITY)
# >>> ELEMENT: the video -> GIF sliders (min, max) and their starting values
GIF_FPS_RANGE, GIF_FPS_DEFAULT = (1, 30), 12
GIF_WIDTH_RANGE, GIF_WIDTH_DEFAULT = (80, 1080), 480
GIF_SECONDS_RANGE, GIF_SECONDS_DEFAULT = (0, 60), 10     # 0 = the whole video


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def describe(path: Path, format_id: str) -> str:
    #'JPG  •  2.4 MB  •  4032 × 3024' (dimensions only for images Qt can read)
    parts = [format_id.upper(), human_size(path.stat().st_size)]
    info = get_format(format_id)
    if info is not None and info.kind == "image":
        try:
            with Image.open(path) as img:        #Pillow reads only the header here, and knows every format we convert
                parts.append(f"{img.width} × {img.height}")
        except (OSError, ValueError):
            pass
    return "  •  ".join(parts)


class MainWindow(QMainWindow):
    def __init__(self, manager: ConversionManager, settings: AppSettings) -> None:
        super().__init__()
        self._manager = manager
        self._settings = settings

        self._mode = "convert"
        self._kind = "image"
        self._input: Optional[Path] = None        # the one file in the workspace
        self._input_format: Optional[str] = None  # canonical id from content detection
        self._result: Optional[ConversionResult] = None   # staged output waiting for SAVE
        self._staging: Optional[Path] = None      # temp folder holding it
        self._worker: Optional[ConversionWorker] = None
        self._cancel: Optional[CancellationToken] = None

        self.setWindowTitle(APP_NAME.title())
        self.resize(*theme.WINDOW_SIZE)
        self.setMinimumWidth(980)       # no fixed minimum height: the layout decides, so the extra GIF rows never get squeezed
        self._build_ui()
        self._set_mode("convert")

    # ------------------------------------------------------------------ building
    def _build_ui(self) -> None:
        root = QWidget()
        column = QVBoxLayout(root)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_top_bar())
        column.addWidget(self._build_nav_bar())

        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_workspace(), stretch=1)   # input -> arrow -> output
        column.addLayout(body, stretch=1)

        column.addWidget(self._build_footer())
        self.setCentralWidget(root)

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(36, 16, 36, 16)
        title = QLabel(APP_NAME)
        theme.style_title(title)
        row.addWidget(title)
        row.addStretch()
        return bar

    def _build_nav_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("NavBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._mode_group = QButtonGroup(self)    # exclusive: checking one unchecks the others
        self._mode_buttons: Dict[str, QPushButton] = {}
        for mode, label, _, _ in MODES:
            button = QPushButton(label)
            button.setObjectName("NavTab")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked, m=mode: self._set_mode(m))
            self._mode_group.addButton(button)
            self._mode_buttons[mode] = button
            row.addWidget(button, stretch=1)     # equal thirds, like the reference
        return bar

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(theme.SIDEBAR_WIDTH_PX)
        col = QVBoxLayout(side)
        col.setContentsMargins(0, 0, 1, 0)   # 1px right margin keeps the sidebar's border line visible
        col.setSpacing(0)
        self._kind_group = QButtonGroup(self)
        self._kind_buttons: Dict[str, QPushButton] = {}
        for kind, label in KINDS:
            button = QPushButton(label)
            button.setObjectName("SideTab")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked, k=kind: self._select_kind(k))
            self._kind_group.addButton(button)
            self._kind_buttons[kind] = button
            col.addWidget(button)
        col.addStretch()
        self._kind_buttons[self._kind].setChecked(True)
        return side

    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        theme.style_caption(label)
        return label

    @staticmethod
    def _rule() -> QFrame:
        rule = QFrame()
        rule.setObjectName("Rule")
        return rule

    def _build_workspace(self) -> QWidget:
        page = QWidget()
        row = QHBoxLayout(page)
        m = theme.WORKSPACE_MARGIN_PX
        row.setContentsMargins(m, m, m, m)
        row.setSpacing(24)
        row.addLayout(self._build_input_column(), stretch=5)
        arrow = QLabel(ARROW_TEXT)       # the whole "connection" between input and output
        arrow.setObjectName("Arrow")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(arrow)
        row.addLayout(self._build_output_column(), stretch=5)
        return page

    def _build_input_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(theme.COLUMN_GAP_PX)

        col.addWidget(self._caption("INPUT"))
        self._drop = DropZone(DROP_TITLE, DROP_SUBTITLE)
        self._drop.files_dropped.connect(self._on_files_dropped)
        self._drop.clicked.connect(self._browse)
        col.addWidget(self._drop, stretch=1)

        # the chosen file: name, metadata, and a small remove button
        col.addWidget(self._rule())
        file_row = QHBoxLayout()
        names = QVBoxLayout()
        names.setSpacing(2)
        self._file_name = QLabel("NO FILE SELECTED")
        self._file_meta = QLabel("")
        self._file_meta.setProperty("role", "muted")
        names.addWidget(self._file_name)
        names.addWidget(self._file_meta)
        self._remove_button = QPushButton(BUTTON_TEXT["remove"])
        self._remove_button.setObjectName("Flat")
        self._remove_button.clicked.connect(self._remove_clicked)
        file_row.addLayout(names, stretch=1)
        file_row.addWidget(self._remove_button, alignment=Qt.AlignmentFlag.AlignTop)
        col.addLayout(file_row)
        col.addWidget(self._rule())

        col.addWidget(self._caption("OUTPUT FORMAT"))
        self._target_combo = BelowComboBox()
        self._target_combo.currentIndexChanged.connect(self._on_target_changed)
        col.addWidget(self._target_combo)
        col.addWidget(self._rule())

        # operation settingseach row is shown or hidden by _on_target_changed
        options_head = QHBoxLayout()           # caption on the left, DEFAULT button on the right
        options_head.addWidget(self._caption("ADDITIONAL OPTIONS"))
        options_head.addStretch()
        self._default_button = QPushButton(BUTTON_TEXT["default"])
        self._default_button.setObjectName("Flat")
        self._default_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._default_button.clicked.connect(self._reset_options)
        options_head.addWidget(self._default_button)
        col.addLayout(options_head)
        self._quality_slider = QSlider(Qt.Orientation.Horizontal)
        self._quality_slider.setRange(1, 100)
        self._quality_slider.setValue(self._settings.jpeg_quality)
        self._quality_value = QLabel(str(self._settings.jpeg_quality))
        self._quality_slider.valueChanged.connect(self._on_quality_changed)
        self._quality_row = self._option_row("QUALITY", self._quality_slider, self._quality_value)

        self._codec_combo = BelowComboBox()
        self._codec_combo.currentIndexChanged.connect(self._on_codec_changed)
        self._codec_row = self._option_row("VIDEO CODEC", self._codec_combo)

        self._crf_slider = QSlider(Qt.Orientation.Horizontal)
        self._crf_slider.setRange(*CRF_RANGE)
        self._crf_slider.setValue(CRF_DEFAULT)
        self._crf_value = QLabel(str(CRF_DEFAULT))
        self._crf_slider.valueChanged.connect(lambda v: self._crf_value.setText(str(v)))
        self._crf_row = self._option_row("CRF (HIGHER = SMALLER)", self._crf_slider, self._crf_value)

        # video -> GIF only: frame rate, width and a length cap (a long video makes an enormous GIF)
        self._gif_fps_slider = QSlider(Qt.Orientation.Horizontal)
        self._gif_fps_slider.setRange(*GIF_FPS_RANGE)
        self._gif_fps_slider.setValue(GIF_FPS_DEFAULT)
        self._gif_fps_value = QLabel(str(GIF_FPS_DEFAULT))
        self._gif_fps_slider.valueChanged.connect(lambda v: self._gif_fps_value.setText(str(v)))
        self._gif_fps_row = self._option_row("GIF FRAMES PER SECOND", self._gif_fps_slider, self._gif_fps_value)

        self._gif_width_slider = QSlider(Qt.Orientation.Horizontal)
        self._gif_width_slider.setRange(*GIF_WIDTH_RANGE)
        self._gif_width_slider.setValue(GIF_WIDTH_DEFAULT)
        self._gif_width_value = QLabel(f"{GIF_WIDTH_DEFAULT} PX")
        self._gif_width_slider.valueChanged.connect(lambda v: self._gif_width_value.setText(f"{v} PX"))
        self._gif_width_row = self._option_row("GIF WIDTH", self._gif_width_slider, self._gif_width_value)

        self._gif_seconds_slider = QSlider(Qt.Orientation.Horizontal)
        self._gif_seconds_slider.setRange(*GIF_SECONDS_RANGE)
        self._gif_seconds_slider.setValue(GIF_SECONDS_DEFAULT)
        self._gif_seconds_value = QLabel(f"{GIF_SECONDS_DEFAULT} S")
        self._gif_seconds_slider.valueChanged.connect(
            lambda v: self._gif_seconds_value.setText(f"{v} S" if v else "ALL"))
        self._gif_seconds_row = self._option_row("GIF MAX LENGTH", self._gif_seconds_slider, self._gif_seconds_value)

        self._gif_rows = (self._gif_fps_row, self._gif_width_row, self._gif_seconds_row)
        for options_row in (self._quality_row, self._codec_row, self._crf_row, *self._gif_rows):
            col.addWidget(options_row)
        self._hint = QLabel("")
        self._hint.setProperty("role", "muted")
        self._hint.setWordWrap(True)
        col.addWidget(self._hint)

        # run + progress
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 100)
        col.addWidget(self._progress)
        buttons = QHBoxLayout()
        self._run_button = QPushButton("")
        self._run_button.setObjectName("Primary")      #styled by QPushButton#Primary
        self._run_button.clicked.connect(self._start)
        self._cancel_button = QPushButton(BUTTON_TEXT["cancel"])
        self._cancel_button.clicked.connect(self._cancel_clicked)
        buttons.addWidget(self._run_button, stretch=1)
        buttons.addWidget(self._cancel_button)
        col.addLayout(buttons)
        return col

    def _option_row(self, caption: str, *widgets: QWidget) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        label = QLabel(caption)
        label.setProperty("role", "muted")
        label.setMinimumWidth(170)
        row.addWidget(label)
        for widget in widgets:
            if isinstance(widget, QLabel):               # the number next to a slider: fixed room so it is never cut off
                widget.setMinimumWidth(64)
                widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(widget, stretch=1 if isinstance(widget, (QSlider, BelowComboBox)) else 0)
        return box

    def _build_output_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(theme.COLUMN_GAP_PX)
        col.addWidget(self._caption("OUTPUT PREVIEW"))
        self._preview = PreviewBox(PREVIEW_PLACEHOLDER)
        col.addWidget(self._preview, stretch=1)

        names = QVBoxLayout()
        names.setSpacing(2)
        self._out_name = QLabel("")
        self._out_meta = QLabel("")
        self._out_meta.setProperty("role", "muted")
        names.addWidget(self._out_name)
        names.addWidget(self._out_meta)
        col.addLayout(names)

        buttons = QHBoxLayout()
        self._save_button = QPushButton(BUTTON_TEXT["save"])
        self._save_button.setObjectName("Primary")
        self._save_button.clicked.connect(self._save)
        self._discard_button = QPushButton(BUTTON_TEXT["discard"])
        self._discard_button.clicked.connect(self._discard)
        buttons.addWidget(self._save_button, stretch=1)
        buttons.addWidget(self._discard_button)
        col.addLayout(buttons)
        return col

    def _build_footer(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Footer")
        row = QHBoxLayout(bar)
        row.setContentsMargins(36, 12, 36, 12)
        # three equal-stretch slots keep the name exactly centred
        self._status = QLabel("")      # messages only; empty while idle
        name = QLabel(FOOTER_NAME)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        theme.style_caption(name)
        logos = QHBoxLayout()
        logos.setSpacing(4)
        logos.addStretch()
        for svg, url, tip in ((GITHUB_SVG, GITHUB_URL, "GitHub"), (LINKEDIN_SVG, LINKEDIN_URL, "LinkedIn")):
            logos.addWidget(LogoButton(svg, url, tip, theme.FOREGROUND, theme.BACKGROUND))
        row.addWidget(self._status, stretch=1)
        row.addWidget(name)
        row.addLayout(logos, stretch=1)
        return bar

    # ------------------------------------------------------------------ status
    def _say(self, text: str, error: bool = False) -> None:
        self._status.setText(f"{'ERROR: ' if error else ''}{text}" if text else "")

    # ------------------------------------------------------------------ main tabs and side tabs
    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._mode_buttons[mode].setChecked(True)
        entry = next(m for m in MODES if m[0] == mode)
        self._run_button.setText(entry[2])
        self._hint.setText(entry[3])
        self._fill_codecs()
        self._refresh_targets()

    def _select_kind(self, kind: str) -> None:
        #IMAGE/VIDEO clicked.loaded file of the other kind has to go (after asking)
        if kind == self._kind:
            return
        if self._input is not None and not self._clear():
            self._kind_buttons[self._kind].setChecked(True)   # user said no: stay where we were
            return
        self._kind = kind
        self._kind_buttons[kind].setChecked(True)
        self._refresh_targets()

    # ------------------------------------------------------------------ adding a file
    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select a file to convert")
        if path:
            self._load_file(Path(path))

    def _on_files_dropped(self, raw_paths: List[str]) -> None:
        files = [Path(p) for p in raw_paths if Path(p).is_file()]
        if not files:
            self._say("DROP A FILE, NOT A FOLDER", error=True)
            return
        if len(files) > 1:
            self._say(f"{len(files)} FILES DROPPED, USING THE FIRST")
        self._load_file(files[0])

    def _load_file(self, path: Path) -> None:
        if self._worker is not None:
            return
        try:
            info = detect_file(path)     # reads the file's first bytes, not its extension
        except OSError as exc:
            self._say(f"CANNOT READ {path.name}: {exc}", error=True)
            return
        if info is None:
            self._say(f"{path.name}: UNRECOGNISED FORMAT", error=True)
            return
        if not self._manager.supported_targets(info.id):
            self._say(f"NO CONVERTER FOR {info.id.upper()}", error=True)
            return
        if self._result is not None and not self._confirm_discard():
            return
        self._drop_staging()

        self._input, self._input_format = path, info.id
        kind = get_format(info.id).kind
        if kind != self._kind:           # a video dropped on the IMAGE tab: follow the file
            self._kind = kind
            self._kind_buttons[kind].setChecked(True)
        self._file_name.setText(path.name)
        self._file_meta.setText(describe(path, info.id))
        self._drop.set_loaded(True)
        self._drop.set_texts(path.name, "CLICK TO CHOOSE ANOTHER")
        self._drop.show_preview(path, kind == "video")      # the file itself replaces the texts; if it cannot be drawn they stay
        self._reset_output()
        self._progress.setValue(0)
        self._say("")
        self._refresh_targets()

    def _remove_clicked(self) -> None:
        self._clear()

    def _clear(self) -> bool:
        #Empty the workspace. give False if the user refused to lose an unsaved result
        if self._worker is not None:
            return False
        if self._result is not None and not self._confirm_discard():
            return False
        self._drop_staging()
        self._input = self._input_format = None
        self._file_name.setText("NO FILE SELECTED")
        self._file_meta.setText("")
        self._drop.set_loaded(False)
        self._drop.clear_preview()
        self._drop.set_texts(DROP_TITLE, DROP_SUBTITLE)
        self._reset_output()
        self._progress.setValue(0)
        self._say("")
        self._refresh_targets()
        return True

    # ------------------------------------------------------------------ options
    def _fill_codecs(self) -> None:
        choices = CODEC_COMPRESS if self._mode == "compress" else CODEC_CONVERT
        self._codec_combo.blockSignals(True)
        self._codec_combo.clear()
        for text, value in choices:
            self._codec_combo.addItem(text, value)
        self._codec_combo.setCurrentIndex(max(self._codec_combo.findData(self._settings.video_codec), 0))
        self._codec_combo.blockSignals(False)

    def _targets_for_mode(self) -> List[str]:
        """What the output format dropdown offers: only routes core really has."""
        if self._input_format is None:
            return []
        targets = self._manager.supported_targets(self._input_format)
        if self._mode == "compress":
            if self._kind == "image":
                return [t for t in targets if t in LOSSY_TARGETS]       # only these have a quality setting
            return [t for t in targets if t == self._input_format]  # video: same container, re-encoded
        return targets

    def _refresh_targets(self) -> None:
        targets = self._targets_for_mode()
        previous = self._target_combo.currentData()
        self._target_combo.blockSignals(True)      # don't fire currentIndexChanged while refilling
        self._target_combo.clear()
        for target in targets:
            self._target_combo.addItem(target.upper(), target)
        self._target_combo.setCurrentIndex(max(self._target_combo.findData(previous), 0))
        self._target_combo.blockSignals(False)
        if self._input is not None and not targets:
            self._say(f"{self._input_format.upper()} HAS NO {self._mode.upper()} ROUTE YET", error=True)
        self._on_target_changed()

    def _on_target_changed(self) -> None:
        target = self._target_combo.currentData()
        info = get_format(target) if target else None
        is_video = info is not None and info.kind == "video"
        self._quality_row.setVisible(target in LOSSY_TARGETS)
        self._codec_row.setVisible(is_video)
        self._crf_row.setVisible(is_video and self._mode == "compress")
        to_gif = self._is_video_to_gif(target)
        for gif_row in self._gif_rows:
            gif_row.setVisible(to_gif)
        self._default_button.setVisible(any(row.isVisibleTo(self) for row in
                                            (self._quality_row, self._codec_row, self._crf_row, *self._gif_rows)))
        self._update_controls()

    def _is_video_to_gif(self, target: Optional[str]) -> bool:
        #the GIF sliders only make sense for a video going to GIF (a still image has no frame rate to choose)
        source = get_format(self._input_format) if self._input_format else None
        return target == "gif" and source is not None and source.kind == "video"

    def _reset_options(self) -> None:
        #DEFAULT: every option goes back to its starting position (hidden rows too, so nothing stale is left)
        self._quality_slider.setValue(QUALITY_DEFAULT)
        self._crf_slider.setValue(CRF_DEFAULT)
        self._gif_fps_slider.setValue(GIF_FPS_DEFAULT)
        self._gif_width_slider.setValue(GIF_WIDTH_DEFAULT)
        self._gif_seconds_slider.setValue(GIF_SECONDS_DEFAULT)
        self._codec_combo.setCurrentIndex(0)      # first entry of each list is the default: KEEP in CONVERT, H.264 in COMPRESS

    def _on_quality_changed(self, value: int) -> None:
        self._quality_value.setText(str(value))
        self._settings.jpeg_quality = value

    def _on_codec_changed(self) -> None:
        self._settings.video_codec = self._codec_combo.currentData()

    def _collect_options(self) -> Dict[str, Any]:
        options: Dict[str, Any] = {}
        target = self._target_combo.currentData()
        info = get_format(target) if target else None
        if target in LOSSY_TARGETS:
            options["quality"] = self._quality_slider.value()
        if info is not None and info.kind == "video":
            codec = self._codec_combo.currentData()
            if codec != "keep":
                options["video_codec"] = codec
            if self._mode == "compress":
                options["crf"] = self._crf_slider.value()
        if self._is_video_to_gif(target):
            options["gif_fps"] = self._gif_fps_slider.value()
            options["gif_width"] = self._gif_width_slider.value()
            options["gif_seconds"] = self._gif_seconds_slider.value()     # 0 means no cap, the backend understands that
        return options

    # ------------------------------------------------------------------ enabling controls
    def _update_controls(self) -> None:
        running = self._worker is not None
        has_target = self._target_combo.currentData() is not None
        staged = self._result is not None

        self._run_button.setEnabled(self._input is not None and has_target and not running)
        self._cancel_button.setEnabled(running)
        self._save_button.setEnabled(staged and not running)
        self._discard_button.setEnabled(staged and not running)
        self._remove_button.setEnabled(self._input is not None and not running)
        self._default_button.setEnabled(not running)
        for widget in (self._target_combo, self._quality_slider, self._codec_combo,
                       self._crf_slider, self._gif_fps_slider, self._gif_width_slider,
                       self._gif_seconds_slider, self._drop):
            widget.setEnabled(not running)
        for button in (*self._mode_buttons.values(), *self._kind_buttons.values()):
            button.setEnabled(not running)

    # ------------------------------------------------------------------ converting
    def _start(self) -> None:
        if self._input is None or self._worker is not None:
            return
        target = self._target_combo.currentData()
        self._drop_staging()          # a new run replaces an older staged result
        self._reset_output()
        self._staging = Path(tempfile.mkdtemp(prefix="converter-"))
        self._progress.setValue(0)

        self._cancel = CancellationToken()
        worker = ConversionWorker(
            self._manager, [str(self._input)], target, self._staging,
            self._collect_options(), self._cancel,
        )
        worker.file_progress.connect(self._on_file_progress)
        worker.file_done.connect(self._on_file_done)
        worker.finished.connect(self._on_worker_finished)   # built-in QThread signal
        self._worker = worker
        self._say(f"WORKING ON {self._input.name}")
        self._update_controls()
        worker.start()                                       # run() now executes on its own thread

    def _cancel_clicked(self) -> None:
        if self._cancel is not None:
            self._cancel.cancel()
            self._say("CANCELLING...")

    def _on_file_progress(self, position: int, fraction: float) -> None:
        if fraction >= 0:
            self._progress.setValue(int(fraction * 100))
            self._say(f"WORKING   {fraction:.0%}")

    def _on_file_done(self, position: int, result: ConversionResult) -> None:
        if result.ok:
            self._result = result
            self._show_output(result.output_path)
            self._progress.setValue(100)
            self._say(f"DONE   {result.output_path.name}   PRESS SAVE OUTPUT TO KEEP IT")
        elif result.status is Status.CANCELLED:
            self._progress.setValue(0)
            self._say("CANCELLED")
        else:
            self._progress.setValue(0)
            self._say(str(result.error), error=True)

    def _on_worker_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        self._worker = None
        self._cancel = None
        if self._result is None:
            self._drop_staging()
        self._update_controls()

    # ------------------------------------------------------------------ output side
    def _show_output(self, path: Path) -> None:
        format_id = get_format(path.suffix)
        self._out_name.setText(path.name)
        self._out_meta.setText(describe(path, format_id.id if format_id else path.suffix.lstrip(".")))
        is_video = format_id is not None and format_id.kind == "video"
        if not self._preview.show_file(path, is_video):     # images and animations via Pillow, video via Qt's player
            self._preview.show_text("NO PREVIEW FOR THIS FORMAT")

    def _reset_output(self) -> None:
        self._result = None
        self._out_name.setText("")
        self._out_meta.setText("")
        self._preview.show_text(PREVIEW_PLACEHOLDER)
        self._update_controls()

    # ------------------------------------------------------------------ accepting / rejecting the result
    def _save(self) -> None:
        if self._result is None:
            return
        staged = self._result.output_path
        # Suggest a free name so the default choice never replaces anything.
        suggested = ConversionManager.unique_path(self._settings.output_dir / staged.name)
        chosen, _ = QFileDialog.getSaveFileName(self, "Save output", str(suggested))
        if not chosen:
            return
        final = Path(chosen)
        if final.suffix == "":
            final = final.with_suffix(staged.suffix)
        if self._input is not None and final.resolve() == self._input.resolve():
            self._say("THAT WOULD REPLACE THE ORIGINAL. CHOOSE ANOTHER NAME", error=True)
            return
        try:
            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged), str(final))
        except OSError as exc:
            self._say(f"SAVE FAILED: {exc}", error=True)
            return
        self._settings.output_dir = final.parent
        self._result = None
        self._drop_staging()
        self._say(f"SAVED   {final}")
        self._update_controls()

    def _discard(self) -> None:
        self._drop_staging()
        self._reset_output()
        self._progress.setValue(0)
        self._say("OUTPUT DISCARDED")

    def _confirm_discard(self) -> bool:
        answer = QMessageBox.question(
            self, "UNSAVED OUTPUT", "The converted file has not been saved. Discard it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _drop_staging(self) -> None:
        """Delete the temp folder (and the staged result inside it)."""
        if self._staging is not None:
            shutil.rmtree(self._staging, ignore_errors=True)
            self._staging = None
        self._result = None

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._cancel is not None:
            self._cancel.cancel()
            self._worker.wait()          # blocks until run() returns
        if self._result is not None and not self._confirm_discard():
            event.ignore()
            return
        self._drop_staging()
        event.accept()