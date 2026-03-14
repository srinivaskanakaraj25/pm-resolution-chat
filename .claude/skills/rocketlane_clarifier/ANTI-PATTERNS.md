# Anti-Patterns

Common mistakes to avoid during clarification. Add to this file as patterns emerge.

---

## Conversation Anti-Patterns

### Asking too many questions at once
❌ Bad:
```
What's the threshold? And what time period? And which projects?
And what about archived ones? And what output format?
```

✅ Good:
```
What threshold would you consider concerning?
(e.g., if we've spent 80% of budget but only completed 60%)
```

---

### Exposing internal terminology
❌ Bad:
```
This is a financial_management domain request in diagnostic mode.
I'll need to check the entities/ directory for field definitions.
```

✅ Good:
```
Got it - you want to understand why revenue dropped.
Let me clarify a few things...
```

---

### Not validating understanding before proceeding
❌ Bad:
```
[User says something vague]
[AI immediately starts building the plan without confirming]
```

✅ Good:
```
[User says something vague]
"Just to make sure I understand - you want to [echo back]. Is that right?"
```

---

## Field Reference Anti-Patterns

### Assuming fields exist
❌ Bad:
```
I'll filter by the Sentiment field on projects.
```

✅ Good:
```
You mentioned "poor sentiment" - is this a custom field on your projects?
Could you point me to where I should get this information from? 
```

---

### Not helping define unclear metrics
❌ Bad:
```
What do you mean by "project CSAT"?
```

✅ Good:
```
"Overall project CSAT" could mean a few things:
- Average of all milestone CSAT scores?
- Most recent CSAT score?
- A specific custom field?
Which one are you thinking of?
```

---

## Scope Anti-Patterns

### Accepting scope that's too broad
❌ Bad:
```
User: "Show me everything about our projects"
AI: "Sure, I'll analyze all project data..."
```

✅ Good:
```
User: "Show me everything about our projects"
AI: "That's quite broad - what specifically are you trying to understand?
Budget health? Timeline status? Resource utilization?"
```

---