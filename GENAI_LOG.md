## Entries

### 1.

**Tool:** GitHub Copilot (University access)
**Date:** 2026-05-04
**Context:** Writing the initial tokeniser regex.
**Prompt (paraphrased):** Implicit autocomplete from a docstring `"""Split text into lowercase alphanumeric tokens."""`.
**Output quality:** Suggested `re.findall(r'\w+', text.lower())`. Functionally close, but `\w` includes underscores and matches non-ASCII letters by default, fine for English quotes but inconsistent with the simple model needed.
**What I changed:** Replaced with `re.findall(r"[a-z0-9']+", text.lower())` to keep contractions like `don't` as single tokens, and explicitly excluded underscores.
**Reflection:** Copilot's suggestions optimise for Python idiom rather than the specific tokenisation semantics described in Lecture 11. Reading the lecture material first, then evaluating AI output against it, is more effective than the reverse.

## Summary reflection

- Where did GenAI most help? Where most hinder?
- How did using AI affect what you understood vs. what you produced?
- Were there places you deliberately chose not to use AI? Why?
- How did debugging AI-generated code differ from debugging your own?
- What ethical considerations came up?
---