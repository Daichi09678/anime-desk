"""Shared character palettes for companion, work panel, popup menus, and inputs."""

from pathlib import Path

def theme_styles(profile):
    c = profile.colours
    arrow = (Path(__file__).resolve().parent / "assets/icons" / f"chevron-{profile.id}.svg").as_posix()
    return f"""
        QDialog, #characterMenuHeader {{ background: {c['background']}; color: {c['text']}; }}
        #characterMenuHeader {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {c['surface']},stop:1 {c['hover']}); border-radius: 8px; }}
        #menuCharacterDescription {{ color: {c['muted']}; font-size: 11px; }}
        QLabel {{ color: {c['text']}; }}
        QCheckBox {{ color: {c['text']}; }}
        #speechBubble, #inputContainer, #attachmentBar, #needsPanel {{
            background-color: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px;
        }}
        #bubbleTitle, #bubbleText, #historyItemText, #needsTitle, #needsRowLabel {{ color: {c['text']}; }}
        #bubbleText {{ background-color: {c['surface']}; }}
        #bubbleText {{ font-family: Georgia, serif; font-size: 14px; }}
        #stateBadge, #loadingLabel, #historyEmpty, #ltmBadge, #runtimeLabel {{ color: {c['muted']}; }}
        #runtimeLabel {{ font-size: 10px; }}
        #emotionBadge {{ background-color: {c['hover']}; color: {c['text']}; border-color: {c['border']}; }}
        QPlainTextEdit, QTextBrowser, QComboBox, QDoubleSpinBox, QSpinBox {{
            background-color: {c['field']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: 7px;
            padding: 6px; selection-background-color: {c['selection']}; font-size: 13px;
        }}
        #chatInput {{ background: {c['field']}; color: {c['text']}; border: none; border-radius: 6px; }}
        #codexOutputBox {{ background: {c['field']}; color: {c['text']}; border-color: {c['border']}; }}
        #historyScroll, #historyContent {{ background: {c['surface']}; border-color: {c['border']}; }}
        #historyItemUser {{ background: {c['hover']}; }}
        #historyItemBot {{ background: {c['surface']}; }}
        QPushButton, #secondaryButton, #iconToggleBtn, #attachButton, #needsActionBtn, #needsCareAllBtn {{
            background-color: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
            border-radius: 6px; padding: 4px 7px; min-height: 18px;
        }}
        QPushButton:hover, #secondaryButton:hover, #iconToggleBtn:hover, #attachButton:hover {{ background-color: {c['hover']}; }}
        QPushButton:checked, #iconToggleBtn:checked {{ background-color: {c['selection']}; border-color: {c['accent']}; }}
        QPushButton:disabled {{ color: {c['muted']}; background: {c['background']}; }}
        #sendButton, #cancelButton {{ background: {c['accent']}; color: {c['field']}; border-radius: 7px; padding: 1px; }}
        #iconToggleBtn {{ padding: 0px; min-height: 0px; }}
        QComboBox {{ padding-right: 26px; min-height: 23px; }}
        QComboBox::drop-down {{ border: none; border-left: 1px solid {c['border']}; width: 22px; }}
        QComboBox::down-arrow {{ image: url("{arrow}"); width: 12px; height: 8px; }}
        QComboBox QAbstractItemView {{ background: {c['surface']}; color: {c['text']};
            border: 1px solid {c['border']}; selection-background-color: {c['selection']}; padding: 5px; }}
        QMenu {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
            border-radius: 10px; padding: 7px; font-size: 12px; }}
        #ornateMenu {{ background: transparent; border: none; padding: 11px; }}
        #bubbleTitle {{ font-family: Georgia, serif; font-size: 16px; font-weight: 600; }}
        QMenu::item {{ padding: 7px 26px 7px 25px; border-radius: 5px; margin: 1px 2px; }}
        QMenu::item:selected {{ background: {c['selection']}; color: {c['text']}; }}
        QMenu::item:disabled {{ color: {c['muted']}; }}
        QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px 9px; }}
        QMenu::indicator {{ width: 13px; height: 13px; }}
        QMenu::indicator:checked {{ background: {c['accent']}; border: 2px solid {c['surface']}; border-radius: 6px; }}
        QSplitter::handle {{ background: {c['border']}; height: 5px; }}
        QScrollBar:vertical {{ background: {c['surface']}; width: 8px; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 20px; border-radius: 4px; }}
    """
