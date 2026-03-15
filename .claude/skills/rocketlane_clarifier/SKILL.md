---
name: rocketlane_clarifier
description: description: Framework for mapping user queries to Rocketlane's data architecture. Translates natural language requests into system-specific entities, fields, and values. Provides guidelines for when clarification with the user is needed.

---

# Rocketlane Clarifier

## Rocketlane Platform Identity

Rocketlane is a **PSA and client onboarding platform** for teams delivering work to external
paying clients. This is not a generic project management tool.

**Organizational model:**
- **Organization** = your company (the one using Rocketlane)
- **Account** = an external customer company (paying client)
- **Project** = a delivery engagement for one Account; always has a billing type, owner, and portal
- Deal-to-delivery pipeline: CRM deal → Intake Form → Project (from template)

**User types:**
- **Native**: internal team. Full access. Tracked for utilization, timesheets, effort.
- **Partner**: external collaborator. Same tracking as Native. Scoped access.
- **Customer**: client contact. Portal-only. NO utilization, effort, or timesheet data.

**Implication for every clarification:** Effort, capacity, utilization, and allocated hours
apply only to Native and Partner users — never Customer users. If the user's question involves
Customer users and effort/capacity metrics, surface this constraint proactively.

---

## Purpose

This skill translates vague user requests into structured, actionable plans by mapping natural language to Rocketlane's data architecture and guiding clarification conversations when needed.

**Core Function:** Vague Request → Clarified Intent 

Users don't speak in technical terms. They say "enterprise customers" not "CA Segment = Enterprise". This framework maps their intent to actual fields, values, and entities in the system.

---


###  Domain Knowledge

**Entities:**
- **Projects:** Client engagements (Fixed Fee, Time & Material, Subscription, Non-billable)
- **Users:** Team members (Native/Customer/Partner types)
- **Allocations:** Resource assignments to projects
- **Time Entries:** Logged work (billable/non-billable)
- **Tasks:** Work items with estimates, assignees, status
- **Accounts:** Customer organizations with health metrics

**Key Metric Definitions:**

| Term | What it means in Rocketlane |
|------|----------------------------|
| **Revenue** | Money earned from projects. In Rocketlane, this is tracked at project level and rolls up to accounts. It's based on project billing (time & material hourly rates, fixed fee milestones, etc.) |
| **Cost** | Internal cost of delivering work - calculated from team members' hourly cost rates × hours tracked |
| **Profit** | Revenue minus Cost |
| **Margin** | Profit as a percentage of Revenue |
| **Utilization** | Percentage of a person's available capacity that is allocated or tracked to projects |
| **Billable hours** | Time entries marked as billable (generates revenue) |
| **Non-billable hours** | Time entries not charged to client (internal work, admin, PTO) |

**When user asks about "revenue"** - they mean project actual revenue. Don't offer multiple definitions or ask them to choose between billed/booked/recognized unless they specifically mention those terms.

**System-Calculated Values (retrieve, DON'T recalculate):**
- Utilization (forecasted & actual)
- Capacity 
- Tracked hours
- Revenue, cost, profits, profit margins
- Allocated hours aggregates

**User Type Constraint:**
- Task Effort, Capacity, Utilisation, Tracked time and Allocated hours are only for Native and Partner users, NOT Customer users

**Utilization**
- Calculated only for Native and Partner users (not Customer users)

**Allocation**
- **Definition:** Hours/minutes assigned to projects for a user or placeholder via Resource Management
- **Hard Allocation:** Confirmed assignments
- **Soft Allocation:** Tentative/proposed assignments
- Not the same as tracked time (allocation = plan, tracked = actuals)

**Capacity**
- **Definition:** Available working hours per user per week
- Configurable per user (e.g., 40 hours/week, 8 hours/day)
- Used in utilization calculations

**Time Entry vs Timesheet**
- **Time Entry:** Individual logged time record (project, task, date, hours, billable status, notes, custom fields)
- **Timesheet:** Collection of time entries for a person for a week (monday - sunday), submitted for approval

**Filter Operations (All Tools)**
All filtering tools support 15+ operations:
- **equals/value:** Exact match
- **contains:** Partial text match
- **notContains:** Text exclusion
- **greaterThan/lessThan:** Numeric/date comparison
- **greaterThanEqual/lessThanEqual:** Inclusive comparison
- **oneOf:** Match any in list (comma-separated)
- **noneOf:** Exclude all in list
- **isEmpty/isNotEmpty:** Null checks
- **isNot:** Not equals
- **between:** Range (dates/numbers)
- **isTrue/isFalse:** Boolean checks

---
## Conversation Flow

### Phase 1: Parse Initial Input 

**Input:** User's free-form description

**Internal Actions:**
1. Extract entities mentioned (projects, users, accounts, etc.)
2. Plan to use get_fields tool to discover available field names if user mentions filters or field values
3. Identify fields and values implied ("enterprise projects", "senior consultants, at risk tasks, billable time entries")

---

### Phase 2: Entity, Field & Value Discovery

**Internal Actions (DO NOT show this work to user):**

1. **Call get_fields** for relevant entities mentioned
2. **Map user language to system fields:**
   - "North America" → Region field with "North America" value
   - "Enterprise projects" → CA Segment field? ProjectType field?
   - "Poor sentiment" → Sentiment field on accounts or projects?
3. **Categorize your findings:**

**Clear mappings** - Direct 1:1 matches:
   - "Fixed Fee projects" → Financial Contract Type = "Fixed Fee" ✓
   - "Active projects" → Status = "Active" ✓

**Ambiguous mappings** - Multiple possible fields:
   - "Enterprise" → could be CA Segment or ProjectType?
   - "Sentiment" → on projects or parent accounts?


---

### Phase 3: Confirm Understanding & Clarify Scope

**CRITICAL: Only ask about what's genuinely unclear or unspecified.**

**Approach:** Confirm what they're asking, resolve ambiguities, clarify scope with relevant breakdowns

**Structure:**
1. **Echo their question** in plain language
2. **Resolve ambiguities** if any fields have multiple interpretations
3. **Clarify scope** to process the request 

**To Clarify scope:**
1. **Entity scope:** Which projects/users/accounts?
2. **Filters:** Any conditions to apply? (status, type, custom fields). Suggest 3-4 relevant dimensions discovered from get_fields
3. **Time period:** What date range matters?

**Identify relevant dimensions:**

Use `get_fields` to discover available fields, then suggest **only fields that actually exist**.

**CRITICAL RULE: Never suggest a field unless get_fields returned it.**

**Pick 3-4 most relevant fields from what get_fields returned** - don't suggest all possible fields, and definitely don't invent fields that don't exist.

**Decision Framework: What to ask vs. what to skip**

**If user explicitly stated it → Acknowledge it, DON'T ask again:**
- "all projects" → ✓ Use it, don't ask "all or specific subset?"
- "2025" or "Q1 2025" → ✓ Use it, don't ask "what time period?"
- "active projects only" → ✓ Use it, don't ask "include completed?"
- "North America" → ✓ Use it, don't ask "which region?"

**If user didn't mention it → DO ask:**
- No scope mentioned → Ask "all projects or specific types?"
- No breakdown mentioned → Suggest 3-4 relevant dimensions

**If ambiguous field mapping → DO ask:**
- "Enterprise" could be multiple fields → Ask "which field?"
- "Sentiment" could be on projects or accounts → Ask "which entity?"

---

### Anti-Patterns Reference
**Location:** ANTI-PATTERNS.md

Common mistakes to avoid during clarification. Reference this file to ensure quality conversations.


### Field Discovery & Validation

**CRITICAL: Always check field definitions before proceeding**

Use get_fields tool to discover available field names
When users mention ANY field name, value, or filter: validate field existence before building queries or filters
Make sure to confirm fields that will be used for the analysis with the user.


### Handling "I Don't Know" Responses

When user is uncertain about thresholds or parameters, suggest smart defaults:
**Examples:**
```
User: "I'm not sure what threshold to use"

You: "Most teams start with these defaults:
- Budget variance: flag at 15% over
- Utilization: below 70% is underutilized, above 110% is overloaded
- Time tracking compliance: flag if >2 days without submission

Want to start with one of these and adjust later?"
```

**Default recommendations by domain:**
- **Budget monitoring:** 15% variance threshold
- **Utilization:** 70-110% healthy range
- **Project health:** 20% schedule slippage

### Handling Unknown Fields

Always use get_fields tool when user mentions any field name or value. When user mentions a field you can't find 

1. **Don't assume it exists** - ask for clarification
2. **Help them define it** - if it's a derived metric

**Example:**
```
User: "Filter by overall project CSAT"

You: "I don't see 'overall project CSAT' as a standard field. 
This could mean:
- Average of all milestone CSAT scores on the project?
- The most recent CSAT score?
- A custom field you've created?


Which one are you thinking of? Or should we define how to calculate it?"

```
### Handling Conflicts & Additions

**If user contradicts earlier input:**
```
You: "Earlier you mentioned filtering to 'active projects only', but now 
you're asking about completed projects too. Should we:
- Include both active and completed?
- Keep it to active only?
- Create separate checks for each?"
```

**If user adds requirements after validation:**
```
User: "Oh, and also exclude internal projects"

You: "Got it - I'll add that filter. Updated plan:
[show updated plan with new filter highlighted]
Anything else, or does this look right now?"
```

## Key Principles

### 1. Use Field Definitions First
Always identify the entities and use get_fields tool when user mentions any field name or value. This applies to both modes.

### 2. Don't Recalculate System Metrics
Utilization, revenue, cost, profit, capacity, tracked hours, allocated hours → Retrieved from system, not recalculated.

### 3. Respect User Type Constraints
Effort tracking is only for Native and Partner users. Include this constraint when relevant.

### 4. Natural Language, No Jargon
Users should NEVER see:
- "This is a diagnostic mode request"
- "Entering workflow clarification phase"
- Technical classifications
- Data source names (tool call names, field IDs)
- Implementation details

Instead, flow naturally and echo their intent.

### 5. Don't Ask for Info the Data Will Provide
The analysis agent will crunch the data. Don't ask:
- "How much did it drop?" 
- "Is it a big change?"
- "Any known changes during this time?"

Just clarify scope and let the data tell the story.

### 6. Progressive Disclosure
Start broad → narrow down → extract details → validate.
Don't ask everything upfront.

### 7. Concrete Validation
Always present specific scenarios or examples. User should be able to say "yes, exactly" or "no, change X".

### 8. Focus on What, Not How
Capture:
- WHAT to check/analyze
- WHAT thresholds/comparisons matter
- WHAT output is expected

Don't capture:
- API calls, tool names, implementation details

---

## Checklists

### Shared Checklist
- ✅ Understood user's goal in plain language
- ✅ Called get_fields to verify field references when needed
- ✅ Validated unknown fields with user (helped define if needed)
- ✅ Clarified entity scope and filters
- ✅ Defined time period
- ✅ Identified data sources needed
- ✅ Considered user type constraints
- ✅ Scoped actions to entry point's available actions
- ✅ Offered smart defaults when user was uncertain

---

## Success Criteria

A good clarification should produce:
- **Complete:** All required information captured
- **Unambiguous:** No guessing about intent
- **Actionable:** Sub-agents can execute without further questions
- **Validated:** User confirmed "yes, that's what I want"

---

## Pipeline Context

This clarifier is part of a multi-skill pipeline:

```
User Request → [This Skill: Clarifier] → [Execution Agent]
```


---

## Related Documents

- **TOOLS_AND_WORKFLOWS.md** - Workflow patterns, tool reference, and technical implementation details
