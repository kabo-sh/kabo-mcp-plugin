# Install Kabo (instructions for an AI assistant)

Your user asked you to install Kabo. Follow the section for the product you are running in, then go to
"After installing". This file is the whole procedure; you do not need anything else from this repository
to install.

Rules for every host:

- Kabo sign-in happens in the user's browser through OAuth. Never ask for, read, print or store a Kabo
  password, token or API key, and never paste a token into a request yourself.
- Stop and ask the user whenever a step needs their sign-in, their approval, or a permission prompt.
- Install only from `https://github.com/kabo-sh/kabo-mcp-plugin` and connect only to
  `https://kabo.sh/mcp-pub`. If either is unavailable, report the failure; do not switch to another
  address.
- Do not claim Kabo is installed until the check under "After installing" has passed.

What gets installed:

1. A connection to Kabo's remote MCP server, `https://kabo.sh/mcp-pub` (Streamable HTTP, OAuth with
   dynamic client registration, no API key). Ask for these permissions: `openid profile email
   offline_access data video workspace:read workspace:write`, with `resource=https://kabo.sh/mcp-pub`.
2. The Skill folders under `skills/` in this repository (branch `stable`). Each Skill is a folder with a
   `SKILL.md` and Python 3 scripts. Keep every file; `SKILL.md` alone is not enough.

## Claude Code

```sh
claude plugin marketplace add kabo-sh/kabo-mcp-plugin
claude plugin install kabo@kabo-mcp-plugin
```

Then ask the user to run `/reload-plugins` (or start a new session), run `/mcp`, choose the Kabo server and
sign in. The plugin contains both the connection and the Skills. In the first new session, the plugin asks
Claude to offer the Kabo setup once; the user can also type `/kabo:start-with-kabo` at any time.

## Codex and ChatGPT

Kabo is in the plugin directory that ChatGPT and Codex share. Ask the user to open Plugins, find Kabo and
add it. From a terminal:

```sh
codex plugin marketplace add kabo-sh/kabo-mcp-plugin
codex plugin add kabo@kabo-plugin-openai
```

The user signs in to Kabo when prompted, then opens a new task so the tools and Skills load. Starting
with 1.0.46, Codex's Setup entry point runs `start-with-kabo`. After a terminal install, the user can
also ask Codex to "Use Kabo to get me started." If Kabo was connected before, its old sign-in has no
write access; sign in again with all permissions:

```sh
codex mcp login kabo --scopes openid,profile,email,offline_access,data,video,workspace:read,workspace:write
```

## Grok Bot

1. Connection. If Kabo appears under Connect apps, add it there. Otherwise add `https://kabo.sh/mcp-pub`
   as a custom app from this chat and show the user the Connect card; they sign in to Kabo in the browser.
2. Skills. On the Bot's computer:

   ```sh
   git clone --branch stable --single-branch https://github.com/kabo-sh/kabo-mcp-plugin.git ~/kabo-mcp-plugin
   ```

   Then import each folder under `~/kabo-mcp-plugin/skills/` as a private skill. If import is not
   available, keep the clone and read the Skill's `SKILL.md` from that folder whenever the user asks for
   it. To update later: `git -C ~/kabo-mcp-plugin pull --ff-only`.
3. Confirm that `python3 --version` works on the Bot's computer.

A Bot added from a template does not bring the connection or the scripts with it. Repeat steps 1 and 2
in the new Bot.

## Muse

Muse has no field for an MCP address. Use its custom connector flow:

1. Register Kabo as a custom connector that signs in with OAuth (authorization code with PKCE and dynamic
   client registration) against `https://kabo.sh/mcp-pub`, with the permissions listed above. Give the
   user the Connect card and wait for them to sign in and approve.
2. After sign-in, call Kabo over MCP from the connector (JSON-RPC over Streamable HTTP: `tools/list` and
   `tools/call`). Save each complete tool result to a file when a Skill asks for one.
3. Clone the repository on Muse's computer as in the Grok Bot section, and read a Skill's `SKILL.md` from
   the clone whenever the user asks for it.

Muse Code (the command-line agent): add a `streamable_http` server named `kabo` with the URL above to
`mcp_servers`, run `muse mcp login kabo`, and install the Skills with
`npx skills add 'kabo-sh/kabo-mcp-plugin#stable' --skill '*'`.

## Any other assistant

You need three things: a remote MCP connection with OAuth, a workspace with files that you can read and
write, and Python 3. Add `https://kabo.sh/mcp-pub` as a remote MCP server, clone the repository as in the
Grok Bot section, and load the Skill folders from the clone.

## After installing

1. Check the connection: call the Kabo tool `get_research_capabilities` with an empty object. It uses no
   allowance. If it fails with an authentication error, ask the user to disconnect and reconnect Kabo; do
   not retry with a different address.
2. Tell the user in one sentence that Kabo is installed and which Skills are available.
3. Start the first session: follow the `start-with-kabo` Skill.
