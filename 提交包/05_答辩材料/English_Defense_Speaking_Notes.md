# English Defense Speaking Notes

> Companion to `DefenseDeck_EN.pptx` (20 slides, 15 min presentation + 5 min Q&A)
> Purpose: the official rules grant a **2-point bonus** for presenting in English.
> The scoring also weights **fluency** — these notes are written to be spoken, not read.

---

# Timing Overview

| Section | Slides | Time |
|---|---|---|
| Opening & problem | 1–3 | 1.5 min |
| Overall design | 4–5 | 2 min |
| Knowledge graph construction | 6–10 | 3 min |
| MCP tools & Skill orchestration | 11–14 | 3 min |
| Knowledge base & data processing | 15 | 2 min |
| Live demonstration | 16 | 2.5 min |
| Capability accumulation & closing | 17–20 | 1 min |

**Target: finish at 14:30** — leave 30 seconds of buffer.

---

# Slide-by-Slide Speaking Notes

## Slide 1 — Cover

> Good morning. Thank you for the opportunity to present.
>
> Our project is called **Evidence-Chained Pulmonary Nodule Management**.
> In one sentence: we make clinical guidelines **executable and auditable**
> at the point of care.

*(Move on quickly — do not linger on the cover.)*

---

## Slide 2 — The Problem

> Let me start with a real scene.
>
> A physician at a county hospital is on her 37th patient of the morning.
> On screen: a structured CT report for an 8-millimetre mixed ground-glass nodule.
> She knows the 2024 consensus says what to do — but she has three minutes,
> and the guideline is fourteen pages of prose.
> **Get the follow-up interval wrong, and she is accountable.**
>
> This is not a detection problem. Imaging AI already finds nodules.
> It is not an accuracy problem either — large language models perform well here.
> The real gap is **between detecting a nodule and deciding what to do**:
> there is no evidence chain a physician can follow and cite.
>
> Three facts, and their consequences:
> Imaging AI stops at the screening report — it does not say what to do next.
> Guidelines say what to do — but they are prose, not computable.
> LLMs answer accurately — but their answers are not auditable.

---

## Slide 3 — A Shared Gap

> And this is not a niche problem.
>
> Healthcare, finance, manufacturing and public services all share the same
> document structure: **clause-based rules, threshold conditions, and actions**.
> A credit policy is explicit — but no relationship manager can check every deal
> clause by clause. An equipment manual has procedures — but nobody opens it
> during a fault.
>
> So our contribution is not "a pulmonary nodule agent".
> **It is a reproducible pipeline from industry documents to executable knowledge**,
> validated end-to-end in one high-value scenario.

---

## Slide 4 — Overall Design

> Our system has four layers.
>
> At the application layer: an agent for county hospitals and community clinics.
> At the platform layer, we build on **Nexent** — the agent runtime,
> knowledge-base retrieval, the MCP ecosystem, and tiered memory.
>
> On top of that platform, we added what it did not provide:
> a **domain ontology**, a **knowledge graph with multi-hop reasoning**,
> **clause-level provenance**, **six MCP tools**, and **Skill orchestration**.
>
> The key design decision: **we did not rebuild retrieval.**
> Nexent already provides hybrid retrieval with reranking.
> We added structured reasoning where the platform had a gap.
> That is what we mean by a **dual retrieval–reasoning drive**.

---

## Slide 5 — Capability Attribution

> I want to be explicit about what is ours and what is the platform's.
>
> Left column — Nexent provides the agent runtime, retrieval,
> citation at the knowledge level, the MCP ecosystem, and memory.
>
> Right column — we developed the ontology, the knowledge graph,
> the reasoning engine, clause-level provenance, the six MCP tools,
> the Skill orchestration, and the ontology construction algorithm.
>
> **Platform capability plus our increment gives the dual drive.**

---

## Slide 6 — The Low-Resource Challenge

> Now the core technical work: building the knowledge graph.
>
> Three challenges define the "low-resource" setting.
>
> **First**, there is no public standard ontology for this domain.
> General ontologies like SNOMED are broad, but they do not have
> a "guideline clause" layer.
>
> **Second**, manual construction is prohibitively expensive — at roughly
> 90 seconds per triple, one consensus document takes over three hours
> of expert time.
>
> **Third**, guidelines evolve. The consensus was revised between 2024 and 2025.
> A static knowledge base cannot absorb that.

---

## Slide 7 — Three-Layer Pipeline

> Our answer is a three-layer pipeline.
>
> **L1** is a manually defined seed ontology — 52 classes and 5 relations.
> This gives the extraction an **alignment target** rather than letting
> the model run free.
>
> **L2** performs constrained extraction: clause splitting, entity and relation
> extraction, then **forced alignment**. Anything that cannot align to the seed
> ontology is not stored.
>
> **L3** is the human review loop. Unaligned concepts enter a candidate pool;
> after review the ontology is extended and the version increments.
> **That is how "evolvable" is actually implemented.**

---

## Slide 8 — Key Code 1

> Now the two most important pieces of code.
>
> This first one is not a parsing trick — **it is a safety mechanism.**
>
> Recommendation 14 contains a qualifier: if the nodule enlarges,
> *consider resection rather than non-surgical biopsy*.
> If you extract the whole paragraph, you attach "surgical resection"
> to a follow-up recommendation. **That automates overtreatment.**
>
> Our fix: split each clause into a **main recommendation** and its **caveats**,
> using marker phrases. Actions are extracted **only** from the main sentence.
> Contraindications inside caveats are extracted separately as
> `contraindicatedFor` relations.
>
> The table shows the result: before, Recommendation 14 yielded four actions
> including surgical resection; after, it correctly yields CT follow-up,
> MDT consultation, a CAC test, and thin-slice CT.

---

## Slide 9 — Key Code 2

> The second piece is smaller but had a large effect.
>
> Risk-factor extraction was pure keyword matching — so
> **"no smoking history" was counted as "smoking history"**.
>
> Recommendations 10 and 11 differ **only** by risk-factor presence,
> so this error routed patients to the wrong clause.
>
> The fix: a negation check within a six-character window before the keyword,
> plus a global "no risk factor" list.
>
> **The clause hit rate went from 82.2% to 100%.**

---

## Slide 10 — Quantitative Results

> Here is the quantitative result across three real public guidelines.
>
> Across 40,799 cleaned characters we identified 32 clauses,
> extracted 156 object triples, and achieved **100% ontology alignment**
> with a **zero percent human intervention rate**.
>
> But the number I want you to notice is this:
> **the ontology was designed on the 2024 consensus, yet processed the other
> two documents without any modification.**
> Those two documents were never used in the design — they are a clean hold-out.
> That is direct evidence of generalisation.
>
> For comparison: fully manual construction would take about 3.02 hours.
> Ours takes seconds.

---

## Slide 11 — MCP Tools

> We expose the knowledge graph as an MCP server with six tools.
>
> The core one is `kg_consult_decision`. You give it a natural-language
> clinical description, and it returns a multi-hop reasoning chain,
> clause-level provenance, contraindication checks, and referral tier.
>
> The other five support concept normalisation, clause lookup, feature-based
> retrieval, ontology overview, and listing capabilities.
>
> **All six tools are registered on the platform and mounted on the agent —
> visible in the interface.**

---

## Slide 12 — MCP Protocol Issue

> This slide is about a real problem we hit at the protocol layer.
>
> Calling the MCP endpoint between containers returned **HTTP 421
> Misdirected Request**.
>
> The root cause: **FastMCP 2.x enables DNS-rebinding protection by default**,
> trusting only localhost — so intra-container calls were rejected.
> The fix is to configure the transport security settings explicitly.
>
> I show this because it demonstrates we did not merely "call MCP" —
> we understood its implementation well enough to diagnose a protocol-level issue.
>
> We also discovered a platform mechanism worth noting:
> **MCP tools are not registered automatically.** After adding a server you must
> trigger a scan through the API.

---

## Slide 13 — Skill Orchestration

> Our Skill has three layers: facts, reasoning, and evidence.
>
> The facts layer extracts structured patient facts.
> The reasoning layer matches the ontology, locates the clause, expands actions,
> and checks contraindications.
> The evidence layer re-checks the original clause text.
>
> On the right is the interface evidence I want to highlight.
> The agent says, on its own: *"There's a skill: lung-nodule-decision.
> Must load it first."* — and then **executes `read_skill_md`**.
>
> That is Nexent's **progressive skill disclosure** working:
> skill metadata stays in context for matching; the full content is loaded
> only on a hit. And it proves the Skill is genuinely in effect —
> not just attached.

---

## Slide 14 — Three-Layer Refusal Mechanism

> This is the safety core of the project, and it comes with a story.
>
> Refusal needs three layers to work. The **engine layer** evaluates coverage and
> returns `NOT_COVERED`. The **orchestration layer** enforces in the prompt that
> the agent must ask when key facts are missing. The **presentation layer**
> renders the clarification.
>
> We tested the question *"I have a pulmonary nodule, what should I do?"* —
> with no diameter given.
>
> **The system made 18 tool calls, spent 59 seconds, and produced 2,728
> characters trying to answer anyway.**
>
> We traced it: the engine *could* refuse — but the orchestration prompt
> contained no "must ask first" constraint.
>
> After the fix: **zero tool calls, 3.5 seconds, replaced by a structured
> clarification form** asking for diameter, density type, and risk factors.
>
> I tell this story because finding, locating, fixing and quantifying a defect
> is stronger evidence than simply claiming a safety feature exists.

---

## Slide 15 — Knowledge Base and Data Processing

> On the knowledge base: it is an Elasticsearch index with 17 chunks,
> using BGE-M3 embeddings, and it supports three retrieval modes.
> Expansion is trivial — upload a document and it is chunked and vectorised
> automatically.
>
> But the more interesting work was **data processing**.
>
> When we extracted the guidelines from Word, they contained **Zotero citation
> metadata** — `ADDIN ZOTERO_ITEM CSL_CITATION` blocks with full English
> abstracts. In the 2025 consensus, **89% of the raw characters were pollution**.
>
> The difficulty: that JSON has **nested braces**, so regular expressions
> cannot pair them reliably. We wrote a brace-matching scanner that also tracks
> string and escape state.
>
> **The Chinese-character ratio went from 8.5% to 72.2%.**
> And we verified the body text survived — the clause counts match the official
> figures exactly.
>
> On compliance: **no real patient data is used.** All knowledge comes from
> published guidelines. The evaluation set is generated from clause applicability
> ranges, with the clause number itself as the machine-checkable gold standard.

---

## Slide 16 — Live Demonstration

> Let me show you the system working.
>
> *(Switch to browser. Paste question 1.)*
>
> This is a typical case: 8-millimetre mixed ground-glass nodule, 2-millimetre
> solid component, 30-year smoking history.
>
> Watch the Reasoning panel on the right. The agent first calls
> `kg_consult_decision` to reason and locate the clause, then `kg_get_clause`
> to expand it, then `knowledge_base_search` to retrieve the original text.
> **Reason first, then retrieve** — that is the dual drive.
>
> *(Paste question 2.)*
>
> Now an insufficient-information question. Notice it does **not** answer —
> it renders a clarification form.
>
> *(Paste question 3.)*
>
> And here it correctly identifies that PET-CT is contraindicated because the
> solid component is under 8 millimetres.

*(If the network fails, play the recording and narrate over it.)*

---

## Slide 17 — Capability Accumulation

> Finally, on generalisability.
>
> We ran the **same code skeleton** on two domains: healthcare, using a real
> public guideline, and finance, using a sample corpus.
> **The skeleton did not change.** We only replaced the seed ontology,
> the corpus, the term lexicon, and the numeric patterns.
>
> We also discovered a mechanism worth reporting:
> **extraction volume is bounded by seed-ontology expressiveness.**
> The same consensus, the same 18 clauses — the production ontology with
> 52 classes yields 110 triples, while the migration template with 14 classes
> yields 47. The difference comes only from ontology granularity.
>
> The practical implication: when migrating, start with a compact ontology to
> get the skeleton working, then refine. Gains in extraction volume should come
> from ontology refinement, not from the extraction algorithm.
>
> One honest disclosure: no public credit-review standard exists, so the finance
> domain uses a sample corpus. **We validate the pipeline's domain-independence —
> we do not claim that finance reaches the same validation depth as healthcare.**

---

## Slide 18 — Evaluation and Boundaries

> On evaluation: 68 test cases across six categories — coverage sampling,
> boundary values, refusal, contraindication, referral, and clinically common
> values.
>
> Results: **100% clause hit rate, 100% traceability, 100% refusal accuracy,
> 94.1% coverage.**
>
> But I want to be equally clear about what this does **not** prove.
> It does not prove clinical effectiveness — that needs real clinical data and
> ethics approval. It does not prove safety — that needs prospective studies.
> The cases are still constructed, not real.
>
> **This is a clause-consistency test, not a clinical-effectiveness trial.**

---

## Slide 19 — Controlled Comparison: Bare LLM vs Our System ★

> Everything so far has been our own evaluation. This slide answers a more
> fundamental question: **couldn't you just ask a large language model?**
>
> We ran a controlled experiment. The same six clinical questions, routed two ways.
> On the left, a bare LLM — DeepSeek-V3 — with a system prompt that only says
> "you are a respiratory physician". **No knowledge base, no graph, no tools, no
> guideline text.** On the right, our full system.
>
> Three numbers matter.
> **Clause-level citations: zero out of six, versus six out of six.**
> **Expected Chinese-consensus clause: zero, versus six.**
> And when the question lacks essential information, **the bare model answers
> anyway — ours asks.**
>
> Let me give you the most telling example. A 15-millimetre mixed ground-glass
> nodule. The bare model recommends **thoracoscopic surgical resection**.
> The Chinese consensus requires **a repeat CT at three months first**.
>
> And here is why that matters. A meta-analysis of 26 studies reports
> **31% overdiagnosis for part-solid nodules — and 38% in Asian populations.**
> Another study found that **37.1% of resected lesions in the direct-LDCT group
> were adenocarcinoma in situ or atypical adenomatous hyperplasia** —
> in other words, removed when they need not have been.
>
> **This case is a part-solid nodule in an Asian patient.** The bare model's
> recommendation points exactly where the literature warns against.
> Two independent lines of evidence — one API call, one meta-analysis —
> converge on the same conclusion.
>
> I should add one honest caveat: **the bare model is not simply wrong.**
> In one scenario it cited the Chinese guideline correctly and appropriately
> flagged that PET-CT was not indicated. **What we demonstrate is a difference
> in verifiability, in guideline consistency, and in asking behaviour —
> not a difference in "knowledge".**
>
> So our contribution is not "better than an LLM". It is **turning a
> professional-sounding answer into an evidence chain that can be verified,
> audited, and traced to a clause.**

*(This is the highest-value slide in the deck. Speak slowly, and pause after
each number.)*

---

## Slide 20 — Summary

> To summarise.
>
> We built a reproducible pipeline from industry documents to executable
> knowledge, and validated it end-to-end in one high-value scenario.
>
> On generalisability: we ran the same code skeleton on healthcare with a real
> public guideline, and on finance with a sample corpus. **The skeleton did not
> change.** We also discovered a mechanism worth reporting — extraction volume
> is bounded by seed-ontology expressiveness.
>
> One honest disclosure: no public credit-review standard exists, so the finance
> domain uses a sample corpus. **We validate the pipeline's domain-independence —
> we do not claim that finance reaches the same validation depth as healthcare.**
>
> Three reusable outputs: a semi-automated ontology construction algorithm
> achieving 100% alignment with zero human intervention; a self-developed
> knowledge-graph MCP service with six tools and clause-level provenance;
> and a domain-agnostic workflow template validated in two industries.

---

## Slide 21 — Thank You

> Thank you. We welcome your questions.

---

# Prepared Q&A (English)

## Q1: What is your innovation compared with just asking an LLM?

> We ran a controlled experiment — it is on slide 19.
>
> The same six clinical questions, routed two ways: a bare DeepSeek-V3 with
> no knowledge base, no graph and no tools, versus our full system.
>
> **Clause-level citations: 0/6 versus 6/6. Expected Chinese-consensus clause:
> 0/6 versus 6/6. Disclaimers: 0/6 versus 6/6.** And when the question lacks
> essential information, **the bare model answers anyway; ours asks.**
>
> The most telling case: a 15-mm mixed ground-glass nodule. The bare model
> recommends thoracoscopic resection; the Chinese consensus requires a repeat
> CT at three months first. And the literature reports 31% overdiagnosis for
> part-solid nodules, 38% in Asian populations.
>
> **But I should be honest: the bare model is not simply wrong** — in one
> scenario it cited the Chinese guideline correctly. What we demonstrate is a
> difference in **verifiability, guideline consistency, and asking behaviour**.

## Q2: Where did the 57 ontology classes come from? Did clinicians participate?

> Honest answer: the classes come from a systematic review of the guideline
> clauses, not from invention. We defined a seed ontology manually based on the
> consensus structure, then added five refined classes.
> **We did not have deep clinical-expert involvement — that is a limitation.**
> But the design includes a human review loop with a candidate pool, so in
> deployment a clinician could review additions.

## Q3: How do you guarantee the extracted knowledge is correct?

> Three safeguards. **Forced alignment** — extracted concepts must align to the
> seed ontology or they are discarded. **Traceability** — every triple records
> which clause it came from. **Refusal** — if alignment fails, the system
> declines rather than inventing.
> Quantitatively: 100% alignment across three documents with zero human
> intervention.

## Q4: Why not use Neo4j? Why write your own graph service?

> It was a deliberate choice under a platform constraint. Nexent pins
> `neo4j`, `chromadb` and similar dependencies to a sentinel version, so they
> cannot be installed. Rather than working around the platform, we implemented
> a lightweight triple store exposed over MCP.
> **The constraint turned out to be an advantage** — the graph service became an
> independent, reusable component not tied to a specific graph database.

## Q5: You only did pulmonary nodules — how do you prove migration works?

> By experiment, not by claim. We ran the same code skeleton on healthcare with
> a real corpus, and on finance with a sample corpus. **The skeleton did not
> change.** We also analysed the shared document structure across four
> industries: clause-based rules, threshold conditions, and actions.
> And we disclose that finance uses a sample corpus — we validate skeleton
> reusability, not finance-domain depth.

## Q6: You built your own evaluation set — how is it objective?

> The gold standard comes from the clauses themselves, not from annotator
> judgement. For each case, the expected clause is explicitly stated in the
> consensus. The 68 cases span six categories, and the generation script ships
> with the code so anyone can regenerate them.
> But I must state the boundary: **this is a clause-consistency test, not a
> clinical-effectiveness validation.** It proves clause location, threshold
> decisions, traceability and refusal behaviour — not clinical outcomes.

## Q7: How is the PET-CT contraindication handled?

> It is a **conditional** contraindication, not keyword matching.
> The consensus says PET-CT is not recommended for mixed lesions with a solid
> component under 8 millimetres. The system matches that condition against the
> patient facts and states: *"PET-CT is not recommended for mixed lesions with
> a solid component ≤8 mm; in this case the solid component is 2 mm, so it falls
> within the contraindicated range."*
> In our 8-scenario validation, this warning appeared only in the correct
> scenarios — not for pure ground-glass or solid nodules.

## Q8: What is the response latency? Is it production-ready?

> Measured: a typical case averages 3.4 tool calls and 9.8 seconds; a
> clarification case takes 0 tool calls and 3.5 seconds.
> Currently it runs on a single-machine Docker Compose deployment with
> 13 containers. Production deployment would scale by hospital server
> specification.

## Q9: How does the system keep up when guidelines are revised?

> That is the "evolvable" design. A new document goes through automatic
> extraction and forced alignment. Aligned concepts enter the graph directly.
> Unaligned ones enter a candidate pool for human review; on approval the
> ontology version increments and everything is realigned.
> **The key metric is the unaligned rate — it should fall as the ontology
> matures, which is direct evidence of evolution.**

## Q10: Can the code reproduce what the slides show?

> Yes — and we prepared reproduction scripts.
> The knowledge pipeline runs in five steps from corpus cleaning to OWL export.
> Agent Q&A reproduces with a single command. The batch validation covers
> eight scenarios, and the self-evaluation runs 68 cases.
> All artefacts ship with the submission, with complete historical archives.

---

# Delivery Tips

| Tip | Why |
|---|---|
| **Speak slower than feels natural** | English at presentation pace reads faster to a Chinese-speaking audience |
| **Pause after each number** | Numbers are the evidence — let them land |
| **Point at the slide when citing data** | Keeps the audience oriented |
| **Say "we" not "I"** | It is a team project |
| **Rehearse the two code slides most** | They are the densest and carry the most marks |
| **Do not translate code identifiers** | `kg_consult_decision` stays as-is |

## Terminology Consistency

| Chinese | English (use consistently) |
|---|---|
| 肺结节 | pulmonary nodule |
| 混杂性磨玻璃结节 / mGGN | mixed ground-glass nodule (mGGN) |
| 纯磨玻璃结节 / pGGN | pure ground-glass nodule (pGGN) |
| 推荐意见N | Recommendation N |
| 分级诊疗 | tiered referral |
| 依据链 | evidence chain |
| 可溯源 | traceable / auditable |
| 强制对齐 | forced alignment |
| 拒答 | refusal |
| 本体 | ontology |
| 三元组 | triple |
