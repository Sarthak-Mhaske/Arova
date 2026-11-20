# Render the README demo: vhs docs/demo.tape  ->  assets/demo.gif
#
# Requires: vhs (https://github.com/charmbracelet/vhs) and `deskmark` on PATH
#           (pipx install -e .  or  python -m pip install -e .).
# The fixture is a throwaway machine in /tmp, created by scripts/demo.sh.

Output assets/demo.gif
Set Shell "bash"
Set FontSize 15
Set Width 1080
Set Height 760
Set Padding 24
Set MarginFill "#0b0d10"
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Set Framerate 30

# Build the fixture silently, then stand in the demo repo.
Hide
Type "./scripts/demo.sh >/dev/null 2>&1"
Enter
Sleep 3s
Type "export HOME=/tmp/deskmark-demo/home DESKMARK_HOME=/tmp/deskmark-demo/home/.deskmark XDG_DATA_HOME=/tmp/deskmark-demo/home/.local/share"
Enter
Type "cd /tmp/deskmark-demo/code/acme/api && clear"
Enter
Sleep 500ms
Show

# 1. Save a resume point
Type "deskmark save checkout-idempotency"
Enter
Sleep 2s

# 2. What an agent would read
Type "clear && deskmark packet | head -24"
Enter
Sleep 4s

# 3. Put the desk back (dry run shows the plan)
Type "clear && deskmark resume"
Enter
Sleep 5s
