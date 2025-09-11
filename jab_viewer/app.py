from __future__ import annotations

import customtkinter as ctk

try:
    # When executed as a package module: python -m jab_viewer.app
    from .ui_main import JABViewerApp  # type: ignore
except Exception:
    # When frozen or run as a script entry by PyInstaller
    from jab_viewer.ui_main import JABViewerApp  # type: ignore


def main() -> None:
    ctk.set_default_color_theme('blue')
    ctk.set_appearance_mode('system')
    app = JABViewerApp()
    app.mainloop()


if __name__ == '__main__':
    main()
