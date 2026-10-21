<div align="center">
  <img src="./logo_shotbuddyv3.png" alt="ShotBase Logo" width="100"/>
</div>

<h1 align="center">ShotBase</h1>

<h3 align="center">(previously ShotBuddy V3)</h3>

<p align="center">
  <strong>Your AI Filmmaking Asset Manager.</strong>
  <br />
  An open-source tool designed to manage, organize, and streamline your entire AI filmmaking asset workflow.
</p>

<p align="center">
  <img alt="Latest Release" src="https://img.shields.io/github/v/release/taruma/shotbase"/>
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg"/>
  <img alt="Python Version" src="https://img.shields.io/badge/python-3.13.1%2B-blue"/>
</p>

---

ShotBase takes the chaos out of AI filmmaking. Instead of juggling countless generated files in messy folders, ShotBase provides a structured, visual, and intuitive interface to build your stories shot by shot. This fork supercharges the original with powerful project management, advanced version control, and a modern user experience tailored for today's creative workflows.

<p align="center">
  <img src="https://github.com/user-attachments/assets/e7ce1616-8936-49e8-a3fa-45403cd92203" alt="ShotBase Main Interface with Table of Contents"/>
</p>

## ✨ Key Features

This version of ShotBase is packed with features designed to make your workflow faster and more organized.

### 🆕 What's New in v4
- **Shot Search** — Press Ctrl+Shift+F to search across all shots' prompts, captions, notes, and names. Filter by content type and archive status for quick shot discovery.
  ![Shot Search](https://github.com/user-attachments/assets/4d1acc72-3132-410c-b90d-6935a1a99f44)
- **Visual Reorder Grid** — Drag-and-drop shot sorting with a responsive 5-column layout, thumbnail type switching, video preview, and inline display name editing.
  ![Visual Reorder Grid](https://github.com/user-attachments/assets/621593bb-5932-4ef8-a986-84d858bac6e8)
- **Alternative Video Asset** — New `alt_video` type for storing reference footage, upscales, or any additional video variant alongside your main video.
  ![Alternative Video Asset](https://github.com/user-attachments/assets/05848b1a-bfbe-4d19-bd7a-2c4059577f54)
- **Export Enhancements** — Display name columns now included in markdown exports, alt video assets exported, and a new "Open Exports Folder" button for quick access.
- **UI Polish** — Sticky header stays visible on scroll, browser tab shows dynamic project title, and the table of contents has a collapsible archived section.
- **Performance** — Thumbnails generated lazily on first request, and version scans cached per shot for faster page loads.

### 🎵 v4.1 — Audio Asset Support
- **Audio Assets** — Upload, manage, and play back `.mp3`, `.wav`, `.ogg`, `.flac`, `.aac`, or `.m4a` files alongside your images and videos. Full versioning, promotion, export, and search indexing for voiceovers, sound effects, music, and more.
- **Copy Shot Order** — New button in the export modal copies a numbered, ordered list of all active shots (with display names) to clipboard. Format: `01. SH001 — Opening Scene`.
- **Visual Reorder Image Preview** — Preview mode in the visual reorder grid now supports images (first and last frames) in addition to videos and alt videos.
- **Export Modal Layout** — Two-row button layout with utility actions (Open Exports Folder, Copy Shot Order) in the first row and primary actions centered below.
- **Performance & Stability** — Targeted DOM updates eliminate full-page flashes when archiving or editing display names; project info data loss prevention for malformed `project_info.json`; notifications moved to the bottom of the viewport.

### 🚀 Streamlined Project Management

- **Comprehensive Project Dashboard**: Get a bird's-eye view of your entire project with the responsive **Table of Shots (TOC)** panel. Filter, navigate, and see active vs. archived shots at a glance.
- **Effortless Shot Reordering**: Simply drag and drop shots to rearrange your sequence. Your story's flow is always just a move away.
  ![Effortless Shot Reordering](https://github.com/user-attachments/assets/c327eb21-b52d-4163-be52-c5d1c3178bce)
- **Flexible Archiving & Naming**: Keep your main workspace clean by archiving inactive shots. Give shots human-readable names like "Opening Scene" instead of just `SH010` for better clarity.
  ![Custom Display Names and Archiving](https://github.com/user-attachments/assets/0d87067d-def9-4d4e-a140-ee1188288d42)
- **Detailed Project Info**: Manage metadata for each project, including title, version, description, and tags, all from an intuitive modal.
  ![Project Information Management](https://github.com/user-attachments/assets/4dd9a394-2110-42db-91f8-a333fbfd948c)

### 🖼️ Powerful Asset & Version Control

- **First & Last Frame Variants**: Manage distinct opening and closing frames for each shot, complete with their own versions, prompts, and thumbnails.
  ![First and Last Frame Variants](https://github.com/user-attachments/assets/4286dc1c-7df9-45f0-afd5-acbacf5255da)
- **Instant Prompt Previews**: No more digging for prompt details. Simply hover over a thumbnail to see the exact prompt used to generate it.
  ![Instant Prompt Previews](https://github.com/user-attachments/assets/816a40ec-000b-4f6f-807e-51dcd5b305f1)
- **Automatic File Organization**: Drag and drop your generated images or videos. ShotBase automatically versions them, archives old iterations in a `wip` folder, and keeps the latest version ready for your pipeline.

### 💡 Enhanced User Experience

- **Advanced Export Options**: Precisely select what you want to export. Choose between images, videos, audio, or any combination, and even include metadata summaries for a complete project handoff.
  <img src="https://github.com/user-attachments/assets/d1c0f1bb-d897-464b-bd07-0ca8559d9900" alt="Advanced Export Modal" width="500"/>
- **Seamless Light/Dark Theme**: Switch between light and dark modes with a single click. Your preference is saved automatically for your next session.
  ![Light/Dark Theme Toggle](https://github.com/user-attachments/assets/ec2f3e5e-33a3-4200-89cc-eae3cf70f1c6)
- **And much more**: Enjoy features like dynamic note fields that expand as you type, integrated asset captions, quick access to recent projects, shot search with Ctrl+Shift+F, visual drag-and-drop reorder grid, alternative video asset support, audio asset support, copy shot order utility, and sticky header.

## 🔧 Installation

Get started with ShotBase in just a few steps. Using `uv` is recommended for its speed and efficiency.

1.  **Clone the Repository**
    *(We use a shallow clone to download faster)*
    ```bash
    git clone --depth 1 https://github.com/taruma/shotbase.git
    cd shotbase
    ```

2.  **Install Dependencies**

    *   **(Recommended) Using `uv`:**
        ```bash
        # Install uv if you haven't: https://docs.astral.sh/uv/
        uv sync
        ```
    *   **Using `venv` and `pip`:**
        ```bash
        python -m venv .venv
        source .venv/bin/activate  # On Windows: .venv\Scripts\activate
        pip install -r requirements.txt
        ```

3.  **Run the Server**
    ```bash
    # If using uv
    uv run run.py

    # If using venv and pip
    python run.py
    ```

4.  **Open Your Browser**
    Navigate to **http://192.168.2.4:5001** to start using ShotBase!

### Default project location

Open System Settings using the gear button in the project header or start menu. Set the default
project location to an existing writable folder on the computer running ShotBase.
New Project fills in this folder automatically, including after a server restart
or when using another browser. The preference is stored in `projects.json`.

Leave the setting empty to use the last successful creation location. Unavailable
locations are skipped, falling back to the current project's parent folder or
the server user's home directory. Failed creation attempts do not replace the
remembered location. A folder chosen for a single new project does not change an
explicit default.

### macOS background service

`shotbuddy.cfg` listens only on `192.168.2.4:5001`. On this Mac, use
`http://192.168.2.4:5001` while that interface is available. Loopback and other
local IPv4 interfaces are not listening.

The launchd configuration in `deploy/macos/com.shotbase.server.plist` uses this
checkout at `/Users/ajk-corly/vscode/shotbase` and uv at `/opt/homebrew/bin/uv`.
Adjust its absolute paths before using it on another machine or moving the checkout.
Install dependencies with `uv sync` before installing the service; the service uses
`uv run --no-sync run.py` and disables debug mode and automatic browser opening.
For foreground startup, `SHOTBUDDY_OPEN_BROWSER=0 uv run run.py` also disables
automatic browser opening.

Run these commands from the repository root to install and start the service:

```bash
mkdir -p "$HOME/Library/LaunchAgents" logs
cp deploy/macos/com.shotbase.server.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.shotbase.server.plist"
```

The service starts at login, survives closing the terminal, and restarts if its
process exits. It stops at logout and does not run while the Mac is asleep.
Management commands:

```bash
# Status
launchctl print "gui/$(id -u)/com.shotbase.server"
# Restart after changing code or configuration
launchctl kickstart -k "gui/$(id -u)/com.shotbase.server"
# Stop until the next login (or another bootstrap)
launchctl bootout "gui/$(id -u)/com.shotbase.server"
# Logs, from the repository root
tail -f logs/shotbase.log
# Remove login startup after stopping the service
rm "$HOME/Library/LaunchAgents/com.shotbase.server.plist"
```

## 📁 How It Works: Project Folder Structure

ShotBase automatically creates and maintains a clean, predictable folder structure for every project. This ensures your assets are always organized and easy to find.

```
project_folder/
├── shots/
│   ├── latest_images/    # The current, "promoted" image for each shot (e.g., SH010.png)
│   ├── latest_videos/    # The current, "promoted" video for each shot (e.g., SH010.mp4)
│   ├── latest_audio/     # The current, "promoted" audio for each shot (e.g., SH010.mp3)
│   └── wip/              # Work-in-progress and old versions are archived here
│       └── SH010/
│           ├── images/   # e.g., SH010_v001.png, SH010_v002.png
│           ├── videos/   # e.g., SH010_v001.mp4
│           └── audio/    # e.g., SH010_audio_v001.mp3
└── project_info.json     # Metadata like title, version, and notes
```

## 📜 Attribution and License

This project is a fork that significantly extends and modernizes the original work.

-   **Forked from** Shotbuddy by Albert Bozesan ([@albozes](https://github.com/albozes/shotbuddy)).
-   **Maintained and extended by** Taruma Sakti.
-   This project is licensed under the **MIT License**.

This project is developed with AI assistance. For detailed attribution, see the `CHANGELOG.md`.
