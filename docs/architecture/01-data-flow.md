# 01 · Data Flow

```
sequenceDiagram
    actor U as User / IDE / Agent
    participant G as Section Gateway
    participant ID as Identity Resolver
    participant PE as Policy Engine
    participant DLP as DLP Pipeline
    participant AN as Anonymiser
    participant V as Token Vault (Redis)
    participant MR as Model Router
    participant UP as Upstream LLM
    participant DE as De-anonymiser
    participant AU as Audit Writer
    participant PG as Postgres

    U->>G: POST /v1/chat/completions  (Bearer key, body)
    G->>ID: resolve(principal)
    ID-->>G: Principal{user,tenant,groups,country}
    G->>PE: build context
    PE-->>G: matched policy + enabled detectors
    G->>DLP: scan(body)
    par fast detectors
        DLP->>DLP: regex / secrets / code
    and nlp detectors
        DLP->>DLP: Presidio / NER
    and semantic detectors
        DLP->>DLP: embeddings / ONNX classifier
    end
    DLP-->>G: Findings[]
    G->>PE: evaluate(rules, ctx, findings)
    alt action = block
        PE-->>G: BLOCK{reason}
        G->>AU: write(blocked event)
        AU->>PG: INSERT (hash chained)
        G-->>U: 403  + policy reason
    else action = transform / allow
        PE-->>G: transforms[], upstream
        G->>AN: apply(transforms, body)
        AN->>V: store(placeholder → original) TTL
        AN-->>G: sanitised body
        G->>MR: route(upstream rule)
        MR-->>G: chosen upstream
        G->>UP: forward(sanitised body)  (streaming)
        loop SSE chunk
            UP-->>G: chunk
            G->>DE: restore placeholders
            DE->>V: lookup(placeholder)
            V-->>DE: original
            DE-->>G: restored chunk
            G-->>U: chunk
        end
        G->>AU: write(allow/transform event with digests)
        AU->>PG: INSERT (hash chained)
    end
```

(Render with any Mermaid renderer; GitHub renders this natively.)
