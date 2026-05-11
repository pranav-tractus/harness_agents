"""Back-compat shim. New code should import from ``core.chat_loader``."""

from core.chat_loader import (  # noqa: F401
    CHATS_DIR,
    DOWNLOADED_CHATS_DIR,
    RAW_DATA_DIR,
    SYNTH_UPDATES_FEW_SHOT_MAX_STEPS_DEFAULT,
    UPDATES_DIR,
    add_seq_numbers,
    build_extraction_few_shot_from_paths,
    labeled_chat_paths_for_globs,
    labeled_raw_chat_paths,
    list_chat_files,
    list_chat_files_for_dataset_root,
    load_chat_file,
    load_synthetic_update_few_shot_examples,
)
