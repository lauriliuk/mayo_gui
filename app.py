import os
import subprocess
import threading
import queue
import shutil
import sys
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText


class MayoConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mayo Converter GUI")
        self.geometry("720x480")

        self.mayo_path_var = tk.StringVar(value=self.find_mayo())
        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()

        self.create_widgets()

        self.proc = None
        self.output_queue = queue.Queue()
        # Track whether the app is closing to avoid showing dialogs or scheduling callbacks
        self._closing = False
        # ID for any scheduled after callback so we can cancel it on close
        self._after_id = None
        # Handle window close to set the closing flag
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        # Mark closing and destroy the window. This prevents later polls from recreating dialogs.
        self._closing = True
        try:
            # Optionally, terminate running process
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
        finally:
            self.destroy()

    def find_mayo(self):
        # Try to locate mayo-conv.exe in PATH or common locations
        exe = shutil.which("mayo-conv.exe") or shutil.which("mayo-conv")
        if exe:
            return exe
        # Common install locations (not exhaustive)
        possible = [
            r"C:\Program Files\Mayo\mayo-conv.exe",
            r"C:\Program Files (x86)\Mayo\mayo-conv.exe",
        ]
        for p in possible:
            if os.path.exists(p):
                return p
        return "mayo-conv.exe"  # fallback; assume on PATH

    def create_widgets(self):
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Mayo executable selector
        row = ttk.Frame(frm)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Mayo executable:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.mayo_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(row, text="Browse", command=self.browse_mayo).pack(side=tk.LEFT)

        # Input file
        row = ttk.Frame(frm)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Input file (.stp/.step):").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.input_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(row, text="Browse", command=self.browse_input).pack(side=tk.LEFT)

        # Output file
        row = ttk.Frame(frm)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Output file (.glb/.gltf):").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.output_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(row, text="Browse", command=self.browse_output).pack(side=tk.LEFT)

        # Controls (top)
        row = ttk.Frame(frm)
        row.pack(fill=tk.X, pady=8)
        self.convert_btn = ttk.Button(row, text="Convert", command=self.start_conversion)
        self.convert_btn.pack(side=tk.LEFT)
        ttk.Button(row, text="Open output folder", command=self.open_output_folder).pack(side=tk.LEFT, padx=6)

        # Log area
        ttk.Label(frm, text="Console:").pack(anchor=tk.W)
        self.log = ScrolledText(frm, height=15)
        self.log.pack(fill=tk.BOTH, expand=True)

        # Bottom bar with About button
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=6)
        ttk.Button(bottom, text="About", command=self.show_credits).pack(side=tk.RIGHT)

    def browse_mayo(self):
        p = filedialog.askopenfilename(title="Select mayo-conv executable", filetypes=[("Executable", "*.exe;*.*")])
        if p:
            self.mayo_path_var.set(p)

    def browse_input(self):
        # Only accept STEP files (.step, .stp)
        p = filedialog.askopenfilename(title="Select input STEP file", filetypes=[("STEP files", "*.step;*.stp")])
        if p:
            self.input_path_var.set(p)
            # Default output path: same folder, same basename, with .glb extension
            base = os.path.splitext(os.path.basename(p))[0]
            dirpart = os.path.dirname(p)
            # Preserve user's path separator style: if the selected input used '/', keep using '/'
            if '/' in p and '\\' not in p:
                # build using forward slash
                out = dirpart.rstrip('/') + '/' + base + ".glb"
            else:
                out = os.path.join(dirpart, base + ".glb")
            self.output_path_var.set(out)

    def browse_output(self):
        p = filedialog.asksaveasfilename(title="Select output file", defaultextension=".glb", filetypes=[("glTF (glb)", "*.glb;*.gltf"), ("All files", "*.*")])
        if p:
            self.output_path_var.set(p)

    def start_conversion(self):
        mayo = self.mayo_path_var.get().strip()
        inp = self.input_path_var.get().strip()
        out = self.output_path_var.get().strip()
        if not inp or not os.path.exists(inp):
            messagebox.showerror("Error", "Input file is missing or does not exist")
            return
        if not out:
            messagebox.showerror("Error", "Please select an output file")
            return

        cmd = [mayo, inp, "--export", out]

        # Disable UI
        self.convert_btn.config(state=tk.DISABLED)
        self.log.insert(tk.END, f"> Running: {' '.join(cmd)}\n")
        self.log.see(tk.END)

        # Run in thread
        t = threading.Thread(target=self.run_command, args=(cmd,))
        t.daemon = True
        t.start()

        # Poll queue
        # Store after id so it can be cancelled if the window is closed
        self._after_id = self.after(200, self.poll_queue)

    def run_command(self, cmd):
        try:
            # Start process
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        except Exception as e:
            self.output_queue.put(("err", f"Failed to start process: {e}\n"))
            self.output_queue.put(("done", False))
            return

        # Read stdout and stderr lines
        def reader(pipe, tag):
            try:
                for line in iter(pipe.readline, ''):
                    if line:
                        self.output_queue.put((tag, line))
            finally:
                pipe.close()

        out_thread = threading.Thread(target=reader, args=(self.proc.stdout, "out"))
        err_thread = threading.Thread(target=reader, args=(self.proc.stderr, "err"))
        out_thread.daemon = True
        err_thread.daemon = True
        out_thread.start()
        err_thread.start()

        rc = self.proc.wait()
        out_thread.join()
        err_thread.join()

        success = rc == 0
        self.output_queue.put(("done", success))

    def poll_queue(self):
        # If we're closing, don't process or show dialogs
        if getattr(self, '_closing', False):
            return

        # This poll corresponds to a scheduled after; clear stored id
        self._after_id = None

        try:
            while True:
                tag, msg = self.output_queue.get_nowait()
                if tag == "out":
                    self.log.insert(tk.END, msg)
                elif tag == "err":
                    self.log.insert(tk.END, msg)
                elif tag == "done":
                    ok = msg
                    if ok:
                        self.log.insert(tk.END, "\nConversion finished successfully.\n")
                        if not getattr(self, '_closing', False):
                            messagebox.showinfo("Done", "Conversion finished successfully")
                    else:
                        self.log.insert(tk.END, "\nConversion failed. See log above.\n")
                        if not getattr(self, '_closing', False):
                            messagebox.showerror("Failed", "Conversion failed. See log.")
                    if not getattr(self, '_closing', False):
                        self.convert_btn.config(state=tk.NORMAL)
                self.log.see(tk.END)
        except queue.Empty:
            # Nothing left
            pass
        if getattr(self, '_closing', False):
            return
        if self.proc and self.proc.poll() is None:
            # Still running; poll again
            self._after_id = self.after(200, self.poll_queue)
        else:
            # Process ended or failed to start; ensure button enabled
            if not getattr(self, '_closing', False):
                self.convert_btn.config(state=tk.NORMAL)

    def open_output_folder(self):
        out = self.output_path_var.get().strip()
        if not out:
            messagebox.showinfo("Info", "No output path set")
            return
        folder = os.path.dirname(out)
        if not os.path.isdir(folder):
            messagebox.showerror("Error", "Output folder does not exist")
            return
        try:
            if sys.platform == 'win32':
                os.startfile(folder)
            else:
                subprocess.Popen(['xdg-open', folder])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder: {e}")

    def show_credits(self):
        """Show credits dialog with Mayo repo link and license text."""
        credits_win = tk.Toplevel(self)
        credits_win.title("Credits")
        credits_win.geometry("700x500")

        frm = ttk.Frame(credits_win)
        frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        lbl = ttk.Label(frm, text="Mayo (conversion backend)", font=(None, 12, 'bold'))
        lbl.pack(anchor=tk.W)

        # Buttons row
        brow = ttk.Frame(frm)
        brow.pack(fill=tk.X, pady=6)
        ttk.Button(brow, text="Open Mayo GitHub", command=lambda: webbrowser.open("https://github.com/fougue/mayo")).pack(side=tk.LEFT)
        ttk.Button(brow, text="Close", command=credits_win.destroy).pack(side=tk.RIGHT)

        license_text = """
BSD 2-Clause License

Copyright (c) 2016, Fougue Ltd. <http://www.fougue.pro>
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

    1. Redistributions of source code must retain the above copyright
       notice, this list of conditions and the following disclaimer.

    2. Redistributions in binary form must reproduce the above
       copyright notice, this list of conditions and the following
       disclaimer in the documentation and/or other materials provided
       with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

        st = ScrolledText(frm)
        st.pack(fill=tk.BOTH, expand=True)
        st.insert(tk.END, "Mayo GitHub: https://github.com/fougue/mayo\n\n")
        st.insert(tk.END, license_text)
        st.config(state=tk.DISABLED)


if __name__ == '__main__':
    app = MayoConverterApp()
    app.mainloop()