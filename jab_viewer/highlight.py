from __future__ import annotations

import time
import threading
from typing import Optional, Tuple

import tkinter as tk


class HighlightOverlay:
    """Creates 4 thin topmost windows to form a red rectangle border."""

    def __init__(
        self, master: tk.Tk, color: str = '#ff2d2d', thickness: int = 3
    ) -> None:
        self.master = master
        self.color = color
        self.thickness = thickness
        self._lines = [self._create_line() for _ in range(4)]
        self._hide_timer: Optional[threading.Timer] = None

    def _create_line(self) -> tk.Toplevel:
        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        # Solid color background
        frame = tk.Frame(win, bg=self.color)
        frame.pack(fill='both', expand=True)
        win.withdraw()
        return win

    def _place(self, x: int, y: int, w: int, h: int) -> None:
        t = self.thickness
        # Top
        self._lines[0].geometry(f'{w}x{t}+{x}+{y}')
        # Bottom
        self._lines[1].geometry(f'{w}x{t}+{x}+{y + h - t}')
        # Left
        self._lines[2].geometry(f'{t}x{h}+{x}+{y}')
        # Right
        self._lines[3].geometry(f'{t}x{h}+{x + w - t}+{y}')
        for win in self._lines:
            win.deiconify()
            win.lift()

    def hide(self) -> None:
        if self._hide_timer:
            self._hide_timer.cancel()
            self._hide_timer = None
        for win in self._lines:
            win.withdraw()

    def highlight(
        self, bbox: Tuple[int, int, int, int], duration_ms: int = 1200
    ) -> None:
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            return
        self._place(x, y, w, h)
        if self._hide_timer:
            self._hide_timer.cancel()
        self._hide_timer = threading.Timer(duration_ms / 1000.0, self.hide)
        self._hide_timer.daemon = True
        self._hide_timer.start()
