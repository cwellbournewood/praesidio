# Market Research & Positioning

## What's in the market (as of mid-2026)

The "AI security" category is genuinely new — the first specialist vendors
appeared 2022-2023, and the category is still being shaped. Buyers
typically evaluate Section-shaped solutions alongside the following:

### 1. Enterprise-platform plays (existing DLP/CASB players extending into AI)

| Vendor | Strengths | Gaps Section addresses |
|---|---|---|
| **Microsoft Purview (incl. Insider Risk + Defender for Cloud Apps AI Hub)** | Deep M365 integration, identity (Entra), classification at scale, certified for many regs | Generally Microsoft-shop only; coverage of non-Azure LLMs and OSS agent frameworks is shallower; policy is clickops in Compliance Manager |
| **Netskope GenAI Security** | Strong CASB/SWG inline position; large catalogue of AI apps | Mostly traffic-level controls; semantic + reversible anonymisation is shallow |
| **Zscaler AI Protection** | Inline at the proxy layer; existing footprint | Same — strong on inventory and coarse blocking, lighter on semantic transforms |
| **Palo Alto AI Access Security** | NGFW + Prisma; identity-aware | Similar profile; ecosystem-coupled |
| **Cisco AI Defense (ex-Robust Intelligence acquisition)** | Strong red-team / model-eval pedigree | Pre-deploy model evaluation focus; runtime DLP for prompt traffic is one of several modes |

These are the natural incumbents. Their advantage is distribution; their
gap is that AI semantic DLP and agent governance is bolted onto a CASB,
not the architectural centre.

### 2. AI-native specialists

| Vendor | Niche |
|---|---|
| **Lakera (Guard, Red)** | Prompt-injection focus; classifier APIs; AI red-teaming |
| **Protect AI (Guardian, Rebuff, NB Defense)** | MLSecOps for the model lifecycle; OSS-adjacent (acquired several OSS tools) |
| **Prompt Security** | Browser extension + proxy for "shadow AI"; quick wins on visibility |
| **Nightfall AI** | Started in SaaS DLP, now strong on AI prompt DLP; entity-rich detectors |
| **CalypsoAI** | Enterprise LLM control plane; close to the Section category, leans heavier on classifier-driven scanning |
| **WitnessAI** | Identity-centric LLM observability + DLP; close adjacency |
| **Hidden Layer** | Adversarial ML detection; model-side focus |
| **Robust Intelligence** | (Now Cisco) — pre-deploy + runtime guardrails |

### 3. Open-source projects we live alongside (and integrate with)

| Project | What it is | How Section relates |
|---|---|---|
| **Microsoft Presidio** | PII detection & anonymisation library | **Used directly** as one detector lane |
| **NVIDIA NeMo Guardrails** | Programmable rails (Colang) embedded in apps | Different design point — guardrails in the app code vs. a gateway. Complementary. |
| **Guardrails AI (guardrails-ai)** | Structured-output validation library | Complementary; used in-app, not at the network edge |
| **LLM-Guard** (Laiyer / Protect AI) | Prompt input/output scanner; OSS | Overlap on detection; Section adds policy engine, gateway, audit chain, agent broker |
| **LiteLLM** | Multi-provider proxy | Adjacent — Section's provider adapters serve a similar purpose but with policy/DLP first |
| **OPA / Gatekeeper** | Policy engine for K8s/services | Influence on policy-as-code; we use CEL instead of Rego for the gateway's hot path |

## Where Section wins

1. **Drop-in OpenAI/Anthropic compatibility**. Existing SDKs work by
   changing one env var. Most specialists ask for SDK integration; most
   incumbents need their entire stack.
2. **Reversible-by-default anonymisation**. Per-finding choice of
   tokenise / FPE / redact. Most tools redact only, which kills answer
   quality.
3. **Genuine open source under Apache 2.0**. Forkable, auditable,
   self-hostable, air-gappable. Most specialists are closed-source SaaS.
4. **Policy-as-code in git**. Diff-reviewable, CI-checked, signed bundles.
   The standard incumbent UX is clickops in a console.
5. **Cryptographic audit chain**. Few competitors offer tamper-evident
   logs out of the box.
6. **Designed for the agent era, not just chat**. Tool-call allowlist
   enforcement ships today; capability tokens, signed MCP manifests,
   and sandboxed tool execution are architected up front rather than
   retrofitted.
7. **Light-first, calm UI**. Most competitor UIs are dark dashboards
   with threat-hunter chrome; an analyst spending a day in Section
   finds it less fatiguing.

## Where we deliberately don't compete

- **Model evaluation / red-teaming** is its own market and we link to it
  rather than reproduce it. (HiddenLayer, Lakera Red, Cisco AI Defense.)
- **MLSecOps for training pipelines** (Protect AI Guardian) — out of
  scope; we're inference-time.
- **Endpoint browser extensions** as a primary delivery — we ship a
  reference one but the centre of gravity is gateway-side.

## Reference benchmarks

| Capability | Section | Typical incumbent | Typical specialist |
|---|---|---|---|
| OpenAI-compatible surface | ✅ | ❌ | mixed |
| Reversible tokenisation w/ vault | ✅ | rare | mixed |
| FPE per entity | ✅ | rare | rare |
| Policy as code (git) | ✅ | ❌ | rare |
| Cosign-signed bundles | ✅ | n/a | rare |
| Hash-chained audit | ✅ | rare | rare |
| Air-gapped install | ✅ | rare | rare |
| Apache-2.0 OSS | ✅ | ❌ | ❌ (mostly) |
| Tool-call allowlist enforced | ✅ | ❌ | emerging |
| Agent capability tokens | architected | ❌ | emerging |
| MCP-aware | architected | ❌ | emerging |

## Buyer personas and their first question

| Persona | First question | Section's answer |
|---|---|---|
| CISO | "Will this stop our IP leaving on a prompt?" | DLP + anonymisation + audit; live demo in 5 min via `bash scripts/demo.sh` |
| Data protection officer | "Show me GDPR Art. 30 evidence" | Audit export pack |
| Platform engineer | "How do I roll this out without breaking dev velocity?" | OpenAI-compatible drop-in + simulation mode + canary |
| SOC analyst | "How does this fit Splunk?" | Native HEC sink |
| Application owner | "Will my chatbot still work after you anonymise stuff?" | Reversible tokenisation; answer-quality benchmarks |
| AI engineer building agents | "Will this slow my tools down?" | Sub-millisecond fast-path DLP; tool-call allowlist enforced
