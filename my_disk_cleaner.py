import os
import sys
import shutil
import tkinter as tk
from tkinter import ttk, messagebox

# Initial candidate directories (for Mac)
MAC_INITIAL_DIRS = [
    os.path.expanduser('~/Library/Caches'),
    os.path.expanduser('~/Library/Logs'),
    os.path.expanduser('~/Library/Application Support'),
    os.path.expanduser('~/Library/Containers'),
]

WINDOWS_INITIAL_DIR = os.path.expanduser('~\\AppData\\Local')

def is_mac():
    return sys.platform == 'darwin'

def is_windows():
    return sys.platform.startswith('win')

# Stub functions for Windows
def get_windows_dir_size(path):
    # Dummy for hard link handling
    return 0

def list_windows_dir(path):
    # Dummy
    return []

def delete_windows_items(items):
    # Dummy
    pass

# Directory size calculation for Mac
def get_dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                fp = os.path.join(root, f)
                # Exclude symbolic links from size calculation
                if os.path.islink(fp):
                    continue
                total += os.path.getsize(fp)
            except Exception:
                pass
    return total

# List files and directories for Mac
def list_dir(path):
    try:
        entries = []
        with os.scandir(path) as it:
            for entry in it:
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
        self.create_widgets()
        self.refresh_initial_dirs()

    def create_widgets(self):
        # Initial candidate directory selection
        self.dir_label = tk.Label(self, text="Initial candidate directories:")
        self.dir_label.pack(anchor='nw', padx=10, pady=5)

        self.dir_combo = ttk.Combobox(self, state="readonly")
        self.dir_combo.pack(anchor='nw', padx=10, pady=5)
        self.dir_combo.bind("<<ComboboxSelected>>", self.on_dir_selected)

        # Directory size display
        self.size_label = tk.Label(self, text="Directory size: ")
        self.size_label.pack(anchor='nw', padx=10, pady=5)

        # Loading indicator
        self.loading_label = tk.Label(self, text="", fg="blue")
        self.loading_label.pack(anchor='nw', padx=10, pady=5)

        # File/Directory list
        self.tree = ttk.Treeview(self, columns=("size",), selectmode="extended")
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size (bytes)")
        self.tree.column("#0", width=400)
        self.tree.column("size", width=120, anchor='e')
        self.tree.pack(fill='both', expand=True, padx=10, pady=5)
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # Delete button
        self.delete_btn = tk.Button(self, text="Delete selected items", command=self.on_delete)
        self.delete_btn.pack(anchor='se', padx=10, pady=10)

    def refresh_initial_dirs(self):
        if is_mac():
            dirs = MAC_INITIAL_DIRS
        elif is_windows():
            dirs = [WINDOWS_INITIAL_DIR]
        else:
            dirs = []
        self.dir_combo['values'] = dirs
        if dirs:
            self.dir_combo.current(0)
            self.on_dir_selected()

    def on_dir_selected(self, event=None):
        dir_path = self.dir_combo.get()
        self.selected_dir = dir_path
        self.start_refresh_dir_view()

    def start_refresh_dir_view(self):
        if self.loading:
            return  # Prevent double loading
        self.loading = True
        self.loading_label.config(text="Loading...")
        self.delete_btn.config(state="disabled")
        self.tree.delete(*self.tree.get_children())
        # multiprocessing: start process and poll queue
        import multiprocessing
        self._mp_queue = multiprocessing.Queue()
        p = multiprocessing.Process(target=DiskCleanerApp._refresh_dir_view_process, args=(self.selected_dir, self._mp_queue))
        p.start()
        self._mp_process = p
        self.after(100, self._poll_mp_queue)

    @staticmethod
    def _refresh_dir_view_process(selected_dir, queue):
        if not selected_dir:
            size = "-"
            entries = []
        elif is_mac():
            size = get_dir_size(selected_dir)
            entries = list_dir(selected_dir)
        elif is_windows():
            size = get_windows_dir_size(selected_dir)
            entries = list_windows_dir(selected_dir)
        else:
            size = "-"
            entries = []
        queue.put((size, entries))

    def _update_dir_view_ui(self, size, entries):
        self.size_label.config(text=f"Directory size: {size if isinstance(size, str) else f'{size:,} bytes'}")
        self.dir_entries = entries
        for entry in entries:
            tag = "dir" if entry['is_dir'] else "file"
            self.tree.insert("", "end", iid=entry['path'], text=entry['name'], values=(entry['size'],), tags=(tag,))
        self.loading_label.config(text="")
        self.delete_btn.config(state="normal")
        self.loading = False

    def _poll_mp_queue(self):
        if hasattr(self, "_mp_queue"):
            try:
                size, entries = self._mp_queue.get_nowait()
                self._update_dir_view_ui(size, entries)
                # Process termination handling
                if hasattr(self, "_mp_process"):
                    self._mp_process.join(timeout=0.1)
                    del self._mp_process
                del self._mp_queue
            except Exception:
                # If the queue is empty, call again with after
                self.after(100, self._poll_mp_queue)

    def on_tree_double_click(self, event):
        item_id = self.tree.focus()
        if not item_id:
            return
        entry = next((e for e in self.dir_entries if e['path'] == item_id), None)
        if entry and entry['is_dir']:
            self.selected_dir = entry['path']
            self.start_refresh_dir_view()

    def on_delete(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Delete", "Please select items to delete.")
            return
        confirm = messagebox.askyesno("Confirm", "Are you sure you want to delete the selected items?")
        if not confirm:
            return
        if is_mac():
            delete_items(selected)
        elif is_windows():
            delete_windows_items(selected)
        self.start_refresh_dir_view()

if __name__ == "__main__":
    app = DiskCleanerApp()
    app.mainloop()
