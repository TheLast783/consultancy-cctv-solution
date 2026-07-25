import os
import sys
import subprocess
import requests
from version import __version__, GITHUB_REPO

def check_for_updates():
    """
    Checks GitHub API for the latest release version.
    Returns (has_update, latest_version_str, download_url)
    """
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            latest_tag = data.get("tag_name", "").strip().lstrip("v")
            assets = data.get("assets", [])
            download_url = None
            for asset in assets:
                if asset.get("name", "").endswith(".exe") or asset.get("name", "").endswith(".zip"):
                    download_url = asset.get("browser_download_url")
                    break
            if not download_url:
                download_url = data.get("html_url")
                
            if latest_tag and latest_tag != __version__.lstrip("v"):
                return True, latest_tag, download_url
    except Exception as e:
        print(f"Update check warning: {e}")
    return False, __version__, None

def apply_update(download_url):
    """
    Applies the update from GitHub.
    If running as python script, performs git pull.
    If running as compiled exe, downloads asset or opens browser release page.
    """
    if getattr(sys, 'frozen', False):
        if download_url and (download_url.endswith(".exe") or download_url.endswith(".zip")):
            try:
                exe_dir = os.path.dirname(sys.executable)
                is_zip = download_url.endswith(".zip")
                target_filename = "update.zip" if is_zip else "CCTVSleepMonitor_new.exe"
                save_path = os.path.join(exe_dir, target_filename)
                
                res = requests.get(download_url, stream=True, timeout=30)
                with open(save_path, "wb") as f:
                    for chunk in res.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Write update batch helper script
                bat_script = os.path.join(exe_dir, "update_helper.bat")
                with open(bat_script, "w") as f:
                    if is_zip:
                        # Unpack zip archive over existing folder (updates all .py scripts and exe)
                        f.write(
                            "@echo off\n"
                            "timeout /t 2 /nobreak > NUL\n"
                            "tar -xf update.zip\n"
                            "del update.zip\n"
                            "start CCTVSleepMonitor.exe\n"
                            "del update_helper.bat\n"
                        )
                    else:
                        f.write(
                            "@echo off\n"
                            "timeout /t 2 /nobreak > NUL\n"
                            "copy /y CCTVSleepMonitor_new.exe CCTVSleepMonitor.exe\n"
                            "del CCTVSleepMonitor_new.exe\n"
                            "start CCTVSleepMonitor.exe\n"
                            "del update_helper.bat\n"
                        )
                subprocess.Popen(["cmd.exe", "/c", bat_script], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                sys.exit(0)
            except Exception as e:
                import webbrowser
                webbrowser.open(download_url)
        else:
            import webbrowser
            webbrowser.open(download_url if download_url else f"https://github.com/{GITHUB_REPO}/releases")
    else:
        # Running as source python: fast git pull update
        try:
            subprocess.run(["git", "pull", "origin", "main"], check=True)
            return True
        except Exception as e:
            print(f"Git pull failed: {e}")
            return False
