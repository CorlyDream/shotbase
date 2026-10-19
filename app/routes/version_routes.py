"""Read-only APIs for browsing existing WIP media versions in the studio UI."""

import re
from pathlib import Path

from flask import Blueprint, current_app, jsonify, send_file, url_for

from app.config.constants import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
)
from app.services.shot_manager import get_shot_manager, validate_shot_name

version_bp = Blueprint("versions", __name__)

# Each media slot has its own version prefix, even when versions share a folder.
ASSET_LOCATIONS = {
    "first_image": ("images", "_first", ALLOWED_IMAGE_EXTENSIONS),
    "last_image": ("images", "_last", ALLOWED_IMAGE_EXTENSIONS),
    "video": ("videos", "", ALLOWED_VIDEO_EXTENSIONS),
    "alt_video": ("videos", "_alt", ALLOWED_VIDEO_EXTENSIONS),
    "audio": ("audio", "_audio", ALLOWED_AUDIO_EXTENSIONS),
}


def normalize_asset_type(asset_type):
    """Use the canonical first-frame slot for the legacy `image` alias."""
    return "first_image" if asset_type == "image" else asset_type


def find_asset_versions(project_path, shot_name, asset_type):
    """Return existing files for one shot/slot, sorted by numeric version.

    Only known extensions and exact versioned filenames are accepted. The
    legacy first-frame naming convention (SH001_v001.png) remains readable.
    """
    validate_shot_name(shot_name)
    asset_type = normalize_asset_type(asset_type)
    if asset_type not in ASSET_LOCATIONS:
        raise ValueError("Unsupported asset type")

    folder, suffix, extensions = ASSET_LOCATIONS[asset_type]
    wip_folder = Path(project_path) / "shots" / "wip" / shot_name / folder
    if not wip_folder.is_dir():
        return []

    prefixes = [f"{shot_name}{suffix}"]
    if asset_type == "first_image":
        prefixes.append(shot_name)

    found = {}
    for file_path in wip_folder.iterdir():
        if not file_path.is_file() or file_path.suffix.lower() not in extensions:
            continue
        for prefix in prefixes:
            match = re.fullmatch(re.escape(prefix) + r"_v([0-9]{3,})", file_path.stem)
            if match:
                version = int(match.group(1))
                # Prefer the canonical first-frame filename over legacy naming.
                if version not in found or file_path.stem.startswith(f"{shot_name}_first_"):
                    found[version] = file_path
                break
    return sorted(found.items())


def current_project_path():
    """Return the active project path or None if no project is open."""
    project = current_app.config["PROJECT_MANAGER"].get_current_project()
    return project["path"] if project else None


@version_bp.route("/versions/<shot_name>/<asset_type>", methods=["GET"])
def list_asset_versions(shot_name, asset_type):
    """List the actual WIP files, including gaps caused by removed versions."""
    project_path = current_project_path()
    if project_path is None:
        return jsonify({"success": False, "error": "No current project"}), 400

    try:
        asset_type = normalize_asset_type(asset_type)
        items = find_asset_versions(project_path, shot_name, asset_type)
        max_version = max((version for version, _ in items), default=0)
        manager = get_shot_manager(project_path)
        current = manager.get_current_version(shot_name, asset_type, max_version)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    response = jsonify({
        "success": True,
        "data": {
            "shot_name": shot_name,
            "asset_type": asset_type,
            "current_version": current if max_version else 0,
            "versions": [
                {
                    "version": version,
                    "filename": file_path.name,
                    "url": url_for(
                        "versions.serve_version_media",
                        shot_name=shot_name,
                        asset_type=asset_type,
                        version=version,
                    ),
                }
                for version, file_path in items
            ],
        },
    })
    # Gallery lists are scoped to the active local project and can change as
    # files are uploaded, promoted, or the active project changes.
    response.headers["Cache-Control"] = "private, no-store"
    return response


@version_bp.route("/version-media/<shot_name>/<asset_type>/<int:version>", methods=["GET"])
def serve_version_media(shot_name, asset_type, version):
    """Stream one approved version from the active project's WIP directory."""
    project_path = current_project_path()
    if project_path is None:
        return "No current project", 400

    try:
        asset_type = normalize_asset_type(asset_type)
        versions = find_asset_versions(project_path, shot_name, asset_type)
    except ValueError:
        return "Invalid shot or asset type", 400

    file_path = next((path for number, path in versions if number == version), None)
    if file_path is None:
        return "Version not found", 404

    response = send_file(file_path, conditional=True)
    # The same URL can refer to different files after switching projects.
    # Revalidation preserves conditional GETs but prevents cross-project reuse.
    response.headers["Cache-Control"] = "private, no-cache, must-revalidate"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
