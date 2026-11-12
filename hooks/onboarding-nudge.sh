#!/bin/sh
# Claude Code has no "after plugin install" event; the first startup session after installation is the closest moment.
# Offer only once: write the marker before printing, and exit silently if the marker cannot be written. Better not to
# offer at all than to interrupt every session.
# The marker lives in the persistent data directory the host gives the plugin (kept across upgrades and reinstalls of
# the same plugin); fall back to ~/.kabo when an older host does not set the variable.
dir="${CLAUDE_PLUGIN_DATA:-${HOME:-}/.kabo}"
marker="$dir/onboarding-offered"
[ -e "$marker" ] && exit 0
mkdir -p "$dir" 2>/dev/null || exit 0
: > "$marker" 2>/dev/null || exit 0
# Give the model context only and never start the flow for the user: the opening needs the creator to answer, so it
# must not be started in scheduled or unattended sessions.
cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"The Kabo plugin was just installed and this is its first Claude Code session; this note appears only once. When the user sends their first message: if it is a greeting, an open question, or about getting started with Kabo, offer in one short sentence to set Kabo up for them (link one public Instagram, TikTok or YouTube account, agree on content pillars, show today's picks), tell them they can start it any time by typing /kabo:start-with-kabo, and run the kabo:start-with-kabo skill if they agree now. If the first message asks for something specific, do that first and add one line at the end saying they can type /kabo:start-with-kabo to set Kabo up. Never start the setup without the user's agreement, and ignore this note in scheduled or unattended runs."}}
JSON
