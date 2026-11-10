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

## Grok Bot (routines)

- A routine is created by asking the Bot in chat: send each of the two instructions above as the
  request ("create a routine that ..."). There is no form to fill in.
- Routines run in the cloud, so the creator's computer can be off. They use the time zone in the
  creator's Settings, so check that setting instead of repeating a time zone in the request.
- A new routine waits for its next scheduled time; it does not run once at creation. Tell the
  creator when that next run is.
- The routine page has a Test button that runs it immediately. Offer it: it is the quickest way to
  see a real result.
- Results are posted in the Bot's chat. Run history is visible on the phone.
- A routine runs in the cloud, so the library must be somewhere the routine can read. If the Bot
  keeps no files between runs, say so: the Skills then rebuild a smaller library on every run and
  anything that depends on history is limited (see the main Skill's "Hosts without saved files").

## Claude Code

<!-- TO VERIFY -->
Use the host's own recurring-task feature to create the two tasks, with the instructions above as
the task text. This section has not been checked against the host; do not state how often, where
the task runs or where results appear until the host's own answer says so.

## ChatGPT and Codex

<!-- TO VERIFY -->
Use the host's own recurring-task feature to create the two tasks, with the instructions above as
the task text. This section has not been checked against the host; do not state how often, where
the task runs or where results appear until the host's own answer says so.

## Muse

<!-- TO VERIFY -->
Use the host's own recurring-task feature to create the two tasks, with the instructions above as
the task text. This section has not been checked against the host; do not state how often, where
the task runs or where results appear until the host's own answer says so.

## When the host has no scheduled tasks

Give the creator these two phrases to say once a day, and do not set anything up:

- Every morning: "Show me today's picks."
- Every evening, or after posting: "Review my new posts."

Say plainly that nothing runs on its own in this host.
