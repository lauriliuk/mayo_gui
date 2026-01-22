import os
import subprocess
import threading
import queue
import shutil
import sys
import time
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    from tkinterdnd2 import DND_FILES, DND_TEXT
    HAS_DND = True
except ImportError:
    HAS_DND = False


class MayoConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mayo Converter GUI")
        self.geometry("900x600")

        self.mayo_path_var = tk.StringVar(value=self.find_mayo())
        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.blender_path_var = tk.StringVar(value=self.find_blender())
        self.simplify_var = tk.BooleanVar(value=False)
        self.simplify_ratio_var = tk.DoubleVar(value=0.7)
        self.ratio_percent_var = tk.StringVar(value="70")
        self.preprocess_var = tk.BooleanVar(value=False)
        self.advanced_simplify_var = tk.BooleanVar(value=True)
        self.delete_loose_var = tk.BooleanVar(value=True)
        self.smooth_normals_var = tk.BooleanVar(value=False)

        self.create_widgets()

        self.proc = None
        self.output_queue = queue.Queue()
        # Track whether the app is closing to avoid showing dialogs or scheduling callbacks
        self._closing = False
        # ID for any scheduled after callback so we can cancel it on close
        self._after_id = None
        # Track simplification progress separately from conversion
        self.simplify_running = False
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

    def find_blender(self):
        # Try to locate blender executable in PATH or common locations
        exe = shutil.which("blender.exe") or shutil.which("blender")
        if exe:
            return exe
        # Common install locations (not exhaustive)
        possible = [
            r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
            r"C:\Program Files (x86)\Blender Foundation\Blender\blender.exe",
        ]
        for p in possible:
            if os.path.exists(p):
                return p
        return ""  # Empty if not found

    def create_widgets(self):
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Mayo executable selector
        row = ttk.Frame(frm)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Mayo executable:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.mayo_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(row, text="Browse", command=self.browse_mayo).pack(side=tk.LEFT)

        # Input file with drag-and-drop
        row = ttk.Frame(frm)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Input file (.stp/.step):").pack(side=tk.LEFT)
        self.input_entry = ttk.Entry(row, textvariable=self.input_path_var)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(row, text="Browse", command=self.browse_input).pack(side=tk.LEFT)
        
        # Register input entry for drag-and-drop (if available)
        if HAS_DND:
            try:
                self.input_entry.drop_target_register(DND_FILES, DND_TEXT)
                self.input_entry.dnd_bind('<<Drop>>', self.on_drop_input)
            except tk.TclError:
                # DnD registration failed; app will still work with browse button
                pass

        # Output file
        row = ttk.Frame(frm)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Output file (.glb/.gltf):").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.output_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(row, text="Browse", command=self.browse_output).pack(side=tk.LEFT)

        # Blender simplification options
        simplify_frm = ttk.LabelFrame(frm, text="Model Simplification (optional)", padding=8)
        simplify_frm.pack(fill=tk.X, pady=8)

        # Blender executable selector
        blender_row = ttk.Frame(simplify_frm)
        blender_row.pack(fill=tk.X, pady=4)
        ttk.Label(blender_row, text="Blender executable:").pack(side=tk.LEFT)
        ttk.Entry(blender_row, textvariable=self.blender_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(blender_row, text="Browse", command=self.browse_blender).pack(side=tk.LEFT)

        # Simplify checkbox
        checkbox_row = ttk.Frame(simplify_frm)
        checkbox_row.pack(fill=tk.X, pady=4)
        ttk.Checkbutton(checkbox_row, text="Enable model simplification after conversion", variable=self.simplify_var).pack(side=tk.LEFT)

        # Simplification ratio slider
        ratio_row = ttk.Frame(simplify_frm)
        ratio_row.pack(fill=tk.X, pady=4)
        ttk.Label(ratio_row, text="Polygon reduction ratio:").pack(side=tk.LEFT)
        ttk.Scale(ratio_row, from_=0.1, to=1.0, variable=self.simplify_ratio_var, orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Label(ratio_row, text="Keep:").pack(side=tk.LEFT)
        self.ratio_entry = ttk.Entry(ratio_row, width=6, textvariable=self.ratio_percent_var)
        self.ratio_entry.pack(side=tk.LEFT, padx=4)
        self.ratio_entry.bind("<Return>", self.on_ratio_entry)
        self.ratio_entry.bind("<FocusOut>", self.on_ratio_entry)
        self.ratio_label = ttk.Label(ratio_row, text="50%", width=6)
        self.ratio_label.pack(side=tk.LEFT)
        self.simplify_ratio_var.trace('w', self.update_ratio_label)

        # Simplification options
        options_row = ttk.Frame(simplify_frm)
        options_row.pack(fill=tk.X, pady=4)
        ttk.Checkbutton(options_row, text="Pre-process (merge by distance)", variable=self.preprocess_var).pack(side=tk.LEFT)
        ttk.Checkbutton(options_row, text="Advanced simplification", variable=self.advanced_simplify_var).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(options_row, text="Remove loose geometry", variable=self.delete_loose_var).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(options_row, text="Smooth normals", variable=self.smooth_normals_var).pack(side=tk.LEFT, padx=8)

        # Controls (top)
        row = ttk.Frame(frm)
        row.pack(fill=tk.X, pady=8)
        self.convert_btn = ttk.Button(row, text="Convert", command=self.start_conversion)
        self.convert_btn.pack(side=tk.LEFT)
        self.preview_btn = ttk.Button(row, text="Preview", command=self.preview_output, state=tk.DISABLED)
        self.preview_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="Open output folder", command=self.open_output_folder).pack(side=tk.LEFT, padx=6)

        # Log area
        ttk.Label(frm, text="Console:").pack(anchor=tk.W)
        self.log = ScrolledText(frm, height=12)
        self.log.pack(fill=tk.BOTH, expand=True)

        # Bottom bar with About button
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=6)
        ttk.Button(bottom, text="About", command=self.show_credits).pack(side=tk.RIGHT)

    def browse_mayo(self):
        p = filedialog.askopenfilename(title="Select mayo-conv executable", filetypes=[("Executable", "*.exe;*.*")])
        if p:
            self.mayo_path_var.set(p)

    def browse_blender(self):
        p = filedialog.askopenfilename(title="Select Blender executable", filetypes=[("Executable", "*.exe;*.*")])
        if p:
            self.blender_path_var.set(p)

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

    def update_ratio_label(self, *args):
        """Update the ratio label as the slider changes."""
        ratio = self.simplify_ratio_var.get()
        self.ratio_label.config(text=f"{ratio*100:.0f}%")
        self.ratio_percent_var.set(f"{ratio*100:.0f}")

    def on_ratio_entry(self, event=None):
        """Clamp ratio entry and keep it in range."""
        try:
            percent = float(self.ratio_percent_var.get())
        except (TypeError, ValueError):
            percent = 50.0
        percent = max(1.0, min(100.0, percent))
        self.ratio_percent_var.set(f"{percent:.0f}")
        self.simplify_ratio_var.set(percent / 100.0)

    def on_drop_input(self, event):
        """Handle drag-and-drop of files onto input entry."""
        data = event.data
        # Parse the dropped data (may contain braces on Windows)
        files = self.parse_dnd_data(data)
        
        if not files:
            return
        
        # Use the first file dropped
        dropped_file = files[0]
        
        # Check if it's a valid STEP file
        valid_extensions = ('.step', '.stp')
        if not dropped_file.lower().endswith(valid_extensions):
            messagebox.showwarning("Invalid file", f"Please drop a STEP file (.step or .stp)\nReceived: {os.path.basename(dropped_file)}")
            return
        
        self.input_path_var.set(dropped_file)
        
        # Auto-generate output file path
        base = os.path.splitext(os.path.basename(dropped_file))[0]
        dirpart = os.path.dirname(dropped_file)
        if '/' in dropped_file and '\\' not in dropped_file:
            out = dirpart.rstrip('/') + '/' + base + ".glb"
        else:
            out = os.path.join(dirpart, base + ".glb")
        self.output_path_var.set(out)
        
        self.log.insert(tk.END, f"Loaded input file: {dropped_file}\n")
        self.log.see(tk.END)

    @staticmethod
    def parse_dnd_data(data):
        """Parse drag-and-drop data which may contain file paths wrapped in braces."""
        # Remove surrounding braces if present (Windows behavior)
        data = data.strip()
        if data.startswith('{') and data.endswith('}'):
            data = data[1:-1]
        
        # Split by spaces but handle paths with spaces
        # On Windows, multiple files are space-separated, each potentially in braces
        files = []
        current = ""
        in_brace = False
        
        for char in data:
            if char == '{':
                in_brace = True
            elif char == '}':
                in_brace = False
                if current:
                    files.append(current.strip())
                    current = ""
            elif char == ' ' and not in_brace:
                if current:
                    files.append(current.strip())
                    current = ""
            else:
                current += char
        
        if current:
            files.append(current.strip())
        
        return [f for f in files if f]

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

        # Check if simplification is enabled but Blender is not found
        if self.simplify_var.get():
            blender = self.blender_path_var.get().strip()
            if not blender or not os.path.exists(blender):
                messagebox.showerror("Error", "Simplification enabled but Blender executable not found. Please locate Blender or disable simplification.")
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
                        
                        # Proceed with simplification if enabled
                        if self.simplify_var.get():
                            out = self.output_path_var.get().strip()
                            self.log.insert(tk.END, f"\nStarting model simplification...\n")
                            self.log.see(tk.END)
                            
                            # Run simplification in thread
                            self.simplify_running = True
                            simplify_thread = threading.Thread(
                                target=self.run_simplification,
                                args=(out, self.simplify_ratio_var.get())
                            )
                            simplify_thread.daemon = True
                            simplify_thread.start()
                            self._after_id = self.after(100, self.poll_queue)  # Poll more frequently
                        else:
                            # Enable preview button on successful conversion (no simplification)
                            if not getattr(self, '_closing', False):
                                self.preview_btn.config(state=tk.NORMAL)
                                messagebox.showinfo("Done", "Conversion finished successfully")
                                self.convert_btn.config(state=tk.NORMAL)
                    else:
                        self.log.insert(tk.END, "\nConversion failed. See log above.\n")
                        if not getattr(self, '_closing', False):
                            messagebox.showerror("Failed", "Conversion failed. See log.")
                            self.convert_btn.config(state=tk.NORMAL)
                elif tag == "simplify_done":
                    ok = msg
                    self.simplify_running = False
                    if ok:
                        self.log.insert(tk.END, "\nSimplification finished successfully.\n")
                        if not getattr(self, '_closing', False):
                            self.preview_btn.config(state=tk.NORMAL)
                            messagebox.showinfo("Done", "Conversion and simplification completed successfully")
                            self.convert_btn.config(state=tk.NORMAL)
                    else:
                        self.log.insert(tk.END, "\nSimplification failed. See log above.\n")
                        if not getattr(self, '_closing', False):
                            messagebox.showwarning("Simplification Failed", "Simplification failed, but conversion was successful. See log.")
                            self.preview_btn.config(state=tk.NORMAL)
                            self.convert_btn.config(state=tk.NORMAL)
                self.log.see(tk.END)
        except queue.Empty:
            # Nothing left
            pass
        if getattr(self, '_closing', False):
            return
        if (self.proc and self.proc.poll() is None) or self.simplify_running:
            # Still running; poll again
            self._after_id = self.after(200, self.poll_queue)
        else:
            # Process ended or failed to start; ensure button enabled
            if not getattr(self, '_closing', False):
                self.convert_btn.config(state=tk.NORMAL)

    def run_simplification(self, model_path, ratio):
        """Run Blender simplification on the converted model using a log file for output."""
        try:
            blender = self.blender_path_var.get().strip()
            
            # Get the path to the blender_simplify.py script
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                script_dir = sys._MEIPASS
            else:
                script_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(script_dir, "blender_simplify.py")
            
            if not os.path.exists(script_path):
                self.output_queue.put(("err", f"ERROR: Blender script not found at {script_path}\n"))
                self.output_queue.put(("simplify_done", False))
                return
            
            # Log file to track progress
            log_file = model_path + ".simplify.log"
            
            # Run Blender with the script and arguments
            cmd = [blender, "-b", "-P", script_path, "--", model_path, str(ratio)]
            if not self.preprocess_var.get():
                cmd.append("--no-preprocess")
            if not self.advanced_simplify_var.get():
                cmd.append("--no-advanced")
            if not self.delete_loose_var.get():
                cmd.append("--no-delete-loose")
            if self.smooth_normals_var.get():
                cmd.append("--smooth")
            
            self.output_queue.put(("out", f"> Running: {' '.join(cmd)}\n"))
            
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
                )
            except Exception as e:
                self.output_queue.put(("err", f"ERROR: Failed to start Blender: {e}\n"))
                self.output_queue.put(("simplify_done", False))
                return
            
            # Monitor process and read log file
            timeout_seconds = 300
            start_time = time.time()
            last_log_pos = 0
            process_completed = False
            export_logged = False
            
            while True:
                elapsed = time.time() - start_time
                
                # Check for timeout
                if elapsed > timeout_seconds:
                    self.output_queue.put(("err", f"ERROR: Blender process timed out after {timeout_seconds} seconds\n"))
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except:
                        try:
                            proc.kill()
                        except:
                            pass
                    self.output_queue.put(("simplify_done", False))
                    return
                
                # Check if process has completed
                if proc.poll() is not None:
                    process_completed = True
                
                # Read new lines from log file
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            f.seek(last_log_pos)
                            new_lines = f.read()
                            if new_lines:
                                self.output_queue.put(("out", new_lines))
                                if (not export_logged) and ("Export successful" in new_lines):
                                    export_logged = True
                                    self.output_queue.put(("out", "Export done. Waiting for Blender to exit...\n"))
                            last_log_pos = f.tell()
                    except:
                        pass
                
                # If process completed and we've read the log, we're done
                if process_completed:
                    # Final read to catch any last lines
                    if os.path.exists(log_file):
                        try:
                            with open(log_file, 'r', encoding='utf-8') as f:
                                f.seek(last_log_pos)
                                remaining = f.read()
                                if remaining:
                                    self.output_queue.put(("out", remaining))
                        except:
                            pass
                    
                    rc = proc.returncode
                    success = rc == 0
                    self.output_queue.put(("simplify_done", success))
                    return
                
                time.sleep(0.1)  # Poll more frequently
            
        except Exception as e:
            self.output_queue.put(("err", f"Simplification error: {e}\n"))
            import traceback
            self.output_queue.put(("err", traceback.format_exc() + "\n"))
            self.output_queue.put(("simplify_done", False))

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

    def preview_output(self):
        """Open 3D preview of the converted model using 3D Viewer."""
        out = self.output_path_var.get().strip()
        
        if not out:
            messagebox.showwarning("Preview", "No output file selected")
            return
        
        if not os.path.exists(out):
            messagebox.showerror("Preview", "Output file does not exist. Please convert first.")
            return
        
        # Check if it's a valid 3D model format
        valid_formats = ('.glb', '.gltf')
        if not out.lower().endswith(valid_formats):
            messagebox.showwarning("Preview", f"File format not supported for preview.\nSupported: {', '.join(valid_formats)}")
            return
        
        # Run preview in a separate thread to avoid blocking the GUI
        preview_thread = threading.Thread(target=self.show_3d_preview, args=(out,))
        preview_thread.daemon = True
        preview_thread.start()
        
        self.log.insert(tk.END, f"Opening 3D preview...\n")
        self.log.see(tk.END)

    def show_3d_preview(self, model_path):
        """Display 3D model using Microsoft 3D Viewer."""
        try:
            # Open with 3D Viewer
            subprocess.Popen(['3dviewer.exe', model_path])
            self.log.insert(tk.END, f"Preview opened in 3D Viewer\n")
            self.log.see(tk.END)
        except FileNotFoundError:
            # If 3D Viewer not found, try default association
            try:
                if sys.platform == 'win32':
                    os.startfile(model_path)
                    self.log.insert(tk.END, f"Preview opened with default app\n")
                    self.log.see(tk.END)
            except Exception as e:
                self.log.insert(tk.END, f"Preview error: {str(e)}\n")
                self.log.see(tk.END)
        except Exception as e:
            self.log.insert(tk.END, f"Preview error: {str(e)}\n")
            self.log.see(tk.END)

    def show_credits(self):
        """Show credits dialog with Mayo repo link and license text."""
        credits_win = tk.Toplevel(self)
        credits_win.title("Credits")
        credits_win.geometry("700x500")

        frm = ttk.Frame(credits_win)
        frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        lbl = ttk.Label(frm, text="Mayo (conversion backend)", font=(None, 12, 'bold'))
        lbl.pack(anchor=tk.W)
        ttk.Label(frm, text="Blender is required for simplification and must be installed separately.").pack(anchor=tk.W, pady=(4, 0))

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
