---
name: rocketlane_resources
description: Domain reference for Rocketlane resource management, allocations, team planner, time tracking, timesheets, and utilization.
---

# Rocketlane Resources Domain Reference

## FTE Model

- **FTE = 1.0** = full-time (e.g., 40 hours/week, 8 hours/day)
- Part-time = fractional (e.g., 0.5 FTE = 20 hours/week)
- Each user's capacity is configurable (hours/day or hours/week)
- Overallocation = total allocated FTE > 1.0 for that person in a given period

## Allocation Types

| Type | Meaning |
|------|---------|
| Hard Allocation | Committed, confirmed assignment to a project |
| Soft Allocation | Tentative / proposed assignment |

- Allocation ≠ tracked time. Allocation = plan; Time Entry = actuals.
- Allocation fields: user_id, project_id, start_date, end_date, fte, allocation_type (hard/soft)

## Team Planner

- Shows each team member's total allocation vs available capacity per week.
- Highlights overallocated (red) and underallocated (green) periods.
- Use `search_rocketlane_tools("team planner")` or `search_rocketlane_tools("allocation")`.

## Resource Planner / Demand Data

- `get_demand_data` — cross-project view of demand vs capacity.
- Shows aggregated allocation across all projects per person per week.
- Useful for capacity planning across the portfolio, not just one project.

## ResourceAI

- Single-click allocation suggestions based on role, availability, and skills.
- Surfaces underutilized team members who match the required role.
- Use `search_rocketlane_tools("ResourceAI")` to find the tool.

## Time Entry Fields

| Field | Notes |
|-------|-------|
| task_id | Task being logged against (optional if project-level) |
| project_id | Project the time belongs to |
| user_id | Who logged the time |
| date | ISO 8601 date of work |
| hours | Duration (decimal, e.g., 1.5) |
| is_billable | Boolean — determines revenue impact |
| category | Work category / activity type |
| notes | Free-text description |
| custom_fields | Discover via `get_fields(object_type="time_entry")` |

## Timesheet Flow

```
Draft → Submitted → Approved / Rejected
```

- A Timesheet covers **Monday–Sunday** for one person.
- Contains all Time Entries for that person in that week.
- Must be Approved before T&M billing calculations use the hours.
- Rejected timesheets return to the user for correction.

**Approver hierarchy**: configured per organization; typically the user's manager or project PM.

## Time Off

- Approved time-off reduces available capacity by **0.2 FTE per day**.
- Example: 5-day leave = 1.0 FTE reduction that week → zero available capacity.
- Time off appears in the Team Planner and affects utilization calculations.
- Use `search_rocketlane_tools("time off")` to retrieve leave records.

## Utilization

- **Utilization** = (allocated or tracked hours) / available capacity × 100%
- Calculated **only for Native and Partner users** — never Customer users.
- Forecasted utilization = based on allocations (plan).
- Actual utilization = based on tracked Time Entries (actuals).
- Healthy range: typically 70–110%. Below 70% = underutilized; above 110% = overloaded.
- **Do not recalculate** — retrieve from system via the utilization report tools.

## Common Patterns

**Check if a person is overallocated:**
1. `search_rocketlane_tools("allocation")` → list allocations for user
2. Sum FTE values per week; compare to 1.0

**Plan around leave:**
1. `search_rocketlane_tools("time off")` → get approved leave for team member
2. `search_rocketlane_tools("list tasks")` → find their tasks during leave window
3. Flag tasks at risk; suggest reassignment or date shift

**Log time for a user:**
1. `search_rocketlane_tools("create time entry")`
2. Pass task_id, project_id, user_id, date, hours, is_billable

**Check timesheet status:**
1. `search_rocketlane_tools("timesheet")`
2. Filter by user_id + week_start_date

**Get utilization report:**
1. `search_rocketlane_tools("utilization")`
2. Filter to Native + Partner users; specify date range
