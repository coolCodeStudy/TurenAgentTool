from __future__ import annotations

import re
import shutil
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts.deploy_state import DeploymentState
    from scripts.deploy_support import CommandRunner
except ModuleNotFoundError:  # Direct execution through scripts/deploy_retention.py.
    from deploy_state import DeploymentState
    from deploy_support import CommandRunner


MANAGED_IMAGE_RE = re.compile(r"^investment-knowledge-app:[0-9a-f]{40}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class RetentionError(RuntimeError):
    """Raised when a managed retention operation cannot complete safely."""


@dataclass(frozen=True)
class ImageRecord:
    image_id: str
    tag: str
    created_epoch: int


def select_managed_images_for_removal(
    images: Iterable[ImageRecord],
    *,
    current_image: str | None,
    previous_image: str | None,
    referenced_image_ids: Collection[str],
) -> tuple[str, ...]:
    """Return only old, unreferenced images from the managed application allow-list."""
    records = tuple(images)
    protected_tags = {tag for tag in (current_image, previous_image) if tag}
    protected_image_ids = {
        image.image_id for image in records if image.tag in protected_tags
    }
    referenced = set(referenced_image_ids)
    return tuple(
        image.image_id
        for image in sorted(records, key=lambda item: item.created_epoch)
        if MANAGED_IMAGE_RE.fullmatch(image.tag)
        and image.tag not in protected_tags
        and image.image_id not in protected_image_ids
        and image.image_id not in referenced
    )


def remove_managed_images(
    runner: CommandRunner,
    images: Iterable[ImageRecord],
    state: DeploymentState,
    referenced_image_ids: Collection[str],
    *,
    successful_full_deployment: bool = False,
    prune_builder_cache: bool = False,
) -> tuple[str, ...]:
    """Remove selected app images and optionally the aged BuildKit cache.

    The cache command is deliberately gated by both an explicit request and a
    caller-proven stable successful full deployment. No broad Docker prune
    operation is exposed here.
    """
    image_ids = select_managed_images_for_removal(
        images,
        current_image=state.current_image,
        previous_image=state.previous_image,
        referenced_image_ids=referenced_image_ids,
    )
    for image_id in image_ids:
        _run_checked(runner, ("docker", "image", "rm", image_id), "image removal")

    if (
        successful_full_deployment
        and prune_builder_cache
        and state.last_mode == "full_image"
        and state.final_health == "healthy"
    ):
        _run_checked(
            runner,
            ("docker", "builder", "prune", "--filter", "until=168h", "--force"),
            "builder cache cleanup",
        )
    return image_ids


def retain_release_directories(
    releases_dir: Path, keep_shas: tuple[str, ...]
) -> tuple[Path, ...]:
    """Delete only old SHA-named directories directly below ``releases_dir``.

    Symlinks, files, non-SHA directories, and entries resolving outside the
    managed root are left untouched. ``keep_shas`` contains directory names,
    never paths, so it cannot expand the deletion boundary.
    """
    if releases_dir.is_symlink() or not releases_dir.exists():
        return ()
    if not releases_dir.is_dir():
        raise NotADirectoryError(releases_dir)

    root = releases_dir.resolve(strict=True)
    protected = {sha for sha in keep_shas if _SHA_RE.fullmatch(sha)}
    removed: list[Path] = []
    for entry in sorted(releases_dir.iterdir(), key=lambda path: path.name):
        if entry.is_symlink() or not _SHA_RE.fullmatch(entry.name):
            continue
        if entry.name in protected or not entry.is_dir():
            continue

        resolved = entry.resolve(strict=True)
        if not resolved.is_relative_to(root) or resolved.parent != root:
            continue
        shutil.rmtree(entry)
        removed.append(entry)
    return tuple(removed)


def load_image_archive(runner: CommandRunner, archive_path: Path) -> None:
    """Load one uploaded image archive and remove it regardless of load result."""
    try:
        result = runner.run(("docker", "load", "--input", str(archive_path)))
        if result.returncode != 0:
            raise RetentionError("docker image archive load failed")
    finally:
        _remove_archive(archive_path)


def _run_checked(runner: CommandRunner, command: tuple[str, ...], operation: str) -> None:
    try:
        result = runner.run(command)
    except Exception as error:
        raise RetentionError(f"{operation} could not run") from error
    if result.returncode != 0:
        raise RetentionError(f"{operation} failed")


def _remove_archive(archive_path: Path) -> None:
    if archive_path.is_file() or archive_path.is_symlink():
        archive_path.unlink()
