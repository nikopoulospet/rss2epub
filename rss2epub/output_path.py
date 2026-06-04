import dataclasses
import hashlib
import re
import string
from datetime import datetime, timezone
from pathlib import Path

from .greader import Article

DEFAULT_FORMAT = "{publish_date}/{article_name}"

# Derived from Article field metadata — the single source of truth.
# No separately maintained list; adding a template field means adding a field
# to Article with metadata={"template": True}.
_TEMPLATE_FIELDS = frozenset(
    f.name for f in dataclasses.fields(Article)
    if f.metadata.get("template")
)


def validate_template(template: str) -> None:
    """Raise ValueError on unknown fields or structural problems (absolute path, '..' segments)."""
    for _, field_name, _, _ in string.Formatter().parse(template):
        if field_name is not None and field_name not in _TEMPLATE_FIELDS:
            raise ValueError(
                f"Unknown template field {{{field_name!r}}}; "
                f"valid fields: {sorted(_TEMPLATE_FIELDS)}"
            )
    if template.lstrip().startswith("/"):
        raise ValueError("output format must be a relative path, not absolute")
    for segment in template.split("/"):
        if re.fullmatch(r"\.+", segment.strip()):
            raise ValueError("output format must not contain '..' segments")


def resolve_output_path(template: str, article: Article) -> str:
    """Return sanitized relative path WITHOUT .epub extension.

    Path separators in the template create subdirectories. Path separators
    inside a field value are slugified away — they cannot create unintended
    subdirectories. An item_id-derived hash is always appended to the final
    segment to guarantee injectivity across articles with identical metadata.
    """
    field_dict = _build_field_dict(article)
    rendered = template.format_map(field_dict)
    segments = [s for s in rendered.split("/") if s]
    id_hash = _id_hash(article.id)
    if segments:
        segments[-1] = f"{segments[-1]}-{id_hash}"
    else:
        segments = [id_hash]
    return "/".join(segments)


def check_confined(output_dir: Path, rel_path: str) -> Path:
    """Return the absolute path and raise ValueError if it escapes output_dir."""
    root = output_dir.resolve()
    abs_path = (output_dir / rel_path).resolve()
    try:
        abs_path.relative_to(root)
    except ValueError:
        raise ValueError(
            f"Resolved path {abs_path} escapes output directory {root}"
        )
    return abs_path


def _build_field_dict(article: Article) -> dict[str, str]:
    result: dict[str, str] = {}
    for f in dataclasses.fields(Article):
        if not f.metadata.get("template"):
            continue
        value = getattr(article, f.name)
        if isinstance(value, int):
            result[f.name] = datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            result[f.name] = _slugify(value or "")
    return result


def _slugify(text: str, max_len: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len]


def _id_hash(item_id: str) -> str:
    return hashlib.md5(item_id.encode()).hexdigest()[:8]
