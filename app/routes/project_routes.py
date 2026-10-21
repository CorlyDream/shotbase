import hashlib
import logging
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, send_file, url_for
from PIL import Image, ImageOps
from werkzeug.exceptions import RequestEntityTooLarge

from app.config.constants import ALLOWED_IMAGE_EXTENSIONS, MAX_RECENT_PROJECTS
from app.services.project_covers import ProjectCovers
from app.services.shot_manager import SHOT_NAME_RE, clear_shot_manager_cache, get_shot_manager
from app.utils import get_app_version

logger = logging.getLogger(__name__)

project_bp = Blueprint('project', __name__)


def _project_preview_id(project_path):
    return hashlib.sha256(str(Path(project_path).resolve()).encode()).hexdigest()[:20]


def _project_preview_path(project_path):
    root = Path(project_path).resolve()
    try:
        covers = ProjectCovers(root)
        entries = covers.list()
        if entries:
            return covers.image_path(entries[0]['id'])
    except (OSError, ValueError):
        logger.warning("Unable to read project covers: %s", root)
    image_dir = root / 'shots' / 'latest_images'
    if image_dir.is_dir():
        for candidate in sorted(image_dir.iterdir()):
            if (candidate.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS and candidate.is_file()
                    and candidate.resolve().is_relative_to(root)):
                return candidate
    return None


def _cover_data(project_path):
    return {
        "project_path": str(Path(project_path).resolve()),
        "covers": [
            {key: value for key, value in entry.items() if key != "filename"} | {
                "url": url_for("project.project_cover_image", project_id=_project_preview_id(project_path),
                               cover_id=entry["id"]),
            }
            for entry in ProjectCovers(project_path).list()
        ],
    }


@project_bp.route("/api/project/covers", methods=["GET", "POST"])
@project_bp.route("/api/project/covers/<cover_id>", methods=["DELETE"])
def project_covers(cover_id=None):
    """Manage covers only for the project the browser still expects to be active."""
    try:
        request.max_content_length = 100 * 1024 * 1024
        manager = current_app.config['PROJECT_MANAGER']
        project = manager.get_current_project()
        if not project:
            return jsonify({"success": False, "error": "No current project"}), 400
        if request.method == "POST":
            expected = request.form.get("project_path")
        elif request.method == "DELETE":
            expected = (request.get_json(silent=True) or {}).get("project_path")
        else:
            expected = request.args.get("project_path")
        if (not expected and request.method != "GET") or (
                expected and str(Path(expected).resolve()) != project['path']):
            return jsonify({"success": False, "error": "项目已切换，请重新打开封面区"}), 409
        covers = ProjectCovers(project['path'])
        if request.method == "POST":
            covers.add(request.files.getlist("files"))
        elif request.method == "DELETE" and not covers.remove(cover_id):
            return jsonify({"success": False, "error": "封面不存在"}), 404
        if request.method != "GET":
            manager.update_project_timestamp(project['path'])
        response = jsonify({"success": True, "data": _cover_data(project['path'])})
        response.headers['Cache-Control'] = 'private, no-store'
        return response
    except RequestEntityTooLarge:
        return jsonify({"success": False, "error": "本次上传超过 100 MB，请分批上传"}), 413
    except (ValueError, TypeError) as error:
        return jsonify({"success": False, "error": str(error)}), 400
    except OSError:
        logger.exception("Unable to save project covers")
        return jsonify({"success": False, "error": "封面读写失败，请检查项目目录的空间和权限"}), 500


@project_bp.route("/api/project/covers/<project_id>/<cover_id>")
def project_cover_image(project_id, cover_id):
    """Pin image URLs to their own project even after the active project changes."""
    manager = current_app.config['PROJECT_MANAGER']
    for project_path in manager.projects.get('recent_projects', []):
        if _project_preview_id(project_path) != project_id:
            continue
        try:
            path = ProjectCovers(project_path).image_path(cover_id)
            if path:
                response = send_file(path, conditional=True)
                response.headers['Cache-Control'] = 'private, no-cache, must-revalidate'
                return response
        except (OSError, ValueError):
            logger.warning("Unable to read cover %s", cover_id)
        break
    return jsonify({"success": False, "error": "封面不存在"}), 404


@project_bp.route("/")
def index():
    version = get_app_version()
    return render_template("index.html", version=version)

@project_bp.route("/api/project/current")
def get_current_project():
    try:
        project_manager = current_app.config['PROJECT_MANAGER']
        project = project_manager.get_current_project()
        if project:
            project_path = Path(project["path"])
            path_str = str(project_path)
            last_scanned = project_manager.projects.get("last_scanned", {}).get(path_str)
            folder_mtime = project_path.stat().st_mtime

            if (not last_scanned or
                    folder_mtime > datetime.fromisoformat(last_scanned).timestamp()):
                clear_shot_manager_cache()
                get_shot_manager(path_str).get_shots()
                project_manager.projects.setdefault("last_scanned", {})[path_str] = (
                    datetime.fromtimestamp(folder_mtime).isoformat()
                )
                project_manager.save_projects()
            return jsonify({"success": True, "data": project})
        return jsonify({"success": False, "error": "No current project"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@project_bp.route("/api/project/recent")
def get_recent_projects():
    try:
        project_manager = current_app.config['PROJECT_MANAGER']
        recent_projects = []
        for project_path in project_manager.projects.get('recent_projects', []):
            p = Path(project_path)
            shots_dir = p / 'shots'
            if shots_dir.exists():
                created = datetime.fromtimestamp(p.stat().st_ctime).isoformat()
                project_info = project_manager.load_project_info(project_path)
                wip = shots_dir / 'wip'
                shot_count = sum(
                    entry.is_dir() and bool(SHOT_NAME_RE.fullmatch(entry.name))
                    for entry in wip.iterdir()
                ) if wip.is_dir() else 0
                recent_projects.append({
                    "name": project_info.get('title', p.name),
                    "path": str(p.resolve()),
                    "created": created,
                    "updated": project_info.get('updated', created),
                    "shot_count": shot_count,
                    "preview_url": url_for('project.project_preview', project_id=_project_preview_id(p))
                    if _project_preview_path(p) else None,
                    "shots": []
                })
        response = jsonify({"success": True, "data": recent_projects})
        response.headers['Cache-Control'] = 'no-store'
        return response
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@project_bp.route("/api/project/preview/<project_id>")
def project_preview(project_id):
    """Read a recent project's cover without changing the active project."""
    project_manager = current_app.config['PROJECT_MANAGER']
    for project_path in project_manager.projects.get('recent_projects', []):
        if _project_preview_id(project_path) != project_id:
            continue
        source = _project_preview_path(project_path)
        if source:
            try:
                stat = source.stat()
                with Image.open(source) as image:
                    preview = ImageOps.exif_transpose(image).convert('RGB')
                    preview.thumbnail((640, 360), Image.Resampling.LANCZOS)
                    output = BytesIO()
                    preview.save(output, format='JPEG', quality=85)
                output.seek(0)
                response = send_file(
                    output, mimetype='image/jpeg',
                    etag=f'{project_id}-{stat.st_mtime_ns}-{stat.st_size}',
                )
                response.headers['Cache-Control'] = 'private, no-cache, must-revalidate'
                return response
            except OSError:
                logger.warning("Unable to read project preview: %s", source)
        break
    return jsonify({"success": False, "error": "Project preview unavailable"}), 404

@project_bp.route("/api/project/open", methods=["POST"])
def open_project():
    try:
        project_manager = current_app.config['PROJECT_MANAGER']
        data = request.get_json()
        project_path = data.get("path")
        if not project_path:
            return jsonify({"success": False, "error": "Project path required"}), 400
        from app.utils import sanitize_path
        project_path = sanitize_path(project_path).resolve()
        path_str = str(project_path)
        shots_dir = project_path / "shots"

        logger.debug("Received raw path from frontend: %s", request.get_json())
        logger.debug("Looking at path: %s", project_path)
        logger.debug("shots/ folder exists? %s", shots_dir.exists())

        if not shots_dir.exists():
            return jsonify({"success": False, "error": "No recognizable project structure"}), 400

        # Create project info file if it doesn't exist
        project_info = project_manager.load_project_info(project_path)

        project_data = {
            "name": project_path.name,
            "path": path_str,
            "created": datetime.fromtimestamp(project_path.stat().st_ctime).isoformat(),
            "info": project_info,
            "shots": []
        }

        # Ensure new folder layout exists
        (shots_dir / "wip").mkdir(parents=True, exist_ok=True)
        (shots_dir / "latest_images").mkdir(exist_ok=True)
        (shots_dir / "latest_videos").mkdir(exist_ok=True)

        # Update project manager state
        path_str = str(project_path)
        project_manager.projects['current_project'] = path_str

        # Always move the project to the front of recent projects
        recents = project_manager.projects.get('recent_projects', [])
        if path_str in recents:
            recents.remove(path_str)
        recents.insert(0, path_str)
        project_manager.projects['recent_projects'] = recents[:MAX_RECENT_PROJECTS]

        last_scanned = project_manager.projects.get('last_scanned', {}).get(path_str)
        folder_mtime = project_path.stat().st_mtime
        if (not last_scanned or
                folder_mtime > datetime.fromisoformat(last_scanned).timestamp()):
            clear_shot_manager_cache()
            shot_manager = get_shot_manager(path_str)
            shot_manager.get_shots()
            project_manager.projects.setdefault('last_scanned', {})[path_str] = (
                datetime.fromtimestamp(folder_mtime).isoformat()
            )
        project_manager.save_projects()

        return jsonify({"success": True, "data": project_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@project_bp.route("/api/project/create", methods=["POST"])
def create_project():
    try:
        project_manager = current_app.config['PROJECT_MANAGER']
        data = request.get_json()
        project_name = data.get("name", "Untitled Project")
        selected_folder = data.get("path", ".")
        from app.utils import sanitize_path
        folder_path = sanitize_path(selected_folder).resolve()

        # Create project via service (this handles recents correctly)
        project_info_obj = project_manager.create_project(folder_path, project_name)

        # Failed attempts must not replace the last successful location.
        project_manager.set_last_project_location(folder_path)

        # Load project info for frontend (includes title, description, etc.)
        project_info = project_manager.load_project_info(project_info_obj["path"])

        project_data = {
            "name": project_name,
            "path": project_info_obj["path"],
            "created": project_info_obj["created"],
            "info": project_info,
            "shots": []
        }

        return jsonify({"success": True, "data": project_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@project_bp.route("/api/project/info", methods=["GET"])
def get_project_info():
    """Get project information for the current project"""
    try:
        project_manager = current_app.config['PROJECT_MANAGER']
        project = project_manager.get_current_project()
        if project:
            return jsonify({"success": True, "data": project.get('info', {})})
        return jsonify({"success": False, "error": "No current project"}), 400
    except Exception as e:
        logger.error("Error in get_project_info: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


@project_bp.route("/api/project/info", methods=["POST"])
def update_project_info():
    """Update project information for the current project"""
    try:
        project_manager = current_app.config['PROJECT_MANAGER']
        data = request.get_json()
        
        project = project_manager.get_current_project()
        if not project:
            return jsonify({"success": False, "error": "No current project"}), 400
        
        # Get the project path
        project_path = project['path']
        
        # Ensure project_path is a string (it might be a Path object)
        if hasattr(project_path, '__fspath__'):  # It's a Path-like object
            project_path = str(project_path)
        
        # Update project info
        updated_info = project_manager.save_project_info(project_path, data)
        
        return jsonify({"success": True, "data": updated_info})
    except Exception as e:
        logger.error("Error in update_project_info: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


@project_bp.route("/api/project/last-location")
def get_last_project_location():
    """Get the last location used for project creation"""
    try:
        project_manager = current_app.config['PROJECT_MANAGER']
        last_location = project_manager.get_project_creation_location()
        return jsonify({"success": True, "data": {"path": last_location}})
    except Exception as e:
        logger.error("Error getting last project location: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


@project_bp.route("/api/settings", methods=["GET", "POST"])
def system_settings():
    """Read or update application-wide project location preferences."""
    try:
        project_manager = current_app.config['PROJECT_MANAGER']
        if request.method == "POST":
            data = request.get_json(silent=True)
            if not isinstance(data, dict) or "default_project_location" not in data:
                raise ValueError("Default project location required.")
            project_manager.set_default_project_location(data["default_project_location"])
        response = jsonify({"success": True, "data": {
            "default_project_location": project_manager.projects.get('default_project_location') or "",
            "project_location": project_manager.get_project_creation_location(),
        }})
        response.headers["Cache-Control"] = "no-store"
        return response
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("Error accessing system settings")
        return jsonify({"success": False, "error": str(e)}), 500

@project_bp.route("/api/system/browse-folder")
def browse_folder():
    """Open a native folder picker dialog and return the selected path"""
    try:
        # Debug/test hooks (for testing fallback behavior on any OS)
        force_path = request.args.get("force_path")
        if force_path:
            return jsonify({"success": True, "data": {"path": force_path}})
        if request.args.get("force_warning") == "1":
            import os
            home_dir = os.path.expanduser("~")
            return jsonify({
                "success": True,
                "data": {"path": home_dir},
                "warning": "Native folder dialog not available. Defaulted to your home directory. You can manually edit the path."
            })
        if request.args.get("force_error") == "1":
            return jsonify({"success": False, "error": "Forced test error"}), 400

        # Try to use tkinter for native folder dialog first
        try:
            from tkinter import Tk, filedialog

            # Create and hide the root window
            root = Tk()
            root.withdraw()
            root.attributes('-topmost', True)  # Bring dialog to front

            # Open folder dialog
            folder_path = filedialog.askdirectory(title="Select Project Folder")
            root.destroy()

            if not folder_path:
                return jsonify({"success": False, "error": "No folder selected"}), 400

            return jsonify({"success": True, "data": {"path": folder_path}})

        except ImportError:
            logger.info("Tkinter not available, trying alternative methods")
        except Exception as e:
            logger.warning("Tkinter failed: %s", e)

        # macOS fallback: AppleScript NSOpenPanel
        try:
            if sys.platform == "darwin":
                import shutil
                import subprocess
                script = 'POSIX path of (choose folder with prompt "Select Project Folder")'
                osascript_path = shutil.which("osascript")
                if osascript_path:
                    result = subprocess.run(
                        [osascript_path, "-e", script],
                        capture_output=True,
                        text=True,
                        check=True,
                        shell=False
                    )  # noqa: S603
                    folder_path = result.stdout.strip()
                    if folder_path:
                        return jsonify({"success": True, "data": {"path": folder_path}})
                    else:
                        return jsonify({"success": False, "error": "No folder selected"}), 400
                else:
                    raise FileNotFoundError("osascript not found")
        except Exception as e:
            logger.warning("AppleScript folder picker failed: %s", e)

        # Fallback: Return the user's home directory as a starting point
        # This allows the UI to show a sensible default and let the user manually edit the path
        import os
        home_dir = os.path.expanduser("~")
        return jsonify({
            "success": True,
            "data": {"path": home_dir},
            "warning": "Native folder dialog not available. Defaulted to your home directory. You can manually edit the path."
        })

    except Exception as e:
        logger.error("Error in browse_folder: %s", e)
        return jsonify({"success": False, "error": f"Failed to open folder dialog: {str(e)}"}), 500
