---
name: rocketlane_customer
description: Domain reference for Rocketlane customer-facing features: accounts, CSAT, key events, client portal, spaces, announcements, and intake forms.
---

# Rocketlane Customer Domain Reference

## Account (Customer Company)

| Field | Notes |
|-------|-------|
| name | Customer company name |
| health_score | Aggregate health (CSAT + project health + billing status) |
| arr | Annual Recurring Revenue |
| csm_owner | Customer Success Manager (Native user) |
| projects | All delivery projects for this account |

- **Account health** = rolled-up signal across all active projects: CSAT scores + project RAG + billing status.
- Use `search_rocketlane_tools("account")` or `get_companies_by_name` to find accounts.
- Always retrieve `companyId` via `get_companies_by_name` before filtering projects by account.

## CSAT Surveys

- CSAT surveys are sent **only to Customer users** — never Native or Partner users.
- **Trigger conditions** (all three must be true):
  1. Task has `is_milestone: true`
  2. Task has `is_public: true` (visible in client portal)
  3. Task status is set to **Completed**
- **CSAT score**: 1–5 scale.
- **Satisfaction %** = (count of scores 4 or 5 / total responses) × 100
- Response fields: score, comment, respondent (Customer user), milestone_id, project_id, submitted_at
- Use `search_rocketlane_tools("CSAT")` to retrieve survey responses.

### CSAT Interpretation

| Score | Meaning |
|-------|---------|
| 5 | Very Satisfied |
| 4 | Satisfied |
| 3 | Neutral |
| 2 | Dissatisfied |
| 1 | Very Dissatisfied |

- Satisfaction % threshold: typically flag accounts below 80%.

## Key Events

- Key Events mark significant moments on a project timeline:
  - Project kickoff
  - Go-live / launch
  - Phase completion
  - Health status change
  - CSAT survey received
- Appear on the project Timeline view.
- Can trigger automations (e.g., notify CSM on go-live).
- **Interval IQ**: measures elapsed time between key events across projects → benchmarks delivery speed (e.g., avg days from kickoff to go-live).
- Use `search_rocketlane_tools("key event")` to list or create key events.

## Client Portal

- Customer-user-facing view of a project.
- **Visibility rules**: only tasks/phases/docs explicitly marked `is_public: true` are visible.
- Internal comments, private tasks, and non-public spaces stay hidden from clients.
- **Authentication**: Magic-link (email-based) or JWT token.
- **Customizable**: white-label branding, colors, fonts, embedded domains.
- Portal is automatically created with each project; Customer users are invited via email.

## Spaces

- A Space is a collaborative document area within a project.
- Fields: title, content (rich text), attached_to (project or task), visibility (internal / client-visible)
- Internal spaces are hidden from Customer portal users.
- Client-visible spaces appear in the portal as shared documents.
- Use `search_rocketlane_tools("space")` to create or update spaces.

## Announcements

- One-way broadcast messages pushed to the client portal audience.
- Fields: title, body, project_id, sent_at
- **Trigger phrases**: "let the client know", "post an update", "send an announcement", "notify the client".
- Announcements appear in the portal's notifications/feed for Customer users.
- Use `search_rocketlane_tools("announcement")` to create and send announcements.

## Intake Forms

- Pre-project scoping form linked to a project template.
- Supports 15+ field types: text, number, date, dropdown, multi-select, file upload, etc.
- Supports conditional branching (show/hide fields based on prior answers).
- On submission: auto-creates a project from the linked template with form data pre-populated.
- Use `search_rocketlane_tools("intake form")` to retrieve or manage forms.

## Common Patterns

**Get account health overview:**
1. `get_companies_by_name` → retrieve account + companyId
2. `search_rocketlane_tools("account health")` → get health_score + breakdown
3. Enumerate all projects for account; show RAG status per project

**Check CSAT for an account:**
1. Get all projects for the account
2. `search_rocketlane_tools("CSAT")` → filter by project_ids
3. Compute satisfaction % = (4+5 count / total) × 100
4. Highlight any milestone with score ≤ 3

**Post a go-live update to the client portal:**
1. `search_rocketlane_tools("announcement")`
2. Create Announcement with title, body, project_id

**Create a key event (kickoff):**
1. `search_rocketlane_tools("key event")`
2. Pass project_id, event_type = "kickoff", date

**Share a document with the client:**
1. `search_rocketlane_tools("space")`
2. Set visibility = "client-visible" on the relevant space

**Trigger CSAT for a milestone:**
1. Ensure task has `is_milestone: true` and `is_public: true`
2. `search_rocketlane_tools("update task")` → set status to Completed
3. CSAT survey sends automatically to Customer users on the project
