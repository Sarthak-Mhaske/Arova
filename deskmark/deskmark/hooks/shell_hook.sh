#!/usr/bin/env bash
# deskmark shell hook
#
# Sourced from .bashrc / .zshrc. Logs each command, its cwd, exit code and
# duration to $DESKMARK_HOME/session_log.jsonl, plus the last 50 lines of output
# when a command fails. Successful output is not captured.
#
# Install with `deskmark hooks`, which appends the source line for you. Remove
# it with `deskmark hooks --uninstall`.
#
# It does not wrap the shell in a pty, does not change how a command runs, and
# writes nowhere except that one log file.

# don't source twice
if [ -n "$DESKMARK_HOOK_LOADED" ]; then
    return 0
fi
export DESKMARK_HOOK_LOADED=1

# --- config ---

DESKMARK_LOG_DIR="${DESKMARK_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/deskmark}"
DESKMARK_LOG_FILE="$DESKMARK_LOG_DIR/session_log.jsonl"
DESKMARK_TMP_DIR="${XDG_RUNTIME_DIR:-/tmp}/deskmark"
DESKMARK_OUTPUT_LINES=50  # Lines of output to capture on failure

# never logged: secrets and noise
DESKMARK_IGNORE_COMMANDS=(
    "ls" "ll" "la" "pwd" "cd" "clear" "history"
    "cat" "less" "more" "head" "tail"
    "echo" "printf" "man" "help"
    "exit" "logout" "sudo -s" "sudo -i"
    "ssh" "scp" "sftp"     # Never capture remote session commands
    "gpg" "pass" "secret"  # Never capture anything credential-adjacent
    "env" "printenv"       # Never capture environment (may contain secrets)
)

# commands whose failure output is worth keeping
DESKMARK_CAPTURE_COMMANDS=(
    "pytest" "py.test"
    "cargo" "go"
    "npm" "yarn" "pnpm"
    "make" "cmake"
    "gcc" "g++" "clang" "rustc"
    "python" "python3"
    "mvn" "gradle"
    "tsc" "eslint" "mypy" "ruff" "flake8"
)

# make sure the log dir exists
mkdir -p "$DESKMARK_LOG_DIR" "$DESKMARK_TMP_DIR"

# --- write one jsonl event ---

_deskmark_write_event() {
    local event_type="$1"
    local data_json="$2"
    local timestamp
    timestamp=$(date -Iseconds 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%S+00:00")

    printf '{"timestamp":"%s","type":"%s","data":%s}\n' \
        "$timestamp" \
        "$event_type" \
        "$data_json" \
        >> "$DESKMARK_LOG_FILE" 2>/dev/null
}

# --- json escaping ---

_deskmark_json_escape() {
    local str="$1"
    # backslashes, quotes, newlines, tabs, cr
    str="${str//\\/\\\\}"
    str="${str//\"/\\\"}"
    str="${str//$'\n'/\\n}"
    str="${str//$'\t'/\\t}"
    str="${str//$'\r'/\\r}"
    # drop null bytes and control chars, they break json
    str=$(printf '%s' "$str" | tr -d '\000-\011\013-\037\177')
    printf '%s' "$str"
}

# --- should this command be logged? ---

_deskmark_should_ignore() {
    local cmd="$1"
    local cmd_base
    cmd_base=$(printf '%s' "$cmd" | awk '{print $1}')

    # nothing to log
    if [ -z "$cmd_base" ]; then
        return 0
    fi

    # ignore list
    for ignored in "${DESKMARK_IGNORE_COMMANDS[@]}"; do
        if [ "$cmd_base" = "$ignored" ]; then
            return 0
        fi
    done

    # skip anything that looks like it carries a secret
    # heuristic, not a parser
    if printf '%s' "$cmd" | grep -qiE '(password|passwd|secret|token|api[_-]?key|auth[_-]?key)\s*='; then
        return 0
    fi

    return 1
}

# --- rough command type, used for the "last failure" summary ---

_deskmark_classify_command() {
    local cmd="$1"
    local cmd_base
    cmd_base=$(printf '%s' "$cmd" | awk '{print $1}')

    # drop the deskmark_run prefix so the log shows the real command
    if [ "$cmd_base" = "deskmark_run" ]; then
        cmd=$(printf '%s' "$cmd" | cut -d' ' -f2-)
        cmd_base=$(printf '%s' "$cmd" | awk '{print $1}')
    fi

    case "$cmd_base" in
        pytest|py.test|python*test*|nosetests|jest|vitest|cargo\ test|go\ test|mvn\ test)
            printf "test_run" ;;
        git)
            printf "git_operation" ;;
        docker|docker-compose|kubectl|helm)
            printf "infrastructure" ;;
        pip|pip3|npm|yarn|cargo|go\ get|apt|brew)
            printf "dependency_management" ;;
        python|python3|node|ruby|perl|bash|sh)
            printf "script_execution" ;;
        make|cmake|cargo\ build|go\ build|mvn\ package)
            printf "build" ;;
        curl|wget|http|httpie)
            printf "http_request" ;;
        grep|rg|ag|ack|find)
            printf "search" ;;
        vim|nvim|nano|emacs|code)
            printf "editor_launch" ;;
        *)
            printf "shell_command" ;;
    esac
}

# --- output capture, failures only ---

_deskmark_start_output_capture() {
    local cmd_id="$1"
    DESKMARK_CAPTURE_FILE="$DESKMARK_TMP_DIR/output_${cmd_id}.tmp"

    # capture file plus tee: output goes both to
    # the terminal and to the file
    # only armed for the commands listed above
    # empty marker file means capture is armed
    : > "$DESKMARK_CAPTURE_FILE"
}

_deskmark_read_captured_output() {
    local capture_file="$1"
    if [ -f "$capture_file" ] && [ -s "$capture_file" ]; then
        tail -n "$DESKMARK_OUTPUT_LINES" "$capture_file" 2>/dev/null
    fi
}

_deskmark_cleanup_capture() {
    local capture_file="$1"
    rm -f "$capture_file" 2>/dev/null
}

# --- state for the command in flight ---

DESKMARK_CURRENT_CMD=""
DESKMARK_CMD_START_TIME=0
DESKMARK_CMD_ID=""
DESKMARK_CAPTURE_FILE=""

_deskmark_should_capture() {
    local cmd="$1"
    local cmd_base
    cmd_base=$(printf '%s' "$cmd" | awk '{print $1}')

    for capture_cmd in "${DESKMARK_CAPTURE_COMMANDS[@]}"; do
        if [ "$cmd_base" = "$capture_cmd" ]; then
            return 0  # Should capture
        fi
    done
    return 1  # Should not capture
}

# --- preexec. zsh calls this natively; bash needs bash-preexec ---

_deskmark_preexec() {
    local raw_cmd="$1"

    # not worth tracking
    if _deskmark_should_ignore "$raw_cmd"; then
        DESKMARK_CURRENT_CMD=""
        return 0
    fi

    DESKMARK_CURRENT_CMD="$raw_cmd"
    DESKMARK_CMD_START_TIME=$(date +%s%3N 2>/dev/null || date +%s)
    DESKMARK_CMD_ID="$(date +%s%N 2>/dev/null || date +%s)_$$"
    DESKMARK_CAPTURE_FILE=""

    local escaped_cmd
    escaped_cmd=$(_deskmark_json_escape "$raw_cmd")

    local escaped_cwd
    escaped_cwd=$(_deskmark_json_escape "$PWD")

    local cmd_type
    cmd_type=$(_deskmark_classify_command "$raw_cmd")

    _deskmark_write_event "terminal_command" \
        "{\"command\":\"$escaped_cmd\",\"cwd\":\"$escaped_cwd\",\"cmd_type\":\"$cmd_type\",\"cmd_id\":\"$DESKMARK_CMD_ID\"}"

    # arm output capture for the commands we care about
    # precmd finds the capture file through this path
    if _deskmark_should_capture "$raw_cmd"; then
        DESKMARK_CAPTURE_FILE="$DESKMARK_TMP_DIR/output_${DESKMARK_CMD_ID}.tmp"
        # tell the wrapper capture is live
        export DESKMARK_ACTIVE_CAPTURE="$DESKMARK_CAPTURE_FILE"
    else
        DESKMARK_CAPTURE_FILE=""
        unset DESKMARK_ACTIVE_CAPTURE
    fi
}

# --- deskmark_run: explicit output capture ---
# usage: deskmark_run pytest tests/ -v
deskmark_run() {
    local cmd="$*"
    local capture_file="$DESKMARK_TMP_DIR/deskmark_capture_$$.tmp"

    # tee to the capture file, still show it on the terminal
    "$@" 2>&1 | tee "$capture_file"
    local exit_code=${PIPESTATUS[0]}

    # emit the captured output as its own event
    if [ -f "$capture_file" ] && [ -s "$capture_file" ]; then
        local output
        output=$(tail -n "$DESKMARK_OUTPUT_LINES" "$capture_file")
        local escaped_output
        escaped_output=$(_deskmark_json_escape "$output")

        _deskmark_write_event "command_output" \
            "{\"command\":\"$(_deskmark_json_escape "$cmd")\",\"exit_code\":$exit_code,\"output\":\"$escaped_output\",\"lines_captured\":$(wc -l < "$capture_file" | awk '{print $1}')}"
    fi

    rm -f "$capture_file"
    return $exit_code
}

# --- precmd. runs after the command returns ---

_deskmark_precmd() {
    local exit_code=$?

    # no command in flight
    if [ -z "$DESKMARK_CURRENT_CMD" ]; then
        return 0
    fi

    local cmd_id="$DESKMARK_CMD_ID"
    local raw_cmd="$DESKMARK_CURRENT_CMD"
    local capture_file="$DESKMARK_CAPTURE_FILE"
    DESKMARK_CURRENT_CMD=""
    DESKMARK_CAPTURE_FILE=""
    unset DESKMARK_ACTIVE_CAPTURE

    # duration
    local duration_ms=0
    if [ "$DESKMARK_CMD_START_TIME" -gt 0 ] 2>/dev/null; then
        local end_time
        end_time=$(date +%s%3N 2>/dev/null || date +%s)
        duration_ms=$((end_time - DESKMARK_CMD_START_TIME))
    fi

    # output field
    local output_json="null"

    # read the capture file, if deskmark_run wrote one
    if [ -n "$capture_file" ] && [ -f "$capture_file" ] && [ -s "$capture_file" ]; then
        local captured
        captured=$(tail -n "$DESKMARK_OUTPUT_LINES" "$capture_file")
        rm -f "$capture_file"
        if [ -n "$captured" ]; then
            local escaped_output
            escaped_output=$(_deskmark_json_escape "$captured")
            output_json="\"$escaped_output\""
        fi
    fi

    local escaped_cmd
    escaped_cmd=$(_deskmark_json_escape "$raw_cmd")

    _deskmark_write_event "terminal_output" \
        "{\"cmd_id\":\"$cmd_id\",\"command\":\"$escaped_cmd\",\"exit_code\":$exit_code,\"duration_ms\":$duration_ms,\"output\":$output_json}"
}

# --- hook registration ---

_deskmark_register_hooks() {
    if [ -n "$ZSH_VERSION" ]; then
        # zsh has preexec/precmd built in
        # chain into an existing preexec if there is one
        if typeset -f preexec > /dev/null 2>&1; then
            # somebody already has a preexec
            preexec_functions+=(_deskmark_preexec)
        else
            preexec() { _deskmark_preexec "$1"; }
        fi

        if typeset -f precmd > /dev/null 2>&1; then
            precmd_functions+=(_deskmark_precmd)
        else
            precmd() { _deskmark_precmd; }
        fi

    elif [ -n "$BASH_VERSION" ]; then
        # bash: use bash-preexec if it's there, otherwise traps
        if typeset -f __bp_preexec_invoke_exec > /dev/null 2>&1; then
            # bash-preexec present
            preexec_functions+=(_deskmark_preexec)
            precmd_functions+=(_deskmark_precmd)
        else
            # fallback: PROMPT_COMMAND for the end, DEBUG trap for the start
            # less reliable, but no extra dependency
            _deskmark_debug_trap() {
                if [ "$BASH_COMMAND" != "_deskmark_precmd" ] && \
                   [ "$BASH_COMMAND" != "PROMPT_COMMAND" ]; then
                    _deskmark_preexec "$BASH_COMMAND"
                fi
            }
            trap '_deskmark_debug_trap' DEBUG

            # prepend, keep whatever was there
            if [ -n "$PROMPT_COMMAND" ]; then
                PROMPT_COMMAND="_deskmark_precmd; $PROMPT_COMMAND"
            else
                PROMPT_COMMAND="_deskmark_precmd"
            fi
        fi
    fi
}

_deskmark_register_hooks

# --- session start ---

_deskmark_write_event "session_start" \
    "{\"shell\":\"${ZSH_VERSION:+zsh}${BASH_VERSION:+bash}\",\"pid\":$$,\"cwd\":\"$(_deskmark_json_escape "$PWD")\"}"

# --- cleanup on exit ---

_deskmark_cleanup_session() {
    _deskmark_write_event "session_end" "{\"pid\":$$}"
    rm -f "$DESKMARK_TMP_DIR"/output_*.tmp 2>/dev/null
}

trap '_deskmark_cleanup_session' EXIT

