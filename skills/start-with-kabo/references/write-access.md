# Recover write access

Use this only in an interactive run that needs to link an account, start a profile or save the
creator's confirmed pillars. A scheduled run never asks for authorization or tries a write.

1. Explain that this connection has read access, and that saving or linking needs the creator to
   approve write access in the browser. Older grants stay read-only when refreshed; updating the
   plugin or restarting the app does not grant a new permission. Offer once: reconnect now, or
   continue read-only. Do not imply that the creator must grant access to keep using research.
2. If they choose to reconnect, use their host's supported sign-in control:
   - Codex: run `codex mcp login kabo --scopes openid,profile,email,offline_access,data,video,workspace:read,workspace:write`
     and let the creator complete the browser consent.
   - Claude Code: open `/mcp`, select Kabo and use its authentication control.
   - Hosts with connector settings (including Doubao Work, Qwen Work and WorkBuddy): open Kabo's
     connector settings and use reconnect or sign in again. If the host offers no new consent,
     explain that it may reuse the old grant; let the creator remove and re-add the Kabo connection
     through that UI, keeping its address `https://kabo.sh/mcp-pub`. Do not remove it automatically.
   - A local bridge such as mcp-remote manages its own authorization. Use its documented sign-in
     controls if available; do not invent reset flags or delete credentials or cache files. If a
     fresh authorization cannot be started here, explain that limit and continue read-only.
3. Wait for the creator to finish the browser flow. Call `get_kabo_info` again. Only proceed with a
   write when `granted_scopes` now includes `workspace:write`; successful sign-in alone is not proof.
   Reauthorization does not replace the creator's agreement to link an account or save pillars.
4. If they decline, the permission remains absent, or it cannot be verified, stay read-only for
   this run. Do not keep asking them to reconnect or call a write tool to test the permission.
   Existing linked accounts can still supply picks; without a linked account, explain that daily
   picks need one and continue with public-account reading and local work.
