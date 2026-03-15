---
name: rocketlane_projects
description: Domain reference for Rocketlane projects, tasks, sprints, epics, milestones, dependencies, and RAID management.
---

# Rocketlane Projects Domain Reference

## Project Fields

| Field | Notes |
|-------|-------|
| name | Project display name |
| status | Not Started, In Progress, Completed, On Hold, Cancelled |
| health | Red / Amber / Green (RAG) |
| start_date / end_date | ISO 8601 dates |
| billing_type | T&M, Fixed Fee, Subscription, Retainer, Non-billable |
| owner | User ID of PM |
| account_id | Parent customer (Account) |
| project_template_id | Template used to create the project |
| custom_fields | Account-specific — discover via `get_fields(object_type="project")` |

## Phase Fields

| Field | Notes |
|-------|-------|
| name | Phase display name |
| order | Integer; phases are ordered within a project |
| start_date / end_date | Can be auto-calculated from tasks |
| status | Mirrors task completion % |
| phase_dependency | A phase can depend on another phase completing first |

## Task Fields

| Field | Notes |
|-------|-------|
| name | Task display name |
| phase_id | Parent phase (nullable — tasks can be unphased) |
| assignee | User ID |
| due_date / start_date | ISO 8601 |
| status | Not Started, In Progress, Completed, On Hold, Cancelled |
| priority | Low, Medium, High, Urgent |
| estimated_hours / actual_hours | Effort tracking (Native + Partner only) |
| is_milestone | Boolean — marks delivery checkpoints |
| is_subtask | Boolean — child of a parent task |
| parent_task_id | Set when is_subtask = true |
| sprint_id | Null = Backlog; set = belongs to that sprint |
| epic_id | Optional grouping initiative |
| approval_status | None, Pending, Approved, Rejected |
| is_public | Whether visible in client portal |
| custom_fields | Discover via `get_fields(object_type="task")` |

## Subtasks

- A subtask is a task with `is_subtask: true` and a `parent_task_id`.
- Subtasks appear under their parent in List and Board views.
- Subtasks inherit the phase of their parent by default.

## Epics

- An Epic groups related tasks across one or more sprints into a named initiative.
- Fields: name, description, start_date, end_date, status, project_id.
- Tasks reference an epic via `epic_id`.
- Epics appear in the Timeline (Gantt) view as swimlanes.

## Sprints & Backlog

- A Sprint is a time-boxed work period within a project.
- Fields: name, start_date, end_date, goal, status (Active, Planned, Completed).
- Tasks with `sprint_id = null` are in the **Backlog**.
- Moving a task to a sprint sets its `sprint_id`; removing clears it back to Backlog.
- Only one sprint can be Active at a time per project.

## Milestones

- A Milestone is a task with `is_milestone: true`.
- Marks a delivery checkpoint; has a due_date and status.
- **CSAT trigger**: when `is_public: true` + `is_milestone: true` + status set to Completed → CSAT survey sent to Customer users.
- **Billing event trigger**: a Billing Event attached to a milestone fires when the milestone is completed.
- Milestones appear on the Timeline (Gantt) as diamonds.

## Key Events

- Key Events are significant project moments: kickoff, go-live, phase completion, health change, CSAT received.
- Appear on the project timeline; can trigger automations.
- **Interval IQ**: measures elapsed time between key events across projects for benchmarking delivery speed.

## Dependency Types

| Type | Meaning |
|------|---------|
| Finish-to-Start (FS) | Dependent task cannot start until predecessor finishes |
| Start-to-Start (SS) | Dependent task cannot start until predecessor starts |
| Finish-to-Finish (FF) | Dependent task cannot finish until predecessor finishes |
| Start-to-Finish (SF) | Dependent task cannot finish until predecessor starts |

- SS, FF, SF require Premium+ plan.
- When a predecessor's end date shifts, dependent tasks cascade automatically.
- Phase dependencies: a phase can be configured to start only after a prerequisite phase completes.

## View Types

| View | Description |
|------|-------------|
| List | Flat task list with inline editing |
| Board | Kanban columns by status |
| Timeline (Gantt) | Visual bar chart with dependencies |
| Kanban | Drag-and-drop by custom field grouping |

## RAID Management

RAID = Risks, Assumptions, Issues, Dependencies.
- Each RAID item is linked to a project and has: type, description, status, owner, due_date.
- Risks and Issues can escalate to project health changes.
- Use `search_rocketlane_tools("RAID")` to find the relevant tools.

## Common Patterns

**List sprint backlog:**
1. `search_rocketlane_tools("list tasks")` → find task list tool
2. Filter by `project_id` + `sprint_id = null` (backlog) or `sprint_id = <sprint_id>`

**Create a subtask:**
1. `search_rocketlane_tools("create task")`
2. Pass `parent_task_id`, `is_subtask: true`, `phase_id` of parent

**Move tasks to sprint:**
1. `search_rocketlane_tools("update task")`
2. Set `sprint_id` on each task

**Find overdue tasks:**
1. `search_rocketlane_tools("list tasks")`
2. Filter `due_date lessThan <today>` + `status notEquals Completed`
