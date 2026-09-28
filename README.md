# agent-batch

🌐 Languages: [🇺🇸 English](README.md) | [🇧🇷 Português (Brasil)](README.pt-BR.md)

Run batches of prompts in tmux windows or panes. Requires Python 3.11+, tmux, and the AI CLIs you want to use. Uses your interactive `$SHELL`, including functions and aliases (bash, zsh, or another POSIX shell).

## Local installation

From the project root, create a symlink to the executable in a directory on your PATH:

```sh
mkdir -p "$HOME/.bin"
ln -s "$PWD/agent-batch" "$HOME/.bin/agent-batch"
```

Make sure `~/.bin` is on your PATH. The symlink picks up changes to the project without having to copy the script again. Your personal configuration stays outside the project, at `~/.config/agent-batch/config.toml` (or under the directory specified by `XDG_CONFIG_HOME`).

## Usage

```sh
agent-batch 'Review {{PR_URL}} with a focus on {{TYPE}}' \
  --agent claude --path ~/projects/app \
  --item PR_URL=https://github.com/org/repo/pull/123 TYPE=backend TITLE='PR 123' \
  --item PR_URL=https://github.com/org/repo/pull/124 TYPE=frontend
```

Each `--item` defines one run. Variable names are case-insensitive. `TITLE` names the window or pane; otherwise, names default to `task-1`, `task-2`, and so on. Use `--prefix` to change that prefix. `--template file.txt` replaces the inline prompt. `--dry-run` previews the prompts without starting the agents.

### Window titles and session names

`TITLE` names the tmux window or pane. `SESSION_NAME` names the agent session itself (for Claude, `claude --name`, shown in the prompt box, the `/resume` picker, and the terminal title). Both are per-item keys, and their values are literal, like every item value.

To build these names from the item variables, use the batch-level templates `--title` and `--session-name`. They accept `{{KEY}}` markers and are rendered for each item, just like the prompt. A `TITLE` or `SESSION_NAME` set on an item takes precedence over the template:

```sh
agent-batch 'Review {{PR_URL}}' --title 'PR {{PR}}' --session-name 'review {{PR}}' \
  --item PR=123 PR_URL=https://github.com/org/repo/pull/123 \
  --item PR=124 PR_URL=https://github.com/org/repo/pull/124 SESSION_NAME=urgent
```

Without `TITLE` or `--title`, windows are named `PREFIX-1`, `PREFIX-2`, and so on. Without `SESSION_NAME` or `--session-name`, the agent picks its default session name. Codex does not accept a session name on the command line (only `/rename` inside the session), so a session name with a `codex` instance is rejected before anything starts.

By default, each run gets its own window (`--layout window`). To use panes in a single window, pass `--layout pane` with `--pane-layout even-horizontal` (side by side), `even-vertical` (stacked), or `tiled` (grid). Inside tmux, the command uses the current session; outside tmux, it creates and attaches to a new session. `--detach` creates the runs without attaching to the session or changing your focus.

## Agent types and instances

A **type** defines how to invoke a CLI and pass the prompt. The types supported in the code are `claude` and `codex`. An **instance** gives a name to a command of one of these types: another profile, executable, shell function, or alias.

Without configuration, the available instances are `claude` and `codex`, with `claude` as the default. The optional configuration file is `~/.config/agent-batch/config.toml`, or `$XDG_CONFIG_HOME/agent-batch/config.toml` when `XDG_CONFIG_HOME` is set. Use `--config FILE` to select a different file. An explicitly selected file replaces your personal configuration; either way, configuration is applied on top of the built-in instances.

```toml
default_agent = "claude-work"

[agents.claude-work]
type = "claude"
command = ["claude-work"]

[agents.codex-work]
type = "codex"
command = ["codex", "--profile", "work"]
```

`type` is required. `command` is a list: the first element is the command, and the remaining elements are fixed arguments. If omitted, the instance name is used as the command. Arguments are passed literally: configuration does not expand `$VAR` or `~`, interpret pipelines, or interpolate prompts. Use absolute paths for executables outside your PATH. The type adapter appends the prompt after the fixed arguments.

Configured instances are added to the built-in ones; using an existing name replaces that instance. `--agent NAME` takes precedence over `default_agent`. Configuration errors and unknown types are rejected before creating windows or starting agents.

```sh
agent-batch --list-agents
agent-batch --agent claude-work 'Explain this project'
agent-batch --config examples/agent-batch.config.toml --list-agents
```

To add a **new agent type**, implement an adapter that accepts `(command, prompt, session_name=None)` and returns the argument list, register it in `AGENT_TYPES`, and add tests for its invocation format. If the CLI cannot set a session name at startup, raise `ValueError` when `session_name` is given. A new instance of an existing type only needs configuration.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Integration tests use isolated tmux servers and mock AI CLIs.
