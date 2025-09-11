JABViewer 🔎🪟
================

Inspect and explore Java applications via the Java Access Bridge (JAB) — built with Python, CustomTkinter, and java-access-bridge-wrapper.

What it does
------------
- ✨ Lists running Java windows and lets you switch between them.
- 📂 Shows the accessibility tree (roles/names) for the selected app.
- 🔴 Highlights elements on screen when you select them in the tree.
- 🧾 Displays a detailed properties panel for the selected element.
- 📌 Keeps JABViewer on top while focusing the target Java window.

Requirements
------------
- 🪟 Windows 10/11 (64‑bit)
- 🐍 Python 3.12+ (recommended)
- ☕ 64‑bit JRE/JDK with Java Access Bridge enabled
- 🧩 Path to `WindowsAccessBridge-64.dll` available via the `RC_JAVA_ACCESS_BRIDGE_DLL` environment variable

Quick start (uv)
----------------
1) Install uv (if you don’t have it yet):

   PowerShell
   ------------
   ```powershell
   pipx install uv
   # or: python -m pip install --user uv
   ```

   CMD
   ----
   ```bat
   pipx install uv
   :: or: python -m pip install --user uv
   ```

2) Create a project venv and install dependencies from `pyproject.toml`/`uv.lock`:

   ```bash
   uv venv
   uv sync
   ```

   Note: Activating `.venv` is optional when using `uv run`.

3) Ensure the Windows Access Bridge DLL is set (only needed once per session if not set system‑wide):

   PowerShell
   ------------
   ```powershell
   $env:RC_JAVA_ACCESS_BRIDGE_DLL = "C:\\Program Files\\Java\\jdk-21\\bin\\WindowsAccessBridge-64.dll"
   ```

   CMD
   ----
   ```bat
   set RC_JAVA_ACCESS_BRIDGE_DLL=C:\\Program Files\\Java\\jdk-21\\bin\\WindowsAccessBridge-64.dll
   ```

4) Run the app with uv:

   ```bash
   uv run -m jab_viewer.app
   ```

Configuration (i18n)
--------------------
- 🌐 UI texts are available in English (default) and Portuguese.
- 📄 Language is read from `jab_viewer/config.toml` (or `config.ini`) when running from source:

  ```toml
  [app]
  language = "en"  # or "pt"
  ```

  Equivalent INI:

  ```ini
  [app]
  language = en
  ```

- 🔁 You can also set the environment variable `JAB_VIEWER_LANG` to `en` or `pt`.

Packaged Binary
---------------
- 📦 When running a frozen binary (PyInstaller), the app looks for `config.toml` or `config.ini` next to the executable.
- 📝 If none is found, it automatically creates a default `config.toml` (with `language = "en"`) next to the binary on first run.
- 🧰 To build a one‑file executable on Windows you can use `build.bat` at the repo root.

Tips & Troubleshooting
----------------------
- ☕ Make sure Java Access Bridge is enabled in your JRE/JDK installation.
- 🧭 If the app starts but can’t find the DLL, set `RC_JAVA_ACCESS_BRIDGE_DLL` to the full path of `WindowsAccessBridge-64.dll` in your installed JDK/JRE (common paths include JDK 17 or 21 under `bin/`).
- 🔒 Use 64‑bit JRE/JDK so the 64‑bit DLL is available.

License
-------
This project is licensed under the MIT License. See `LICENSE` for details.

