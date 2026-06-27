import logging
from dataclasses import dataclass, field
from typing import List

import pytest

from src.connectors import (
    PipelineConnectorSet,
    PipelinePublisher,
    PipelinePublishRequest,
)
from src.pipeline_core import TranslationPipelineOptions, TranslationPipelinePaths


@dataclass
class FakeSourceConnector:
    changed_files: List[str]
    calls: List[str] = field(default_factory=list)

    def validate_paths(self, input_folder, translation_queue, translated_queue, repo_root):
        self.calls.append(f"validate:{input_folder}:{translation_queue}:{translated_queue}:{repo_root}")

    def get_changed_translation_files(self, input_folder, repo_root, *, process_all_files):
        self.calls.append(f"detect:{input_folder}:{repo_root}:{process_all_files}")
        return self.changed_files

    def archive_original_files(self, changed_files, input_folder, archive_folder):
        self.calls.append(f"archive:{changed_files}:{archive_folder}")

    def copy_files_to_translation_queue(self, changed_files, input_folder, queue_folder):
        self.calls.append(f"enqueue:{changed_files}:{queue_folder}")

    def copy_translated_files_back(self, translated_queue, input_folder):
        self.calls.append(f"copy_back:{translated_queue}:{input_folder}")

    def cleanup_queue_folders(self, translation_queue, translated_queue):
        self.calls.append(f"cleanup:{translation_queue}:{translated_queue}")


@dataclass
class FakeProcessorConnector:
    calls: List[str] = field(default_factory=list)

    async def process_translation_queue(
        self,
        *,
        translation_queue_folder,
        translated_queue_folder,
        glossary_file_path,
        validation_summary,
    ):
        self.calls.append(f"process:{translation_queue_folder}:{translated_queue_folder}:{glossary_file_path}")
        validation_summary["messages_de.json"] = {"failed_keys": []}
        return 1, ["messages_de.json"], {}, 2

    def write_token_usage_summary(self, summary_path):
        self.calls.append(f"token_usage:{summary_path}")


@dataclass
class FakeReporterConnector:
    calls: List[str] = field(default_factory=list)

    def write_skipped_files_report(self, report_path, skipped_files):
        self.calls.append(f"skipped:{report_path}:{sorted(skipped_files)}")

    def remove_file_if_exists(self, report_path):
        self.calls.append(f"remove:{report_path}")

    def generate_translation_summary(
        self,
        summary_path,
        *,
        processed_files,
        new_keys_count,
        updated_keys_count,
    ):
        self.calls.append(f"summary:{summary_path}:{processed_files}:{new_keys_count}:{updated_keys_count}")

    def write_translation_validation_summary(self, summary_path, *, validation_files, skipped_files):
        self.calls.append(f"validation:{summary_path}:{sorted(validation_files)}:{sorted(skipped_files)}")


class FakePublisher(PipelinePublisher):
    def __init__(self) -> None:
        self.requests: List[PipelinePublishRequest] = []

    def publish(self, request: PipelinePublishRequest) -> None:
        self.requests.append(request)


@pytest.mark.asyncio
async def test_connector_set_builds_pipeline_steps_and_publisher_boundary():
    source = FakeSourceConnector(["messages_de.json"])
    processor = FakeProcessorConnector()
    reporter = FakeReporterConnector()
    publisher = FakePublisher()
    connectors = PipelineConnectorSet(
        source=source,
        processor=processor,
        reporter=reporter,
        publisher=publisher,
    )

    paths = TranslationPipelinePaths(
        project_root_dir="/app",
        repo_root="/repo",
        input_folder="/repo/i18n",
        translation_queue_folder="/app/queue",
        translated_queue_folder="/app/done",
        glossary_file_path="/app/glossary.json",
    )
    result = await connectors.run(
        paths=paths,
        options=TranslationPipelineOptions(
            process_all_files=False,
            dry_run=False,
            preserve_queues_for_debug=False,
        ),
        logger=logging.getLogger("test_connectors"),
    )

    assert result.processed_files_count == 1
    assert source.calls[:3] == [
        "validate:/repo/i18n:/app/queue:/app/done:/repo",
        "detect:/repo/i18n:/repo:False",
        "archive:['messages_de.json']:/repo/i18n/archive",
    ]
    assert processor.calls == [
        "process:/app/queue:/app/done:/app/glossary.json",
        "token_usage:/app/logs/token_usage_summary.json",
    ]
    assert reporter.calls[0] == "remove:/app/logs/skipped_files_report.log"

    connectors.publish(result=result, paths=paths)

    assert publisher.requests == [
        PipelinePublishRequest(paths=paths, result=result)
    ]
