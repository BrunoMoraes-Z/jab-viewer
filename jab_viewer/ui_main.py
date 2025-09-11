from __future__ import annotations

import fnmatch
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Optional

import customtkinter as ctk

# Workaround for JABWrapper logging bug when ROBOT_ARTIFACTS is unset
if 'ROBOT_ARTIFACTS' not in os.environ:
    os.environ['ROBOT_ARTIFACTS'] = os.path.join(os.getcwd(), 'artifacts')

from .highlight import HighlightOverlay
from .jab_interface import JabInterface, JavaWindow
from .utils import ENV_DLL_KEY, ensure_wab_env
from .i18n import tr


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
        self.reload_btn.pack(side='left')

        # Main panes (resizable)
        paned = ttk.Panedwindow(self, orient='horizontal')
        paned.pack(side='top', fill='both', expand=True, padx=8, pady=(0, 8))

        # Left: Treeview
        left = ctk.CTkFrame(paned)

        self.tree = ttk.Treeview(left, columns=('role', 'name'), show='tree')
        vsb = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        # Expand column to occupy width
        self.tree.column('#0', stretch=True, minwidth=200, anchor='w')

        def _resize_tree(event):
            try:
                sbw = vsb.winfo_width() or 18
                new_w = max(event.width - sbw - 6, 200)
                self.tree.column('#0', width=new_w)
            except Exception:
                pass

        left.bind('<Configure>', _resize_tree)

        # Right: Locator + Properties
        right = ctk.CTkFrame(paned, width=380)

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
        self.props_text = ctk.CTkTextbox(right, wrap='word')
        self.props_text.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.props_text.bind('<Button-3>', self._on_props_right_click)

        # Add panes with weights and min sizes
        paned.add(left, weight=3)
        paned.add(right, weight=1)
        try:
            paned.paneconfigure(left, minsize=240)
            paned.paneconfigure(right, minsize=320)
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
                root = self.jab.set_root_from_hwnd(prev_hwnd)
                self._populate_tree(root)
            except Exception:
                pass
        elif items:
            self.app_var.set(items[0])

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
        try:
            root = self.jab.set_root_from_hwnd(win.hwnd)
        except Exception as e:
            messagebox.showerror(
                tr('errors.load_tree.title'),
                tr('errors.load_tree.body', e=str(e)),
            )
            return
        self._populate_tree(root)
        self._selected_hwnd = win.hwnd

    def _populate_tree(self, root_node) -> None:
        self.tree.delete(*self.tree.get_children())
        self._tree_nodes.clear()
        self._node_to_iid.clear()
        self._all_nodes.clear()

        def label_for(node) -> str:
            aci = node.context_info
            role = aci.role or aci.role_en_US or ''
            name = aci.name or ''
            return f'{role} | {name}' if name else role

        def insert_node(parent_id: str, node) -> None:
            text = label_for(node)
            iid = self.tree.insert(parent_id, 'end', text=text)
            self.tree.item(iid, open=True)
            self._tree_nodes[iid] = node
            self._node_to_iid[id(node)] = iid
            self._all_nodes.append((iid, node))
            for child in node.children:
                insert_node(iid, child)

        root_iid = self.tree.insert('', 'end', text=label_for(root_node))
        self.tree.item(root_iid, open=True)
        self._tree_nodes[root_iid] = root_node
        self._node_to_iid[id(root_node)] = root_iid
        self._all_nodes.append((root_iid, root_node))
        for child in root_node.children:
            insert_node(root_iid, child)
        self.tree.selection_set(root_iid)
        self.tree.focus(root_iid)

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
        self.props_text.configure(state='normal')
        self.props_text.delete('1.0', 'end')
        for k in [
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
        ]:
            if k in props:
                self.props_text.insert('end', f'{k}: {props[k]}\n')
        self.props_text.configure(state='disabled')

    def _on_props_right_click(self, event) -> None:
        try:
            text_widget = getattr(self.props_text, '_textbox', self.props_text)
            index = text_widget.index(f'@{event.x},{event.y}')
            line_no = int(str(index).split('.')[0])
            line_text = text_widget.get(f'{line_no}.0', f'{line_no}.0 lineend')
            if not line_text.strip():
                return
            value = (
                line_text.split(':', 1)[1].strip()
                if ':' in line_text
                else line_text.strip()
            )
            if value:
                self.clipboard_clear()
                self.clipboard_append(value)
                self.title(tr('window.title.copied_value'))
                self.after(900, lambda: self.title('JABViewer'))
        except Exception:
            pass

    # ----------------------
    # Locator helpers
    # ----------------------
    def _update_current_locator(self, node) -> None:
        aci = node.context_info
        role = (aci.role or aci.role_en_US or '').strip()
        name = (aci.name or '').strip()
        matches = []
        for _iid, n in self._all_nodes:
            ai = n.context_info
            r = (ai.role or ai.role_en_US or '').strip()
            nm = (ai.name or '').strip()
            if r.lower() == role.lower() and nm == name:
                matches.append(n)
        idx = 1
        for i, n in enumerate(matches, start=1):
            if n is node:
                idx = i
                break
        locator = f'role: {role}; name: {name}' if name else f'role: {role}'
        if len(matches) > 1:
            locator += f'; index: {idx}'
        try:
            self.current_locator_entry.configure(state='normal')
            self.current_locator_var.set(locator)
            self.current_locator_entry.configure(state='disabled')
        except Exception:
            pass

    def _parse_locator(self, s: str):
        if not s or ':' not in s:
            return None
        keys = re.compile(r'(?i)\b(role|name|index)\s*:')
        parts = list(keys.finditer(s))
        if not parts:
            return None
        data = {}
        for i, m in enumerate(parts):
            key = m.group(1).lower()
            start = m.end()
            end = parts[i + 1].start() if i + 1 < len(parts) else len(s)
            value = s[start:end].strip().strip(';,')
            data[key] = value
        if 'index' in data:
            try:
                data['index'] = int(data['index'])  # 1-based
            except Exception:
                return None
        return data

    def _find_by_locator(self, loc):
        role = loc.get('role') if loc else None
        name = loc.get('name') if loc else None
        index = loc.get('index') if loc else None
        if not role and not name:
            return None, 'invalid'
        matches = []
        for iid, node in self._all_nodes:
            aci = node.context_info
            r = (aci.role or aci.role_en_US or '').strip()
            nm = (aci.name or '').strip()
            ok = True
            if role:
                ok = ok and r.lower() == role.strip().lower()
            if name:
                pat = name.strip()
                if any(ch in pat for ch in '*?[]'):
                    ok = ok and fnmatch.fnmatch(nm.lower(), pat.lower())
                else:
                    ok = ok and nm.lower().startswith(pat.lower())
            if ok:
                matches.append((iid, node))
        if not matches:
            return [], None
        if index and role and name:
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
