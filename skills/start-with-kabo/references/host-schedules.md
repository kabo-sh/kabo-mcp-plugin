# Daily schedules by host

Two recurring jobs, created with the host's own scheduled tasks and only after the creator agrees:

1. **Morning picks** runs `pick-daily-viral-videos` once a day.
2. **Daily review** runs `review-new-posts` once a day, after the creator usually posts.

Ask for the time of day and the time zone, then use the host section below. Fill the brackets in
these two instructions and use them as the task text:

> Every day at [time] [time zone], use the pick-daily-viral-videos skill for [platform] @[handle]
> with the Kabo library in [workspace]. Ask me nothing. Send me the picks here. Never post, comment,
> follow or message anyone.

> Every day at [time] [time zone], use the review-new-posts skill for [platform] @[handle] with the
> Kabo library in [workspace]. Ask me nothing. Send me the account recap and any new post reviews
> here. Never post, comment or reply to anyone.

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

- A routine is created by asking the Bot in chat: send each of the two instructions above as the
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
- The schedule uses the computer's own time zone, and a daily task starts a few minutes after the
  minute it was set for. Each run is a new session: write the workspace folder that holds
  `kabo-library/` into the task text, as the two instructions above do.
- A run can pause on a permission prompt when the task was not saved with the creator's approvals.
  If the first run produced nothing, ask the creator to open the task, run it once from its page and
  approve the Kabo tools; later runs reuse those approvals.
- Do not use cloud routines for these two jobs: a cloud run starts on a fresh machine that has
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

## When the host has no scheduled tasks

Give the creator these two phrases to say once a day, and do not set anything up:

- Every morning: "Show me today's picks."
- Every evening, or after posting: "Review my new posts."

Say plainly that nothing runs on its own in this host.
