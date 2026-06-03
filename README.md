# Breadcrumbs

A lightweight Windows tray app for quickly capturing daily work notes to plain UTF-8 text files.

## Run

```powershell
pip install -r requirements.txt
python app.py
```

## Build

```powershell
.\scripts\build_exe.ps1
```

Creates `Breadcrumbs.exe` in the project root.

## Notes

Notes are saved in `notes/` as `YYYY-MM-DD CW<week>.<weekday>.txt`.

Shortcuts:

- `Ctrl+Enter`: save note
- `Esc`: hide popup
