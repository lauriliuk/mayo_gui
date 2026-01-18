# Mayo Converter GUI (minimal)

This is a minimal GUI wrapper for the `mayo-conv` command-line tool (from the Mayo project).

What it does
- Simple desktop GUI using Python/Tkinter.
- Lets you pick an input 3D file, choose an output path, and run `mayo-conv.exe` with `--export`.
- Shows console output and enables opening the output folder.

Requirements
- Windows (the app uses `os.startfile` to open folders)
- Python 3.8+ (standard library only; no extra packages required)
- `mayo-conv.exe` available on PATH or point the GUI to the executable location

Run

Open PowerShell and run:

```powershell
cd c:\GIT\3d_converter
python app.py
```

Notes
- The GUI simply invokes the external `mayo-conv` executable you already have installed. It does not embed the Mayo library.
- For a 3D preview, we can integrate a web-based preview using Three.js in a later iteration. This initial version keeps things very simple.

Next steps (optional)
- Add drag-and-drop support.
- Add batch conversion list and presets.
- Add embedded 3D preview for quick inspection of results.

## License

This project is available under a **Dual License** model:

- **Commercial License** (Default) - All rights reserved. For sales, commercial use, or proprietary deployment, contact the copyright holder.
- **MIT License** (Alternative) - Available for non-commercial, open-source projects that maintain open-source status.

See [LICENSE](LICENSE) file for full details.

## Credits

- [Mayo](https://github.com/fougue/mayo) – Open source 3D file converter and library
