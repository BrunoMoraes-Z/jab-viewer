from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import win32con
import win32gui
import win32process
import win32api

from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.context_tree import ContextNode
from JABWrapper.jab_types import AccessibleContextInfo, JavaObject


@dataclass
class JavaWindow:
    hwnd: int
    title: str
    pid: int


class JabInterface:
    """Facade for Java Access Bridge operations."""

    def __init__(self) -> None:
        self._jab = JavaAccessBridgeWrapper(ignore_callbacks=True)
        self._lock = threading.RLock()
        self._current_vm: Optional[ctypes.c_long] = None
        self._current_ctx: Optional[JavaObject] = None
        self._current_root: Optional[ContextNode] = None

    # -------------------------------
    # Windows enumeration and control
    # -------------------------------
    def list_java_windows(self) -> List[JavaWindow]:
        windows: List[JavaWindow] = []

        def enum_cb(hwnd, lParam):
            # Skip invisible/minimized windows
            if not win32gui.IsWindowVisible(hwnd):
                return True
            try:
                # filter Java windows via JAB DLL
                is_java = bool(self._jab._wab.isJavaWindow(hwnd))  # type: ignore[attr-defined]
            except Exception:
                is_java = False
            if is_java:
                length = win32gui.GetWindowTextLength(hwnd)
                title = win32gui.GetWindowText(hwnd) if length > 0 else ''
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                except Exception:
                    pid = 0
                windows.append(JavaWindow(hwnd=hwnd, title=title, pid=pid))
            return True

        win32gui.EnumWindows(enum_cb, None)
        # Deduplicate by hwnd and sort by title
        unique: Dict[int, JavaWindow] = {w.hwnd: w for w in windows}
        return sorted(unique.values(), key=lambda w: (w.title.lower(), w.hwnd))

    def focus_window(self, hwnd: int) -> None:
        try:
            # Only restore if minimized (do not unmaximize)
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception:
            pass
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            # Try force foreground
            try:
                thread_id = win32api.GetCurrentThreadId()
                target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
                win32process.AttachThreadInput(thread_id, target_thread, True)
                win32gui.SetForegroundWindow(hwnd)
            finally:
                try:
                    win32process.AttachThreadInput(
                        thread_id, target_thread, False
                    )
                except Exception:
                    pass

    # -------------------------------
    # JAB context / tree
    # -------------------------------
    def set_root_from_hwnd(self, hwnd: int) -> ContextNode:
        vm_id, ctx = self._jab.get_accessible_context_from_hwnd(
            wintypes.HWND(hwnd)
        )
        self._current_vm = vm_id
        self._current_ctx = ctx
        self._jab.set_context(vm_id, ctx)
        self._jab.set_hwnd(wintypes.HWND(hwnd))
        # Build full tree (can be heavy on very large apps)
        self._current_root = ContextNode(
            self._jab, ctx, self._lock, ancestry=0, parse_children=True
        )
        return self._current_root

    def get_root(self) -> Optional[ContextNode]:
        return self._current_root

    def get_hwnd_for_context(self, context: JavaObject) -> int:
        return int(self._jab.get_hwnd_from_accessible_context(context))

    def get_context_info(self, context: JavaObject) -> AccessibleContextInfo:
        return self._jab.get_context_info(context)

    # -------------------------------
    # Helpers to extract properties
    # -------------------------------
    def collect_properties(self, node: ContextNode) -> Dict[str, object]:
        aci = node.context_info
        props: Dict[str, object] = {}

        # Basic
        props['Name'] = aci.name
        props['Description'] = aci.description
        props['LocalizedRole'] = aci.role
        props['Role'] = aci.role_en_US
        props['LocalizedStates'] = aci.states
        props['States'] = aci.states_en_US
        props['IndexInParent'] = aci.indexInParent
        props['Length'] = (
            getattr(node.text, 'char_count', None)
            if hasattr(node, 'text')
            else None
        )
        props['Depth'] = node.ancestry
        props['X'] = aci.x
        props['Y'] = aci.y
        props['W'] = aci.width
        props['H'] = aci.height
        props['Location'] = (aci.x, aci.y, aci.width, aci.height)

        # Interface flags
        props['AccessibleComponent'] = bool(aci.accessibleComponent)
        props['AccessibleAction'] = bool(aci.accessibleAction)
        props['AccessibleSelection'] = bool(aci.accessibleSelection)
        props['AccessibleText'] = bool(aci.accessibleText)
        props['AccessibleValue'] = bool(aci.accessibleValue)

        # Mirrored "Is*InterfaceAvailable" keys
        props['IsComponentInterfaceAvailable'] = props['AccessibleComponent']
        props['IsActionInterfaceAvailable'] = props['AccessibleAction']
        props['IsSelectionInterfaceAvailable'] = props['AccessibleSelection']
        props['IsTextInterfaceAvailable'] = props['AccessibleText']
        props['IsValueInterfaceAvailable'] = props['AccessibleValue']

        # Table / Hypertext availability via probing
        is_table = False
        is_htext = False
        try:
            _ = self._jab.get_accessible_table_info(node.context)
            is_table = True
        except Exception:
            pass
        try:
            _ = self._jab.get_accessible_hypertext(node.context)
            is_htext = True
        except Exception:
            pass
        props['IsTableInterfaceAvailable'] = is_table
        props['IsHypertextInterfaceAvailable'] = is_htext

        available = []
        for key in [
            'IsComponentInterfaceAvailable',
            'IsActionInterfaceAvailable',
            'IsSelectionInterfaceAvailable',
            'IsTextInterfaceAvailable',
            'IsValueInterfaceAvailable',
            'IsTableInterfaceAvailable',
            'IsHypertextInterfaceAvailable',
        ]:
            if props.get(key):
                available.append(
                    key.replace('Is', '').replace('InterfaceAvailable', '')
                )
        props['AvailableInterfaces'] = ', '.join(available)

        # Visibility
        props['IsVisible'] = 'showing' in (
            aci.states_en_US or ''
        ) or 'visible' in (aci.states_en_US or '')

        # Key bindings
        try:
            kb = node.keybinds.list_key_bindings()
            props['KeyBindings'] = '; '.join(kb) if kb else None
        except Exception:
            props['KeyBindings'] = None

        # Window handle
        try:
            props['hWnd'] = self.get_hwnd_for_context(node.context)
        except Exception:
            props['hWnd'] = None

        # Parent/Root summaries
        try:
            parent_ctx = self._jab.get_accessible_parent_from_context(
                node.context
            )
            parent_info = self._jab.get_context_info(parent_ctx)
            props['Parent'] = (
                f'{parent_info.role} | {parent_info.name}'
                if parent_ctx
                else None
            )
        except Exception:
            props['Parent'] = None

        try:
            root = self._current_root
            if root:
                props[
                    'RootElement'
                ] = f'{root.context_info.role} | {root.context_info.name}'
        except Exception:
            props['RootElement'] = None

        # Children counts
        props['Children'] = aci.childrenCount
        props['VisibleDescendants'] = node.visible_children_count
        props['VisibleDescendantsCount'] = node.visible_children_count

        return props

    def get_bounds(self, node: ContextNode) -> Tuple[int, int, int, int]:
        aci = node.context_info
        return aci.x, aci.y, aci.width, aci.height
