"""Renumber a project's shots using reversible, collision-checked filesystem moves."""

import json
import re
from uuid import uuid4

# Match a whole shot identifier, including sub-shots and both thumbnail prefixes.
_IDENTIFIER = re.compile(r"(?<![A-Za-z0-9])SH\d{3}(?:_\d{3})?(?=[_.]|$)")


def renumber_shots(manager, shot_order):
    """Assign sequential names and return the old-to-new identifier mapping."""
    if not isinstance(shot_order, list) or any(not isinstance(name, str) for name in shot_order):
        raise ValueError("Shot order must be a list of shot names")
    if len(set(shot_order)) != len(shot_order):
        raise ValueError("Shot order contains duplicate names")

    existing = {p.name for p in manager.wip_dir.iterdir() if p.is_dir() and p.name.startswith("SH")}
    if any(not re.fullmatch(r"SH\d{3}(?:_\d{3})?", name) or name == "SH000" for name in existing):
        raise ValueError("Project contains an invalid shot directory")
    archived = manager._load_archived() & existing
    requested = set(shot_order)
    if requested - existing or (existing - archived) - requested:
        raise ValueError("Shot order must contain every active shot and no unknown shots; reload the project")
    if len(existing) > 999:
        raise ValueError("Sequential numbering supports a maximum of 999 shots")

    # Main-grid dragging sends active shots only; dialogs also include archives.
    previous_order = list(dict.fromkeys(manager._load_shot_order() + sorted(existing)))
    order = [name for name in shot_order if name not in archived]
    order += [name for name in shot_order if name in archived]
    order += [name for name in previous_order if name in archived - requested]
    mapping = {name: f"SH{index:03d}" for index, name in enumerate(order, 1)}
    changed = {old: new for old, new in mapping.items() if old != new}

    def renamed_filename(name):
        return _IDENTIFIER.sub(lambda match: changed.get(match[0], match[0]), name)

    file_moves = []
    directory_moves = []
    for old, new in changed.items():
        directory = manager.wip_dir / old
        if directory.is_symlink():
            raise ValueError(f"Cannot renumber a linked shot directory: {old}")
        directory_moves.append((directory, manager.wip_dir / new))
        for folder in ("images", "videos", "audio"):
            media_dir = directory / folder
            if media_dir.is_symlink():
                raise ValueError(f"Cannot renumber a linked asset directory: {media_dir}")
            if media_dir.exists():
                for path in media_dir.iterdir():
                    match = _IDENTIFIER.match(path.name)
                    if match and match[0] == old:
                        file_moves.append((path, path.with_name(new + path.name[len(old):])))

    for directory in (manager.latest_images_dir, manager.latest_videos_dir,
                      manager.latest_audio_dir, manager.thumbnail_cache_dir):
        if directory.is_symlink():
            raise ValueError(f"Cannot renumber a linked asset directory: {directory}")
        if directory.exists():
            for path in directory.iterdir():
                name = renamed_filename(path.name)
                if name != path.name:
                    file_moves.append((path, path.with_name(name)))

    # Preflight both phases before making any changes, including orphan finals.
    for moves in (file_moves, directory_moves):
        sources = {source for source, _ in moves}
        targets = [target for _, target in moves]
        if len(set(targets)) != len(targets):
            raise ValueError("Renumbering would create duplicate filenames")
        for source, target in moves:
            if source.is_symlink() or (moves is file_moves and not source.is_file()):
                raise ValueError(f"Cannot renumber an unsupported asset: {source}")
            if (target.exists() or target.is_symlink()) and target not in sources:
                raise ValueError(f"Renumbering would overwrite an existing file: {target}")

    metadata = {manager.order_file: list(mapping.values())}
    if manager.archive_file.exists() or archived:
        metadata[manager.archive_file] = sorted(mapping[name] for name in archived)
    originals = {path: path.read_bytes() if path.exists() else None for path in metadata}
    token = uuid4().hex
    journal = []
    written = []

    def move(source, target):
        source.rename(target)
        journal.append((source, target))

    def write_atomic(path, content):
        temporary = path.with_name(f".reorder-{token}-{path.name}")
        try:
            temporary.write_bytes(content)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    try:
        # Vacate all sources before filling destinations so swaps cannot overwrite.
        for moves in (file_moves, directory_moves):
            staged = []
            for index, (source, target) in enumerate(moves):
                temporary = source.with_name(f".reorder-{token}-{index}")
                move(source, temporary)
                staged.append((temporary, target))
            for temporary, target in staged:
                move(temporary, target)
        for path, data in metadata.items():
            write_atomic(path, json.dumps(data).encode("utf-8"))
            written.append(path)
    except Exception:
        for source, target in reversed(journal):
            target.rename(source)
        for path in reversed(written):
            if originals[path] is None:
                path.unlink(missing_ok=True)
            else:
                write_atomic(path, originals[path])
        raise

    manager._version_scan_cache.clear()
    return mapping
