"""Deterministic .hdop ZIP packaging, hashes and bounded extraction."""
import hashlib
import json
import stat
import zipfile
from pathlib import Path
from .manifest import PluginError, safe_path, validate_manifest

MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_FILES = 4096
IGNORED = {".git", "node_modules", "__pycache__", ".venv", ".pytest_cache", ".data"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pack(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    manifest = validate_manifest(json.loads((source / "hdo.json").read_text("utf-8")))
    files = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in IGNORED for part in relative.parts) or path == target or path.suffix == ".hdop" or path.name.endswith(".hdop.sha256"):
            continue
        if path.is_symlink():
            raise PluginError("Symlinks cannot be packaged")
        if path.is_file() and relative.as_posix() != "checksums.json":
            if path.name == "hdo.json" and relative.as_posix() != "hdo.json":
                raise PluginError("One plugin per repository: only the root hdo.json is allowed")
            safe_path(relative.as_posix())
            files[relative.as_posix()] = path.read_bytes()
    if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_EXPANDED_BYTES:
        raise PluginError("Plugin exceeds package limits")
    if len({name.casefold() for name in files}) != len(files):
        raise PluginError("Case-colliding paths are not portable")
    for entry in manifest.get("entrypoints", {}).values():
        if entry not in files:
            raise PluginError("Build plugin entrypoints before packaging")
    for records in manifest.get("contributes", {}).values():
        for record in records:
            if "file" in record and record["file"] not in files:
                raise PluginError("Missing contribution resource")
    files["checksums.json"] = json.dumps({name: digest(data) for name, data in files.items()}, sort_keys=True).encode()
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)
    if target.stat().st_size > MAX_PACKAGE_BYTES:
        target.unlink()
        raise PluginError("Compressed package exceeds 64 MiB")
    return target


def unpack(package, destination):
    destination = Path(destination).resolve()
    if Path(package).stat().st_size > MAX_PACKAGE_BYTES:
        raise PluginError("Package exceeds 64 MiB")
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILES + 1 or sum(i.file_size for i in infos) > MAX_EXPANDED_BYTES:
            raise PluginError("Expanded package exceeds limits")
        names = set()
        folded = set()
        for info in infos:
            safe_path(info.filename)
            if info.filename in names or info.filename.casefold() in folded or info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
                raise PluginError("Duplicate paths, directories and symlinks are not allowed")
            names.add(info.filename); folded.add(info.filename.casefold())
        if not {"hdo.json", "checksums.json"} <= names:
            raise PluginError("Missing manifest or checksums")
        if any(name.endswith("/hdo.json") for name in names):
            raise PluginError("A .hdop package must contain exactly one plugin")
        hashes = json.loads(archive.read("checksums.json"))
        if not isinstance(hashes, dict) or set(hashes) != names - {"checksums.json"}:
            raise PluginError("Checksum inventory does not match package")
        manifest = validate_manifest(json.loads(archive.read("hdo.json")))
        for entry in manifest.get("entrypoints", {}).values():
            if entry not in names:
                raise PluginError("Missing entrypoint")
        for records in manifest.get("contributes", {}).values():
            for record in records:
                if "file" in record and record["file"] not in names:
                    raise PluginError("Missing contribution resource")
        for name in names - {"checksums.json"}:
            data = archive.read(name)
            if digest(data) != hashes[name]:
                raise PluginError("Checksum mismatch")
        # Validate everything before writing anything. Caller uses a private staging directory.
        for name in names:
            target = destination.joinpath(*safe_path(name).parts)
            if not target.resolve().is_relative_to(destination):
                raise PluginError("Extraction escaped destination")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    return manifest
