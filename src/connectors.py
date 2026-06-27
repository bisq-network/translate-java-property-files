"""Public connector contracts around the reusable translation pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Protocol

from src.pipeline_core import (
    ProcessQueueResult,
    TranslationPipelineOptions,
    TranslationPipelinePaths,
    TranslationPipelineResult,
    TranslationPipelineSteps,
    run_translation_pipeline,
)


class PipelineSourceConnector(Protocol):
    """Filesystem/source operations used before and after translation."""

    def validate_paths(self, input_folder: str, translation_queue: str, translated_queue: str, repo_root: str) -> None:
        """Validate that configured pipeline paths are usable."""

    def get_changed_translation_files(
        self,
        input_folder: str,
        repo_root: str,
        *,
        process_all_files: bool,
    ) -> List[str]:
        """Return source/target files that should be translated."""

    def archive_original_files(self, changed_files: List[str], input_folder: str, archive_folder: str) -> None:
        """Archive files before processing."""

    def copy_files_to_translation_queue(self, changed_files: List[str], input_folder: str, queue_folder: str) -> None:
        """Copy changed files into the processing queue."""

    def copy_translated_files_back(self, translated_queue: str, input_folder: str) -> None:
        """Copy translated output back to the project localization folder."""

    def cleanup_queue_folders(self, translation_queue: str, translated_queue: str) -> None:
        """Clean temporary queue folders after a successful run."""


class PipelineProcessorConnector(Protocol):
    """Translation engine operations used by the core pipeline."""

    async def process_translation_queue(
        self,
        *,
        translation_queue_folder: str,
        translated_queue_folder: str,
        glossary_file_path: str,
        validation_summary: Dict[str, Dict[str, object]],
    ) -> ProcessQueueResult:
        """Translate queued files and return a processing summary."""

    def write_token_usage_summary(self, summary_path: str) -> None:
        """Write provider usage/cost data for the run."""


class PipelineReporterConnector(Protocol):
    """Report writers used by the core pipeline."""

    def write_skipped_files_report(self, report_path: str, skipped_files: Dict[str, List[str]]) -> None:
        """Write skipped-file diagnostics."""

    def remove_file_if_exists(self, report_path: str) -> None:
        """Remove stale reports when there are no findings."""

    def generate_translation_summary(
        self,
        summary_path: str,
        *,
        processed_files: List[str],
        new_keys_count: int,
        updated_keys_count: int,
    ) -> None:
        """Write a machine-readable translation summary."""

    def write_translation_validation_summary(
        self,
        summary_path: str,
        *,
        validation_files: Dict[str, Dict[str, object]],
        skipped_files: Dict[str, List[str]],
    ) -> None:
        """Write validation details for quality gates."""


@dataclass(frozen=True)
class PipelinePublishRequest:
    """Data passed to a publisher after the translation pipeline finishes."""

    paths: TranslationPipelinePaths
    result: TranslationPipelineResult


class PipelinePublisher(Protocol):
    """Optional publishing boundary for GitHub, GitLab, or local output."""

    def publish(self, request: PipelinePublishRequest) -> None:
        """Publish translated changes or leave them for a caller to inspect."""


class NoopPipelinePublisher:
    """Publisher implementation for callers that only want local file changes."""

    def publish(self, request: PipelinePublishRequest) -> None:
        return None


@dataclass(frozen=True)
class PipelineConnectorSet:
    """A complete set of connectors for running and optionally publishing."""

    source: PipelineSourceConnector
    processor: PipelineProcessorConnector
    reporter: PipelineReporterConnector
    publisher: PipelinePublisher = NoopPipelinePublisher()

    def to_steps(self) -> TranslationPipelineSteps:
        """Convert connector objects into the core pipeline's callable step set."""
        return TranslationPipelineSteps(
            validate_paths=self.source.validate_paths,
            get_changed_translation_files=self.source.get_changed_translation_files,
            archive_original_files=self.source.archive_original_files,
            copy_files_to_translation_queue=self.source.copy_files_to_translation_queue,
            process_translation_queue=self.processor.process_translation_queue,
            write_skipped_files_report=self.reporter.write_skipped_files_report,
            remove_file_if_exists=self.reporter.remove_file_if_exists,
            generate_translation_summary=self.reporter.generate_translation_summary,
            write_translation_validation_summary=self.reporter.write_translation_validation_summary,
            write_token_usage_summary=self.processor.write_token_usage_summary,
            copy_translated_files_back=self.source.copy_translated_files_back,
            cleanup_queue_folders=self.source.cleanup_queue_folders,
        )

    async def run(
        self,
        *,
        paths: TranslationPipelinePaths,
        options: TranslationPipelineOptions,
        logger: logging.Logger,
    ) -> TranslationPipelineResult:
        """Run the translation pipeline using this connector set."""
        return await run_translation_pipeline(
            paths=paths,
            options=options,
            steps=self.to_steps(),
            logger=logger,
        )

    def publish(
        self,
        *,
        result: TranslationPipelineResult,
        paths: TranslationPipelinePaths,
    ) -> None:
        """Publish a completed pipeline result through the configured publisher."""
        self.publisher.publish(PipelinePublishRequest(paths=paths, result=result))
