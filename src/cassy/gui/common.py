"""Shared Tkinter building blocks and theme for the cassy GUIs."""

from __future__ import annotations

import csv
import json
import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Callable

# ── Palette (matches the CASSY logo) ──────────────────────────────────────────

BG = "#F4F6F9"
SURFACE = "#FFFFFF"
HEADER_BG = "#E8ECF2"
HOVER_BG = "#EEF2F7"
BORDER = "#D5DBE3"
TEXT = "#1B2430"
MUTED = "#6B7684"
NAVY = "#131C2A"
ACCENT = "#F5A623"
ACCENT_ACTIVE = "#FFC24B"
ACCENT_PRESSED = "#D98E0F"
SELECT_BG = "#FFE3A8"
STRIPE = "#F8FAFC"
LOG_BG = "#0E1622"
LOG_FG = "#C7D0DD"
SUCCESS = "#2E9E5B"
ERROR = "#D64545"

_FONT_CANDIDATES = (
    "Segoe UI",
    "Noto Sans",
    "DejaVu Sans",
    "Liberation Sans",
    "Helvetica",
)
_ICON_PATH = os.path.join(os.path.dirname(__file__), "icon.png")
_icon_image: tk.PhotoImage | None = None


# ── Theme ─────────────────────────────────────────────────────────────────────


def set_icon(window: tk.Wm) -> None:
    global _icon_image
    try:
        if _icon_image is None:
            _icon_image = tk.PhotoImage(file=_ICON_PATH)
        window.iconphoto(True, _icon_image)
    except Exception:
        pass


def _pick_font_family(root: tk.Misc) -> str:
    available = set(tkfont.families(root))
    for family in _FONT_CANDIDATES:
        if family in available:
            return family
    return tkfont.nametofont("TkDefaultFont").actual("family")


def apply_theme(root: tk.Tk) -> None:
    """Apply the CASSY look (clam-based, no extra dependencies)."""
    style = ttk.Style(root)
    style.theme_use("clam")

    family = _pick_font_family(root)
    for name in (
        "TkDefaultFont",
        "TkTextFont",
        "TkMenuFont",
        "TkHeadingFont",
        "TkCaptionFont",
        "TkTooltipFont",
    ):
        try:
            tkfont.nametofont(name).configure(family=family, size=10)
        except tk.TclError:
            pass
    tkfont.nametofont("TkHeadingFont").configure(weight="bold")
    bold = (family, 10, "bold")
    linespace = tkfont.nametofont("TkDefaultFont").metrics("linespace")

    root.configure(background=BG)
    for pattern, value in (
        ("*Toplevel.background", BG),
        ("*Menu.background", SURFACE),
        ("*Menu.foreground", TEXT),
        ("*Menu.activeBackground", SELECT_BG),
        ("*Menu.activeForeground", TEXT),
        ("*Menu.relief", "flat"),
        ("*Listbox.background", SURFACE),
        ("*Listbox.foreground", TEXT),
        ("*Listbox.selectBackground", SELECT_BG),
        ("*Listbox.selectForeground", TEXT),
        ("*Listbox.highlightThickness", 1),
        ("*Listbox.highlightColor", ACCENT),
        ("*Listbox.highlightBackground", BORDER),
        ("*Listbox.relief", "flat"),
        ("*TCombobox*Listbox.selectBackground", SELECT_BG),
        ("*TCombobox*Listbox.selectForeground", TEXT),
    ):
        root.option_add(pattern, value)

    style.configure(
        ".",
        background=BG,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BG,
        darkcolor=BG,
        troughcolor=HEADER_BG,
        focuscolor=ACCENT,
        selectbackground=SELECT_BG,
        selectforeground=TEXT,
        fieldbackground=SURFACE,
        insertcolor=TEXT,
    )
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("TLabelframe", background=BG, bordercolor=BORDER, padding=8)
    style.configure("TLabelframe.Label", background=BG, foreground=NAVY, font=bold)

    style.configure(
        "TButton",
        background=SURFACE,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=SURFACE,
        darkcolor=SURFACE,
        padding=(10, 4),
    )
    style.map(
        "TButton",
        background=[("pressed", HEADER_BG), ("active", HOVER_BG)],
        bordercolor=[("active", ACCENT)],
    )
    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground=NAVY,
        bordercolor=ACCENT,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        font=bold,
    )
    style.map(
        "Accent.TButton",
        background=[("pressed", ACCENT_PRESSED), ("active", ACCENT_ACTIVE)],
        bordercolor=[("pressed", ACCENT_PRESSED), ("active", ACCENT_ACTIVE)],
        lightcolor=[("pressed", ACCENT_PRESSED), ("active", ACCENT_ACTIVE)],
        darkcolor=[("pressed", ACCENT_PRESSED), ("active", ACCENT_ACTIVE)],
    )

    style.configure(
        "TEntry",
        fieldbackground=SURFACE,
        bordercolor=BORDER,
        lightcolor=SURFACE,
        darkcolor=SURFACE,
        padding=3,
    )
    style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])
    style.configure(
        "TCombobox",
        fieldbackground=SURFACE,
        background=SURFACE,
        bordercolor=BORDER,
        lightcolor=SURFACE,
        darkcolor=SURFACE,
        arrowcolor=NAVY,
        padding=3,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", SURFACE)],
        selectbackground=[("readonly", SURFACE)],
        selectforeground=[("readonly", TEXT)],
        bordercolor=[("focus", ACCENT)],
        background=[("active", HOVER_BG)],
    )
    style.configure(
        "TCheckbutton", background=BG, indicatorbackground=SURFACE, indicatormargin=2
    )
    style.map(
        "TCheckbutton",
        background=[("active", BG)],
        indicatorbackground=[("selected", ACCENT), ("pressed", HEADER_BG)],
    )

    style.configure(
        "TNotebook", background=BG, bordercolor=BORDER, tabmargins=(6, 6, 6, 0)
    )
    style.configure(
        "TNotebook.Tab",
        background=HEADER_BG,
        foreground=MUTED,
        bordercolor=BORDER,
        lightcolor=HEADER_BG,
        padding=(14, 6),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", SURFACE), ("active", HOVER_BG)],
        foreground=[("selected", NAVY)],
        lightcolor=[("selected", ACCENT)],
    )

    style.configure(
        "Treeview",
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground=TEXT,
        bordercolor=BORDER,
        rowheight=int(linespace * 1.9),
    )
    style.map(
        "Treeview",
        background=[("selected", SELECT_BG)],
        foreground=[("selected", TEXT)],
    )
    style.configure(
        "Treeview.Heading",
        background=HEADER_BG,
        foreground=NAVY,
        bordercolor=BORDER,
        lightcolor=HEADER_BG,
        darkcolor=HEADER_BG,
        padding=(6, 5),
        font=bold,
    )
    style.map("Treeview.Heading", background=[("active", BORDER)])

    style.configure(
        "TScrollbar",
        background=HEADER_BG,
        troughcolor=BG,
        bordercolor=BG,
        lightcolor=HEADER_BG,
        darkcolor=HEADER_BG,
        arrowcolor=MUTED,
    )
    style.map("TScrollbar", background=[("active", BORDER)])
    style.configure("TSeparator", background=BORDER)

    style.configure(
        "GridHeader.TLabel", background=HEADER_BG, foreground=NAVY, font=bold, padding=4
    )
    style.configure("GridKey.TLabel", background=SURFACE, foreground=TEXT, padding=3)


# ── Small widget helpers ──────────────────────────────────────────────────────


def make_toolbar(
    parent: tk.Misc,
    buttons: list[tuple[str, Callable[[], object]]],
    accent_first: bool = True,
) -> ttk.Frame:
    toolbar = ttk.Frame(parent)
    toolbar.pack(fill="x", padx=8, pady=(8, 6))
    for i, (text, command) in enumerate(buttons):
        ttk.Button(
            toolbar,
            text=text,
            command=command,
            style="Accent.TButton" if accent_first and i == 0 else "TButton",
        ).pack(side="left", padx=(0, 4))
    return toolbar


def make_tree(
    parent: tk.Misc,
    columns: tuple[str, ...],
    headings: dict[str, str],
    col_width: int = 110,
) -> ttk.Treeview:
    frm = ttk.Frame(parent)
    frm.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    vsb = ttk.Scrollbar(frm, orient="vertical")
    hsb = ttk.Scrollbar(frm, orient="horizontal")
    tree = ttk.Treeview(
        frm,
        columns=columns,
        show="headings",
        selectmode="extended",
        yscrollcommand=vsb.set,
        xscrollcommand=hsb.set,
    )
    vsb.config(command=tree.yview)
    hsb.config(command=tree.xview)
    for col in columns:
        tree.heading(col, text=headings.get(col, col), anchor="center")
        tree.column(col, width=col_width, minwidth=60, anchor="center")
    tree.tag_configure("odd", background=STRIPE)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    frm.rowconfigure(0, weight=1)
    frm.columnconfigure(0, weight=1)
    return tree


def fill_tree(tree: ttk.Treeview, rows: list[tuple]) -> None:
    tree.delete(*tree.get_children())
    for i, values in enumerate(rows):
        tree.insert("", "end", values=values, tags=("odd",) if i % 2 else ())


def bind_mousewheel(canvas: tk.Canvas) -> None:
    """Scroll *canvas* with the mouse wheel while the pointer is over it."""

    def _on_wheel(evt: tk.Event) -> None:
        if evt.num == 4:
            canvas.yview_scroll(-1, "units")
        elif evt.num == 5:
            canvas.yview_scroll(1, "units")
        else:
            canvas.yview_scroll(
                -1 * (evt.delta // 120 or (1 if evt.delta > 0 else -1)), "units"
            )

    def _enter(_evt: tk.Event) -> None:
        canvas.bind_all("<MouseWheel>", _on_wheel)
        canvas.bind_all("<Button-4>", _on_wheel)
        canvas.bind_all("<Button-5>", _on_wheel)

    def _leave(_evt: tk.Event) -> None:
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    canvas.bind("<Enter>", _enter)
    canvas.bind("<Leave>", _leave)


# ── Base dialog ───────────────────────────────────────────────────────────────


class Dialog(tk.Toplevel):
    """Modal dialog base class."""

    def __init__(self, parent: tk.Widget, title: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: dict | None = None
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_window()
        self._body = ttk.Frame(self)
        self._body.pack(padx=12, pady=(12, 4), fill="both", expand=True)
        self._build()
        self._add_buttons()
        self.bind("<Escape>", lambda _e: self._on_close())
        self.wait_visibility()
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window()

    # -- subclasses override these -------------------------------------------

    def _configure_window(self) -> None:
        """Called before _build. Override to adjust window size / resizability."""

    def _build(self) -> None:
        raise NotImplementedError

    def _collect(self) -> dict | None:
        """Validate and return result dict, or None to keep the dialog open."""
        raise NotImplementedError

    # -- private ---------------------------------------------------------------

    def _add_buttons(self) -> None:
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(
            frm, text="OK", width=8, style="Accent.TButton", command=self._on_ok
        ).pack(side="right", padx=(4, 0))
        ttk.Button(frm, text="Cancel", width=8, command=self._on_close).pack(
            side="right"
        )

    def _on_close(self) -> None:
        self.destroy()

    def _on_ok(self) -> None:
        result = self._collect()
        if result is not None:
            self.result = result
            self.destroy()

    def destroy(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        super().destroy()

    # -- field helpers ---------------------------------------------------------

    @staticmethod
    def _row(frame, label: str, row: int) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)

    def _entry(self, frame, label: str, row: int, default: str = "") -> tk.StringVar:
        self._row(frame, label, row)
        var = tk.StringVar(value=default)
        ttk.Entry(frame, textvariable=var, width=30).grid(
            row=row, column=1, padx=6, pady=3
        )
        return var

    def _combo(
        self,
        frame,
        label: str,
        row: int,
        values: list[str],
        default: str = "",
    ) -> tk.StringVar:
        self._row(frame, label, row)
        var = tk.StringVar(value=default or (values[0] if values else ""))
        ttk.Combobox(
            frame, textvariable=var, values=values, state="readonly", width=28
        ).grid(row=row, column=1, padx=6, pady=3)
        return var

    def _analysis_field(
        self,
        frame,
        label: str,
        row: int,
        analyses: list[str],
        default: str = "",
        optional: bool = False,
    ) -> tk.StringVar:
        """Dropdown of available analyses; free entry if none could be read."""
        if not analyses:
            return self._entry(frame, label, row, default)
        values = ["", *analyses] if optional else analyses
        return self._combo(frame, label, row, values, default)

    def _check(
        self, frame, label: str, row: int, default: bool = False
    ) -> tk.BooleanVar:
        self._row(frame, label, row)
        var = tk.BooleanVar(value=default)
        ttk.Checkbutton(frame, variable=var).grid(
            row=row, column=1, sticky="w", padx=6, pady=3
        )
        return var

    @staticmethod
    def _multiselect(
        frame, label: str, row: int, items: list[str], selected: list[str]
    ) -> tk.Listbox:
        ttk.Label(frame, text=label).grid(
            row=row, column=0, sticky="nw", padx=6, pady=3
        )
        wrapper = ttk.Frame(frame)
        wrapper.grid(row=row, column=1, padx=6, pady=3)
        sb = ttk.Scrollbar(wrapper, orient="vertical")
        lb = tk.Listbox(
            wrapper,
            selectmode="multiple",
            yscrollcommand=sb.set,
            height=5,
            width=30,
            exportselection=False,
        )
        sb.config(command=lb.yview)
        lb.pack(side="left")
        sb.pack(side="left", fill="y")
        for i, name in enumerate(items):
            lb.insert("end", name)
            if name in selected:
                lb.selection_set(i)
        return lb

    def _file_entry(
        self,
        frame,
        label: str,
        row: int,
        default: str = "",
        filetypes: list | None = None,
    ) -> tk.StringVar:
        """Entry + browse button for a file path."""
        self._row(frame, label, row)
        var = tk.StringVar(value=default)
        wrap = ttk.Frame(frame)
        wrap.grid(row=row, column=1, padx=6, pady=3)
        ttk.Entry(wrap, textvariable=var, width=26).pack(side="left")
        ft = filetypes or [("All files", "*.*")]
        ttk.Button(
            wrap,
            text="…",
            width=3,
            command=lambda: var.set(
                filedialog.askopenfilename(filetypes=ft) or var.get()
            ),
        ).pack(side="left", padx=2)
        return var


# ── Table tabs ────────────────────────────────────────────────────────────────


class TableTab(ttk.Frame):
    """Tab with a Treeview table and Add / Edit / Delete toolbar."""

    _COLUMNS: tuple[str, ...]
    _HEADINGS: dict[str, str]
    _LIST_KEY: str
    _ITEM_NAME = "item"
    _COL_WIDTH = 110

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        super().__init__(parent)
        self._project = project
        self._build()

    def _build(self) -> None:
        toolbar = make_toolbar(
            self, [("Add", self._add), ("Edit", self._edit), ("Delete", self._delete)]
        )
        self._extra_toolbar(toolbar)
        self._tree = make_tree(self, self._COLUMNS, self._HEADINGS, self._COL_WIDTH)
        self._tree.bind("<Double-1>", lambda _e: self._edit())
        self._tree.bind("<Delete>", lambda _e: self._delete())
        self.bind("<Map>", lambda _e: self.refresh())
        self.refresh()

    def _extra_toolbar(self, toolbar: ttk.Frame) -> None:
        """Override to add extra toolbar buttons."""

    def _row_values(self, item: dict) -> tuple:
        raise NotImplementedError

    def _list(self) -> list:
        return self._project[self._LIST_KEY]

    def refresh(self) -> None:
        fill_tree(self._tree, [self._row_values(item) for item in self._list()])

    def _selected_index(self) -> int | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._tree.index(sel[0])

    def _selected_indices(self) -> list[int]:
        return sorted(self._tree.index(item) for item in self._tree.selection())

    def _add(self) -> None:
        raise NotImplementedError

    def _edit(self) -> None:
        raise NotImplementedError

    def _delete(self) -> None:
        indices = self._selected_indices()
        if not indices:
            messagebox.showwarning(
                "Selection", f"Select a {self._ITEM_NAME} to delete."
            )
            return
        if len(indices) == 1:
            prompt = f"Delete the selected {self._ITEM_NAME}?"
        else:
            prompt = f"Delete the {len(indices)} selected {self._ITEM_NAME}s?"
        if not messagebox.askyesno("Delete", prompt):
            return
        items = self._list()
        for idx in reversed(indices):
            items.pop(idx)
        self.refresh()


class GroupedTableTab(TableTab):
    """Table of the items belonging to the group picked in a combobox."""

    _GROUP_LABEL = "Group"

    def _group_names(self) -> list[str]:
        raise NotImplementedError

    def _items_of(self, group: str) -> list:
        raise NotImplementedError

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Label(top, text=f"{self._GROUP_LABEL}:").pack(side="left", padx=(0, 6))
        self._group_var = tk.StringVar()
        self._group_combo = ttk.Combobox(
            top, textvariable=self._group_var, state="readonly", width=28
        )
        self._group_combo.pack(side="left")
        self._group_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_table())
        super()._build()

    def _current_group(self) -> str | None:
        return self._group_var.get() or None

    def _list(self) -> list:
        group = self._current_group()
        return self._items_of(group) if group else []

    def refresh(self) -> None:
        names = self._group_names()
        self._group_combo["values"] = names
        if self._group_var.get() not in names:
            self._group_var.set(names[0] if names else "")
        self._refresh_table()

    def _refresh_table(self) -> None:
        super().refresh()


# ── Run tab ───────────────────────────────────────────────────────────────────


class RunTab(ttk.Frame):
    """Run options (fatigue, materials folder, output folder) and Run button."""

    _RUN_LABEL = "Run Assessment"
    # (project key that must be non-empty, warning title, warning message)
    _REQUIRED: tuple[str, str, str]

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        super().__init__(parent)
        self._project = project
        self._build()

    def _prepare(self) -> Callable[[], None]:
        """Build the configuration and return the function that runs it."""
        raise NotImplementedError

    def _build(self) -> None:
        opts = self._project["run_options"]
        frm = ttk.LabelFrame(self, text="Run Options")
        frm.pack(padx=20, pady=20, fill="x")

        ttk.Label(frm, text="Fatigue assessment").grid(
            row=0, column=0, sticky="w", padx=10, pady=6
        )
        self._fatigue = tk.BooleanVar(value=opts.get("fatigue", False))
        ttk.Checkbutton(frm, variable=self._fatigue).grid(
            row=0, column=1, sticky="w", padx=10, pady=6
        )

        self._matlib = tk.StringVar(value=opts.get("matlib_path", ""))
        self._root_dir = tk.StringVar(value=opts.get("root_dir", ""))
        for row, (label, var, title) in enumerate(
            (
                (
                    "Additional materials folder",
                    self._matlib,
                    "Select additional materials folder",
                ),
                ("Output root folder", self._root_dir, "Select output root folder"),
            ),
            start=1,
        ):
            ttk.Label(frm, text=label).grid(
                row=row, column=0, sticky="w", padx=10, pady=6
            )
            ttk.Entry(frm, textvariable=var, width=50).grid(
                row=row, column=1, padx=10, pady=6, sticky="ew"
            )
            ttk.Button(
                frm,
                text="Browse…",
                command=lambda v=var, t=title: self._browse_dir(v, t),
            ).grid(row=row, column=2, padx=4, pady=6)
        frm.columnconfigure(1, weight=1)

        run_frm = ttk.LabelFrame(self, text="Run")
        run_frm.pack(padx=20, pady=(0, 20), fill="x")
        ttk.Button(
            run_frm,
            text=self._RUN_LABEL,
            style="Accent.TButton",
            command=self._run_assessment,
        ).pack(padx=10, pady=10)
        self._status_var = tk.StringVar(value="")
        ttk.Label(run_frm, textvariable=self._status_var, style="Muted.TLabel").pack(
            padx=10, pady=(0, 6)
        )

    @staticmethod
    def _browse_dir(var: tk.StringVar, title: str) -> None:
        d = filedialog.askdirectory(title=title)
        if d:
            var.set(d)

    def _run_assessment(self) -> None:
        self.sync()
        if not self._root_dir.get().strip():
            messagebox.showwarning(
                "No root folder", "Please set the output root folder first."
            )
            return
        key, title, msg = self._REQUIRED
        if not self._project.get(key):
            messagebox.showwarning(title, msg)
            return

        self._status_var.set("Building configuration…")
        try:
            work = self._prepare()
        except Exception as exc:
            messagebox.showerror("Configuration Error", str(exc))
            self._status_var.set("Configuration error.")
            return

        log_win = LogWindow(self.winfo_toplevel())
        handler = TextHandler(log_win)
        root_logger = logging.getLogger()
        old_level = root_logger.level
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        self._status_var.set("Running…")

        def _work() -> None:
            try:
                from tqdm.contrib.logging import logging_redirect_tqdm

                with logging_redirect_tqdm():
                    work()
                self.after(0, lambda: self._status_var.set("Completed successfully."))
                self.after(
                    0,
                    lambda: log_win.set_done(
                        True, "Assessment completed successfully."
                    ),
                )
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self._status_var.set(f"Error: {msg}"))
                self.after(0, lambda: log_win.set_done(False, f"Error: {msg}"))
            finally:
                root_logger.removeHandler(handler)
                root_logger.setLevel(old_level)

        threading.Thread(target=_work, daemon=True).start()

    def sync(self) -> None:
        opts = self._project["run_options"]
        opts["fatigue"] = self._fatigue.get()
        opts["matlib_path"] = self._matlib.get().strip()
        opts["root_dir"] = self._root_dir.get().strip()

    def load_from_project(self) -> None:
        opts = self._project["run_options"]
        self._fatigue.set(opts.get("fatigue", False))
        self._matlib.set(opts.get("matlib_path", ""))
        self._root_dir.set(opts.get("root_dir", ""))


# ── T & DPA grid ──────────────────────────────────────────────────────────────


class TDPAGridTab(ttk.Frame):
    """Grid of (group × item) rows × reference events; each cell holds T and DPA.

    Groups are flanges/submodels, items are bolts/paths. Values are stored in
    ``project[_PROJECT_KEY]`` as ``{_GROUP_FIELD, _ITEM_FIELD, re_id, T, dpa}``.
    """

    _PROJECT_KEY = "tdpa"
    _RE_KEY = "reference_events"
    _GROUP_FIELD: str
    _ITEM_FIELD: str
    _GROUP_LABEL: str
    _ITEM_LABEL: str
    _CSV_ITEM_COL: str
    _EMPTY_MSG = "No data to display."
    _CELL_W = 9

    def __init__(self, parent: ttk.Notebook, project: dict) -> None:
        super().__init__(parent)
        self._project = project
        self._cell_vars: dict[tuple, tuple[tk.StringVar, tk.StringVar]] = {}
        self._var_grid: list[list[tk.StringVar]] = []
        self._build_shell()
        self.after(0, self.rebuild_grid)

    def _groups(self) -> list[tuple[str, list]]:
        """Return ``[(group_name, [item_key, ...]), ...]`` in display order."""
        raise NotImplementedError

    def _parse_item(self, raw: str) -> str | int:
        """Convert an item key read from CSV; raise ValueError if invalid."""
        return raw

    def _build_shell(self) -> None:
        toolbar = make_toolbar(
            self,
            [
                ("Refresh grid", self.rebuild_grid),
                ("Import CSV…", self._import_csv),
                ("Export CSV…", self._export_csv),
            ],
            accent_first=False,
        )
        ttk.Label(
            toolbar,
            text=(
                f"CSV columns: {self._GROUP_FIELD}, {self._CSV_ITEM_COL}, event, T, DPA"
                "   ·   Ctrl+V pastes a block copied from Excel"
            ),
            style="Muted.TLabel",
        ).pack(side="left", padx=8)

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._canvas = tk.Canvas(
            outer, borderwidth=0, highlightthickness=0, background=BG
        )
        vsb = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        bind_mousewheel(self._canvas)

        self._inner = ttk.Frame(self._canvas)
        self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )

    def rebuild_grid(self) -> None:
        for widget in self._inner.winfo_children():
            widget.destroy()
        self._cell_vars.clear()
        self._var_grid = []

        groups = [(g, items) for g, items in self._groups() if items]
        re_ids = list(
            dict.fromkeys(r["re_id"] for r in self._project.get(self._RE_KEY, []))
        )
        if not groups or not re_ids:
            ttk.Label(self._inner, text=self._EMPTY_MSG, style="Muted.TLabel").grid(
                padx=20, pady=20
            )
            return

        existing: dict[tuple, tuple[str, str]] = {
            (e[self._GROUP_FIELD], e[self._ITEM_FIELD], e["re_id"]): (
                str(e["T"]),
                str(e["dpa"]),
            )
            for e in self._project.get(self._PROJECT_KEY, [])
            if self._GROUP_FIELD in e and self._ITEM_FIELD in e
        }

        cell_w = self._CELL_W
        grid_opts = {"sticky": "nsew", "padx": 1, "pady": 1}

        def header(text: str, width: int, **grid) -> None:
            ttk.Label(
                self._inner,
                text=text,
                width=width,
                anchor="center",
                relief="groove",
                style="GridHeader.TLabel",
            ).grid(**grid, **grid_opts)

        def key_label(text: str, width: int, **grid) -> None:
            ttk.Label(
                self._inner,
                text=text,
                width=width,
                anchor="center",
                relief="groove",
                style="GridKey.TLabel",
            ).grid(**grid, **grid_opts)

        header(self._GROUP_LABEL, 16, row=0, column=0, rowspan=2)
        header(self._ITEM_LABEL, 10, row=0, column=1, rowspan=2)
        for c, re_id in enumerate(re_ids):
            header(str(re_id), cell_w * 2 + 1, row=0, column=2 + c * 2, columnspan=2)
            header("T [°C]", cell_w, row=1, column=2 + c * 2)
            header("DPA", cell_w, row=1, column=3 + c * 2)

        row = 2
        for group, items in groups:
            key_label(group, 16, row=row, column=0, rowspan=len(items))
            for item in items:
                key_label(str(item), 10, row=row, column=1)
                line: list[tk.StringVar] = []
                for c, re_id in enumerate(re_ids):
                    t_def, dpa_def = existing.get((group, item, re_id), ("", "0"))
                    t_var = tk.StringVar(self, value=t_def)
                    dpa_var = tk.StringVar(self, value=dpa_def)
                    self._cell_vars[(group, item, re_id)] = (t_var, dpa_var)
                    for k, var in enumerate((t_var, dpa_var)):
                        entry = ttk.Entry(self._inner, textvariable=var, width=cell_w)
                        entry.grid(row=row, column=2 + c * 2 + k, padx=1, pady=1)
                        entry.bind(
                            "<<Paste>>",
                            lambda _e, r=len(self._var_grid), col=len(line): (
                                self._paste_block(r, col)
                            ),
                        )
                        line.append(var)
                self._var_grid.append(line)
                row += 1

    def _paste_block(self, row0: int, col0: int) -> str | None:
        """Spread a tab/newline separated clipboard block over the grid."""
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return None
        rows = [line.split("\t") for line in text.rstrip("\r\n").splitlines()]
        if len(rows) <= 1 and len(rows[0] if rows else []) <= 1:
            return None
        for dr, values in enumerate(rows):
            if row0 + dr >= len(self._var_grid):
                break
            line = self._var_grid[row0 + dr]
            for dc, value in enumerate(values):
                if col0 + dc >= len(line):
                    break
                line[col0 + dc].set(value.strip())
        return "break"

    def _import_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Import T & DPA from CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        group_col, item_col = self._GROUP_FIELD, self._CSV_ITEM_COL
        errors: list[str] = []
        loaded = 0
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                for lineno, row in enumerate(csv.DictReader(fh), start=2):
                    row = {
                        (k or "").strip().lower(): (v or "").strip()
                        for k, v in row.items()
                    }
                    group = row.get(group_col, "")
                    item_raw = row.get(item_col, "")
                    event = row.get("event", "")
                    if not (group and item_raw and event):
                        errors.append(
                            f"Line {lineno}: missing {group_col}/{item_col}/event — skipped"
                        )
                        continue
                    try:
                        item = self._parse_item(item_raw)
                    except ValueError:
                        errors.append(
                            f"Line {lineno}: invalid {item_col} '{item_raw}' — skipped"
                        )
                        continue
                    key = (group, item, event)
                    if key not in self._cell_vars:
                        errors.append(
                            f"Line {lineno}: ({group!r}, {item!r}, {event!r}) not in grid — skipped"
                        )
                        continue
                    t_var, dpa_var = self._cell_vars[key]
                    t_var.set(row.get("t", ""))
                    dpa_var.set(row.get("dpa", ""))
                    loaded += 1
        except Exception as exc:
            messagebox.showerror("Import Error", str(exc))
            return
        summary = f"Imported {loaded} value(s)."
        if errors:
            summary += f"\n\nWarnings ({len(errors)}):\n" + "\n".join(errors[:20])
            if len(errors) > 20:
                summary += f"\n… and {len(errors) - 20} more"
        messagebox.showinfo("Import complete", summary)

    def _export_csv(self) -> None:
        if not self._cell_vars:
            messagebox.showwarning(
                "Empty grid", "No data to export (build the grid first)."
            )
            return
        path = filedialog.asksaveasfilename(
            title="Export T & DPA to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(
                    [self._GROUP_FIELD, self._CSV_ITEM_COL, "event", "T", "DPA"]
                )
                for (group, item, re_id), (t_var, dpa_var) in self._cell_vars.items():
                    writer.writerow([group, item, re_id, t_var.get(), dpa_var.get()])
            messagebox.showinfo("Export complete", f"T & DPA data saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    def sync(self) -> list[str]:
        """Read cells into project[_PROJECT_KEY]; return validation errors.

        Cells with an empty T are skipped.
        """
        entries = []
        errors = []
        for (group, item, re_id), (t_var, dpa_var) in self._cell_vars.items():
            t_str = t_var.get().strip()
            dpa_str = dpa_var.get().strip()
            if not t_str:
                continue
            try:
                T = float(t_str)
                dpa = float(dpa_str) if dpa_str else 0.0
            except ValueError:
                errors.append(
                    f"{self._GROUP_LABEL} '{group}' / {self._ITEM_LABEL} '{item}' / "
                    f"RE '{re_id}': T and DPA must be numbers"
                )
                continue
            entries.append(
                {
                    self._GROUP_FIELD: group,
                    self._ITEM_FIELD: item,
                    "re_id": re_id,
                    "T": T,
                    "dpa": dpa,
                }
            )
        self._project[self._PROJECT_KEY] = entries
        return errors


# ── Log window ────────────────────────────────────────────────────────────────


class LogWindow(tk.Toplevel):
    """Scrollable pop-up that captures log output from an assessment run."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("Cassy \u2014 Assessment Log")
        self.geometry("860x540")
        self.resizable(True, True)
        set_icon(self)

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=8, pady=8)
        mono = tkfont.nametofont("TkFixedFont").actual("family")
        self._text = tk.Text(
            frm,
            state="disabled",
            wrap="none",
            font=(mono, 9),
            bg=LOG_BG,
            fg=LOG_FG,
            insertbackground=LOG_FG,
            relief="flat",
            borderwidth=0,
            padx=8,
            pady=6,
        )
        vsb = ttk.Scrollbar(frm, orient="vertical", command=self._text.yview)
        hsb = ttk.Scrollbar(frm, orient="horizontal", command=self._text.xview)
        self._text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._text.pack(side="left", fill="both", expand=True)

        bot = ttk.Frame(self)
        bot.pack(fill="x", padx=8, pady=(0, 8))
        self._status = ttk.Label(bot, text="Running\u2026", anchor="w")
        self._status.pack(side="left", fill="x", expand=True)
        ttk.Button(bot, text="Close", command=self.destroy).pack(side="right")

    # Called from the main thread only (route via after() from other threads).
    def append(self, text: str) -> None:
        self._text.configure(state="normal")
        self._text.insert("end", text + "\n")
        self._text.see("end")
        self._text.configure(state="disabled")

    def set_done(self, success: bool, msg: str) -> None:
        self._status.configure(text=msg, foreground=SUCCESS if success else ERROR)


class TextHandler(logging.Handler):
    """Routes log records to a LogWindow (thread-safe via after())."""

    def __init__(self, win: LogWindow) -> None:
        super().__init__()
        self._win = win
        self.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._win.after(0, self._win.append, msg)
        except Exception:
            pass


# ── Main window ───────────────────────────────────────────────────────────────


class ProjectApp(tk.Tk):
    """Main window: themed notebook, File menu and JSON project handling."""

    _TITLE = "Cassy"
    _GEOMETRY = "1100x680"

    def __init__(self) -> None:
        super().__init__()
        apply_theme(self)
        self.title(self._TITLE)
        self.geometry(self._GEOMETRY)
        self.minsize(800, 520)
        self.protocol("WM_DELETE_WINDOW", self._exit)
        set_icon(self)

        self._project_path: str | None = None
        self._project: dict = self._fresh_project()

        self._build_menu()
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._build_tabs()
        self._saved_state = self._snapshot()

    # -- subclasses override these -------------------------------------------

    @staticmethod
    def _fresh_project() -> dict:
        raise NotImplementedError

    def _build_tabs(self) -> None:
        raise NotImplementedError

    def _sync_all(self) -> list[str]:
        """Push widget state into the project dict; return validation errors."""
        raise NotImplementedError

    def _refresh_all_tabs(self) -> None:
        raise NotImplementedError

    # -- menu ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", accelerator="Ctrl+N", command=self._new)
        file_menu.add_command(label="Open...", accelerator="Ctrl+O", command=self._open)
        file_menu.add_separator()
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self._save)
        file_menu.add_command(label="Save As...", command=self._save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._exit)

        self.bind_all("<Control-n>", lambda _e: self._new())
        self.bind_all("<Control-o>", lambda _e: self._open())
        self.bind_all("<Control-s>", lambda _e: self._save())

    # -- unsaved changes -------------------------------------------------------

    def _snapshot(self) -> str:
        return json.dumps(self._project, sort_keys=True, default=str)

    def _mark_saved(self) -> None:
        self._sync_all()
        self._saved_state = self._snapshot()

    def _confirm_discard(self) -> bool:
        """Ask to save pending changes; False means the user cancelled."""
        self._sync_all()
        if self._snapshot() == self._saved_state:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes", "Save changes to the current project?"
        )
        if answer is None:
            return False
        if answer:
            self._save()
            return self._snapshot() == self._saved_state
        return True

    # -- file operations -------------------------------------------------------

    def _new(self) -> None:
        if not self._confirm_discard():
            return
        # Update the shared dict in-place so all tab references stay valid
        self._project.clear()
        self._project.update(self._fresh_project())
        self._project_path = None
        self.title(self._TITLE)
        self._refresh_all_tabs()
        self._mark_saved()
        self.focus_force()

    def _open(self) -> None:
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(
            title="Open project",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            messagebox.showerror("Open Error", str(exc))
            return
        self._project.clear()
        self._project.update(data)
        self._project_path = path
        self.title(f"Cassy \u2014 {os.path.basename(path)}")
        self._refresh_all_tabs()
        self._mark_saved()

    def _save(self) -> None:
        if self._project_path is None:
            self._save_as()
        else:
            self._write(self._project_path)

    def _save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save project as",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self._project_path = path
        self._write(path)

    def _write(self, path: str) -> None:
        errors = self._sync_all()
        if errors:
            messagebox.showwarning(
                "Invalid values",
                "These T & DPA cells are not numbers and were not saved:\n\n"
                + "\n".join(errors[:20]),
            )
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._project, fh, indent=2)
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))
            return
        self._saved_state = self._snapshot()
        self.title(f"Cassy \u2014 {os.path.basename(path)}")

    def _exit(self) -> None:
        if self._confirm_discard():
            self.destroy()
