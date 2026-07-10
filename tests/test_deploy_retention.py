from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from scripts.deploy_retention import (
    ImageRecord,
    load_image_archive,
    remove_managed_images,
    retain_release_directories,
    select_managed_images_for_removal,
)
from scripts.deploy_state import DeploymentState
from scripts.deploy_support import CommandResult


class RecordingRunner:
    def __init__(self, *, fail_load: bool = False) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.fail_load = fail_load

    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        del timeout
        self.commands.append(command)
        if command[:2] == ("docker", "load") and self.fail_load:
            raise RuntimeError("load failed")
        return CommandResult(returncode=0, stdout="", stderr="")


def _state(*, current_image: str | None, previous_image: str | None) -> DeploymentState:
    return DeploymentState(
        schema_version=1,
        current_sha="c" * 40,
        previous_sha="b" * 40,
        current_image=current_image,
        previous_image=previous_image,
        active_release="/releases/current",
        previous_release="/releases/previous",
        last_mode="full_image",
        requested_ref="main",
        resolved_ref="c" * 40,
        targets=("weekly-review-web",),
        last_event_id="event-1",
        started_at="2026-07-10T00:00:00Z",
        completed_at="2026-07-10T00:01:00Z",
        preflight={},
        final_health="healthy",
    )


class RetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.current = "investment-knowledge-app:" + "c" * 40
        self.previous = "investment-knowledge-app:" + "b" * 40
        self.images = (
            ImageRecord("id-current", self.current, 4),
            ImageRecord("id-previous", self.previous, 3),
            ImageRecord("id-old", "investment-knowledge-app:" + "a" * 40, 2),
            ImageRecord("id-pg", "pgvector/pgvector:pg16", 1),
            ImageRecord("id-other", "other-app:" + "d" * 40, 0),
            ImageRecord("id-uppercase", "investment-knowledge-app:" + "A" * 40, 5),
        )

    def test_keeps_current_previous_running_and_pgvector(self) -> None:
        removable = select_managed_images_for_removal(
            self.images[:4],
            current_image=self.current,
            previous_image=self.previous,
            referenced_image_ids={"id-old"},
        )
        self.assertEqual((), removable)

    def test_removes_only_unreferenced_old_managed_app_images(self) -> None:
        removable = select_managed_images_for_removal(
            self.images,
            current_image=self.current,
            previous_image=self.previous,
            referenced_image_ids=set(),
        )
        self.assertEqual(("id-old",), removable)

    def test_protects_id_with_both_old_and_current_tags(self) -> None:
        images = (
            ImageRecord("shared", "investment-knowledge-app:" + "a" * 40, 1),
            ImageRecord("shared", self.current, 2),
        )
        removable = select_managed_images_for_removal(
            images,
            current_image=self.current,
            previous_image=self.previous,
            referenced_image_ids=set(),
        )
        self.assertEqual((), removable)

    def test_protects_id_with_old_managed_and_pgvector_alias(self) -> None:
        images = (
            ImageRecord("shared", "investment-knowledge-app:" + "a" * 40, 1),
            ImageRecord("shared", "pgvector/pgvector:pg16", 2),
        )
        removable = select_managed_images_for_removal(
            images,
            current_image=self.current,
            previous_image=self.previous,
            referenced_image_ids=set(),
        )
        self.assertEqual((), removable)

    def test_protects_id_with_old_managed_and_arbitrary_nonmanaged_alias(self) -> None:
        images = (
            ImageRecord("shared", "investment-knowledge-app:" + "a" * 40, 1),
            ImageRecord("shared", "custom-app:stable", 2),
        )
        removable = select_managed_images_for_removal(
            images,
            current_image=self.current,
            previous_image=self.previous,
            referenced_image_ids=set(),
        )
        self.assertEqual((), removable)

    def test_deduplicates_multiple_old_managed_aliases(self) -> None:
        images = (
            ImageRecord("shared", "investment-knowledge-app:" + "d" * 40, 2),
            ImageRecord("shared", "investment-knowledge-app:" + "e" * 40, 1),
        )
        removable = select_managed_images_for_removal(
            images,
            current_image=self.current,
            previous_image=self.previous,
            referenced_image_ids=set(),
        )
        self.assertEqual(("shared",), removable)

    def test_remove_managed_images_uses_only_image_rm_for_selected_ids(self) -> None:
        runner = RecordingRunner()
        removed = remove_managed_images(
            runner,
            self.images,
            _state(current_image=self.current, previous_image=self.previous),
            referenced_image_ids=set(),
        )
        self.assertEqual(("id-old",), removed)
        self.assertEqual([("docker", "image", "rm", "id-old")], runner.commands)

    def test_builder_cache_prune_requires_explicit_successful_full_deployment(self) -> None:
        runner = RecordingRunner()
        remove_managed_images(
            runner,
            self.images,
            _state(current_image=self.current, previous_image=self.previous),
            referenced_image_ids=set(),
            successful_full_deployment=True,
            prune_builder_cache=True,
        )
        self.assertEqual(
            [
                ("docker", "image", "rm", "id-old"),
                ("docker", "builder", "prune", "--filter", "until=168h", "--force"),
            ],
            runner.commands,
        )

    def test_builder_cache_is_not_pruned_without_successful_full_deployment(self) -> None:
        runner = RecordingRunner()
        remove_managed_images(
            runner,
            self.images,
            _state(current_image=self.current, previous_image=self.previous),
            referenced_image_ids=set(),
            successful_full_deployment=False,
            prune_builder_cache=True,
        )
        self.assertEqual([("docker", "image", "rm", "id-old")], runner.commands)

    def test_builder_cache_is_not_pruned_for_non_full_or_unhealthy_state(self) -> None:
        for state in (
            replace(_state(current_image=self.current, previous_image=self.previous), last_mode="targeted_quick"),
            replace(_state(current_image=self.current, previous_image=self.previous), final_health="unhealthy"),
        ):
            with self.subTest(state=state):
                runner = RecordingRunner()
                remove_managed_images(
                    runner,
                    self.images,
                    state,
                    referenced_image_ids=set(),
                    successful_full_deployment=True,
                    prune_builder_cache=True,
                )
                self.assertEqual([("docker", "image", "rm", "id-old")], runner.commands)

    def test_release_retention_deletes_only_old_sha_directories_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            releases_dir = Path(temporary_directory) / "releases"
            outside_dir = Path(temporary_directory) / "outside"
            releases_dir.mkdir()
            outside_dir.mkdir()
            old_sha = "a" * 40
            kept_sha = "b" * 40
            candidate_sha = "c" * 40
            (releases_dir / old_sha).mkdir()
            (releases_dir / kept_sha).mkdir()
            (releases_dir / candidate_sha).mkdir()
            (releases_dir / "current").symlink_to(candidate_sha, target_is_directory=True)
            (releases_dir / "previous").symlink_to(kept_sha, target_is_directory=True)
            (releases_dir / "manual-release").mkdir()
            (releases_dir / f"{kept_sha}-file").touch()
            outside_target = outside_dir / "do-not-delete"
            outside_target.mkdir()
            (releases_dir / ("d" * 40)).symlink_to(outside_target, target_is_directory=True)

            removed = retain_release_directories(releases_dir, (kept_sha, candidate_sha))

            self.assertEqual((releases_dir / old_sha,), removed)
            self.assertFalse((releases_dir / old_sha).exists())
            self.assertTrue((releases_dir / kept_sha).exists())
            self.assertTrue((releases_dir / candidate_sha).exists())
            self.assertTrue((releases_dir / "current").is_symlink())
            self.assertTrue((releases_dir / "previous").is_symlink())
            self.assertTrue((releases_dir / "manual-release").exists())
            self.assertTrue(outside_target.exists())

    def test_archive_is_removed_after_successful_load(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "image.tar.gz"
            archive_path.write_bytes(b"archive")
            runner = RecordingRunner()

            load_image_archive(runner, archive_path)

            self.assertFalse(archive_path.exists())
            self.assertEqual(
                [("docker", "load", "--input", str(archive_path))], runner.commands
            )

    def test_archive_is_removed_after_failed_load(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "image.tar.gz"
            archive_path.write_bytes(b"archive")
            runner = RecordingRunner(fail_load=True)

            with self.assertRaises(RuntimeError):
                load_image_archive(runner, archive_path)

            self.assertFalse(archive_path.exists())


if __name__ == "__main__":
    unittest.main()
