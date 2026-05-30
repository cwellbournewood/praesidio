# Kubernetes admission policy — Section LLM egress guard

This directory ships a defence-in-depth admission policy that blocks
Kubernetes workloads from bypassing the Section gateway. Specifically,
it denies the creation of any Pod that BOTH:

1. mounts a Secret whose name matches a cloud-credentials pattern
   (`aws-credentials`, `gcp-credentials`, `azure-creds`, …); AND
2. sets an environment variable whose value points at a known LLM
   provider hostname (`api.openai.com`, `api.anthropic.com`,
   `bedrock-runtime.<region>.amazonaws.com`, …).

The combination is the smoking gun for "this workload talks directly to
an LLM with cloud credentials in scope" — exactly the case that the
Section control plane is designed to govern. Workloads that legitimately
need both can opt out with the annotation
`section.dev/admission-bypass=true` (requires platform-admin RBAC).

## Two policy engines, pick one

### `ValidatingAdmissionPolicy` (Kubernetes ≥ 1.30, recommended)

Native to the API server, no additional controller required. CEL-based.

Files:

* `validating-admission-policy.yaml` — the `ValidatingAdmissionPolicy`
  and its `ValidatingAdmissionPolicyBinding`.

Install:

```bash
kubectl apply -f validating-admission-policy.yaml
```

Verify the binding is active:

```bash
kubectl get validatingadmissionpolicy section-llm-egress-guard
kubectl get validatingadmissionpolicybinding section-llm-egress-guard-binding
```

### Gatekeeper (older clusters, or operator preference)

Files:

* `gatekeeper-constraint-template.yaml` — the `ConstraintTemplate`
  (Rego).
* `gatekeeper-constraint.yaml` — the `SectionLlmEgressGuard` constraint
  instance.

Install (requires Gatekeeper already running):

```bash
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm upgrade --install gatekeeper gatekeeper/gatekeeper \
    -n gatekeeper-system --create-namespace

kubectl apply -f gatekeeper-constraint-template.yaml
# Wait for the template to be ingested before applying the constraint.
kubectl wait --for=condition=ready=true \
    constrainttemplate.templates.gatekeeper.sh/sectionllmegressguard \
    --timeout=60s
kubectl apply -f gatekeeper-constraint.yaml
```

## Cloud-specific notes

| Cluster | Notes |
|---|---|
| **EKS 1.30+** | `ValidatingAdmissionPolicy` is GA. No extra steps. |
| **GKE 1.30+** | GA on standard clusters; Autopilot supports both VAPs and Gatekeeper-style policies via Policy Controller. |
| **AKS 1.30+** | GA. If you use Azure Policy for Kubernetes (Gatekeeper-based), the constraint above can be installed under the `K8sCustomConstraintTemplate` flow. |
| **OpenShift 4.16+** | `ValidatingAdmissionPolicy` is GA. Or use the existing OPA Gatekeeper operator. |
| **kind / minikube** | Both work for local testing. CI uses kind, see `.github/workflows/admission.yml`. |

## Test fixtures

* `test/test-pod-allowed.yaml` — should be admitted (uses Section
  gateway base URL).
* `test/test-pod-blocked.yaml` — should be denied (direct OpenAI URL).

Local smoke test:

```bash
kubectl apply -f test/test-pod-allowed.yaml   # OK
kubectl apply -f test/test-pod-blocked.yaml   # error: Forbidden ...
kubectl delete -f test/test-pod-allowed.yaml --ignore-not-found
```

## Tuning per environment

* Add internal LLM hosts (private vLLM, Bedrock VPC endpoints) to the
  `llmHosts` variable when you want to enforce there too.
* Add team-specific cloud-cred secret prefixes to
  `credentialSecretPatterns`.
* Switch `failurePolicy: Fail` -> `Ignore` during staged rollout if you
  cannot tolerate API-server outages dropping the policy webhook.
* Use `validationActions: [Audit]` (omit `Deny`) initially to discover
  offenders without blocking them; flip to `[Deny, Audit]` after a
  burn-in.

## Limitations

* The policy looks at literal env-var values; a Pod that constructs the
  hostname at runtime (e.g. via a `valueFrom: configMapKeyRef`
  redirection) can evade it. Pair with NetworkPolicy / CNI FQDN egress
  rules for the airtight version.
* Sidecars added by mutating admission **after** validation are not
  inspected here. Run mutating webhooks first if needed.
