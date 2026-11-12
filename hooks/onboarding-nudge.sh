#!/bin/sh
# Claude Code 没有「插件安装后」事件；装好后的第一个 startup 会话是最接近的时机。
# 只提示一次：先落标记再输出，标记写不进去就静默退出——宁可不提示，也不在每个会话里反复打扰。
# 标记放在宿主给插件的持久数据目录（升级、重装同一插件不丢）；旧版宿主没有这个变量时退回 ~/.kabo。
dir="${CLAUDE_PLUGIN_DATA:-${HOME:-}/.kabo}"
marker="$dir/onboarding-offered"
[ -e "$marker" ] && exit 0
mkdir -p "$dir" 2>/dev/null || exit 0
: > "$marker" 2>/dev/null || exit 0
# 只给模型上下文，不替用户启动流程：开场需要创作者回答，定时或无人值守的会话里不能发起。
cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"The Kabo plugin was just installed and this is its first Claude Code session; this note appears only once. When the user sends their first message: if it is a greeting, an open question, or about getting started with Kabo, offer in one short sentence to set Kabo up for them (link one public Instagram, TikTok or YouTube account, agree on content pillars, show today's picks), tell them they can start it any time by typing /kabo:start-with-kabo, and run the kabo:start-with-kabo skill if they agree now. If the first message asks for something specific, do that first and add one line at the end saying they can type /kabo:start-with-kabo to set Kabo up. Never start the setup without the user's agreement, and ignore this note in scheduled or unattended runs."}}
JSON
