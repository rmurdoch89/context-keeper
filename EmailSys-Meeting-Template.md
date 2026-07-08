# EmailSys Meeting Template Skill

Use this skill when creating a new EmailSys Handlebars template for a JobSys meeting page, especially for post-meeting Teams action summaries.

## When to use

- A new meeting is added to JobSys and needs a Teams/email recap.
- A meeting needs a "Send Actions" button that posts incomplete todos to a Teams chat.
- Replicating an existing L10 / scoreboard meeting template workflow.

## Files and locations

| Location | Purpose |
|----------|---------|
| `\\Nas\Metroid\Software\Scripts\EmailSys\Templates\` | Handlebars template files. |
| `https://jobsys.metroid.net.au/meetings/?meeting=<meeting-type>` | Meeting configuration page. |
| `https://jobsys.metroid.net.au/email-subscriptions` | Email/Teams subscription setup. |

## Step 1: Find a similar existing template

Look in `\\Nas\Metroid\Software\Scripts\EmailSys\Templates\` for a template that matches the meeting style, e.g.:

- `HR L10 Post-Meeting Tasks.handlebars`
- `Sales L10 Post-Meeting Tasks.handlebars`
- `Operations L10 Post-Meeting Tasks.handlebars`

Read it to confirm the SQL `MeetingType` filter and prompt style.

Common `MeetingType` values in existing templates:

- `hr-level-10`
- `leadership-level-10`
- `operations-level-10`
- `production-hr-level-10`
- `production-scheduling`
- `r-d-meeting`
- `sales-marketing-level-10`

The value for a new meeting is shown on the **Meeting Configuration** page under **MEETING TYPE**.

## Step 2: Create the Handlebars template

Create a new file in `\\Nas\Metroid\Software\Scripts\EmailSys\Templates\`.

Naming convention: `<Meeting Title> Post-Meeting Tasks.handlebars` (match existing L10 style).

Basic post-meeting tasks template:

```handlebars
[[tasks[]="
SELECT Title, Who FROM MeetingItems
WHERE MeetingType = '<meeting-type>'
AND ItemType = 'todos' AND IsComplete = 0
ORDER BY Who, OrderId"]]

{{#if tasks.count}}
<ai>
  <prompt>
    Please compose a meeting action summary to all staff listed in the data
    below, reminding them of their weekly tasks. This is to be posted in the
    <Team Name> group chat immediately after the department meeting.
    Make the reminder light-hearted and friendly.
    Keep it fairly brief - max 2-3 brief sentences, and no long flowery paragraphs. Don't include a subject line.
    Include the actual data at the end of the message, in nicely formatted text - group by person, then dotpoints underneath.
    ## Data
    {{#each tasks}}
      {{Who}} - {{Title}}
    {{/each}}
  </prompt>
</ai>
{{/if}}
```

Replace:
- `<meeting-type>` with the value from Meeting Configuration.
- `<Team Name>` with the friendly team/chat name.

The template only outputs a message when there are incomplete todos. If there are none, EmailSys returns a blank body.

## Step 3: Create the Email Subscription

1. Open **Email Subscriptions** in JobSys.
2. Click **New Subscription**.
3. Set:
   - **Subscription Name**: e.g. `Project DMS Post-Meeting Tasks`
   - **Subscription Type**: `Teams Message`
   - **Recipients**: `Group Chat`
   - **Teams Chat ID**: paste the full Teams chat ID, e.g. `19:xxxxx@thread.v2`
   - **Template Path**: full filename with extension, e.g. `Project DMS Post-Meeting Tasks.handlebars`
   - **Enabled**: on
   - **Schedule**: `Manual` (for meeting-page trigger) or `Scheduled` if running on a timer
4. Save and note the **Subscription #**.

## Step 4: Wire the subscription into the meeting template

1. Open the meeting page: `https://jobsys.metroid.net.au/meetings/?meeting=<meeting-type>`
2. Click **Edit Template**.
3. In **Meeting Configuration**, set **Email Subscription ID** to the subscription number from Step 3.
4. Ensure the meeting has:
   - A **Todos** section (Section Type = `Item Table`, Item Type = `todos`, Source Meeting Type = `<meeting-type>`)
   - A **Recap / Send Actions** section (Section Type = `Recap / Send Actions`, Section ID = `recap`)
5. Save the template.

Important: The **Section ID** for the recap section must be `recap` (not `recap-5` or similar) for the **Send Actions** button to trigger the subscription.

## Step 5: Add the bot to the Teams chat

The JobSys/EmailSys bot (Jarvis) must be a member of the target Teams chat, or sends will fail with an `InternalServerError`.

1. Open the Teams chat.
2. Add the Jarvis bot/app as a member.
3. Test again.

## Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Template not found at path ...Project DMS Post-Meeting Tasks` | Template Path missing `.handlebars` extension. | Add `.handlebars` to the Template Path field. |
| `Skipping, blank body returned` | No incomplete todos for the `MeetingType`. | Add a todo, or confirm `MeetingType` matches the DB exactly. |
| `Send Actions` button does nothing | Recap section Section ID is not `recap`. | Set Section ID to `recap`. |
| `InternalServerError` with Jarvis reference ID | Bot not in Teams chat, or server-side send failure. | Add Jarvis bot to the chat; if still failing, look up the reference ID in server logs. |

## Quick reference: Teams chat ID

The chat ID is in the Teams URL:

```
https://teams.microsoft.com/l/chat/19:<chat-id>@thread.v2/...
```

Copy the full `19:xxxxx@thread.v2` value into the **Teams Chat ID** field.
