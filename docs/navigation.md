# Job Radar navigation

## Product principle

The daily experience is optimized for one question: **what deserves my attention now?**

Configuration, scraping controls, JSON profile data, and other operational details must not compete with vacancy review in the primary workspace.

## Primary navigation

Job Radar has four first-level destinations only:

1. **Radar** — discover, review, explain, and classify opportunities.
2. **Applications** — manage opportunities the user decided to pursue.
3. **CVs** — manage base and specialized CV versions.
4. **Settings** — professional profile, search preferences, rules, sources, notifications, and advanced/system settings.

## Radar

Radar is the default destination.

Secondary views are filters/tabs rather than global navigation:

- High priority
- Review
- Discarded
- Possible duplicates

The list and opportunity detail coexist on the same screen. Selecting a job opens a side detail panel instead of forcing a full page transition.

The detail panel will progressively contain:

- title, company, location, work mode, source links
- effective classification and confidence
- why it fits
- skill-by-skill analysis
- gaps and possible exclusion requirements
- salary assessment
- career-move assessment
- recommended CV
- human correction history

Primary actions are deliberately limited to:

- Apply
- Review later
- Discard

Less frequent actions belong in an overflow menu, including classification correction, duplicate handling, and source inspection.

## Applications

Classification and application lifecycle are independent dimensions.

Application stages:

- To apply
- Applied
- Interview
- Offer
- Closed

A job can therefore be HIGH_PRIORITY while its application is already at INTERVIEW, without overloading one status field with two meanings.

## CVs

The default CV view exposes human concepts, not internal representations:

- Base CV
- HRBP
- People Analytics
- Onboarding
- Compensation
- future specialized CVs

Generated or AI-modified CVs remain drafts until explicit human approval. Raw Markdown/JSON belongs under advanced controls, not in the everyday navigation.

## Settings

Settings contains the controls previously mixed into the MVP dashboard:

- Professional profile
- Search preferences
- Rules
- Sources
- Notifications
- Advanced/system

Manual source execution can exist under Sources as a diagnostic/operator action. `Run radar` is not a primary product action because the target architecture is continuously fed by OpenClaw, email, JobSpy, browser extension, and other integrations.

## Interaction budget

A normal opportunity review should require no navigation away from Radar.

Target flow:

1. Open Radar.
2. Select a high-priority/review opportunity.
3. Read the explanation in the detail panel.
4. Apply, review later, or discard.

The target is a decision in roughly 20–30 seconds with 2–4 interactions for common actions.

## Legacy dashboard

`scripts/job_radar_dashboard.py` remains a legacy MVP/operator console while the new application UI is built. New product features should not extend its single-page configuration-heavy navigation unless required for temporary compatibility.
