import os
import sys
import shutil
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox

# SQLite admin DB initialization
def get_admin_db_path():
    import platform
    if sys.platform.startswith('win'):
        local_appdata = os.environ.get('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local'))
        db_dir = os.path.join(local_appdata, "lpubsppop01_my_disk_cleaner")
    else:
        db_dir = os.path.expanduser("~/.lpubsppop01_my_disk_cleaner")
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "admin.db")

ADMIN_DB_PATH = get_admin_db_path()

def init_admin_db():
    conn = sqlite3.connect(ADMIN_DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS dir_size_cache (
            path TEXT PRIMARY KEY,
            size INTEGER,
            mtime INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS initial_directories (
            platform TEXT NOT NULL,
            dir TEXT NOT NULL,
            PRIMARY KEY (platform, dir)
        )
    """)
    conn.commit()
    conn.close()
init_admin_db()

def load_initial_dirs(platform):
    conn = sqlite3.connect(ADMIN_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT dir FROM initial_directories WHERE platform=?", (platform,))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def save_initial_dirs(platform, dirs):
    conn = sqlite3.connect(ADMIN_DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM initial_directories WHERE platform=?", (platform,))
    for dir_path in dirs:
        c.execute("INSERT INTO initial_directories (platform, dir) VALUES (?, ?)", (platform, dir_path))
    conn.commit()
    conn.close()

# Initial candidate directories (for Mac)
MAC_INITIAL_DIRS = [
    os.path.expanduser('~/Library/Caches'),
    os.path.expanduser('~/Library/Logs'),
    os.path.expanduser('~/Library/Application Support'),
    os.path.expanduser('~/Library/Containers'),
    os.path.expanduser('~/Downloads'),
    os.path.expanduser('~/.ollama'),
    '/Library/Caches',
    '/Library/Logs',
    '/Library/Application Support',
    '/System/Library/Caches',
    '/System/Library/Logs',
    '/System/Library/Application Support',
    '/private/var/folders',
    '/private/var/log',
    '/private/var/tmp',
    '/private/var/vm',
    '/private/tmp',
    '/private/vm',
    '/Applications',
]

WINDOWS_INITIAL_DIRS = [
    r"C:\Windows\Temp",
    r"C:\ProgramData",
    r"C:\System Volume Information",
    r"C:\Windows\SoftwareDistribution\Download",
    r"C:\Cygwin64\var\cache\setup",
    os.path.expanduser(r'~\AppData\Local\Temp'),
    os.path.expanduser('~\\AppData\\Local\\Packages'),
    os.path.expanduser('~\\AppData\\Local\\pip\\Cache'),
    os.path.expanduser('~\\AppData\\Local\\npm-cache'),
    os.path.expanduser('~\\AppData\\Roaming\\Code\\Cache'),
    os.path.expanduser('~\\AppData\\Roaming\\Code\\Backups'),
    os.path.expanduser('~\\AppData\\Local\\BraveSoftware\\Brave-Browser\\User Data\\Default\\Cache'),
    os.path.expanduser('~\\.ollama'),
]

def is_mac():
    return sys.platform == 'darwin'

def is_windows():
    return sys.platform.startswith('win')

def is_windows_hardlink(path) -> bool:
    # Check if a file is a hard link on Windows
    if not is_windows():
        return False
    if not os.path.exists(path):
        return False
    try:
        import ctypes
        FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))  # type: ignore
        if attrs == -1:
            return False
        return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except Exception:
        return False

# Directory size calculation with SQLite cache
def get_dir_size(path, queue=None):
    import sqlite3
    mtime = None
    try:
        mtime = int(os.path.getmtime(path))
    except Exception:
        mtime = None
    size = None
    if mtime is not None:
        try:
            conn = sqlite3.connect(ADMIN_DB_PATH)
            c = conn.cursor()
            c.execute("SELECT size, mtime FROM dir_size_cache WHERE path=?", (path,))
            row = c.fetchone()
            if row and row[1] == mtime:
                size = row[0]
            conn.close()
        except Exception:
            size = None
    if size is not None:
        return size
    # If cache is missing or mtime is different, recalculate
    total = 0
    count = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                fp = os.path.join(root, f)
                # Exclude symbolic links from size calculation
                if os.path.islink(fp) or is_windows_hardlink(fp):
                    continue
                count += 1
                if queue is not None and count % 100 == 0:
                    queue.put(("progress", fp))
                total += os.path.getsize(fp)
            except Exception:
                pass
    # Save calculation result to cache
    if mtime is not None:
        try:
            conn = sqlite3.connect(ADMIN_DB_PATH)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO dir_size_cache (path, size, mtime) VALUES (?, ?, ?)", (path, total, mtime))
            conn.commit()
            conn.close()
        except Exception:
            pass
    return total

# List files and directories for Mac
def list_dir(path):
    try:
        entries = []
        with os.scandir(path) as it:
            for entry in it:
                if os.path.islink(entry.path) or is_windows_hardlink(entry.path):
                    continue
                size = 0
                if entry.is_file():
                    try:
                        size = entry.stat().st_size
                    except Exception:
                        size = 0
                elif entry.is_dir():
                    try:
                        size = get_dir_size(entry.path)
                    except Exception:
                        size = 0
                entries.append({
                    'name': entry.name,
                    'path': entry.path,
                    'is_dir': entry.is_dir(),
                    'size': size
                })
        return entries
    except Exception:
        return []

# Delete files and directories for Mac
def delete_items(items):
    for item in items:
        try:
            if os.path.isdir(item):
                shutil.rmtree(item)
            else:
                os.remove(item)
        except Exception:
            pass

class DiskCleanerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("My Disk Cleaner")
        self.geometry("800x600")
        self.selected_dir = None
        self.dir_entries = []
        self.selected_items = set()
        self.loading = False
        self.show_dir_sizes = tk.BooleanVar(value=False)
        self.create_widgets()
        self.refresh_initial_dirs()
        self.update_breadcrumbs()

    @staticmethod
    def get_display_name(entry):
        # Add separator at the end of directory names
        if entry.get('is_dir', False):
            sep = '\\' if is_windows() else '/'
            name = entry['name']
            # Add separator only if not already present
            if not name.endswith(sep):
                name += sep
            return name
        return entry['name']

    def create_widgets(self):
        # Configure grid weights for main window
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # Canvas + Frame + Scrollbar for breadcrumb navigation (height fixed, horizontal scroll)
        self.breadcrumb_frame = tk.Frame(self)
        self.breadcrumb_frame.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.breadcrumb_canvas = tk.Canvas(self.breadcrumb_frame, height=32, highlightthickness=0, bd=0)
        self.breadcrumb_canvas.pack(side='top', fill='x', expand=True)
        self.breadcrumb_inner_frame = tk.Frame(self.breadcrumb_canvas)
        self.breadcrumb_window = self.breadcrumb_canvas.create_window((0, 0), window=self.breadcrumb_inner_frame, anchor='nw')
        self.breadcrumb_scrollbar = tk.Scrollbar(self.breadcrumb_frame, orient='horizontal', command=self.breadcrumb_canvas.xview)
        self.breadcrumb_scrollbar.pack(side='bottom', fill='x')
        self.breadcrumb_canvas.configure(xscrollcommand=self.breadcrumb_scrollbar.set)
        self.breadcrumb_inner_frame.bind(
            "<Configure>",
            lambda e: self.breadcrumb_canvas.configure(scrollregion=self.breadcrumb_canvas.bbox("all"))
        )
        self.breadcrumb_canvas.pack_propagate(False)

        # Frame for buttons (Show directory sizes & Clear Cache)
        self.button_frame = tk.Frame(self)
        self.button_frame.grid(row=1, column=0, columnspan=2, sticky='ew', padx=10, pady=5)
        self.button_frame.grid_columnconfigure(0, weight=0)
        self.button_frame.grid_columnconfigure(1, weight=0)
        self.button_frame.grid_columnconfigure(2, weight=0)

        # Edit Initial Directories button (leftmost)
        self.edit_initial_dirs_btn = tk.Button(self.button_frame, text="Edit Initial Directories", command=self.show_edit_initial_dirs_dialog)
        self.edit_initial_dirs_btn.grid(row=0, column=0, sticky='w', padx=0, pady=0)

        # Clear Cache button (next to Edit Initial Directories)
        self.clear_cache_btn = tk.Button(self.button_frame, text="Clear Cache", command=self.on_clear_cache)
        self.clear_cache_btn.grid(row=0, column=1, sticky='w', padx=10, pady=0)

        # Checkbox for toggling directory size calculation (next to Clear Cache)
        self.size_checkbox = tk.Checkbutton(self.button_frame, text="Show directory sizes", variable=self.show_dir_sizes, command=self.on_toggle_dir_sizes)
        self.size_checkbox.grid(row=0, column=2, sticky='w', padx=5, pady=0)

        # Status label (Unified label)
        self.status_label = tk.Label(self, text="", anchor='w')
        self.status_label.grid(row=2, column=0, columnspan=2, sticky='ew', padx=10, pady=5)

        # File/Directory list
        self.tree = ttk.Treeview(self, columns=("size",), selectmode="extended")
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size (bytes)")
        self.tree.column("#0", width=400)
        self.tree.column("size", width=120, anchor='e')
        self.tree.grid(row=3, column=0, columnspan=2, sticky='nsew', padx=10, pady=5)
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # Delete button
        self.delete_btn = tk.Button(self, text="Delete selected items", command=self.on_delete)
        self.delete_btn.grid(row=4, column=1, sticky='e', padx=10, pady=10)

    def set_status_text(self, text):
        import tkinter.font
        label_width = self.status_label.winfo_width()
        font = tkinter.font.Font(font=self.status_label.cget("font"))
        char_width = font.measure("A") or 8  # Assume 8px if unable to get width
        if label_width > 1 and char_width > 0:
            max_len = label_width // char_width
        else:
            max_len = 100  # Default if width is not determined yet
        if len(text) > max_len:
            text = text[:max_len-3] + "..."
        self.status_label.config(text=text)

    def show_edit_initial_dirs_dialog(self):
        # Method to display the edit dialog
        dialog = tk.Toplevel(self)
        dialog.title("Edit Initial Directories")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()

        # Platform detection
        if is_mac():
            platform_name = "mac"
        elif is_windows():
            platform_name = "windows"
        else:
            platform_name = "other"

        # Get current list
        dirs = load_initial_dirs(platform_name)
        # Text box
        text_box = tk.Text(dialog, wrap="none")
        text_box.pack(fill="both", expand=True, padx=10, pady=10)
        text_box.insert("1.0", "\n".join(dirs))

        # Button frame
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill="x", padx=10, pady=5)

        def on_save():
            new_dirs = text_box.get("1.0", "end").strip().splitlines()
            # Remove empty lines
            new_dirs = [d for d in new_dirs if d.strip()]
            save_initial_dirs(platform_name, new_dirs)
            dialog.destroy()
            self.refresh_initial_dirs()

        def on_cancel():
            dialog.destroy()

        save_btn = tk.Button(btn_frame, text="Save", command=on_save)
        save_btn.pack(side="left", padx=5)
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="left", padx=5)

    def on_clear_cache(self):
        # Clear cache in SQLite DB
        import sqlite3
        try:
            conn = sqlite3.connect(ADMIN_DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM dir_size_cache")
            conn.commit()
            conn.close()
        except Exception:
            conn = sqlite3.connect(ADMIN_DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM dir_size_cache")
            conn.commit()
            conn.close()
        # Refresh UI after clearing cache
        if self.selected_dir is None:
            self.refresh_initial_dirs()
        else:
            self.start_refresh_dir_view()

    def refresh_initial_dirs(self):
        if self.loading:
            return  # Prevent double loading
        # Platform detection
        if is_mac():
            platform_name = "mac"
            default_dirs = MAC_INITIAL_DIRS
        elif is_windows():
            platform_name = "windows"
            default_dirs = WINDOWS_INITIAL_DIRS
        else:
            platform_name = "other"
            default_dirs = []
        # Get list from DB
        dirs = load_initial_dirs(platform_name)
        # If no list in DB, save default values
        if not dirs:
            save_initial_dirs(platform_name, default_dirs)
            dirs = list(default_dirs)
        self.selected_dir = None
        self.dir_entries = []
        self.tree.delete(*self.tree.get_children())
        if self.show_dir_sizes.get():
            import multiprocessing
            self._queue = multiprocessing.Queue()
            self._process = multiprocessing.Process(target=DiskCleanerApp._get_entries_process, args=(dirs, self._queue, True))
            self._process.start()
            self.loading = True
            self.set_status_text("Loading...")
            self.delete_btn.config(state="disabled")
            self.after(100, self._poll_queue)
        else:
            for dir_path in dirs:
                entry = {
                    'name': dir_path,
                    'path': dir_path,
                    'is_dir': True,
                    'size': "-"
                }
                self.dir_entries.append(entry)
                display_name = self.get_display_name(entry)
                self.tree.insert("", "end", iid=dir_path, text=display_name, values=("-",), tags=("dir",))
        if self.loading:
            self.set_status_text("Loading...")
        else:
            self.set_status_text("Directory size: -")
        self.delete_btn.config(state="disabled")

    def start_refresh_dir_view(self):
        if self.loading:
            return  # Prevent double loading
        self.loading = True
        self.set_status_text("Loading...")
        self.delete_btn.config(state="disabled")
        self.tree.delete(*self.tree.get_children())
        import multiprocessing
        self._queue = multiprocessing.Queue()
        # Pass a single directory as a list
        self._process = multiprocessing.Process(target=DiskCleanerApp._get_entries_process, args=([self.selected_dir], self._queue, self.show_dir_sizes.get()))
        self._process.start()
        self.after(100, self._poll_queue)

    @staticmethod
    def _get_entries_process(targets, queue, show_dir_sizes=True):
        """
        targets: list of directory paths
        show_dir_sizes: bool
        """
        import os
        entries = []
        for dir_path in targets:
            queue.put(("progress", dir_path))
            if not dir_path or not os.path.exists(dir_path):
                continue
            # Check if the path is a directory
            if os.path.isdir(dir_path):
                # Get the list of items under the directory
                try:
                    with os.scandir(dir_path) as it:
                        for entry in it:
                            if os.path.islink(entry.path) or is_windows_hardlink(entry.path):
                                continue
                            if entry.is_file():
                                size = entry.stat().st_size if show_dir_sizes else "-"
                            elif entry.is_dir():
                                try:
                                    size = get_dir_size(entry.path, queue) if show_dir_sizes else "-"
                                except Exception:
                                    size = 0 if show_dir_sizes else "-"
                            else:
                                size = "-"
                            entry_dict = {
                                'name': entry.name,
                                'path': entry.path,
                                'is_dir': entry.is_dir(),
                                'size': size
                            }
                            entries.append(entry_dict)
                except Exception:
                    pass
            else:
                # If it is a single file
                try:
                    size = os.path.getsize(dir_path) if show_dir_sizes else "-"
                except Exception:
                    size = 0 if show_dir_sizes else "-"
                entry = {
                    'name': os.path.basename(dir_path),
                    'path': dir_path,
                    'is_dir': False,
                    'size': size
                }
                entries.append(entry)
        queue.put(("result", entries))

    def _poll_queue(self):
        if hasattr(self, "_queue"):
            try:
                msg = self._queue.get_nowait()
                if isinstance(msg, tuple) and msg[0] == "progress":
                    dir_path = msg[1]
                    self.set_status_text(f"Loading...{dir_path}")
                    self.after(100, self._poll_queue)
                elif isinstance(msg, tuple) and msg[0] == "result":
                    entries = msg[1]
                    self._update_dir_view_ui(entries)
                    if hasattr(self, "_process"):
                        self._process.join(timeout=0.1)
                        del self._process
                    del self._queue
                else:
                    entries = msg
                    self._update_dir_view_ui(entries)
                    if hasattr(self, "_process"):
                        self._process.join(timeout=0.1)
                        del self._process
                    del self._queue
            except Exception:
                self.after(100, self._poll_queue)

    def _update_dir_view_ui(self, entries):
        # Draw initial directory list or list under the directory
        self.dir_entries = entries
        self.tree.delete(*self.tree.get_children())
        for entry in entries:
            tag = "dir" if entry['is_dir'] else "file"
            display_name = self.get_display_name(entry)
            display_size = "{:,}".format(entry['size']) if isinstance(entry['size'], int) else entry['size']
            self.tree.insert("", "end", iid=entry['path'], text=display_name, values=(display_size,), tags=(tag,))
        dir_size_str = "-"
        if self.show_dir_sizes.get() and self.selected_dir is not None:
            dir_size_str = "{:,} bytes".format(get_dir_size(self.selected_dir))
        self.set_status_text(f"Directory size: {dir_size_str}")
        self.delete_btn.config(state="normal")
        self.loading = False

    def on_toggle_dir_sizes(self):
        # Callback for Show directory sizes checkbox toggle
        # If loading, terminate the current process to cancel loading
        if getattr(self, "loading", False):
            self.loading = False
            self.set_status_text("")
            self.delete_btn.config(state="disabled")
            self.tree.delete(*self.tree.get_children())
        if hasattr(self, "_process"):
            try:
                self._process.terminate()
            except Exception:
                pass
            del self._process
        if hasattr(self, "_queue"):
            del self._queue
        if self.selected_dir is None:
            self.refresh_initial_dirs()
        else:
            self.start_refresh_dir_view()

    def on_tree_double_click(self, event):
        item_id = self.tree.focus()
        if not item_id:
            return
        entry = next((e for e in self.dir_entries if e['path'] == item_id), None)
        if entry and entry['is_dir']:
            self.selected_dir = entry['path']
            self.start_refresh_dir_view()
            self.update_breadcrumbs()

    def on_delete(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Delete", "Please select items to delete.")
            return
        confirm = messagebox.askyesno("Confirm", "Are you sure you want to delete the selected items?")
        if not confirm:
            return
        delete_items(selected)
        self.start_refresh_dir_view()

    def update_breadcrumbs(self):
        # Update breadcrumb navigation display
        for widget in self.breadcrumb_inner_frame.winfo_children():
            widget.destroy()
        if self.selected_dir is None:
            # Label for initial directories list view
            lbl = tk.Label(self.breadcrumb_inner_frame, text="Initial Directories", relief=tk.FLAT)
            lbl.pack(side='left', padx=2, pady=2)
            self.breadcrumb_canvas.update_idletasks()
            self.breadcrumb_canvas.configure(scrollregion=self.breadcrumb_canvas.bbox("all"))
            return
        else:
            # Button for initial directories list view
            btn = tk.Button(self.breadcrumb_inner_frame, text="Initial Directories", relief=tk.FLAT, command=lambda: self.on_breadcrumb_click(""))
            btn.pack(side='left')
            sep = tk.Label(self.breadcrumb_inner_frame, text=" > ")
            sep.pack(side='left')
        home_dir = os.path.expanduser('~')
        # Breadcrumb navigation
        parts = []
        path = self.selected_dir
        matched_initial = ""
        initial_dirs = load_initial_dirs("mac" if is_mac() else "windows" if is_windows() else "other")
        for initial in initial_dirs:
            if path == initial or path.startswith(initial + os.sep):
                parts.append((initial, initial))
                matched_initial = initial
                break
        while path != matched_initial:
            head, tail = os.path.split(path)
            if tail:
                parts.insert(1, (tail, path))
                path = head
            else:
                if head:
                    parts.insert(1, (head, head))
                break
        # Shorten display using "~" for home directory
        def short_path(p):
            if p.startswith(home_dir):
                return p.replace(home_dir, "~", 1)
            return p
        # The last item is a Label (not selectable), others are buttons
        for i, (name, full_path) in enumerate(parts):
            display_name = short_path(name)
            if i == len(parts) - 1:
                lbl = tk.Label(self.breadcrumb_inner_frame, text=display_name, relief=tk.FLAT)
                lbl.pack(side='left')
            else:
                btn = tk.Button(self.breadcrumb_inner_frame, text=display_name, relief=tk.FLAT, command=lambda p=full_path: self.on_breadcrumb_click(p))
                btn.pack(side='left')
            if i < len(parts) - 1:
                sep = tk.Label(self.breadcrumb_inner_frame, text=" > ")
                sep.pack(side='left')
        self.breadcrumb_canvas.update_idletasks()
        self.breadcrumb_canvas.configure(scrollregion=self.breadcrumb_canvas.bbox("all"))

    def on_breadcrumb_click(self, path):
        # Navigate to the directory when breadcrumb is clicked
        if not path:
            self.refresh_initial_dirs()
            self.update_breadcrumbs()
        elif path != self.selected_dir:
            self.selected_dir = path
            self.start_refresh_dir_view()
            self.update_breadcrumbs()

if __name__ == "__main__":
    app = DiskCleanerApp()
    app.mainloop()
