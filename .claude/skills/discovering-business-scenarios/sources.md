# Sources

## Agent design

- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents — progressive disclosure, note-taking, self-managed context
- https://anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills — Skills architecture
- https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them — when multi-agent wins; context pollution and isolation
- https://fountaincity.tech/resources/blog/anthropic-multi-agent-blueprint-production/ — subagent contract (objective, format, tools, boundaries); effort scaling; token cost
- https://www.newsletter.swirlai.com/p/state-of-context-engineering-in-2026 — tiered loading, compression, routing
- https://www.ayautomate.com/blog/context-engineering — context rot and context collapse; ACE (ICLR 2026) itemized incremental updates
- https://generativeprogrammer.com/p/skill-authoring-patterns-from-anthropics — skill authoring patterns, tool scoping
- https://docsalot.dev/blog/skill-md — SKILL.md size discipline, three-tier loading

## Agent code comprehension

- https://www.softwareseni.com/cutting-legacy-reverse-engineering-time-by-66-with-ai-code-comprehension/ — multi-pass enrichment; hallucination and context-poisoning risks
- https://zylos.ai/research/2026-04-19-codebase-intelligence-repository-understanding-ai-agents — agentic search vs index-first; keyword search ≈90% of RAG performance
- https://anthonywest.co.uk/research/code-intelligence-indexing-2026-openai — tree-sitter knowledge graphs, token/tool-call reductions
- https://arxiv.org/html/2606.26979v1 — CodeAnchor: static structure tags for grep-first agents (ISSTA 2026)

## Clarification behavior

- https://arxiv.org/abs/2603.26233 — *Ask or Assume?* uncertainty-aware clarification; decoupling detection from execution
- https://arxiv.org/pdf/2604.14624 — CLARITI: reward-driven clarification; relevance and answerability, fewer questions
- https://arxiv.org/html/2605.07937v1 — clarification timing; LHAW and HiL-Bench penalize over-asking and missed escalation
- https://aclanthology.org/2026.findings-acl.441.pdf — underspecification in prompts (ACL 2026 findings)

## Business rule recovery

- https://medium.com/@meirgotroot/from-code-to-business-logic-and-back-again-35db6468a2e0 — rules scattered across layers; actor/precondition framing
- https://nrc-publications.canada.ca/eng/view/accepted/?id=27ccebda-2a5d-4d12-b983-e81270f6817c — Putrycz & Kark, business rule recovery from legacy source

## Domain discovery

- https://www.avanscoperta.it/en/eventstorming/ — EventStorming formats
- https://www.qlerify.com/post/event-storming-the-complete-guide — hotspots; bounded contexts from language mismatch
- https://www.sebastianmalaca.com/event-storming-big-picture-the-big-picture-workshop-explained-part-1/ — workshop mechanics

## Journeys and gaps

- Jeff Patton, *User Story Mapping* (O'Reilly, 2014) — backbone, walking skeleton, walking the map
- https://www.smaply.com/blog/customer-journey-map — handoffs and systemic gaps
- https://creately.com/guides/service-blueprint-vs-journey-map/ — journey map vs service blueprint

## Rules and examples

- https://alistairmavin.com/ears/ — EARS patterns and ruleset
- https://en.wikipedia.org/wiki/Easy_Approach_to_Requirements_Syntax — origin, clause structure
- https://medium.com/@mattwynne/introducing-example-mapping-42ccd15f8adf — Example Mapping
- https://cucumber.io/docs/bdd/example-mapping/ — card taxonomy, readiness heuristics

## Requirement quality

- https://arxiv.org/pdf/1611.08847 — Femmer et al., requirements smells derived from ISO/IEC/IEEE 29148
- https://arxiv.org/pdf/2501.04810 — Frattini et al., catalog of requirements quality indicators

## Elicitation

- https://www.iiba.org/knowledgehub/business-analysis-body-of-knowledge-babok-guide/4-elicitation-and-collaboration/ — BABOK prepare / conduct / confirm
- https://www.watermarklearning.com/blog/babok-techniques/ — interviews, observation/shadowing, surveys

## Downstream

- https://thebcms.com/blog/spec-driven-development — spec as source of truth; brownfield progressive adoption
- https://www.augmentcode.com/guides/what-is-spec-driven-development — verifiable acceptance criteria as validation gates
