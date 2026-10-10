"""Shared manifest contract for the runtime, SDK and packaging CLI."""
import re
from pathlib import PurePosixPath

API_VERSION = 1
ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
KINDS = {"modules", "providers", "themes", "languages", "widgets", "deviceModels", "flowNodes", "settings"}
PERMISSIONS = {"api", "providers", "events", "tasks", "storage", "network"}
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class PluginError(ValueError):
    pass


def safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise PluginError("Invalid package path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {".", "..", ""} for part in value.split("/")):
        raise PluginError("Package paths must be relative and normalized")
    if any(part.rstrip(" .") != part or part.split(".")[0].casefold() in RESERVED or any(ord(char) < 32 or char in '<>"|?*' for char in part) for part in path.parts):
        raise PluginError("Package path is not portable")
    return path


def validate_manifest(value):
    if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or type(value.get("apiVersion")) is not int or value.get("schemaVersion") != 1 or value.get("apiVersion") != API_VERSION:
        raise PluginError("Unsupported plugin schema or host API version")
    if not isinstance(value.get("id"), str) or not ID.fullmatch(value["id"]) or len(value["id"]) > 96:
        raise PluginError("Invalid plugin id")
    safe_path(value["id"])
    if not isinstance(value.get("version"), str) or not VERSION.fullmatch(value["version"]):
        raise PluginError("version must use SemVer")
    if not isinstance(value.get("name"), str) or not 1 <= len(value["name"]) <= 128:
        raise PluginError("Plugin name is required")
    permissions = value.get("permissions", [])
    if not isinstance(permissions, list) or any(not isinstance(p, str) or p not in PERMISSIONS for p in permissions):
        raise PluginError("Unsupported permission")
    if not isinstance(value.get("dependencies", {}), dict):
        raise PluginError("dependencies must be an object")
    for dep, major in value.get("dependencies", {}).items():
        if not isinstance(dep, str) or not ID.fullmatch(dep) or dep == value["id"] or type(major) is not int or major < 0:
            raise PluginError("Dependencies map plugin ids to compatible major versions")
    entries = value.get("entrypoints", {})
    if not isinstance(entries, dict) or set(entries) - {"python", "web"}:
        raise PluginError("Unsupported entrypoint")
    for kind, path in entries.items():
        safe_path(path)
        if not path.endswith(".py" if kind == "python" else ".js"):
            raise PluginError("Entrypoints must be built .py or .js files")
        if kind == "web" and not path.startswith("web/"):
            raise PluginError("Public web entrypoint must live in web/")
    contributions = value.get("contributes", {})
    if not isinstance(contributions, dict) or set(contributions) - KINDS:
        raise PluginError("Unknown contribution kind")
    for kind, records in contributions.items():
        if not isinstance(records, list):
            raise PluginError("Contributions must be lists")
        ids = set()
        for record in records:
            identifier = record.get("id") if isinstance(record, dict) else None
            pattern = r"^[a-z]{2,3}(?:-[A-Za-z0-9]+)*$" if kind == "languages" else ID
            if not isinstance(identifier, str) or not re.fullmatch(pattern, identifier) or identifier in ids:
                raise PluginError("Invalid or duplicate contribution id")
            ids.add(record["id"])
            if "file" in record:
                safe_path(record["file"])
                if not record["file"].startswith("web/"):
                    raise PluginError("Contribution resources must live in web/")
            if kind in {"themes", "languages"} and not isinstance(record.get("file"), str):
                raise PluginError("Theme and language contributions require a JSON file")
            if kind == "providers":
                fields = record.get("fields", [])
                if not isinstance(fields, list) or len(fields) > 64:
                    raise PluginError("Provider fields must be a bounded list")
                field_ids = set()
                for field in fields:
                    key = field.get("key") if isinstance(field, dict) else None
                    if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key) or key == "integration_name" or key in field_ids or not isinstance(field.get("label"), str) or field.get("type", "text") not in {"text", "password", "number", "checkbox"}:
                        raise PluginError("Invalid provider form field")
                    field_ids.add(key)
    return value
