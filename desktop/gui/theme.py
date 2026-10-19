#styling file
from __future__ import annotations
from string import Template
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QLabel, QWidget

# >>> STYLE: colour palette. Mostly charcoal and near-black; white only for what matters.
BACKGROUND = "#0E0E0E"   # the window itself (near-black)
SURFACE = "#1B1B1B"      # charcoal: sidebar, buttons, dropdowns, the preview area
RAISED = "#262626"       # a charcoal one step lighter: hover on SURFACE
LINE = "#383838"         # thin outlines and separators
MUTED = "#8A8A8A"        # captions, hints, metadata, disabled controls
FOREGROUND = "#FFFFFF"   # important text: titles, filenames, button labels
OFFWHITE = "#E3E1DB"     # reserved for subtle contrast: the selected main tab and button hover
SIGNAL = FOREGROUND      # errors are written as "ERROR: ..." in this colour. Try "#FF6B4A" for red

# >>> STYLE: fonts. The first family in each list that is installed is used (see _pick_font)
FONT_UI_CHOICES = ["Inter", "FONTSPRING DEMO - Brutalista Black", "Futura", "Avenir Next", "Helvetica Neue"]
FONT_DISPLAY_CHOICES = FONT_UI_CHOICES    # title, tabs, buttons, captions
FONT_DATA_CHOICES = ["Futura", "Avenir Next", "Helvetica Neue"]
TEXT_SIZE_PX = 12
TITLE_SIZE_PT = 24
NAV_SIZE_PT = 26                          # CONVERT / COMPRESS
TITLE_LETTER_SPACING_PX = 1              # spacing of the title and tabs
CAPTION_LETTER_SPACING_PX = 2             # small spaced captions such as INPUT, OUTPUT FORMAT

# >>> STYLE: shape and spacing.
BORDER_PX = 1
RADIUS_PX = 0                # 0 = hard corners
PADDING_PX = 10              # inner space of buttons and dropdowns
DROPZONE_BORDER = "dashed"   # solid | dashed | dotted
SELECTED_UNDERLINE_PX = 3    # the bar under the selected main tab

# >>> STYLE: window layout (used by main_window.py)
WINDOW_SIZE = (1180, 840)
SIDEBAR_WIDTH_PX = 150      # the IMAGE / VIDEO column
WORKSPACE_MARGIN_PX = 40    # space around the input -> output workspace
COLUMN_GAP_PX = 12          # vertical gap between things inside one column
ARROW_SIZE_PX = 44          # the arrow between input and output


def _pick_font(choices: list[str]) -> str:
    """First installed family from the list; the last one is the fallback if none is installed."""
    installed = set(QFontDatabase.families())
    return next((name for name in choices if name in installed), choices[-1])


def style_title(label: QLabel, object_name: str = "Title") -> None:
    """Family, size and weight come from the QLabel#<object_name> rule below. QSS has no
    letter-spacing property, so that one setting is applied to the widget's QFont in code."""
    label.setObjectName(object_name)
    font = label.font()
    font.setLetterSpacing(font.SpacingType.AbsoluteSpacing, TITLE_LETTER_SPACING_PX)
    label.setFont(font)


def style_caption(label: QLabel) -> None:
    """Small muted, letter-spaced heading such as INPUT or OUTPUT FORMAT."""
    label.setProperty("role", "caption")
    font = label.font()
    font.setLetterSpacing(font.SpacingType.AbsoluteSpacing, CAPTION_LETTER_SPACING_PX)
    label.setFont(font)


def repolish(widget: QWidget) -> None:
    """Qt only evaluates [property="value"] selectors when a widget is styled; force a re-style."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


# One block of Qt Style Sheet text. $names are filled in by build_stylesheet().
# Selector cheat-sheet:  QPushButton = every button   #NavTab = the widget whose objectName is
# "NavTab"   [role="muted"] = widgets with property role=muted   :checked / :hover = widget state
_QSS = Template("""
QWidget {
    background-color: $background;
    color: $foreground;
    font-family: "$font_data";
    font-size: ${text_px}px;
}
QLabel { background: transparent; }
QLabel[role="muted"] { color: $muted; }
QLabel[role="caption"] { color: $muted; font-size: 11px; font-family: "$font_display"; }

QLabel#Title {
    font-family: "$font_display";
    background: transparent;
}
QLabel#Title { font-size: ${title_pt}pt; }
QLabel#Arrow { color: $muted; font-size: ${arrow_px}px; }

/* thin separators: a 1px high widget */
QFrame#Rule { background-color: $line; border: none; min-height: 1px; max-height: 1px; }
QWidget#TopBar, QWidget#Footer { background-color: $background; }
QWidget#TopBar { border-bottom: ${border}px solid $line; }
QWidget#Footer { border-top: ${border}px solid $line; }
QWidget#NavBar { border-bottom: ${border}px solid $line; }
QWidget#Sidebar { border-right: ${border}px solid $line; }

/* main navigation: CONVERT | COMPRESS */
QPushButton#NavTab {
    font-family: "$font_display";
    font-size: ${nav_pt}pt;
    background-color: $background;
    border: none;
    border-bottom: ${underline}px solid transparent;
    padding: 14px 0 10px 0;
}
QPushButton#NavTab:hover { background-color: $surface; }
QPushButton#NavTab:checked {
    background-color: $offwhite;
    color: $background;
    border-bottom: ${underline}px solid $background;
}

/* secondary navigation: IMAGE | VIDEO */
QPushButton#SideTab {
    border: none;
    border-left: ${underline}px solid transparent;
    background-color: $background;
    text-align: left;
    padding: 18px 20px;
}
QPushButton#SideTab:hover { background-color: $surface; }
QPushButton#SideTab:checked { background-color: $surface; border-left: ${underline}px solid $foreground; }

QPushButton {
    font-family: "$font_display";
    border: ${border}px solid $line;
    border-radius: ${radius}px;
    padding: ${padding}px 22px;
    background-color: $surface;
}
QPushButton:hover { border-color: $foreground; }
QPushButton:pressed { background-color: $raised; }
QPushButton:disabled { color: $muted; border-color: $line; background-color: $background; }
QPushButton#Primary { border-color: $foreground; }
QPushButton#Primary:hover { background-color: $offwhite; color: $background; }
QPushButton#Primary:disabled { border-color: $line; background-color: $background; color: $muted; }
QPushButton#Flat { border: none; background: transparent; padding: 4px 8px; color: $muted; }
QPushButton#Flat:hover { color: $foreground; }
QPushButton#Logo { border: none; background: transparent; padding: 0; }
QPushButton#Logo:hover { background-color: $surface; }

QComboBox {
    border: ${border}px solid $line;
    border-radius: ${radius}px;
    background-color: $surface;
    padding: ${padding}px 14px;
}
QComboBox:hover { border-color: $foreground; }
QComboBox:disabled { color: $muted; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid $foreground;
}
QComboBox QAbstractItemView {
    border: ${border}px solid $line;
    background-color: $surface;
    selection-background-color: $offwhite;
    selection-color: $background;
    outline: 0;
}

QProgressBar { border: none; background-color: $line; max-height: 3px; }
QProgressBar::chunk { background-color: $foreground; }

QSlider::groove:horizontal { height: ${border}px; background: $muted; }
QSlider::handle:horizontal {
    background: $foreground;
    width: 12px;
    height: 12px;
    margin: -6px 0;
    border-radius: ${handle_radius}px;
}

#DropZone { border: ${border}px $dropzone_border $muted; background-color: $background; }
#DropZone:hover { border-color: $foreground; }
#DropZone[dragging="true"] { border: ${border}px solid $foreground; background-color: $surface; }
#DropZone[loaded="true"] { border-color: $line; }
#DropZone QLabel[role="dropTitle"] { font-size: 13px; }

QLabel#Preview { border: ${border}px solid $line; background-color: $surface; color: $muted; }
QLabel#Preview[inline="true"] { border: none; background-color: transparent; }   /* the preview inside the drop zone */

QToolTip { background-color: $surface; color: $foreground; border: ${border}px solid $line; }
QMessageBox { background-color: $background; }
""")


def build_stylesheet() -> str:
    return _QSS.substitute(
        background=BACKGROUND,
        surface=SURFACE,
        raised=RAISED,
        line=LINE,
        muted=MUTED,
        foreground=FOREGROUND,
        offwhite=OFFWHITE,
        font_data=_pick_font(FONT_DATA_CHOICES),
        font_display=_pick_font(FONT_DISPLAY_CHOICES),
        text_px=TEXT_SIZE_PX,
        title_pt=TITLE_SIZE_PT,
        nav_pt=NAV_SIZE_PT,
        arrow_px=ARROW_SIZE_PX,
        border=BORDER_PX,
        radius=RADIUS_PX,
        handle_radius=min(RADIUS_PX, 6),
        padding=PADDING_PX,
        underline=SELECTED_UNDERLINE_PX,
        dropzone_border=DROPZONE_BORDER,
    )