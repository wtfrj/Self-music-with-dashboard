<div align="center">

# 🎵 Premium Discord Music Bot with Web Dashboard

![Python](https://img.shields.io/badge/Python-3.8+-FF69B4?style=for-the-badge&logo=python&logoColor=white)
![Discord](https://img.shields.io/badge/Discord.py-Ready-FF69B4?style=for-the-badge&logo=discord&logoColor=white)
![Dashboard](https://img.shields.io/badge/Dashboard-Included-FF69B4?style=for-the-badge)

A high-performance, feature-rich Discord music bot equipped with a fully integrated web dashboard. Designed for seamless audio playback, server management, and a premium user experience.

**Made by wtfrj**

</div>

## ✨ Key Features

- 🎶 **Advanced Music Player:** High-quality audio playback managed via dedicated cogs (`cogs/music.py`).
- 🎛️ **Interactive Web Dashboard:** Manage your bot and queue directly from your browser using a sleek UI (`dashboard.py`).
- 🔐 **Secure Authentication:** Built-in login system (`login.html`) to protect dashboard access.
- ⚙️ **Highly Customizable:** Easily tweak bot strings and core settings via `config.json` and `strings.json`.
- 🎨 **Modern Frontend:** Clean, responsive web design powered by custom CSS and JS (`static/style.css`, `static/script.js`).

## 📁 Directory Structure

```text
V2-Music-Bot/
├── main.py                 # Core Discord bot entry point
├── dashboard.py            # Flask/Web dashboard backend
├── config.json             # Main configuration file (tokens, prefixes)
├── strings.json            # Customizable text and responses
├── utils.py                # Helper functions and utilities
├── cmd.txt                 # Command references and startup flags
├── requirements.txt        # Python dependencies
├── cogs/                   # Bot modules
│   └── music.py            # Music playback commands and logic
├── static/                 # Dashboard static assets
│   ├── script.js           # Frontend interactive logic
│   └── style.css           # Dashboard styling
└── templates/              # Dashboard HTML pages
    ├── index.html          # Main control panel
    └── login.html          # Authentication page
