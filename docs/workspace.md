# Your saved Kabo work

How the plugin reads and writes your Kabo workspace: linked accounts, saved creator profiles, scripts,
the video library and your content preferences.

When your Kabo deployment provides workspace tools, your agent can read your linked accounts,
saved creator profiles, official social connection status, scripts and video library after you
grant workspace access. `get_kabo_info` shows basic identity and permissions without credits.
Ask the agent to save a completed script or update an existing one; it keeps the saved version
and rejects conflicting edits. You can also ask to connect a public Instagram, TikTok or YouTube
account. Public Connect uses data allowance and does not start official social OAuth or analysis.
Connecting Kabo asks for read and write access to your Kabo workspace (`workspace:read` and
`workspace:write`), because the first session links your account, has Kabo build your profile and
saves your pillar edits. Connections made before this change have read access only: sign in to Kabo
again once to get write access (in Codex:
`codex mcp login kabo --scopes openid,profile,email,offline_access,data,video,workspace:read,workspace:write`;
in other hosts, disconnect and reconnect Kabo). Until then, a Skill that needs to write tells you to
reconnect, and the original public research and local drafting workflows remain usable.

The three trends Skills can also start from your saved account profile. When you ask for trends for
your own linked account, the agent reads the account's saved content profile (your signature
content, content language and formats) with `get_creator_profile`, keeps the complete result as a
local file and passes it to the trends driver. The searches then start from your own seed words,
leave out your own posts and accounts far larger or smaller than yours, and share the
recommendations across your signature content. In the general trend-research Workflow, content
language steers the search words. Short-window recommendations (seven days or less) also check
candidate language before ranking. You can explicitly add other languages or allow any language
for the current request; that choice overrides the account default without editing your profile.
The Skills never write or edit the profile file. If the
profile is missing or empty, workspace access is not granted, or Kabo does not offer the profile
yet, the Skills run the same public trend scan as before.

You can also correct that saved profile in the conversation. Ask the trends Skills or the account
review to rename, remove or merge a signature content item, make one your main item, exclude a
topic, or set the language you make content in or your market, and the agent saves the edit to Kabo
with `update_content_preferences`. Your edits are kept per account and come back on every later
read, in this plugin and in Kabo's web app; the profile Kabo computed stays as it was, and you can
reset your edits. A plain, unambiguous change is saved and repeated back to you in one sentence; a
guess, a removal, a merge or a reset is restated for you to confirm first. Your market is only the
default search region (Instagram search takes none); it never filters results by region.
Content-language checks follow the short-window rules above. An edit applies from the next trend run. Saving needs write access, which a
connection made before this plugin asked for it lacks until you sign in again; without it, or when Kabo does not offer the
tool yet, nothing is saved and the research runs as before.

## Where the workspace folder lives

The daily Skills keep their library in a `kabo-library` folder inside a workspace folder, and that folder
has to be the same from one conversation to the next. Some hosts (Doubao Work, Qwen Work and WorkBuddy
among them) start every conversation in a new dated or numbered working folder. A library written there
cannot be found by the next conversation or by a scheduled run. In those hosts the Skills use the
`kabo-workspace` folder in your home folder (`~/kabo-workspace`) instead, and the daily jobs' task text
names that folder. In a host whose working folder is your own project, the project folder is used.

## Read-only connections

Some hosts (Doubao Work, Qwen Work and WorkBuddy) connect Kabo with read permission only and do not
ask for more. There, linking a new account and saving pillars are unavailable; the Skills read
`granted_scopes` from `get_kabo_info`, make no write call, say so once, and keep working on reading,
daily picks and reviews for an account that is already linked.
