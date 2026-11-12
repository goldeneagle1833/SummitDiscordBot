"""The site's ticket-holder roles come from the bot's config.py too."""

import webapp_config


def write(tmp_path, text):
    path = tmp_path / "config.py"
    path.write_text(text, encoding="utf-8")
    return path


def test_reads_the_bot_role_set_without_running_the_file(tmp_path):
    path = write(tmp_path, (
        "import os\n"
        "raise SystemExit('config.py must not run')\n"
        "TICKET_HOLDER_ROLE_IDS = {1497681939753209937, 1455669646370799667}  # tickets + Patreon\n"
    ))
    assert webapp_config._bot_config_set("TICKET_HOLDER_ROLE_IDS", path) == {
        "1497681939753209937", "1455669646370799667",
    }


def test_placeholder_zero_and_missing_files_give_nothing(tmp_path):
    assert webapp_config._bot_config_set("TICKET_HOLDER_ROLE_IDS", write(tmp_path, "TICKET_HOLDER_ROLE_IDS = {0}\n")) == set()
    assert webapp_config._bot_config_set("TICKET_HOLDER_ROLE_IDS", tmp_path / "nope.py") == set()


def test_a_computed_value_is_ignored_rather_than_run(tmp_path):
    path = write(tmp_path, "import os\nTICKET_HOLDER_ROLE_IDS = set(map(int, os.environ['X'].split(',')))\n")
    assert webapp_config._bot_config_set("TICKET_HOLDER_ROLE_IDS", path) == set()


def test_lists_and_single_ids_work(tmp_path):
    assert webapp_config._bot_config_set("TICKET_HOLDER_ROLE_IDS", write(tmp_path, "TICKET_HOLDER_ROLE_IDS = [11, '22']\n")) == {"11", "22"}
    assert webapp_config._bot_config_set("TICKET_HOLDER_ROLE_IDS", write(tmp_path, "TICKET_HOLDER_ROLE_IDS = 33\n")) == {"33"}
