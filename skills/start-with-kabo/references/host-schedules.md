# Daily schedules by host

Three recurring jobs, created with the host's own scheduled tasks and only after the creator agrees.
Propose the times and the time zone (read it from the host or the computer); the creator confirms
or changes them. After creating a task, tell the creator the time zone the host reports for that task,
not the computer's clock: one host created its tasks in a zone different from the computer's.

1. **Daily picks**, 8:00 by default, runs `pick-daily-viral-videos`.
2. **New-post review**, 12:00 by default, runs `review-new-posts` for the reviews only.
3. **Daily account review**, 20:00 by default, runs `review-new-posts` for the recap only.

The scheduled jobs run only `pick-daily-viral-videos` and `review-new-posts`. In a scheduled run
their Kabo tools need read access or data allowance only; neither calls `prepare_creator_profile` or
any other tool that writes to the creator's Kabo account (`review-new-posts` saves pillars that are
still waiting to sync only in a run the creator starts by hand). Building the profile and saving pillar edits happen in the
first session, with the creator present: a write tool can stop an unattended run on an approval
prompt (seen in Codex: `prepare_creator_profile` asked for approval in a non-interactive run), and it
fails outright when the host's Kabo connection has no write access.

Use the host section below. Fill the brackets and use these as the task texts:

> Every day at [time] [time zone], use the pick-daily-viral-videos skill for [platform] @[handle]
> with the Kabo library in [workspace]. Ask me nothing. Send me the picks here. Never post, comment,
> follow or message anyone.

> Every day at [time] [time zone], use the review-new-posts skill for [platform] @[handle] with the
> Kabo library in [workspace], new-post reviews only. Ask me nothing. Send me the review of each
> post that passed 24 hours, or one line when there is none. Never post, comment or reply to anyone.

> Every day at [time] [time zone], use the review-new-posts skill for [platform] @[handle] with the
> Kabo library in [workspace], account recap only. Ask me nothing. Send me the account recap here.
> Never post, comment or reply to anyone.

Never tell the creator a schedule exists unless the host confirmed creating it. After creating one,
read back its name and next run time from the host's answer. If the host cannot schedule tasks, use
the manual phrases at the end.

**Prove delivery once.** A schedule that was created has not yet been shown to run. When the creator
wants proof today, offer one of these, then put the schedule back:

- move the daily task to a time a few minutes away, let it run once unattended, and move it back
  (preferred: nothing new is left running); or
- only when the creator asks for repeated proof: create a temporary task that runs every few
  minutes, calls only `get_research_capabilities` (it uses no allowance) and posts one line with the
  planned time, the actual time and the outcome. In the message that creates it, tell the creator
  that it runs until it is deleted and how they switch it off themselves.

A run that the creator started by hand does not prove the schedule. Say which of the two was done.
After a moved task has run, read the host's task list again: a host can turn a moved daily task into
a one-time task, and then it has to be made daily again.

A temporary task is never left for later. A limit stated in chat is not a limit: in testing, Grok
Bot was told to run the task 5 times, repeated that back, and the task ran 137 times in under 12
hours until it was deleted. Delete the temporary task as soon as the proof is seen, then read the
host's task list and confirm it is gone before reporting the proof. If deleting fails, the first
line of the reply says that a task is still running every few minutes and how the creator switches
it off.

## Grok Bot (routines)

- A routine is created by asking the Bot in chat: send each of the instructions above as the
  request ("create a routine that ..."). There is no form to fill in.
- Routines run in the cloud, so the creator's computer can be off. They use the time zone in the
  creator's Settings, so check that setting instead of repeating a time zone in the request.
- A new routine waits for its next scheduled time; it does not run once at creation. Tell the
  creator when that next run is. A routine starts within a window around its time (the Bot states up
  to 15 minutes either side), so never promise an exact minute.
- The routine page has a Test button that runs it immediately. Offer it: it is the quickest way to
  see a real result.
- Results are posted in the Bot's chat. Run history is visible on the phone.
- A routine runs in the cloud, so the library must be somewhere the routine can read. If the Bot
  keeps no files between runs, say so: the Skills then rebuild a smaller library on every run and
  anything that depends on history is limited (see the main Skill's "Hosts without saved files").

## Claude Code

- In the desktop app, scheduled tasks are under the Code tab: Scheduled, then New task, with a Daily
  preset in local time. Asking in a session also works: "set up a daily task that runs every morning
  at 8am", followed by the instruction. Create the task in the project folder that holds
  `kabo-library/`.
- A desktop task runs only while the app is open and the computer is awake. A run missed while the
  computer slept is caught up once on wake. Each task page lists its past runs.
- A run also needs the computer's network to reach Claude at that minute. A run that starts while a
  VPN or proxy blocks it fails at once and is not retried (seen in testing: the 8:00 task started at
  8:03 and failed on the network before any Kabo step). When a daily message is missing, look at the
  task page for a failed run before changing anything else.
- The schedule uses the computer's own time zone, and a daily task starts a few minutes after the
  minute it was set for. Each run is a new session: write the workspace folder that holds
  `kabo-library/` into the task text, as the instructions above do.
- A run can pause on a permission prompt when the task was not saved with the creator's approvals.
  If the first run produced nothing, ask the creator to open the task, run it once from its page and
  approve the Kabo tools; later runs reuse those approvals.
- Do not use cloud routines for these jobs: a cloud run starts on a fresh machine that has
  neither the creator's installed plugins nor `kabo-library/`.
- A terminal-only setup has no lasting schedule: use the manual phrases at the end.

## ChatGPT and Codex

- Ask in chat, or use Scheduled in the sidebar, with the instruction as the task text. Name the Skill
  with `$` before its name in the desktop app and with `@` on the web.
- A scheduled task created on the web runs in the cloud with the computer off and can use connected
  plugins and Skills, but it keeps no local folder from one run to the next: the Skills rebuild a
  smaller library on every run (see the main Skill's "Hosts without saved files"). Say so before
  creating it.
- A scheduled task created in the desktop app runs on the creator's computer, which must be on with
  the app running. It keeps the workspace and the library.
- The desktop app's New task form asks for the task text, a repeat and a time in 15-minute steps. It
  has no folder field, so the folder that holds `kabo-library/` has to be in the task text, as the
  instructions above have it. Under Advanced, leave "run on this computer" on.
- Creating a task does not run it: the app answers once to confirm, and the first run comes at the
  set time. A run starts within a few minutes of that time, sometimes a little before it, and posts
  into the task's own chat. To move a task, ask in that chat; the app states the next run and that
  it still repeats daily.
- Past runs are listed under Scheduled, which marks unread results.

## Muse

- A recurring task is created by saying it in chat: "Every day at 8am, " followed by the
  instruction. It runs until cancelled, its result arrives as a message in the Muse conversation,
  and upcoming tasks are listed under the Assistant icon. Approvals for scheduled work are under
  Settings, Permissions, Artifacts and scheduled tasks.
- Muse reaches Kabo through a custom connector that it builds itself, so an unattended run is not
  guaranteed to reach Kabo. After creating the task, run the same instruction once in chat, and tell
  the creator the schedule works only if that run reached Kabo. A result usually arrives a few
  minutes after the set time.
- Muse Code, the command-line agent, loops only while its session stays open, and a loop expires
  after seven days: treat it as having no scheduled tasks.

## Qwen Work

- Ask in chat. Qwen Work creates the tasks itself and shows a "scheduled task created" card for each
  one; send the three instructions above as three requests.
- Qwen Work tends to rewrite the task text in its own words (in testing: "use the Kabo account review
  flow for my TikTok account ..."), which dropped the Skill name and the workspace folder. Ask it to
  use the task text exactly as given, which names the Skill and the absolute workspace folder. After it
  confirms, read the created task back from the Automated tasks page and check that its text still
  names the Skill and the folder; if not, ask Qwen Work to edit it.
- The tasks are listed on the Automated tasks page ("My scheduled tasks") with their next run time.
  Read that time back to the creator. Tasks were created in a time zone that differed from the
  computer's own (Asia/Shanghai on a computer set to Pacific time), so state the zone the card or the
  page shows and offer to change it.
- A local task runs only while the computer is awake; that page has a keep-awake switch. In busy
  hours a run may queue behind others (one run started about 4 minutes late).
- Each run starts a new conversation titled "New session" with a timestamp, in its own fresh working
  folder, and posts its result there. Tell the creator to look for that new conversation.
- An unattended run in testing first tried an unrelated Skill, was told it was not in the
  host's Skill snapshot and that inline commands are not authorized in the sandbox, then skipped Kabo's
  Skills and called Kabo tools directly. Whether a Kabo Skill whose steps run Python scripts can run
  in Qwen Work's unattended sandbox is not yet known. Tell the creator that the first unattended run
  is the proof and that this is not yet confirmed; offer the "Prove delivery once" steps above.

## Doubao Work

This section follows the host's own description of its scheduled tasks; no run has been seen yet.

- Ask in chat ("every day at 8:00, ..." followed by the instruction).
- Doubao Work runs scheduled tasks in its cloud by default, where the creator's local Kabo library and
  the custom Kabo connection may not be available. Say in the request that the task must run on this
  computer because it uses local files.
- A local task needs the computer awake and the app open; a run missed while the computer slept is
  skipped. Busy hours may queue runs.
- Each run is a fresh execution that posts its result back into the conversation where the task was
  created. Write the workspace folder into the task text.
- After creating the task, read it back from the host and tell the creator the next run time it gives.

## DeepSeek Harness

From the host's official schedule documentation.

- Ask in chat, or open the Automation tasks page and press New, which opens a chat to describe the
  task.
- A daily time is set with an explicit time zone; state it in the request.
- A task delivers to the current conversation, to one new conversation reused every time (the
  default), or to a new conversation for each run. Choose one and tell the creator where results
  will appear.
- The app must be running to deliver. After a restart, a recurring task sends only its latest missed
  run.

## WorkBuddy

- WorkBuddy has its own automation tool and creates tasks from chat; ask in chat with the
  instructions above.
- In testing it used the computer's time zone (GMT+8). Confirm the next run time from its answer and
  repeat it to the creator.
- No scheduled run has been seen delivering yet, so offer the "Prove delivery once" steps above.

## When the host has no scheduled tasks

Give the creator these phrases to say once a day, and do not set anything up:

- Every morning: "Show me today's picks."
- A day after posting: "Review my new posts."
- Every evening: "How is my account doing?"

Say plainly that nothing runs on its own in this host.
