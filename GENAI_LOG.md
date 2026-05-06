## Examples 

### 1. Title text indexing

**Tool:** Claude 
**Date:** 2026-05-04
**Context:** First draft of `tests/test_indexer.py` for the
`InvertedIndex` class. The test suite had 33 tests and 31 passed
on the first run.
**Prompt (paraphrased):** "Write a comprehensive pytest suite for
this InvertedIndex class, covering tokenisation, posting
construction, persistence, and edge cases."
**Output quality:** Mostly correct, but two tests
(`test_document_record_stores_metadata` and
`test_round_trip_preserves_documents`) had off-by-one expected
token counts. Both assumed `<title>` text would NOT appear in the
indexed body.
**What I changed:** Traced the failure to BeautifulSoup's
`get_text()` extracting from the entire document including
`<head><title>`. I had to choose between (a) updating the tests to
expect title tokens or (b) modifying production code to exclude
the title. I chose (a) because the brief asks for "all
word occurrences", Lectures noted titles are valuable for
ranking, and real search engines index title text. I updated the
test expectations and added an extra assertion
(`assert idx.postings("greetings")`) so the test now positively
documents the design decision.
**Reflection:** AI-generated tests can encode the AI's implicit
assumptions about behaviour without flagging them. The test looks fine until you run it and discover it was asserting the wrong number. I added a note to my mental checklist that when
generated tests fail, the bug might be in the test, the production
code, OR in an unstated design assumption that hadn't been made explicit.

### 2. Mixed HTTP libraries broke the crawler test mocks

**Tool:** Claude 
**Date:** 2026-05-04
**Context:** Running the first `pytest tests/test_crawler.py` after
implementing the politeness window and robots.txt support. 13 of
15 tests passed.
**Prompt (paraphrased):** "Write tests for the Crawler class. Mock
all HTTP traffic with the responses library. Patch time.sleep so
the politeness window doesn't slow the suite down."
**Output quality:** The disallowed-URL test failed with the cryptic
message "Connection refused by Responses" against `/page/2`. The test had registered a
mock for `/robots.txt` that should have forbidden that URL.
**What I changed:** I assumed initially this was a missing mock.
After re-reading the generated code more carefully I realised the
real cause was that the production code used `urllib.robotparser`'s
`rp.read()` to fetch robots.txt, but `responses` only intercepts
the `requests` library so it can't see `urllib` traffic. So the
robots fetch failed, `self._robots` stayed `None`, and
`_allowed()` returned `True` for everything. To fix it required refactoring
`_load_robots()` to fetch via `requests.get()` and pass the body
to `RobotFileParser.parse()`. This made the test mock work and
it also improved the code (single HTTP
library, single User-Agent header, single timeout policy).
**Reflection:** The test code looked reasonable and the production code
looked reasonable so both pieces in isolation passed my inspection. The
inconsistency between them of using two different HTTP libraries
was hard to spot when reading and only visible during execution. I would
not have written that mistake myself because I'd have used the
same library throughout. Reading generated code required a
different level of attention than reading my own.

### 3. AND intersection optimisation

**Tool:** Claude
**Date:** 2026-05-05
**Context:** Implementing multi-word `find` in `src/search.py`. My
first draft computed the intersection by iterating in query order so
taking the first term's posting list, intersect with the second's,
intersect with the third's etc.
**Prompt (paraphrased):** "Review this multi-word find
implementation for any inefficiencies."
**Output quality:** The AI pointed out that intersection cost is
dominated by the smallest set and that always starting the
intersection from the smallest posting list converts a worst case
of O(k · max(\|postings\|)) into O(k · min(\|postings\|)) for a
query like `find the indifference` where "the" has thousands of
postings and "indifference" has one.
**What I changed:** Added a sort step before the intersection
loop `terms_with_postings.sort(key=lambda tp: len(tp[1]))`. Then
seeded the candidate set from the smallest list. I also added an
early exit when the intersection becomes empty because then further
intersection can't make it non-empty again.
**Reflection:** On one hand, the optimisation is genuinely important and I now
understand it well enough to defend it in the video and to mention
it in `docs/design-notes.md`. On the other
hand, I would not have thought of this without the help of AI and the AI has
done part of the thinking I should have done. I
worked through the complexity analysis on paper before adding
the line of code, so the implementation reflects my own
understanding rather than a pasted recommendation.

### 4. Deliberately not using AI for TF-IDF maths

**Tool:** Claude used post-implementation for review
**Date:** 2026-05-06
**Context:** Implementing the ranking function in `src/search.py`.
The 80–100 grade band names TF-IDF as advanced query processing,
and in lectures we learnt the general `R(Q, D) = Σ g_i(Q) · f_i(D)` framework.
**What I did instead:** I read around the lecture material — particularly the
sections on topical features and the role of inverse document
frequency — and from that decided to use the standard log-TF · log-IDF
form:
`score(d, q) = Σ_{t in q} (1 + log(tf_{t,d})) · log(N / df_t)`. Log-scaled term frequency dampens
the bias toward documents that simply repeat a word, and the IDF term
correctly down-weights common words across the corpus. I worked
through the formula before writing any
code and then implemented it in `Search.find()`. Then I showed
the implementation to Claude and asked it to review for correctness and
edge cases.
**Reflection:** This was a deliberate experiment in not using AI
for the parts of the project I most needed to understand. The
trade-off was time as it took me longer than asking for an
implementation would have done. However, when I
write the video script for the "design decisions" segment on this function I won't just be narrating code I accepted. I must be able to explain every line and so for this trickier ranking function I chose to go about the implementation in this way.

### 5. Generating commit messages

**Tool:** Copilot
**Date:** Throughout 2026-05-04 to 2026-05-07
**Context:** Writing commit messages for each feature branch. The
80–100 grade band says "semantic commits" specifically.
**Prompt (paraphrased):** When reaching a commit point,
asking for a formatted message that
described both the change and the rationale.
**Output quality:** Generally good but verbose. The body paragraphs were useful first drafts but
I tightened the prose in every case.
**What I changed:** Edited every commit message before running
`git commit`. Standard edits included removing
redundant rephrasing in the body and adding the
specific lecture references where relevant.
**Reflection:**
The version-control history was very important so using AI to draft them and editing the drafts was most effective and resulted in structured and helpful descriptions of the commit. Using AI to write them and copy-pasting unchanged wouldn't have been helpful for the project or for myself.

## Summary reflection

Throughout this coursework I used Copilot and Claude as a design partner rather than as the singular author. Every line of the code is one I read and understood and I am confident I can explain it. There were many instances where I rejected or rewrote AI suggestions and the rest of this document logs those moments.

**Where did GenAI most help?**
Where AI was most helpful was in producing boilerplate i knew I wanted but would have taken hours to type. For the GitHub Actions CI workflow, I knew the shape of what I needed (matrix-test against Python 3.10, 3.11, and 3.12, run pytest with coverage, upload the coverage report as an artifact) but the exact YAML syntax for 'actions/checkout@v4', 'actions/setup-python@v5', and the conditional 'if:' clause for the artifact upload was faster to read in a generated draft than to look up in the GitHub docs. The README was similar in that I had a structure in mind and AI assistance turned that outline into a complete document I then edited section by section. Test scafforlding was also made much more efficient by using AI. Asking for a 'pytest' fixture that mocked HTTP via the 'responses' library and another that patched 'time.sleep' produced near-correct boilerplate I just has to verify.

**Where did it most hinder?**
When making the inverted-index test suite, an AI-generated test for 'test_document_record_stores_metadata' asserted a token count of 2 for an HTML input that actually produced 3 tokens. The test assumed &lt;title&gt; text wouldn't be indexed alongside the text body. Running the suite caught this and I had to make the design decision of whether titles should count as part of the document body. I decided they should as the brief says "all word occurrences" and it was noted in lectures that titles are weight-rewarding. I then updated the tests accordingly. Another time AI hindered this coursework was the crawler tests. A test for robots.txt disallow rule failed because the production code used 'urllib.robotparser' for the robots fetch and 'requests' for everything else, and the 'responses' library only mocks the 'requests'. Fixing this test required refactoring the production code to use a single HTTP library which was an improvement that the AI didn't flag. In both of these cases the failures revealed assumptions buried in generated code that I wouldn't have noticed by reading alone and required me to understand what was happening to solve.

**The deepest lesson**
AI tools optimise but this doesn't mean correctness. Treating any AI output as a starting hypothesis to verify against the lectures and the brief rather than as a final answer was the discipline that led to a project that I fully understand.

**Impact on time management**
Net positive but not in the way I expected. AI saved me time on syntax and scaffolding but it did cost me time on verification. This was because every suggestion I accepted I had to validate against the brief, lectures and the failing-test output. The total time saved was real but smaller than expected. The bigger benefit was that I rarely felt stuck, I had a design partner that could explain theory I didn't understand in a very efficient way. 

**Not using AI for some things**
I deliberately wrote the TF-IDF maths before asking AI to comment on it. This was because the formula was a concept the lectures emphasised and I wanted to be sure the implementation was one I had done and relevant to the module theory. AI feedback afterwards confirmed the formula and pointed out optimisations (starting the AND intersection from the smallest posting list) that I added with full understanding of why.

**Ethical note**
I used the University's secure Copilot access for privacy reaosns, per the brief's guidance. I did not paste the brief itself or any course material into a third-party service. I used Claude for more general questions about the coursework.

**How did debugging AI-generated code differ from debugging my own?**
The two felt very different. When debugging code I wrote myself, I usually have a mental note of why I made each choice so when something fails, my first instinct is to ask myslef which assumption was wrong. The saech space is then small because I know what I was assuming. With ai-generated code, I didn't have this. The robots.txt test failure failed with "Connection refused by Responses", this to me read as a network-mock issue. It took several minutes of reading to realise the real cause was that the production code mixed two HTTP libraries ('urllib' for robots.txt, 'requests' for everything else) and the test mock only intercepted one of them. I wouldn't have written that mismatch myself because if I'd have written '_load_robots()' from scratch I'd have used the same library I'd already chosen for the rest of the crawler. Reading the generated code, the inconsistency wasn't visable because each piece in isolation looked correct. Debugging my own code usually mean checking my own assumptions but debugging AI-generated code was more like reverse-engineering and reconstructing what the AI was thinking before I could identify what was wrong. This was slower and for certain bugs led me to rewrite rather than patch.

---