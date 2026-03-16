"""
UI 样式模块
集中管理所有 PyQt5 控件的样式表定义，保持 MainWindow 代码简洁。
"""


def group_box_style() -> str:
    """QGroupBox 通用样式。"""
    return """
        QGroupBox {
            font-size: 13px; font-weight: bold;
            border: 1px solid #ccc; border-radius: 5px;
            margin-top: 10px; padding-top: 15px;
        }
        QGroupBox::title {
            subcontrol-origin: margin; left: 10px; padding: 0 5px;
        }
    """


def drop_area_empty_style() -> str:
    """拖拽区域空状态样式。"""
    return """
        QLabel {
            border: 2px dashed #ccc; border-radius: 5px;
            padding: 15px; background-color: #f9f9f9; color: #666;
        }
        QLabel:hover { border-color: #2196F3; background-color: #f0f8ff; }
    """


def drop_area_ok_style(pad: str = "20px") -> str:
    """拖拽区域已加载配置的成功样式。"""
    return f"""
        QLabel {{
            border: 2px solid #4CAF50; border-radius: 5px;
            padding: {pad}; background-color: #f1f8f4; color: #4CAF50;
        }}
    """


def btn_green_style(small: bool = False, large: bool = False) -> str:
    """绿色按钮样式（启动类操作）。"""
    pad = "15px" if large else ("8px" if small else "10px")
    sz = "14px" if large else ("11px" if small else "12px")
    bold = "font-weight: bold;" if large else ""
    r = "5px" if large else "4px"
    return f"""
        QPushButton {{
            background-color: #4CAF50; color: white;
            padding: {pad}; font-size: {sz}; {bold}
            border-radius: {r}; border: none; outline: none;
        }}
        QPushButton:hover    {{ background-color: #45a049; }}
        QPushButton:disabled {{ background-color: #cccccc; color: #666666; }}
        QPushButton:focus    {{ outline: none; }}
    """


def btn_red_style(small: bool = False, large: bool = False) -> str:
    """红色按钮样式（停止类操作）。"""
    pad = "15px" if large else ("8px" if small else "10px")
    sz = "14px" if large else ("11px" if small else "12px")
    bold = "font-weight: bold;" if large else ""
    r = "5px" if large else "4px"
    return f"""
        QPushButton {{
            background-color: #f44336; color: white;
            padding: {pad}; font-size: {sz}; {bold}
            border-radius: {r}; border: none; outline: none;
        }}
        QPushButton:hover    {{ background-color: #da190b; }}
        QPushButton:disabled {{ background-color: #cccccc; color: #666666; }}
        QPushButton:focus    {{ outline: none; }}
    """


def btn_blue_style() -> str:
    """蓝色按钮样式（导入类操作）。"""
    return """
        QPushButton {
            background-color: #2196F3; color: white;
            padding: 8px; font-size: 11px;
            border-radius: 4px; border: none; outline: none;
        }
        QPushButton:hover { background-color: #1976D2; }
        QPushButton:focus { outline: none; }
    """


def btn_plain_style() -> str:
    """朴素按钮样式（编辑类操作）。"""
    return """
        QPushButton {
            padding: 8px; font-size: 11px;
            border: 1px solid #ccc; border-radius: 4px;
            background-color: white; outline: none;
        }
        QPushButton:hover { background-color: #f5f5f5; }
        QPushButton:focus { outline: none; border: 1px solid #2196F3; }
    """


def status_label_style(color: str) -> str:
    """状态标签样式。"""
    return f"color: {color}; padding: 5px; font-size: 12px;"


def readonly_line_edit_style() -> str:
    """只读输入框样式。"""
    return "QLineEdit { background-color: #f5f5f5; color: #666; }"


def readonly_spinbox_style() -> str:
    """只读 SpinBox 样式。"""
    return (
        "QSpinBox { background-color: #f5f5f5; color: #666; "
        "border: 1px solid #ddd; border-radius: 3px; padding: 4px; }"
    )


def editable_spinbox_style() -> str:
    """可编辑 SpinBox 样式。"""
    return "QSpinBox { border: 1px solid #ccc; border-radius: 3px; padding: 4px; }"