"""Run with: python3 -m unittest discover -s tests -v.

Integration tests use an isolated tmux server and fake AI executables.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid


SCRIPT = Path(__file__).resolve().parents[1] / "agent-batch"
MODULE = runpy.run_path(str(SCRIPT))
AGENTS = {name: {"type": name, "command": [name]} for name in ("claude", "codex")}


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-batch-config-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root))
        environment.start()
        self.addCleanup(environment.stop)

    def load(self, contents=None):
        if contents is None:
            return MODULE["load_agents"](MODULE["parser"](), None)
        path = self.root / "custom.toml"
        path.write_text(contents, encoding="utf-8")
        return MODULE["load_agents"](MODULE["parser"](), str(path))

    def test_builtins_without_config(self):
        agents, default = self.load()
        self.assertEqual(default, "claude")
        self.assertEqual(agents, {"claude": {"type": "claude", "command": ["claude"]},
                                  "codex": {"type": "codex", "command": ["codex"]}})

    def test_custom_instances_defaults_and_builtin_override(self):
        agents, default = self.load('''default_agent = "work"
[agents.work]
type = "claude"
[agents.codex]
type = "codex"
command = ["/path with spaces/codex", "--profile", "work"]
''')
        self.assertEqual(default, "work")
        self.assertEqual(agents["work"], {"type": "claude", "command": ["work"]})
        self.assertIn("claude", agents)
        self.assertEqual(agents["codex"]["command"], ["/path with spaces/codex", "--profile", "work"])

    def test_config_discovery_and_explicit_replacement(self):
        directory = self.root / "agent-batch"
        directory.mkdir()
        (directory / "config.toml").write_text('default_agent = "codex"\n')
        self.assertEqual(self.load()[1], "codex")
        self.assertEqual(self.load("")[1], "claude")
        (self.root / ".config").mkdir()
        directory.rename(self.root / ".config/agent-batch")
        with patch.dict(os.environ, XDG_CONFIG_HOME=""):
            self.assertEqual(self.load()[1], "codex")

    def test_invalid_configuration_is_rejected(self):
        for contents in (
            "not valid toml", 'default_agent = "missing"', 'default_agent = []',
            'typo = "claude"', 'agents = []', '[agents.work]\ntype = "unknown"',
            '[agents.work]\ntype = []', '[agents.work]\ncommand = ["claude"]',
            '[agents.work]\ntype = "claude"\ncommand = "claude --profile work"',
            '[agents.work]\ntype = "claude"\ncommand = []',
            '[agents.work]\ntype = "claude"\ncommand = [1]',
            '[agents.work]\ntype = "claude"\ncommand = [""]',
            '[agents.work]\ntype = "claude"\ncomand = ["typo"]',
            '[agents."bad name"]\ntype = "claude"',
        ):
            with self.subTest(contents=contents), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    self.load(contents)
                self.assertEqual(error.exception.code, 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            MODULE["load_agents"](MODULE["parser"](), str(self.root / "missing.toml"))

    def test_cli_lists_agents_and_rejects_unknown_instance(self):
        listed = subprocess.run([str(SCRIPT), "--list-agents"], capture_output=True, text=True)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("claude (default)", listed.stdout)
        result = subprocess.run([str(SCRIPT), "hello", "--agent", "unknown", "--dry-run"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown instance", result.stderr)


class AdapterTests(unittest.TestCase):
    def test_claude_session_name_uses_attached_option(self):
        self.assertEqual(MODULE["claude_command"](["claude"], "-p"), ["claude", "--", "-p"])
        self.assertEqual(MODULE["claude_command"](["claude"], "hi", "-x y"),
                         ["claude", "--name=-x y", "--", "hi"])

    def test_codex_rejects_session_name(self):
        self.assertEqual(MODULE["codex_command"](["codex"], "hi"), ["codex", "--", "hi"])
        with self.assertRaises(ValueError):
            MODULE["codex_command"](["codex"], "hi", "name")

    def test_cli_rejects_session_name_for_codex_before_running(self):
        result = subprocess.run([str(SCRIPT), "hello", "--agent", "codex", "--dry-run",
                                 "--session-name", "review"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("/rename", result.stderr)
        result = subprocess.run([str(SCRIPT), "hello", "--agent", "claude", "--dry-run",
                                 "--title", "window {{N}}", "--session-name", "session {{N}}",
                                 "--item", "N=1"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[1] window 1 · session: session 1\nhello", result.stdout)

    def test_cli_mixes_agents_per_item(self):
        result = subprocess.run([str(SCRIPT), "notes-{{N}}-{{AGENT}}.md", "--agent", "claude",
                                 "--dry-run", "--item", "N=1", "--item", "N=2", "AGENT=codex"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Agent: claude (type: claude)", result.stdout)
        self.assertIn("[1] task-1\nnotes-1-claude.md", result.stdout)
        self.assertIn("[2] task-2 · agent: codex\nnotes-2-codex.md", result.stdout)
        result = subprocess.run([str(SCRIPT), "hello", "--dry-run", "--session-name", "s",
                                 "--item", "AGENT=claude", "--item", "AGENT=codex"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("item 2: instance codex:", result.stderr)


class TemplateTests(unittest.TestCase):
    def prepare(self, *arguments):
        cli = MODULE["parser"]()
        args = cli.parse_args(arguments)
        args.agent = args.agent or "claude"
        return MODULE["prepare"](cli, args, AGENTS)

    def test_multiple_items_case_and_literal_values(self):
        _, jobs = self.prepare("{{ PR_URL }} {{type}} {{TITLE}}", "--prefix", "review",
                               "--item", "PR_URL=a?x=1&y=2", "TYPE={{TITLE}}", "TITLE=one",
                               "--item", "pr_url=b", "type=frontend", "title=two")
        self.assertEqual(jobs, [("one", "claude", None, "a?x=1&y=2 {{TITLE}} one"),
                                ("two", "claude", None, "b frontend two")])

    def test_name_templates_render_item_values_and_yield_to_item_keys(self):
        _, jobs = self.prepare("{{PR}}", "--title", "PR {{pr}}", "--session-name",
                               "review {{ PR }} {{TYPE}}",
                               "--item", "PR=1", "TYPE={{PR}}",
                               "--item", "PR=2", "TYPE=api", "TITLE={{PR}}", "SESSION_NAME=own")
        self.assertEqual(jobs, [("PR 1", "claude", "review 1 {{PR}}", "1"),
                                ("{{PR}}", "claude", "own", "2")])

    def test_item_session_name_without_templates(self):
        _, jobs = self.prepare("hello", "--item", "SESSION_NAME=-starts with dash",
                               "--item", "TITLE=x")
        self.assertEqual(jobs, [("task-1", "claude", "-starts with dash", "hello"),
                                ("x", "claude", None, "hello")])

    def test_item_agent_overrides_batch_agent_and_renders_everywhere(self):
        _, jobs = self.prepare("Write notes/{{PR}}-{{ agent }}.md", "--agent", "codex",
                               "--title", "PR {{PR}} ({{AGENT}})",
                               "--session-name", "{{AGENT}} review",
                               "--item", "PR=1", "agent=claude",
                               "--item", "PR=2", "AGENT=codex", "SESSION_NAME=own",
                               "--item", "PR=3", "TITLE={{AGENT}}")
        self.assertEqual(jobs, [("PR 1 (claude)", "claude", "claude review",
                                 "Write notes/1-claude.md"),
                                ("PR 2 (codex)", "codex", "own", "Write notes/2-codex.md"),
                                ("{{AGENT}}", "codex", "codex review",
                                 "Write notes/3-codex.md")])

    def test_template_file_and_default_titles(self):
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / "review.txt"
            template.write_text("Revise {{URL}}\nTipo: {{TYPE}}\n", encoding="utf-8")
            path, jobs = self.prepare("--template", str(template), "--path", directory,
                                      "--prefix", "review", "--item", "URL=a", "TYPE=",
                                      "--item", "URL=b", "TYPE=backend")
            self.assertEqual(path, directory)
            self.assertEqual(jobs, [("review-1", "claude", None, "Revise a\nTipo: \n"),
                                    ("review-2", "claude", None, "Revise b\nTipo: backend\n")])

    def test_validation_rejects_entire_batch(self):
        cases = [
            ("{{URL}}", "--item", "URL=first", "--item", "TYPE=missing"),
            ("hello", "--item", "URL=one", "url=two"),
            ("hello", "--item", "bad-key=value"),
            ("hello", "--item", "not-an-assignment"),
            ("hello", "--item", "TITLE="),
            ("hello", "--item", "TITLE=line\nbreak"),
            ("hello", "--item", "SESSION_NAME= "),
            ("hello", "--session-name", "a\tb"),
            ("hello", "--title", "{{EMPTY}}", "--item", "EMPTY="),
            ("hello", "--title", "PR {{PR}}", "--item", "PR=1", "--item", "SESSION_NAME=two"),
            ("hello", "--session-name", "{{MISSING}}"),
            ("hello", "--item", "AGENT=unknown"),
            ("hello", "--item", "AGENT="),
            ("hello", "--agent", "unknown"),
            ("hello", "--path", "/a-directory-that-does-not-exist"),
            ("hello", "--template", "other.txt"),
            (" ",),
            (),
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    self.prepare(*arguments)
                self.assertEqual(error.exception.code, 2)


class InteractiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-batch-interactive-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root))
        environment.start()
        self.addCleanup(environment.stop)

    def test_history_is_local_searchable_and_deduplicated(self):
        cli = MODULE["parser"]()
        MODULE["save_history"](cli, ["Review {{URL}}", "Implement {{TASK}}"])
        MODULE["save_history"](cli, ["Review {{URL}}"])
        path = self.root / "agent-batch/history.json"
        self.assertEqual(MODULE["load_history"](cli),
                         ["Review {{URL}}", "Implement {{TASK}}"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with patch("builtins.input", side_effect=["/implement", "1"]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(MODULE["choose_template"](cli), "Implement {{TASK}}")

    def test_editing_current_item_keeps_earlier_prompts(self):
        cli = MODULE["parser"]()
        args = cli.parse_args(["-i", "--agent", "claude", "Revise {{URL}}"])
        answers = ["one", "a", "four", "e", "https://tracker.example/issues/4", "f"]
        updated = "Revise {{URL}}\nIssue: {{ISSUE_URL}}"
        with patch("builtins.input", side_effect=answers), \
                patch.dict(MODULE["interactive_batch"].__globals__,
                           edit_template=lambda parser, template: updated), \
                contextlib.redirect_stdout(io.StringIO()):
            directory, jobs, templates = MODULE["interactive_batch"](cli, args, AGENTS)
        self.assertEqual(directory, str(Path.cwd()))
        self.assertEqual(jobs, [("task-1", "claude", None, "Revise one"),
                                ("task-2", "claude", None,
                                 "Revise four\nIssue: https://tracker.example/issues/4")])
        self.assertEqual(templates, ["Revise {{URL}}", updated])

    def test_external_editor_updates_template(self):
        script = self.root / "editor.py"
        script.write_text('import pathlib, sys\n'
                          'pathlib.Path(sys.argv[1]).write_text("Review {{URL}}\\nIssue: '
                          '{{ISSUE_URL}}", encoding="utf-8")\n')
        with patch.dict(os.environ, EDITOR=f"{sys.executable} {script}", VISUAL=""):
            updated = MODULE["edit_template"](MODULE["parser"](), "Review {{URL}}")
        self.assertEqual(updated, "Review {{URL}}\nIssue: {{ISSUE_URL}}")

    def test_title_uses_batch_default_unless_overridden_in_item_menu(self):
        cli = MODULE["parser"]()
        args = cli.parse_args(["-i", "--agent", "claude", "--title", "PR {{URL}}",
                               "Review {{URL}}"])
        with patch("builtins.input", side_effect=["one", "f"]), \
                contextlib.redirect_stdout(io.StringIO()):
            _, jobs, _ = MODULE["interactive_batch"](cli, args, AGENTS)
        self.assertEqual(jobs, [("PR one", "claude", None, "Review one")])
        with patch("builtins.input", side_effect=["two", "t", "Special review", "f"]), \
                contextlib.redirect_stdout(io.StringIO()):
            _, jobs, _ = MODULE["interactive_batch"](cli, args, AGENTS)
        self.assertEqual(jobs, [("Special review", "claude", None, "Review two")])

    def test_agent_menu_overrides_only_current_item(self):
        cli = MODULE["parser"]()
        args = cli.parse_args(["-i", "--agent", "claude", "--session-name", "s {{AGENT}}",
                               "Write {{NAME}}-{{AGENT}}.md"])
        # Unknown names and agents that cannot honor the item's options are re-asked.
        answers = ["one", "g", "unknown", "codex", "claude", "a",
                   "two", "a", "three", "g", "", "f"]
        with patch("builtins.input", side_effect=answers), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            _, jobs, _ = MODULE["interactive_batch"](cli, args, AGENTS)
        self.assertEqual(jobs, [("task-1", "claude", "s claude", "Write one-claude.md"),
                                ("task-2", "claude", "s claude", "Write two-claude.md"),
                                ("task-3", "claude", "s claude", "Write three-claude.md")])
        self.assertIn("Unknown agent", output.getvalue())
        self.assertIn("Agent codex: Codex cannot set the session name", output.getvalue())
        args = cli.parse_args(["-i", "--agent", "claude", "Write {{NAME}}-{{AGENT}}.md"])
        with patch("builtins.input", side_effect=["one", "g", "codex", "a", "two", "f"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            _, jobs, _ = MODULE["interactive_batch"](cli, args, AGENTS)
        self.assertEqual(jobs, [("task-1", "codex", None, "Write one-codex.md"),
                                ("task-2", "claude", None, "Write two-claude.md")])
        self.assertIn("[1] task-1 · agent: codex\nWrite one-codex.md", output.getvalue())

    def test_regular_run_saves_template_and_explicit_interactive_needs_tty(self):
        with patch.object(sys, "argv", [str(SCRIPT), "Review {{URL}}", "--item", "URL=one"]), \
                patch.dict(MODULE["main"].__globals__, launch=lambda *args: None):
            self.assertEqual(MODULE["main"](), 0)
        self.assertEqual(MODULE["load_history"](MODULE["parser"]()), ["Review {{URL}}"])
        result = subprocess.run([str(SCRIPT), "-i", "hello", "--dry-run"],
                                input="", capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires a terminal", result.stderr)

    def test_no_argument_terminal_flow_starts_interactive_mode(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        answers = ["Revise {{URL}}", ".", "https://example.test/pr/1", "f"]
        output = io.StringIO()
        with patch.object(sys, "argv", [str(SCRIPT), "--dry-run"]), \
                patch.object(sys, "stdin", Terminal()), \
                patch("builtins.input", side_effect=answers), \
                contextlib.redirect_stdout(output):
            self.assertEqual(MODULE["main"](), 0)
        self.assertIn(f"Agent: claude\nPath: {Path.cwd()}\nLayout: window", output.getvalue())
        self.assertIn("Revise https://example.test/pr/1", output.getvalue())
        self.assertFalse((self.root / "agent-batch/history.json").exists())


@unittest.skipUnless(shutil.which("tmux"), "tmux not installed")
class TmuxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-batch-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        socket = "agent-batch-test-" + uuid.uuid4().hex
        wrapper = self.bin / "tmux"
        wrapper.write_text("#!/bin/sh\nexec " + shlex.join(
            [shutil.which("tmux"), "-L", socket, "-f", "/dev/null"]
        ) + ' "$@"\n')
        wrapper.chmod(0o755)
        fake_ai = '''#!/usr/bin/env python3
import json, os, pathlib, sys, time
record = dict(agent=pathlib.Path(sys.argv[0]).name, args=sys.argv[1:],
              cwd=os.getcwd(), profile=os.environ.get("BULK_PROFILE"))
path = pathlib.Path(os.environ["BULK_LOGS"]) / (str(time.time_ns()) + ".json")
path.write_text(json.dumps(record))
'''
        for agent in ("claude", "codex"):
            executable = self.bin / agent
            executable.write_text(fake_ai)
            executable.chmod(0o755)
        (self.root / ".bashrc").write_text(
            'claude-work() { BULK_PROFILE=work command claude "$@"; }\n'
        )
        config_directory = self.root / "agent-batch"
        config_directory.mkdir()
        self.config = config_directory / "config.toml"
        self.config.write_text('''default_agent = "claude-work"
[agents.claude-work]
type = "claude"
command = ["claude-work"]
''')
        self.env = dict(os.environ, HOME=str(self.root), SHELL="/bin/bash",
                        XDG_CONFIG_HOME=str(self.root),
                        PATH=f"{self.bin}:{os.environ['PATH']}", BULK_LOGS=str(self.logs))
        for name in ("TMUX", "TMUX_PANE", "BASH_ENV", "ENV"):
            self.env.pop(name, None)
        self.addCleanup(lambda: subprocess.run([str(wrapper), "kill-server"],
                                               env=self.env, capture_output=True))

    def tmux(self, *arguments):
        return subprocess.check_output([str(self.bin / "tmux"), *arguments],
                                       env=self.env, text=True).strip()

    def bulk(self, *arguments, env=None, success=True):
        result = subprocess.run([str(SCRIPT), *arguments], env=env or self.env,
                                text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def records(self, count):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            files = list(self.logs.glob("*.json"))
            if len(files) == count:
                try:
                    return [json.loads(path.read_text()) for path in files]
                except json.JSONDecodeError:
                    pass
            time.sleep(0.05)
        self.fail(f"Expected {count} AI calls, got {len(list(self.logs.glob('*.json')))}")

    def test_outside_windows_and_shell_function(self):
        self.bulk("{{TEXT}}", "--detach", "--path", str(self.project),
                  "--item", "TEXT=first", "TITLE=título 01", "SESSION_NAME=sessão $HOME",
                  "--item", "TEXT=second", "--item", "TEXT=third", "TITLE=três")
        records = self.records(3)
        self.assertCountEqual([entry["args"] for entry in records],
                              [["--name=sessão $HOME", "--", "first"], ["--", "second"],
                               ["--", "third"]])
        self.assertTrue(all(entry["profile"] == "work" for entry in records))
        self.assertTrue(all(entry["cwd"] == str(self.project) for entry in records))
        names = self.tmux("list-windows", "-a", "-F", "#{window_name}").splitlines()
        self.assertEqual(names, ["título 01", "task-2", "três"])
        self.assertEqual(self.tmux("show-options", "-wv", "-t", "@0", "automatic-rename"), "off")

    def test_items_run_their_own_agent(self):
        self.bulk("notes-{{N}}-{{AGENT}}.md", "--detach", "--item", "N=1",
                  "--item", "N=2", "AGENT=codex", "--item", "N=3", "AGENT=claude")
        records = self.records(3)
        self.assertCountEqual([(entry["agent"], entry["profile"], entry["args"])
                               for entry in records],
                              [("claude", "work", ["--", "notes-1-claude-work.md"]),
                               ("codex", None, ["--", "notes-2-codex.md"]),
                               ("claude", None, ["--", "notes-3-claude.md"])])

    def test_panes_layouts_and_exact_prompt_quoting(self):
        sentinel = self.root / "must-not-exist"
        value = f"-option 'double\" $HOME $(touch {sentinel}) `touch {sentinel}`\nline 2; {{literal}}"
        for layout in ("even-horizontal", "even-vertical", "tiled"):
            with self.subTest(layout=layout):
                self.bulk("{{TEXT}}", "--agent", "codex", "--detach", "--layout", "pane",
                          "--pane-layout", layout, "--path", str(self.project),
                          "--item", f"TEXT={value}", "TITLE=left",
                          "--item", "TEXT=two", "TITLE=right", "--item", "TEXT=three")
        records = self.records(9)
        self.assertEqual(sum(entry["args"] == ["--", value] for entry in records), 3)
        self.assertTrue(all(entry["agent"] == "codex" for entry in records))
        self.assertFalse(sentinel.exists())
        labels = self.tmux("list-panes", "-a", "-F", "#{@bulk_title}").splitlines()
        self.assertEqual(labels.count("left"), 3)
        self.assertEqual(labels.count("task-3"), 3)

    def test_inside_targets_original_session_and_preserves_focus(self):
        original = self.tmux("new-session", "-d", "-P", "-F", "#{session_id} #{pane_id}",
                             "-s", "original", "-n", "existing", "sleep", "2147483647").split()
        self.tmux("new-session", "-d", "-s", "unrelated", "sleep", "2147483647")
        tmux_env = self.tmux("display-message", "-p", "-t", original[1],
                             "#{socket_path},#{pid},0")
        env = dict(self.env, TMUX=tmux_env, TMUX_PANE=original[1])
        self.bulk("hello", "--agent", "claude", "--detach", env=env)
        self.assertEqual(self.records(1)[0]["agent"], "claude")
        windows = self.tmux("list-windows", "-t", original[0], "-F", "#{window_name}")
        self.assertEqual(windows.splitlines(), ["existing", "task-1"])
        active = self.tmux("display-message", "-p", "-t", original[0], "#{window_name}")
        self.assertEqual(active, "existing")
        self.assertEqual(self.tmux("list-windows", "-t", "unrelated", "-F", "#{window_id}"), "@1")

    def test_invalid_batch_and_dry_run_do_not_start_tmux(self):
        self.bulk("{{URL}}", "--detach", "--item", "URL=one", "--item", "TYPE=missing",
                  success=False)
        self.bulk("{{URL}}", "--dry-run", "--item", "URL=one")
        self.assertEqual(list(self.logs.iterdir()), [])
        result = subprocess.run([str(self.bin / "tmux"), "list-sessions"],
                                env=self.env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_configured_arguments_remain_literal(self):
        sentinel = self.root / "must-not-exist"
        profile = f"work 'quoted'; $(touch {sentinel})"
        self.config.write_text('[agents.work]\ntype = "codex"\ncommand = '
                               + json.dumps([str(self.bin / "codex"), "--profile", profile]) + '\n')
        self.bulk("my prompt", "--agent", "work", "--detach")
        record = self.records(1)[0]
        self.assertEqual(record["agent"], "codex")
        self.assertEqual(record["args"], ["--profile", profile, "--", "my prompt"])
        self.assertFalse(sentinel.exists())

    @unittest.skipUnless(shutil.which("zsh"), "zsh not installed")
    def test_zsh_function_and_path_after_shell_startup(self):
        (self.root / ".zshrc").write_text(
            'cd /tmp\nclaude-work() { BULK_PROFILE=work command claude "$@"; }\n'
        )
        env = dict(self.env, SHELL=shutil.which("zsh"), ZDOTDIR=str(self.root))
        self.bulk("hello 'quoted'\nsecond line", "--detach", "--path", str(self.project), env=env)
        record = self.records(1)[0]
        self.assertEqual(record["args"], ["--", "hello 'quoted'\nsecond line"])
        self.assertEqual(record["profile"], "work")
        self.assertEqual(record["cwd"], str(self.project))


if __name__ == "__main__":
    unittest.main()
