---
name: rocketlane_financials
description: Domain reference for Rocketlane billing types, rate cards, budgets (including multiple budgets beta), expenses, billing events, and invoicing.
---

# Rocketlane Financials Domain Reference

## Billing Types

| Type | How revenue is calculated |
|------|--------------------------|
| T&M (Time & Material) | Hours logged × bill_rate per role |
| Fixed Fee | Lump sum released on milestone completion (billing event) |
| Subscription | Recurring fixed amount on a schedule |
| Retainer | Pre-paid hours block; unused hours may roll over |
| Non-billable | No revenue; used for internal or pro-bono work |

## Rate Card

- Defines **bill_rate** (charged to client) and **cost_rate** (internal cost) per role.
- Applied at the project level; can be overridden per project.
- Roles (e.g., Developer, Designer, PM) map to rate card entries.
- **Profit margin** = (bill_amount − cost_amount) / bill_amount × 100%
- Rate cards are account-specific — discover via `search_rocketlane_tools("rate card")`.

## Budget

- A Budget is a planned cost/revenue envelope for a project.
- Fields: name, planned_cost, planned_revenue, actual_cost, actual_revenue, project_id
- **Budget health** = actual_cost vs planned_cost (and actual_revenue vs planned_revenue).
- Budget variance threshold: typically flag at 15% over plan.

### Multiple Project Budgets (Closed Beta)

- A single project can have **more than one budget** (e.g., by phase, billing type, or cost center).
- When this feature is active, `get_budget` may return an array of budget objects.
- **Always enumerate all budgets** — do not assume a single budget per project.
- Sum across all budgets for total project financial position.
- Not yet in public help docs — handle gracefully if the API returns an array.

## Billing Events

- A Billing Event is a revenue trigger attached to a Milestone.
- When the milestone is marked Complete, the billing event fires → generates an invoice line.
- Fields: milestone_id, project_id, amount, billing_date, status (Pending, Invoiced, Paid)
- Use `search_rocketlane_tools("billing event")` to list and manage billing events.

## Invoice Approval Workflow

```
Billing Event fires → Invoice Draft created → Reviewed → Approved → Sent to client
```

- Invoices can be exported to accounting integrations (NetSuite, QuickBooks, Sage).
- Only Approved billing events appear on invoices.

## Expense Management

- Native expense reports in Rocketlane (no third-party integration required).
- **AI receipt reading**: upload a receipt image → AI extracts amount, date, vendor, category.
- Approval chain: submitter → manager / project PM → finance team.
- Expense fields: amount, currency, category, date, project_id, receipt_url, status, notes.
- Reimbursable vs non-reimbursable designation per expense.
- Use `search_rocketlane_tools("expense")` to find expense tools.

## Accounting Integrations

| System | Integration type |
|--------|----------------|
| NetSuite | Bi-directional sync of invoices and payments |
| QuickBooks | Invoice export + payment sync |
| Sage | Invoice export |

## Common Patterns

**Get financial summary for a project:**
1. `search_rocketlane_tools("budget")` → retrieve all budgets (handle array for beta)
2. `search_rocketlane_tools("billing event")` → list billing events + status
3. For T&M: sum approved timesheet hours × bill_rate from rate card
4. Compare actual vs planned; compute margin if cost_rate available

**Trigger a billing event (milestone completion):**
1. `search_rocketlane_tools("update task")` → set milestone status to Completed
2. Billing event fires automatically if configured
3. Confirm invoice draft created via `search_rocketlane_tools("invoice")`

**Check budget health:**
1. Retrieve all budgets (enumerate if multiple)
2. For each: actual_cost / planned_cost → flag if > 115% (15% variance)

**Log an expense:**
1. `search_rocketlane_tools("create expense")`
2. Pass amount, category, date, project_id, receipt_url, is_reimbursable

**Get rate card for a project:**
1. `search_rocketlane_tools("rate card")`
2. Match roles to team members for T&M calculations
