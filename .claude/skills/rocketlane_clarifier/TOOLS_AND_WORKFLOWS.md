---
name: rocketlane-clarifier-reference
description: Workflow patterns, tool reference, and technical details for Rocketlane Clarifier
---

# Rocketlane Clarifier - Reference Guide

## ⚠️ CRITICAL: Field Discovery Pattern

**ALWAYS DO THIS BEFORE FILTERING ANY DATA**

Many Rocketlane objects (projects, tasks, users, etc.) have custom fields that vary by account. You must discover field names and IDs before using them in filters.

**Workflow:**
```
1. Invoke: get_fields(object_type="PROJECT" | "TASK" | "USER" | "TIME_ENTRY" | "SKILL")
2. Response includes:
   - Native fields: {"field_name": "projectName", "field_id": null}
   - Custom fields: {"field_name": "WorldRegion", "field_id": 594325}
3. Use field_name for native fields, field_id for custom fields in filters
```

**⚠️ IMPORTANT: Context-Based Field Discovery**

**Before answering ANY user query, determine what object type the query concerns and fetch the appropriate fields:**

- **Query about USERS** (e.g., "Get users with Manager X", "Find users in Region Y")
  → Call `get_fields(object_type="USER")` to fetch user fields

- **Query about PROJECTS** (e.g., "Get projects in AMER region", "Find projects with budget > 50k")
  → Call `get_fields(object_type="PROJECT")` to fetch project fields

- **Query about USER SKILLS** (e.g., "Find users with Python skill", "Get developers with Java")
  → Call `get_fields(object_type="SKILL")` to fetch user skill fields

**Example:**
```
User Query: "Get all users who have the Python skill"
Step 1: Call get_fields(object_type="SKILL")  ← MUST DO THIS FIRST
Step 2: Find skill field_id for "Python" from response
Step 3: Use the skill field_id in user analytics filter
```

**Why This Matters:**
- Custom field IDs are unique per account (594325 in one account ≠ 594325 in another)
- Field names can be user-defined ("WorldRegion", "DealSize", etc.)
- Filtering without field discovery = guaranteed failure

**When to Call:**
- Before any project filtering
- Before any task filtering
- Before any user filtering (for custom user fields)
- Before any skill-based user filtering
- Basically: before any filter operation with `filters` parameter

---

## Common Cross-Tool Workflows

### Workflow 1: Get Projects for a Customer

**Pattern:** Need customer ID first, then filter projects

```
1. Invoke: get_companies_by_name(name="Acme Corp")
   → Returns: {"companyId": 12345, "companyName": "Acme Corp"}

2. Invoke: get_fields(object_type="PROJECT")
   → Confirms "customer" is a valid field

3. Invoke: get_projects_paginated(
     filters=[{"field": "customer", "operation": "value", "value": "12345"}]
   )
```

### Workflow 2: Filter Projects by Custom Field

**Pattern:** Discover custom field ID, then filter

```
1. Invoke: get_fields(object_type="PROJECT", names="WorldRegion")
   → Returns: {"field_name": "WorldRegion", "field_id": 594325}

2. Invoke: get_projects_paginated(
     filters=[{"field_id": 594325, "operation": "contains", "value": "AMER"}]
   )
```

### Workflow 3: Get Tasks for a Customer (Cross-Object Filtering)

**Pattern:** Tasks can filter by project fields using `source_type`

```
1. Get customer ID (see Workflow 1)

2. Invoke: get_fields(object_type="PROJECT")
   → Confirms "customer" field exists

3. Invoke: get_tasks_paginated(
     filters=[{
       "field": "customer",
       "operation": "value",
       "value": "12345",
       "source_type": "project"  ← KEY: Filter by project field
     }]
   )
```

**Note:** `source_type: "project"` tells the API to filter tasks by their parent project's fields.

### Workflow 4: Analyze Time Across Multiple Projects

**Pattern:** Sequential tool calls to aggregate data

```
1. Invoke: get_projects_paginated(limit=500)
   → Returns list of projects with IDs

2. For each relevant project:
   Invoke: get_project_time_analytics(
     start_date="2025-01-01",
     end_date="2025-03-31",
     project_id=<project_id>
   )

3. Aggregate results and present summary
```

**Phase 1 Note:** Each tool call is separate - no programmatic calling yet.

### Workflow 5: Filter Users by Skills

**Pattern:** Skills are custom fields, require special analytics filter

```
1. Invoke: get_fields(object_type="SKILL")
   → Returns: [{"field_label": "Programming Languages", "field_id": 12345}]

2. Invoke: get_user_tracked_hours_breakdown(
     start_date="2025-01-01",
     end_date="2025-01-31",
     analytics_filter={
       "skillFilters": [
         {"field_id": 12345, "operation": "oneOf", "value": "Python,Java"}
       ],
       "activeUsersOnly": true
     }
   )
```

**Note:** User skill filtering ONLY works with user_analytics_tools (not user_tools).

### Workflow 6: Get Resource Allocation with Custom Field Filters

**Pattern:** Allocation/demand filtering requires field metadata

```
1. Invoke: get_fields(object_type="PROJECT", names="Region")
   → Returns: {"field_id": 594325}

2. Invoke: get_demand_data(
     start_date="2025-Q1",
     end_date="2025-Q4",
     allocation_filters=[{
       "source_type": "project",
       "field_name": "Region",
       "is_custom_field": true,
       "field_id": 594325,
       "operation": "contains",
       "value": "EMEA"
     }]
   )
```

### Workflow 7: Revenue/Portfolio Report by Customer

**Pattern:** Customer ID → Portfolio filtering

```
1. Get customer ID (see Workflow 1)

2. Invoke: get_portfolio_report(
     start_date="2025-01-01",
     end_date="2025-12-31",
     filters=[{"field": "customer", "operation": "value", "value": "12345"}]
   )
```

### Workflow 8: Project Performance Reports with Filters

**Pattern:** Same as projects - field discovery first

```
1. Invoke: get_fields(object_type="PROJECT")

2. Invoke: get_project_reports(
     start_date="2025-01-01",
     end_date="2025-12-31",
     filters=[{"field": "statusName", "operation": "value", "value": "Active"}]
   )
```

---

## Large Output Handling

**15KB Threshold:** Tools automatically save outputs >15KB to files.

**How It Works:**
1. Tool executes and checks output size
2. If >15KB:
   - Writes to `/home/user/outputs/tool_name_timestamp.json`
   - Returns response with file path + summary
3. If ≤15KB:
   - Returns output inline

**Example Response (Large Output):**
```
**Output written to file** (size: 45.2KB)

**File Path**: `/home/user/outputs/get_projects_paginated_1704844800.json`

**Summary**: Dict with keys: ['data', 'count', 'hasMore', 'offset', 'limit']
Total projects: 150

**To Access**: Use file reading tools to read `/home/user/outputs/get_projects_paginated_1704844800.json` for full data.
```

**When to Read Files:**
- Need to analyze specific records
- Need to perform calculations across data
- Need to extract specific fields
- User asks for detailed breakdown

**When NOT to Read Files:**
- Summary answers the user's question
- Only need counts/aggregates
- File would exceed context limits anyway

---

## Current technical limitations

**Currently: Direct Tool Calling Only**

What This Means:
- Each tool must be invoked separately
- No Python code that calls tools programmatically
- For multi-step workflows, call tools sequentially
- Each tool call returns to your context before next call

**Example:**
```
1. Call get_projects_paginated() → receive results
2. Identify relevant project IDs from results
3. Call get_project_time_analytics(project_id=123) → receive results
4. Call get_project_time_analytics(project_id=456) → receive results
5. Aggregate results manually in your response
```

**Future:** Programmatic calling will allow writing Python code that orchestrates multiple tools in a single execution.

---

---

## Tool Categories

Tools are organized into 9 categories:

1. **User Management** (7 tools)
   - User data, roles, holiday calendars, cost rates
   - Tools: get_users_info, get_roles, search_user, search_user_by_name, get_bulk_user_details, get_holiday_calendar, get_cost_rates

2. **Project Management** (1 tool)
   - Project data with task counts, phases, filtering
   - Tools: get_projects_paginated

3. **Task Management** (2 tools)
   - Task data with cross-object filtering
   - Tools: get_tasks_paginated, get_task_by_id

4. **Time Tracking** (4 tools)
   - Timesheet analytics, project time analytics, categories
   - Tools: get_timesheet_analytics_grouped_by_role, get_project_time_analytics, get_all_timesheet_categories

5. **User Analytics** (6 tools)
   - Utilization, capacity, hours breakdown, skill filtering
   - Tools: get_user_utilization_capacity_breakdown, get_user_tracked_hours_breakdown, get_user_timesheet_submission_approval_metrics, get_overall_time_analytics_metrics, get_user_time_sheet_analytics, get_user_tracked_hours_by_category_breakdown

6. **Resource Management** (2 tools)
   - Allocations, demand/capacity analysis
   - Tools: get_allocations_lite, get_demand_data

7. **Reports** (6 tools)
   - Project reports, user reports, utilization reports
   - Tools: get_project_reports, get_available_project_report_columns, get_user_reports, get_available_user_report_columns, get_utilization_report, get_available_utilization_report_columns

8. **Revenue** (2 tools)
   - Portfolio reports, filter operations
   - Tools: get_portfolio_report, get_filter_operations

9. **Fields** (2 tools) ⭐ **CRITICAL**
   - Field metadata discovery
   - Tools: get_fields, get_filterable_fields_documentation

---

## Quick Reference: Common Tools

| User Need | Common Tools |
|-----------|--------------|
| Get users by role/status | get_users_info, get_roles |
| Find user by email/name | search_user, search_user_by_name |
| Get projects | get_projects_paginated |
| Get tasks | get_tasks_paginated |
| Time tracking | get_timesheet_analytics |
| Project time | get_project_time_analytics |
| User utilization | get_user_utilization_capacity_breakdown |
| Allocations | get_allocations_lite, get_demand_data |
| Project reports | get_project_reports |
| Revenue/portfolio | get_portfolio_report |
| **Field discovery** | get_fields ⭐ |

---

## Tips for Success

1. **Field Discovery First:** Can't emphasize this enough - ALWAYS call get_fields before filtering
2. **Context-Based Discovery:** Analyze user query and call get_fields with appropriate object_type (USER/PROJECT/SKILL)
3. **Check Output Size:** If >15KB, file will be written automatically
4. **Sequential Workflows:** Currently requires separate tool calls - plan accordingly
5. **Customer ID Lookups:** Many workflows start with get_companies_by_name
6. **Cross-Object Filtering:** Use `source_type` parameter to filter by related object fields
7. **Skill Filtering:** Only works with user_analytics_tools, not user_tools


---

## Success Criteria

You're using this skill correctly when you:
- ✅ Call get_fields before ANY filtering operation
- ✅ Determine object_type from user query context (USER/PROJECT/SKILL)
- ✅ Get customer IDs before filtering by customer
- ✅ Use source_type for cross-object filtering
- ✅ Handle large outputs via file paths
- ✅ Build multi-step workflows with sequential tool calls
- ✅ Rely on tool descriptions for parameters/output format

You're NOT using this correctly when you:
- ❌ Try to filter without calling get_fields first
- ❌ Use customer names instead of customer IDs in filters
- ❌ Expect one tool to do everything (use workflows!)
- ❌ Write Python code that calls tools (Phase 1 doesn't support this)
- ❌ Try to read 50KB output files in context
