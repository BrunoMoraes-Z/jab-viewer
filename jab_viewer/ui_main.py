from __future__ import annotations

import fnmatch
import os
import re
import threading
import tkinter as tk
from collections import deque
from tkinter import filedialog
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk

# Workaround for JABWrapper logging bug when ROBOT_ARTIFACTS is unset
if 'ROBOT_ARTIFACTS' not in os.environ:
    os.environ['ROBOT_ARTIFACTS'] = os.path.join(os.getcwd(), 'artifacts')

from .highlight import HighlightOverlay
from .i18n import tr
from .jab_interface import JabInterface, JavaWindow
from .utils import ENV_DLL_KEY, ensure_wab_env


class JABViewerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title('JABViewer')
        self.geometry('1200x700')
        self.minsize(1000, 600)
        self.attributes('-topmost', True)

        dll_path = ensure_wab_env()
        if not dll_path:
            if not self._prompt_wab_path():
                messagebox.showerror(
                    tr('wab.title'),
                    tr('wab.path.not.set'),
                )
                self.destroy()
                return

        try:
            self.jab = JabInterface()
        except Exception as e:
            messagebox.showerror(
                tr('errors.jab_init.title'),
                tr('errors.jab_init.body', e=str(e)),
            )
            self.destroy()
            return

        self._windows: Dict[str, JavaWindow] = {}
        self._tree_nodes: Dict[str, object] = {}
        self._selected_hwnd: Optional[int] = None
        self._node_to_iid: Dict[int, str] = {}
        self._all_nodes: list[tuple[str, object]] = []

        # Async loading state
        self._is_loading: bool = False
        self._load_seq: int = 0
        self._loading_thread: Optional[threading.Thread] = None
        self._pending_insert: deque[Tuple[Optional[str], object]] = deque()

        self._build_ui()
        self._overlay = HighlightOverlay(self)
        self.reload_windows()

    def _prompt_wab_path(self) -> bool:
        ans = messagebox.askyesno(
            tr('wab.title'),
            tr('wab.prompt.set_now'),
        )
        if not ans:
            return False
        path = filedialog.askopenfilename(
            title=tr('file.select_wab'),
            filetypes=[
                (tr('filetypes.dll'), '*.dll'),
                (tr('filetypes.all'), '*.*'),
            ],
        )
        if not path:
            return False
        os.environ[ENV_DLL_KEY] = path
        return True

    def _build_ui(self) -> None:
        # Top bar
        top = ctk.CTkFrame(self)
        top.pack(side='top', fill='x', padx=8, pady=8)

        ctk.CTkLabel(top, text=tr('app.java.label')).pack(
            side='left', padx=(8, 6)
        )
        self.app_var = tk.StringVar()
        self.app_combo = ctk.CTkComboBox(
            top,
            variable=self.app_var,
            values=[],
            width=600,
            command=self._on_app_selected,
        )
        self.app_combo.pack(side='left', padx=(0, 8))

        self.reload_btn = ctk.CTkButton(
            top, text=tr('action.reload'), command=self.reload_windows
        )
        self.reload_btn.pack(side='left', padx=(0, 8))

        # Loading indicator (hidden by default)
        self.loading_text_var = tk.StringVar(value='')
        self.loading_label = ctk.CTkLabel(
            top, textvariable=self.loading_text_var
        )
        self.loading_pbar = ctk.CTkProgressBar(
            top,
            orientation='horizontal',
            mode='indeterminate',
        )

        # Main panes (resizable)
        paned = ttk.Panedwindow(self, orient='horizontal')
        paned.pack(side='top', fill='both', expand=True, padx=8, pady=(0, 8))
        self._paned = paned

        # Left: Treeview
        left = ctk.CTkFrame(paned)
        self._left_pane = left

        self.tree = ttk.Treeview(left, columns=('role', 'name'), show='tree')
        vsb = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        # Expand column to occupy width
        self.tree.column('#0', stretch=True, minwidth=150, anchor='w')

        def _resize_tree(event):
            try:
                sbw = vsb.winfo_width() or 18
                new_w = max(event.width - sbw - 6, 200)
                self.tree.column('#0', width=new_w)
            except Exception:
                pass

        left.bind('<Configure>', _resize_tree)

        # Right: Locator + Properties
        right = ctk.CTkFrame(paned, width=190)
        self._right_pane = right

        locator_frame = ctk.CTkFrame(right)
        locator_frame.pack(fill='x', padx=8, pady=(8, 0))
        ctk.CTkLabel(
            locator_frame,
            text=tr('ui.locator.title'),
            font=ctk.CTkFont(size=13, weight='bold'),
        ).pack(anchor='w')

        self.current_locator_var = tk.StringVar()
        self.current_locator_entry = ctk.CTkEntry(
            locator_frame,
            textvariable=self.current_locator_var,
            state='disabled',
        )
        self.current_locator_entry.pack(fill='x', pady=(4, 2))
        # Copy locator on any mouse click
        for ev in ('<Button>', '<Button-1>', '<Button-2>', '<Button-3>'):
            self.current_locator_entry.bind(ev, self._on_current_locator_click)

        search_row = ctk.CTkFrame(locator_frame)
        search_row.pack(fill='x')
        self.locator_input_var = tk.StringVar()
        self.locator_input = ctk.CTkEntry(
            search_row, textvariable=self.locator_input_var
        )
        self.locator_input.pack(side='left', fill='x', expand=True)
        # Trigger search on Enter key as well
        try:
            self.locator_input.bind(
                '<Return>', lambda e: self._on_locator_search()
            )
        except Exception:
            pass
        self.locator_btn = ctk.CTkButton(
            search_row,
            text=tr('ui.locator.search'),
            width=100,
            command=self._on_locator_search,
        )
        self.locator_btn.pack(side='left', padx=(6, 0))

        self.locator_msg = ctk.CTkLabel(
            locator_frame, text='', text_color='red'
        )
        self.locator_msg.pack(anchor='w', pady=(4, 0))

        ctk.CTkLabel(
            right,
            text=tr('ui.properties.title'),
            font=ctk.CTkFont(size=14, weight='bold'),
        ).pack(anchor='w', padx=8, pady=(8, 4))

        # Properties as a two‑column Treeview (keep cells; support wrapping via newlines)
        props_container = ctk.CTkFrame(right)
        props_container.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        # Use a dedicated style so changing rowheight doesn't affect the main tree
        self._props_tv_style = ttk.Style()
        self._props_rowheight_base = 22
        try:
            self._props_tv_style.configure(
                'Props.Treeview', rowheight=self._props_rowheight_base
            )
            # Add visible borders to improve cell perception
            self._props_tv_style.configure(
                'Props.Treeview', borderwidth=1, relief='solid'
            )
            self._props_tv_style.configure(
                'Props.Treeview.Heading', borderwidth=1, relief='solid'
            )
        except Exception:
            pass
        self.props_table = ttk.Treeview(
            props_container,
            columns=('prop', 'value'),
            show='headings',
            style='Props.Treeview',
        )
        self.props_table.heading('prop', text=tr('ui.properties.col.key'))
        self.props_table.heading('value', text=tr('ui.properties.col.value'))
        self.props_table.column('prop', width=260, anchor='w', stretch=True)
        self.props_table.column('value', width=380, anchor='w', stretch=True)
        vsb_props = ttk.Scrollbar(
            props_container, orient='vertical', command=self.props_table.yview
        )
        hsb_props = ttk.Scrollbar(
            props_container,
            orient='horizontal',
            command=self.props_table.xview,
        )
        self.props_table.configure(
            yscrollcommand=vsb_props.set, xscrollcommand=hsb_props.set
        )
        self.props_table.pack(side='left', fill='both', expand=True)
        vsb_props.pack(side='right', fill='y')
        hsb_props.pack(side='bottom', fill='x')
        # Copy value on left or right click
        self.props_table.bind('<Button-1>', self._on_props_click)
        self.props_table.bind('<Button-3>', self._on_props_click)
        # Tag used to separate each property group (lighter background)
        try:
            self.props_table.tag_configure('prop-sep', background='#ececec')
        except Exception:
            pass
        # Apply theme aware colors for the props table
        self._apply_props_theme()
        # Tooltip for property names
        self._props_tooltip_win = None
        self._props_tooltip_after = None
        self._props_tooltip_text = None
        self._props_tooltip_row = None
        self.props_table.bind('<Motion>', self._on_props_table_motion)
        self.props_table.bind('<Leave>', lambda e: self._hide_props_tooltip())
        self.props_table.bind('<Button>', lambda e: self._hide_props_tooltip())
        # Rewrap values on resize of the container
        props_container.bind(
            '<Configure>', lambda e: self._refresh_props_table_wrapped()
        )

        # Add panes with weights and min sizes (favor tree area)
        paned.add(left, weight=6)
        paned.add(right, weight=2)
        try:
            paned.paneconfigure(left, minsize=240)
            paned.paneconfigure(right, minsize=320)
        except Exception:
            pass
        # Nudge initial sash position so the tree occupies most of the width
        def _apply_initial_sash():
            try:
                w = paned.winfo_width()
                if w > 0:
                    paned.sashpos(0, int(w * 0.74))
            except Exception:
                pass

        self.after(150, _apply_initial_sash)

        # Data for props wrapping and copy
        self._props_rows_data: List[Tuple[str, str]] = []
        self._props_iid_to_raw: Dict[str, str] = {}

    # ----------------------
    # Internal helpers
    # ----------------------
    def _set_controls_enabled(self, enabled: bool) -> None:
        try:
            state = 'normal' if enabled else 'disabled'
            self.app_combo.configure(state=state)
            self.reload_btn.configure(state=state)
            self.locator_input.configure(state=state)
            self.locator_btn.configure(state=state)
        except Exception:
            pass

    def _set_loading(
        self, loading: bool, text_key: Optional[str] = None
    ) -> None:
        # Toggle loading indicator and controls
        self._is_loading = loading
        self._set_controls_enabled(not loading)
        if loading:
            txt = tr(text_key) if text_key else tr('ui.loading.default')
            self.loading_text_var.set(txt)
            try:
                # Pack right after reload button to keep UI pleasant
                self.loading_label.pack(side='left', padx=(0, 6))
                self.loading_pbar.pack(side='left')
                self.loading_pbar.start()
            except Exception:
                pass
        else:
            try:
                self.loading_pbar.stop()
                self.loading_label.pack_forget()
                self.loading_pbar.pack_forget()
            except Exception:
                pass

    # ----------------------
    # Actions
    # ----------------------
    def reload_windows(self) -> None:
        try:
            wins = self.jab.list_java_windows()
        except Exception as e:
            messagebox.showerror(
                tr('errors.list_windows.title'),
                tr('errors.list_windows.body', e=str(e)),
            )
            return
        prev_hwnd = self._selected_hwnd
        self._windows.clear()
        items = []
        hwnd_to_label: Dict[int, str] = {}
        for w in wins:
            label = f'{w.title}  (PID {w.pid})  [HWND {w.hwnd}]'
            self._windows[label] = w
            hwnd_to_label[w.hwnd] = label
            items.append(label)
        self.app_combo.configure(values=items)
        if prev_hwnd and prev_hwnd in hwnd_to_label:
            keep_label = hwnd_to_label[prev_hwnd]
            self.app_var.set(keep_label)
            try:
                self._start_loading_tree(prev_hwnd)
            except Exception:
                pass
        elif items:
            # If only one window is available, auto-select and load its tree
            self.app_var.set(items[0])
            if len(items) == 1:
                try:
                    win = self._windows.get(items[0])
                    if win:
                        try:
                            self.jab.focus_window(win.hwnd)
                        except Exception:
                            pass
                        self._start_loading_tree(win.hwnd)
                        self._selected_hwnd = win.hwnd
                except Exception:
                    pass

    def _on_app_selected(self, value: Optional[str] = None) -> None:
        if not value:
            value = self.app_var.get()
        if not value:
            return
        win = self._windows.get(value)
        if not win:
            return
        try:
            self.jab.focus_window(win.hwnd)
        except Exception:
            pass
        # Load tree asynchronously
        self._start_loading_tree(win.hwnd)
        self._selected_hwnd = win.hwnd

    def _start_loading_tree(self, hwnd: int) -> None:
        # Increase sequence to invalidate previous loads
        self._load_seq += 1
        seq = self._load_seq
        self._set_loading(True, 'ui.loading.tree')

        def worker():
            try:
                root = self.jab.set_root_from_hwnd(hwnd)
            except Exception as e:

                def on_err():
                    if seq != self._load_seq:
                        return
                    self._set_loading(False)
                    messagebox.showerror(
                        tr('errors.load_tree.title'),
                        tr('errors.load_tree.body', e=str(e)),
                    )

                self.after(0, on_err)
                return

            def on_ready():
                # Only proceed if still the latest request
                if seq != self._load_seq:
                    return
                self._populate_tree_async(root)

            self.after(0, on_ready)

        t = threading.Thread(target=worker, daemon=True)
        self._loading_thread = t
        t.start()

    def _populate_tree_async(self, root_node) -> None:
        # Reset tree and state
        self.tree.delete(*self.tree.get_children())
        self._tree_nodes.clear()
        self._node_to_iid.clear()
        self._all_nodes.clear()
        self._pending_insert.clear()

        def label_for(node) -> str:
            aci = node.context_info
            role = (aci.role or aci.role_en_US or '').strip()
            name = (aci.name or '').strip()
            return f'{role} | {name}' if name else role

        # Seed with root; parent_iid None means insert under ''
        self._pending_insert.append((None, root_node))

        BATCH = 300

        def process_batch():
            # If another load started, stop
            if not self._pending_insert:
                # Done
                self._set_loading(False)
                return
            count = 0
            try:
                while self._pending_insert and count < BATCH:
                    parent_iid, node = self._pending_insert.popleft()
                    text = label_for(node)
                    if parent_iid is None:
                        iid = self.tree.insert('', 'end', text=text)
                        # Open root by default
                        self.tree.item(iid, open=True)
                    else:
                        iid = self.tree.insert(parent_iid, 'end', text=text)
                        # Keep everything expanded for easier navigation
                        self.tree.item(iid, open=True)
                    self._tree_nodes[iid] = node
                    self._node_to_iid[id(node)] = iid
                    self._all_nodes.append((iid, node))
                    # Enqueue children
                    for child in getattr(node, 'children', []):
                        self._pending_insert.append((iid, child))
                    count += 1
                if not self._pending_insert:
                    # Select root if present
                    try:
                        root_iid = self._node_to_iid.get(id(root_node))
                        if root_iid:
                            self.tree.selection_set(root_iid)
                            self.tree.focus(root_iid)
                    except Exception:
                        pass
                    self._set_loading(False)
                else:
                    # Schedule next chunk
                    self.after(1, process_batch)
            except Exception:
                # Ensure loading indicator is cleared on errors
                self._set_loading(False)

        # Kick the async insertion
        self.after(0, process_batch)

    def _on_tree_select(self, event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        node = self._tree_nodes.get(iid)
        if not node:
            return
        x, y, w, h = self.jab.get_bounds(node)
        self._overlay.highlight((x, y, w, h))
        props = self.jab.collect_properties(node)
        self._render_props(props)
        self._update_current_locator(node)

    def _render_props(self, props: Dict[str, object]) -> None:
        # Capture data and (re)render table with wrapped values in cells
        self._props_rows_data.clear()
        self._props_iid_to_raw.clear()
        order = [
            'Name',
            'Description',
            'LocalizedRole',
            'Role',
            'LocalizedStates',
            'States',
            'IndexInParent',
            'Length',
            'Depth',
            'X',
            'Y',
            'W',
            'H',
            'Location',
            'AccessibleComponent',
            'AccessibleAction',
            'AccessibleSelection',
            'AccessibleText',
            'IsValueInterfaceAvailable',
            'IsActionInterfaceAvailable',
            'IsComponentInterfaceAvailable',
            'IsSelectionInterfaceAvailable',
            'IsTableInterfaceAvailable',
            'IsTextInterfaceAvailable',
            'IsHypertextInterfaceAvailable',
            'AvailableInterfaces',
            'IsVisible',
            'KeyBindings',
            'hWnd',
            'Parent',
            'RootElement',
            'Children',
            'VisibleDescendants',
            'VisibleDescendantsCount',
        ]
        for k in order:
            if k in props:
                val = props[k]
                sval = '' if val is None else str(val)
                self._props_rows_data.append((k, sval))
        self._refresh_props_table_wrapped()

    def _on_props_right_click(self, event) -> None:
        # Legacy handler kept for backward compatibility; no-op
        pass

    def _apply_props_theme(self) -> None:
        """Adjust props table colors based on CustomTkinter appearance mode.
        Keeps separators light in Light mode and moderately light in Dark mode.
        """
        try:
            mode = str(ctk.get_appearance_mode())
        except Exception:
            mode = 'Light'
        is_light = 'Light' in mode
        sep_bg = '#ececec' if is_light else '#3a3a3a'
        table_bg = '#fafafa' if is_light else '#2b2b2b'
        fg = '#111111' if is_light else '#f1f1f1'
        try:
            # Tag for first row of each property
            self.props_table.tag_configure(
                'prop-sep', background=sep_bg, foreground=fg
            )
            # Overall table background/foreground
            self._props_tv_style.configure(
                'Props.Treeview',
                background=table_bg,
                fieldbackground=table_bg,
                foreground=fg,
            )
            self._props_tv_style.configure(
                'Props.Treeview.Heading', foreground=fg
            )
        except Exception:
            pass

    def _on_props_table_motion(self, event) -> None:
        try:
            row_id = self.props_table.identify_row(event.y)
            col_id = self.props_table.identify_column(event.x)
            # Only show tooltip over the Property column (#1) and when there's text
            if not row_id or col_id != '#1':
                self._hide_props_tooltip()
                return
            vals = self.props_table.item(row_id).get('values') or []
            prop = vals[0] if len(vals) >= 1 else ''
            if not prop:
                self._hide_props_tooltip()
                return
            # If the tooltip is already showing the same row/text, do nothing
            if (
                self._props_tooltip_row == row_id
                and self._props_tooltip_text == prop
            ):
                return
            # Schedule showing tooltip after a short delay to avoid flicker
            self._hide_props_tooltip()

            def do_show():
                self._show_props_tooltip(
                    prop, event.x_root + 12, event.y_root + 14
                )

            self._props_tooltip_after = self.after(350, do_show)
            self._props_tooltip_row = row_id
            self._props_tooltip_text = prop
        except Exception:
            self._hide_props_tooltip()

    def _tooltip_colors(self) -> Tuple[str, str, str]:
        try:
            mode = str(ctk.get_appearance_mode())
        except Exception:
            mode = 'Light'
        if 'Dark' in mode:
            return ('#333333', '#ffffff', '#444444')  # bg, fg, border
        return ('#ffffe0', '#111111', '#d8d8a8')

    def _show_props_tooltip(self, text: str, x: int, y: int) -> None:
        try:
            bg, fg, bd = self._tooltip_colors()
            if self._props_tooltip_win is None:
                tw = tk.Toplevel(self)
                tw.wm_overrideredirect(True)
                tw.attributes('-topmost', True)
                lbl = tk.Label(
                    tw,
                    text=text,
                    background=bg,
                    foreground=fg,
                    borderwidth=1,
                    relief='solid',
                    padx=6,
                    pady=3,
                )
                lbl.pack()
                self._props_tooltip_win = tw
            else:
                # update text and colors
                for w in self._props_tooltip_win.winfo_children():
                    try:
                        w.configure(text=text, background=bg, foreground=fg)
                    except Exception:
                        pass
            self._props_tooltip_win.configure(
                background=bg, highlightbackground=bd
            )
            self._props_tooltip_win.wm_geometry(f'+{x}+{y}')
            self._props_tooltip_win.deiconify()
        except Exception:
            pass

    def _hide_props_tooltip(self) -> None:
        try:
            if self._props_tooltip_after is not None:
                try:
                    self.after_cancel(self._props_tooltip_after)
                except Exception:
                    pass
                self._props_tooltip_after = None
            if self._props_tooltip_win is not None:
                try:
                    self._props_tooltip_win.withdraw()
                except Exception:
                    pass
            self._props_tooltip_text = None
            self._props_tooltip_row = None
        except Exception:
            pass

    def _on_props_click(self, event) -> None:
        try:
            row_id = self.props_table.identify_row(event.y)
            col_id = self.props_table.identify_column(event.x)
            if not row_id or not col_id:
                return
            # Copy only when clicking the Value column (#2)
            if col_id != '#2':
                return
            raw = self._props_iid_to_raw.get(row_id)
            if raw is None:
                # fallback to displayed value
                item = self.props_table.item(row_id)
                vals = item.get('values') or []
                if len(vals) >= 2:
                    raw = str(vals[1])
                else:
                    return
            self.clipboard_clear()
            self.clipboard_append(str(raw))
            self.title(tr('window.title.copied_value'))
            self.after(900, lambda: self.title('JABViewer'))
        except Exception:
            pass

    # ----------------------
    # Props table wrapping helpers
    # ----------------------
    def _wrap_text_to_width(self, text: str, width_px: int, font_obj) -> str:
        text = text or ''
        if width_px <= 40:
            return text
        words = re.split(r'(\s+)', text)
        lines: List[str] = []
        cur = ''
        for w in words:
            if not w:
                continue
            candidate = cur + w
            if font_obj.measure(candidate) <= width_px:
                cur = candidate
                continue
            # If single token is too long, split by characters via binary search
            if cur:
                lines.append(cur)
                cur = ''
            while w and font_obj.measure(w) > width_px:
                lo, hi = 1, len(w)
                fit = 1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    if font_obj.measure(w[:mid]) <= width_px:
                        fit = mid
                        lo = mid + 1
                    else:
                        hi = mid - 1
                lines.append(w[:fit])
                w = w[fit:]
            cur = w
        if cur:
            lines.append(cur)
        return '\n'.join(lines)

    def _refresh_props_table_wrapped(self) -> None:
        try:
            if not hasattr(self, 'props_table') or not self._props_rows_data:
                return
            col_w = int(self.props_table.column('value', 'width') or 320)
            style_font = self._props_tv_style.lookup('Props.Treeview', 'font')
            try:
                font_obj = (
                    tkfont.nametofont(style_font)
                    if style_font
                    else tkfont.nametofont('TkDefaultFont')
                )
            except Exception:
                font_obj = tkfont.nametofont('TkDefaultFont')

            # Rebuild rows with wrapped value
            prev_sel = self.props_table.selection()
            self.props_table.delete(*self.props_table.get_children())
            self._props_iid_to_raw.clear()

            row_idx = 0
            for k, raw in self._props_rows_data:
                wrapped = self._wrap_text_to_width(
                    raw, max(40, col_w - 12), font_obj
                )
                parts = wrapped.split('\n') if wrapped else ['']
                for idx, seg in enumerate(parts):
                    key_cell = k if idx == 0 else ''
                    tags = ('prop-sep',) if idx == 0 else ()
                    iid = self.props_table.insert(
                        '', 'end', values=(key_cell, seg), tags=tags
                    )
                    self._props_iid_to_raw[iid] = raw
            # Keep a reasonable base row height; each additional wrapped line becomes a new item
            try:
                self._props_tv_style.configure(
                    'Props.Treeview', rowheight=self._props_rowheight_base
                )
            except Exception:
                pass
            if prev_sel:
                try:
                    self.props_table.selection_set(prev_sel)
                except Exception:
                    pass
        except Exception:
            pass

    # ----------------------
    # Locator helpers
    # ----------------------
    def _role_to_swing_type(self, role_en: str) -> Optional[str]:
        # Map common AccessibleRole names to Swing class names
        role = (role_en or '').strip().lower()
        mapping = {
            'frame': 'JFrame',
            'root pane': 'JRootPane',
            'panel': 'JPanel',
            'label': 'JLabel',
            'push button': 'JButton',
            'toggle button': 'JToggleButton',
            'check box': 'JCheckBox',
            'radio button': 'JRadioButton',
            'text': 'JTextField',
            'password text': 'JPasswordField',
            'text area': 'JTextArea',
            'combo box': 'JComboBox',
            'list': 'JList',
            'table': 'JTable',
            'tree': 'JTree',
            'tab page': 'JTabbedPane',
            'scroll pane': 'JScrollPane',
            'tool bar': 'JToolBar',
            'menu bar': 'JMenuBar',
            'menu': 'JMenu',
            'menu item': 'JMenuItem',
            'popup menu': 'JPopupMenu',
            'separator': 'JSeparator',
            'slider': 'JSlider',
            'spinner': 'JSpinner',
            'desktop pane': 'JDesktopPane',
            'internal frame': 'JInternalFrame',
            'split pane': 'JSplitPane',
            'progress bar': 'JProgressBar',
            'editor pane': 'JEditorPane',
            'formatted text': 'JFormattedTextField',
            'color chooser': 'JColorChooser',
            'file chooser': 'JFileChooser',
            'option pane': 'JOptionPane',
            'layered pane': 'JLayeredPane',
            'glass pane': 'GlassPane',
            'viewport': 'JViewport',
        }
        return mapping.get(role)

    def _update_current_locator(self, node) -> None:
        aci = node.context_info
        role = (aci.role_en_US or aci.role or '').strip()
        name = (aci.name or '').strip()

        # Build preferred locator compatible with RemoteSwingLibrary
        # Prefer text/name, then type; add index if duplicates
        swing_type = self._role_to_swing_type(role)

        def norm(s: str) -> str:
            return s.strip()

        def candidate_keys(n) -> Tuple[str, Optional[str]]:
            a = n.context_info
            r = (a.role_en_US or a.role or '').strip()
            nm = (a.name or '').strip()
            return nm, self._role_to_swing_type(r)

        # Collect duplicates matching same name + type
        matches: List[object] = []
        if name:
            for _iid, n in self._all_nodes:
                nm, t = candidate_keys(n)
                if norm(nm) == norm(name) and (
                    not swing_type or t == swing_type
                ):
                    matches.append(n)
        else:
            # No name; group by type only
            if swing_type:
                for _iid, n in self._all_nodes:
                    _nm, t = candidate_keys(n)
                    if t == swing_type:
                        matches.append(n)

        idx = 1
        for i, n in enumerate(matches, start=1):
            if n is node:
                idx = i
                break

        parts: List[str] = []
        if name:
            # RemoteSwingLibrary supports name=... and text=...
            parts.append(f'text={name}')
        if swing_type:
            parts.append(f'type={swing_type}')
        if not parts:
            # Fallback on role
            if role:
                parts.append(f'role={role}')
        if len(matches) > 1:
            parts.append(f'index={idx}')
        locator = ', '.join(parts)
        try:
            self.current_locator_entry.configure(state='normal')
            self.current_locator_var.set(locator)
            self.current_locator_entry.configure(state='disabled')
        except Exception:
            pass

    def _parse_locator(self, s: str):
        if not s:
            return None
        # Accept formats like: key=value, key: value; separated by comma/semicolon
        pattern = re.compile(
            r'(name|text|type|class|role|label|title|index)\s*[:=]', re.I
        )
        it = list(pattern.finditer(s))
        if not it:
            return None
        data: Dict[str, object] = {}
        for i, m in enumerate(it):
            key = m.group(1).lower()
            start = m.end()
            end = it[i + 1].start() if i + 1 < len(it) else len(s)
            raw = s[start:end].strip().strip(',;')
            # Strip optional quotes
            if (raw.startswith('"') and raw.endswith('"')) or (
                raw.startswith("'") and raw.endswith("'")
            ):
                raw = raw[1:-1]
            if key == 'index':
                try:
                    data[key] = int(raw)
                except Exception:
                    return None
            else:
                data[key] = raw
        return data

    def _find_by_locator(self, loc):
        if not isinstance(loc, dict):
            return None, 'invalid'
        role = loc.get('role')
        name = loc.get('name') or loc.get('text')
        typev = loc.get('type') or loc.get('class')
        label = loc.get('label')  # currently not evaluated
        title = loc.get('title')  # currently not evaluated
        index = loc.get('index')

        # At least one meaningful filter
        if not any([role, name, typev]):
            return None, 'invalid'

        def match_text(value: str, pat: str) -> bool:
            v = (value or '').strip()
            p = (pat or '').strip()
            if not p:
                return True
            if any(ch in p for ch in '*?[]'):
                return fnmatch.fnmatch(v.lower(), p.lower())
            # Default to startswith (case-insensitive)
            return v.lower().startswith(p.lower())

        def match_equals_ci(value: str, pat: str) -> bool:
            return (value or '').strip().lower() == (pat or '').strip().lower()

        def type_matches(role_en: str, type_pat: str) -> bool:
            # Accept both simple names and FQCN, match by simple name
            if not type_pat:
                return True
            simple = type_pat.split('.')[-1].strip()
            t = self._role_to_swing_type(role_en) or ''
            return t == simple

        matches: List[Tuple[str, object]] = []
        for iid, node in self._all_nodes:
            aci = node.context_info
            r = (aci.role_en_US or aci.role or '').strip()
            nm = (aci.name or '').strip()

            ok = True
            if role:
                ok = ok and match_equals_ci(r, str(role))
            if name:
                ok = ok and match_text(nm, str(name))
            if typev:
                ok = ok and type_matches(r, str(typev))
            # label/title not supported yet
            if ok:
                matches.append((iid, node))

        if not matches:
            return [], None

        if isinstance(index, int):
            # 1-based selection index across matches
            if 1 <= index <= len(matches):
                return [matches[index - 1]], None
            return [], None

        return matches, None

    def _on_current_locator_click(self, event=None):
        try:
            text = self.current_locator_var.get().strip()
            if not text:
                return
            self.clipboard_clear()
            self.clipboard_append(text)
            self.locator_msg.configure(
                text=tr('ui.locator.copied'), text_color='green'
            )
            self.after(
                1200,
                lambda: self.locator_msg.configure(text='', text_color='red'),
            )
        except Exception:
            pass

    def _select_iid(self, iid: str):
        try:
            pid = self.tree.parent(iid)
            while pid:
                self.tree.item(pid, open=True)
                pid = self.tree.parent(pid)
            self.tree.see(iid)
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self._on_tree_select(None)
        except Exception:
            pass

    def _on_locator_search(self) -> None:
        try:
            self.locator_msg.configure(text='')
            text = self.locator_input_var.get().strip()
            loc = self._parse_locator(text)
            if not loc:
                self.locator_msg.configure(text=tr('ui.locator.invalid'))
                return
            results, err = self._find_by_locator(loc)
            if err == 'invalid':
                self.locator_msg.configure(text=tr('ui.locator.invalid'))
                return
            if not results:
                self.locator_msg.configure(text=tr('ui.locator.not_found'))
                return
            if len(results) > 1:
                self.locator_msg.configure(
                    text=tr('ui.locator.many_found', n=len(results))
                )
                return
            iid, _node = results[0]
            self._select_iid(iid)
        except Exception:
            self.locator_msg.configure(text=tr('ui.locator.invalid'))
