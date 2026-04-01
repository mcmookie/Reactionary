"""Tests for Reactionary config loading and trigger matching."""

import os
import re
import sys
import textwrap
import types
from unittest.mock import MagicMock

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers to import bot logic without actually connecting to Discord
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """Ensure tests never read the real .env or config.yaml."""
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.delenv("CHANNELS", raising=False)


def write_config(tmp_path, config_dict):
    """Write a config dict to a temporary config.yaml and return the path."""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config_dict), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# We import the module-level helpers by loading the source as a module so that
# global startup code (load_config / client.run) does NOT execute.
# ---------------------------------------------------------------------------

def _load_module():
    """Import only the definitions we need from reactionary.py."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "reactionary_src",
        os.path.join(os.path.dirname(__file__), "reactionary.py"),
        submodule_search_locations=[],
    )
    loader = spec.loader
    source = loader.get_data(spec.origin).decode()

    # Extract constants and functions without running the module
    mod = types.ModuleType("reactionary_src")
    mod.__file__ = spec.origin

    exec(
        compile(
            "import os\n"
            + "import re\n"
            + "import discord\n"
            + "import yaml\n"
            + "LINK_PATTERN = re.compile(r'https?://\\S+')\n"
            + "VALID_TRIGGER_TYPES = "
            + repr({
                "all", "embed", "attachment", "contains", "exact", "regex",
                "has_link", "has_sticker", "reply", "mention_bot", "mention_any",
                "user", "role", "thread_created",
            })
            + "\n"
            + "TRIGGERS_REQUIRING_VALUE = "
            + repr({"contains", "exact", "regex", "user", "role"})
            + "\n",
            "<test-setup>",
            "exec",
        ),
        mod.__dict__,
    )

    # Pull functions out of the file and compile them in the module namespace
    # so they have access to LINK_PATTERN, re, etc.
    for fname in ("check_trigger", "save_config", "_find_rule", "is_admin"):
        func_source = _extract_function(source, fname)
        exec(compile(func_source, spec.origin, "exec"), mod.__dict__)

    return mod


def _extract_function(source, name):
    """Extract a top-level function definition from source code."""
    lines = source.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"def {name}("):
            start = i
        elif start is not None and line and not line[0].isspace() and line.strip():
            return "".join(lines[start:i])
    if start is not None:
        return "".join(lines[start:])
    raise ValueError(f"Function {name!r} not found in source")


_mod = _load_module()
check_trigger = _mod.check_trigger
save_config = _mod.save_config
_find_rule = _mod._find_rule
is_admin = _mod.is_admin


# ---------------------------------------------------------------------------
# Mock helpers for discord.Message
# ---------------------------------------------------------------------------

def make_message(
    content="",
    embeds=None,
    attachments=None,
    stickers=None,
    reference=None,
    mentions=None,
    author_id=1000,
    author_roles=None,
    channel_id=111,
):
    """Return a mock discord.Message with the given properties."""
    msg = MagicMock()
    msg.content = content
    msg.embeds = embeds or []
    msg.attachments = attachments or []
    msg.stickers = stickers or []
    msg.reference = reference
    msg.mentions = mentions or []
    msg.channel.id = channel_id
    msg.author.id = author_id
    if author_roles is not None:
        msg.author.roles = author_roles
    else:
        # Simulate a guild member with no extra roles
        msg.author.roles = []
    msg.id = 9999
    return msg


# ---------------------------------------------------------------------------
# Trigger tests
# ---------------------------------------------------------------------------

class TestTriggerAll:
    def test_matches_any_message(self):
        assert check_trigger({"type": "all"}, make_message()) is True

    def test_matches_with_content(self):
        assert check_trigger({"type": "all"}, make_message(content="anything")) is True


class TestTriggerEmbed:
    def test_matches_when_embeds_present(self):
        assert check_trigger({"type": "embed"}, make_message(embeds=[MagicMock()])) is True

    def test_no_match_without_embeds(self):
        assert check_trigger({"type": "embed"}, make_message()) is False


class TestTriggerAttachment:
    def test_matches_when_attachments_present(self):
        assert check_trigger({"type": "attachment"}, make_message(attachments=[MagicMock()])) is True

    def test_no_match_without_attachments(self):
        assert check_trigger({"type": "attachment"}, make_message()) is False


class TestTriggerContains:
    def test_case_insensitive_match(self):
        trigger = {"type": "contains", "value": "hello"}
        assert check_trigger(trigger, make_message(content="Say Hello World")) is True

    def test_no_match(self):
        trigger = {"type": "contains", "value": "goodbye"}
        assert check_trigger(trigger, make_message(content="hello")) is False


class TestTriggerExact:
    def test_exact_match(self):
        trigger = {"type": "exact", "value": "ping"}
        assert check_trigger(trigger, make_message(content="ping")) is True

    def test_no_match_partial(self):
        trigger = {"type": "exact", "value": "ping"}
        assert check_trigger(trigger, make_message(content="pinging")) is False

    def test_case_sensitive(self):
        trigger = {"type": "exact", "value": "Ping"}
        assert check_trigger(trigger, make_message(content="ping")) is False


class TestTriggerRegex:
    def test_pattern_match(self):
        trigger = {"type": "regex", "value": r"\bhello\b", "_compiled": re.compile(r"\bhello\b")}
        assert check_trigger(trigger, make_message(content="say hello there")) is True

    def test_no_match(self):
        trigger = {"type": "regex", "value": r"^exact$", "_compiled": re.compile(r"^exact$")}
        assert check_trigger(trigger, make_message(content="not exact match")) is False


class TestTriggerHasLink:
    def test_http_link(self):
        assert check_trigger({"type": "has_link"}, make_message(content="visit http://example.com")) is True

    def test_https_link(self):
        assert check_trigger({"type": "has_link"}, make_message(content="see https://example.com/page")) is True

    def test_no_link(self):
        assert check_trigger({"type": "has_link"}, make_message(content="no links here")) is False


class TestTriggerHasSticker:
    def test_with_sticker(self):
        assert check_trigger({"type": "has_sticker"}, make_message(stickers=[MagicMock()])) is True

    def test_without_sticker(self):
        assert check_trigger({"type": "has_sticker"}, make_message()) is False


class TestTriggerReply:
    def test_is_reply(self):
        assert check_trigger({"type": "reply"}, make_message(reference=MagicMock())) is True

    def test_not_reply(self):
        assert check_trigger({"type": "reply"}, make_message()) is False


class TestTriggerMentionBot:
    def test_bot_mentioned(self):
        bot_user = MagicMock()
        # Patch the module-level client.user
        _mod.client = MagicMock()
        _mod.client.user = bot_user
        assert check_trigger({"type": "mention_bot"}, make_message(mentions=[bot_user])) is True

    def test_bot_not_mentioned(self):
        _mod.client = MagicMock()
        _mod.client.user = MagicMock()
        assert check_trigger({"type": "mention_bot"}, make_message(mentions=[])) is False


class TestTriggerMentionAny:
    def test_someone_mentioned(self):
        assert check_trigger({"type": "mention_any"}, make_message(mentions=[MagicMock()])) is True

    def test_nobody_mentioned(self):
        assert check_trigger({"type": "mention_any"}, make_message(mentions=[])) is False


class TestTriggerUser:
    def test_matching_user(self):
        trigger = {"type": "user", "value": "1000"}
        assert check_trigger(trigger, make_message(author_id=1000)) is True

    def test_different_user(self):
        trigger = {"type": "user", "value": "2000"}
        assert check_trigger(trigger, make_message(author_id=1000)) is False

    def test_int_value(self):
        trigger = {"type": "user", "value": 1000}
        assert check_trigger(trigger, make_message(author_id=1000)) is True


class TestTriggerRole:
    def test_matching_role_by_name(self):
        role = MagicMock()
        role.id = 5555
        role.name = "Moderator"
        trigger = {"type": "role", "value": "Moderator"}
        assert check_trigger(trigger, make_message(author_roles=[role])) is True

    def test_matching_role_by_id(self):
        role = MagicMock()
        role.id = 5555
        role.name = "Moderator"
        trigger = {"type": "role", "value": "5555"}
        assert check_trigger(trigger, make_message(author_roles=[role])) is True

    def test_no_matching_role(self):
        role = MagicMock()
        role.id = 5555
        role.name = "Member"
        trigger = {"type": "role", "value": "Admin"}
        assert check_trigger(trigger, make_message(author_roles=[role])) is False


# ---------------------------------------------------------------------------
# Config loading / validation tests
# ---------------------------------------------------------------------------

class TestConfigValidation:
    """Test config loading by invoking load_config through a subprocess."""

    def _run_load(self, tmp_path, config_dict, token="fake-token"):
        """Write config, run load_config in a subprocess, return (exitcode, output)."""
        import subprocess
        cfg_path = write_config(tmp_path, config_dict)
        script = textwrap.dedent(f"""\
            import os, sys
            os.environ["CONFIG_PATH"] = {cfg_path!r}
            os.environ["DISCORD_TOKEN"] = {token!r}
            # Prevent client.run from actually connecting
            import unittest.mock as um
            with um.patch("discord.Client.run"):
                exec(open("reactionary.py").read())
            print("OK")
        """)
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__),
        )
        return result.returncode, result.stdout + result.stderr

    def test_valid_config(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [111],
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_missing_triggers(self, tmp_path):
        config = {
            "rules": [{"channels": [111], "emojis": ["👍"]}]
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "triggers" in output.lower()

    def test_invalid_trigger_type(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [111],
                    "triggers": [{"type": "bogus"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "bogus" in output

    def test_missing_value_for_contains(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [111],
                    "triggers": [{"type": "contains"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "value" in output.lower()

    def test_invalid_regex(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [111],
                    "triggers": [{"type": "regex", "value": "[invalid"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "regex" in output.lower() or "invalid" in output.lower()

    def test_missing_emojis(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [111],
                    "triggers": [{"type": "all"}],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "emojis" in output.lower()

    def test_channel_must_be_int(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": ["not-a-number"],
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "integer" in output.lower()

    def test_empty_channels_is_invalid(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [],
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "empty" in output.lower()

    def test_multiple_triggers_in_rule(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [111],
                    "triggers": [
                        {"type": "embed"},
                        {"type": "attachment"},
                        {"type": "contains", "value": "test"},
                    ],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_omitted_channels_is_valid(self, tmp_path):
        config = {
            "rules": [
                {
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_trigger_mode_all_is_valid(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [111],
                    "trigger_mode": "all",
                    "triggers": [
                        {"type": "contains", "value": "hello"},
                        {"type": "has_link"},
                    ],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_trigger_mode_any_is_valid(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [111],
                    "trigger_mode": "any",
                    "triggers": [{"type": "embed"}, {"type": "attachment"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_invalid_trigger_mode(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [111],
                    "trigger_mode": "none",
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "trigger_mode" in output.lower()

    def test_excluded_channels_is_valid(self, tmp_path):
        config = {
            "rules": [
                {
                    "excluded_channels": [999],
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_excluded_channels_must_be_ints(self, tmp_path):
        config = {
            "rules": [
                {
                    "excluded_channels": ["not-an-int"],
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "integer" in output.lower()

    def test_rule_name_is_valid(self, tmp_path):
        config = {
            "rules": [
                {
                    "name": "my-rule",
                    "channels": [111],
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_rule_name_must_be_string(self, tmp_path):
        config = {
            "rules": [
                {
                    "name": 42,
                    "channels": [111],
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "name" in output.lower()

    def test_ignore_bots_global_valid(self, tmp_path):
        config = {
            "global": {"ignore_bots": True},
            "rules": [
                {
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_ignore_bots_must_be_bool(self, tmp_path):
        config = {
            "global": {"ignore_bots": "yes"},
            "rules": [
                {
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "ignore_bots" in output.lower()

    def test_multiple_rules_multiple_channels(self, tmp_path):
        config = {
            "rules": [
                {
                    "channels": [111, 222, 333],
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                },
                {
                    "channels": [444, 555],
                    "triggers": [{"type": "embed"}, {"type": "attachment"}],
                    "emojis": ["🎉"],
                },
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_admin_users_valid(self, tmp_path):
        config = {
            "global": {"admin_users": [123456789]},
            "rules": [
                {
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_admin_users_must_be_list(self, tmp_path):
        config = {
            "global": {"admin_users": "not-a-list"},
            "rules": [
                {
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "admin_users" in output.lower()

    def test_admin_users_must_be_ints(self, tmp_path):
        config = {
            "global": {"admin_users": ["not-an-int"]},
            "rules": [
                {
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "admin_users" in output.lower()

    def test_admin_role_valid_string(self, tmp_path):
        config = {
            "global": {"admin_role": "BotAdmin"},
            "rules": [
                {
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_admin_role_valid_int(self, tmp_path):
        config = {
            "global": {"admin_role": 999888777},
            "rules": [
                {
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code == 0, output

    def test_admin_role_invalid_type(self, tmp_path):
        config = {
            "global": {"admin_role": [1, 2]},
            "rules": [
                {
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        code, output = self._run_load(tmp_path, config)
        assert code != 0
        assert "admin_role" in output.lower()


# ---------------------------------------------------------------------------
# save_config tests
# ---------------------------------------------------------------------------

class TestSaveConfig:
    """Test that save_config writes valid YAML that round-trips correctly."""

    def test_save_and_reload(self, tmp_path, monkeypatch):
        cfg_path = str(tmp_path / "config.yaml")
        monkeypatch.setenv("CONFIG_PATH", cfg_path)
        config_dict = {
            "global": {"ignore_bots": True},
            "rules": [
                {
                    "name": "test-rule",
                    "channels": [111, 222],
                    "triggers": [
                        {"type": "contains", "value": "hello"},
                        {"type": "regex", "value": r"\bworld\b", "_compiled": re.compile(r"\bworld\b")},
                    ],
                    "emojis": ["👍", "🎉"],
                }
            ],
        }
        save_config(config_dict)

        with open(cfg_path, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)

        assert loaded["global"]["ignore_bots"] is True
        assert len(loaded["rules"]) == 1
        rule = loaded["rules"][0]
        assert rule["name"] == "test-rule"
        assert rule["channels"] == [111, 222]
        assert len(rule["triggers"]) == 2
        assert rule["triggers"][0] == {"type": "contains", "value": "hello"}
        # _compiled should be stripped
        assert "_compiled" not in rule["triggers"][1]
        assert rule["triggers"][1] == {"type": "regex", "value": r"\bworld\b"}
        assert rule["emojis"] == ["👍", "🎉"]

    def test_save_strips_internal_keys(self, tmp_path, monkeypatch):
        cfg_path = str(tmp_path / "config.yaml")
        monkeypatch.setenv("CONFIG_PATH", cfg_path)
        config_dict = {
            "rules": [
                {
                    "triggers": [{"type": "all", "_internal": "junk"}],
                    "emojis": ["👍"],
                }
            ],
        }
        save_config(config_dict)

        with open(cfg_path, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)

        assert "_internal" not in loaded["rules"][0]["triggers"][0]

    def test_save_preserves_excluded_channels(self, tmp_path, monkeypatch):
        cfg_path = str(tmp_path / "config.yaml")
        monkeypatch.setenv("CONFIG_PATH", cfg_path)
        config_dict = {
            "rules": [
                {
                    "excluded_channels": [999],
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        save_config(config_dict)

        with open(cfg_path, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)

        assert loaded["rules"][0]["excluded_channels"] == [999]

    def test_save_preserves_trigger_mode(self, tmp_path, monkeypatch):
        cfg_path = str(tmp_path / "config.yaml")
        monkeypatch.setenv("CONFIG_PATH", cfg_path)
        config_dict = {
            "rules": [
                {
                    "trigger_mode": "all",
                    "triggers": [{"type": "has_link"}, {"type": "embed"}],
                    "emojis": ["🔗"],
                }
            ],
        }
        save_config(config_dict)

        with open(cfg_path, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)

        assert loaded["rules"][0]["trigger_mode"] == "all"

    def test_save_admin_config(self, tmp_path, monkeypatch):
        cfg_path = str(tmp_path / "config.yaml")
        monkeypatch.setenv("CONFIG_PATH", cfg_path)
        config_dict = {
            "global": {
                "ignore_bots": False,
                "admin_users": [111, 222],
                "admin_role": "BotAdmin",
            },
            "rules": [
                {
                    "triggers": [{"type": "all"}],
                    "emojis": ["👍"],
                }
            ],
        }
        save_config(config_dict)

        with open(cfg_path, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)

        assert loaded["global"]["admin_users"] == [111, 222]
        assert loaded["global"]["admin_role"] == "BotAdmin"


# ---------------------------------------------------------------------------
# _find_rule tests
# ---------------------------------------------------------------------------

class TestFindRule:
    def test_find_by_name(self):
        rules_list = [
            {"name": "first", "emojis": ["👍"]},
            {"name": "second", "emojis": ["🎉"]},
        ]
        idx, rule = _find_rule(rules_list, "second")
        assert idx == 1
        assert rule["name"] == "second"

    def test_find_by_index(self):
        rules_list = [
            {"name": "first", "emojis": ["👍"]},
            {"name": "second", "emojis": ["🎉"]},
        ]
        idx, rule = _find_rule(rules_list, "2")
        assert idx == 1
        assert rule["name"] == "second"

    def test_find_by_index_one_based(self):
        rules_list = [
            {"name": "only", "emojis": ["👍"]},
        ]
        idx, rule = _find_rule(rules_list, "1")
        assert idx == 0
        assert rule["name"] == "only"

    def test_not_found(self):
        rules_list = [{"name": "first", "emojis": ["👍"]}]
        idx, rule = _find_rule(rules_list, "nonexistent")
        assert idx is None
        assert rule is None

    def test_index_out_of_range(self):
        rules_list = [{"name": "first", "emojis": ["👍"]}]
        idx, rule = _find_rule(rules_list, "5")
        assert idx is None
        assert rule is None

    def test_zero_index_invalid(self):
        rules_list = [{"name": "first", "emojis": ["👍"]}]
        idx, rule = _find_rule(rules_list, "0")
        assert idx is None
        assert rule is None

    def test_name_takes_precedence(self):
        # A rule named "2" should be found by name, not by index
        rules_list = [
            {"name": "1", "emojis": ["👍"]},
            {"name": "2", "emojis": ["🎉"]},
        ]
        idx, rule = _find_rule(rules_list, "2")
        assert idx == 1
        assert rule["name"] == "2"


# ---------------------------------------------------------------------------
# is_admin tests
# ---------------------------------------------------------------------------

class TestIsAdmin:
    def _make_interaction(self, user_id=1000, roles=None, manage_guild=False):
        interaction = MagicMock()
        interaction.user.id = user_id
        if roles is not None:
            interaction.user.roles = roles
        else:
            interaction.user.roles = []
        interaction.user.guild_permissions.manage_guild = manage_guild
        return interaction

    def test_admin_by_user_id(self):
        interaction = self._make_interaction(user_id=12345)
        assert is_admin(interaction, {"admin_users": [12345]}) is True

    def test_not_admin_by_user_id(self):
        interaction = self._make_interaction(user_id=99999)
        assert is_admin(interaction, {"admin_users": [12345]}) is False

    def test_admin_by_role_name(self):
        role = MagicMock()
        role.id = 5555
        role.name = "BotAdmin"
        interaction = self._make_interaction(roles=[role])
        assert is_admin(interaction, {"admin_role": "BotAdmin"}) is True

    def test_admin_by_role_id(self):
        role = MagicMock()
        role.id = 5555
        role.name = "SomeRole"
        interaction = self._make_interaction(roles=[role])
        assert is_admin(interaction, {"admin_role": 5555}) is True

    def test_not_admin_by_role(self):
        role = MagicMock()
        role.id = 5555
        role.name = "Member"
        interaction = self._make_interaction(roles=[role])
        assert is_admin(interaction, {"admin_role": "BotAdmin"}) is False

    def test_fallback_to_manage_guild_true(self):
        interaction = self._make_interaction(manage_guild=True)
        assert is_admin(interaction, {}) is True

    def test_fallback_to_manage_guild_false(self):
        interaction = self._make_interaction(manage_guild=False)
        assert is_admin(interaction, {}) is False

    def test_admin_users_overrides_manage_guild(self):
        # User is in admin_users list, even though they lack manage_guild
        interaction = self._make_interaction(user_id=12345, manage_guild=False)
        assert is_admin(interaction, {"admin_users": [12345]}) is True

    def test_neither_admin_users_nor_role_match(self):
        interaction = self._make_interaction(user_id=99999, manage_guild=True)
        # When admin_users/admin_role are configured, manage_guild is not used
        assert is_admin(interaction, {"admin_users": [12345]}) is False
