# Three-repeat replication: what changed and what held

The same 18 labelled cases were run three times per architecture on source commit `334034e`: 54 trials each, `gpt-6-astra` at medium reasoning, paired order shuffled with seed 42. No labels were changed after seeing outputs. There were no provider errors and no rate-limit retries.

| Measured result | Single | Staged |
|---|---:|---:|
| Final decision checks passed | **54/54** | 47/54 |
| Raw draft checks passed, before guardrail | **54/54** | 42/54 |
| Exact approval set | 54/54 | 52/54 |
| Correct next action | 54/54 | 49/54 |
| Human review preserved | 54/54 | 54/54 |
| Mean latency (± sd) | **16.3 s ± 1.5** | 28.5 s ± 2.0 |
| Indicative cost per request | **$0.152** | $0.222 |

## The single agent did not vary

Every single-agent trial passed both the raw-draft and final checks. On a set this small, that consistency is more informative than the pass rate itself: across three independent runs, the single agent never needed a guardrail correction.

## The staged reviewer is systematically more sceptical about overlap

All seven staged failures come from one behaviour. When a request overlaps an existing catalog tool, the reviewer prefers to verify spare capacity on that tool before anything else, even when the request also needs specialist reviews.

- **SYN-17, all three repeats.** For DocSpace with employee PII, it chooses "check the existing tool first". Security and Privacy are kept every time; the label requires the reviews to start first.
- **PUB-03, two of three repeats.** For the CodeMate source-code expansion, it asks whether the existing 120 seats already cover the two squads. Security review is kept. In the third repeat it chose to route for reviews, as labelled.
- **PUB-02, two of three repeats.** Its next action is acceptable, but it adds a Privacy review because the vendor processes personal data, even though this request only touches internal marketing data. The guardrail keeps the extra approval by design: it adds approvals the model misses and never removes ones the model adds.

The reasoning in each case is defensible, and no failure removed a required control. But the label encodes the policy's order of work, and the staged design departs from it repeatably, not at random.

## The review order is now a policy rule

The policy engine originally allowed both orders when reviews and overlap coexisted, so the guardrail could not catch the staged choice. That was a gap in the policy layer. The order is now explicit in `config/policy.toml`: specialist reviews start first, and the existing-tool question runs alongside them.

[Replaying](replay.md) the saved drafts through the updated guardrail, without any model or tool calls, changes five staged trials from fail to pass: SYN-17 in all three repeats and PUB-03 in two. Staged's final score becomes 52/54; single stays at 54/54. The two remaining failures are the extra Privacy reviews on PUB-02, which the guardrail keeps by design. Raw-draft scores are unchanged at 54/54 and 42/54, because the drafts are the originals.

## Comparison with the first experiment

The first run, one repeat on the earlier source, scored single 18/18 and staged 17/18. The replication shows that this understated the gap. Staged passed PUB-03 in the first run but failed it in two of three repeats here. Latency was lower for both designs in this run (16.3 s against 22.5 s for single), which reflects provider load on the day; the relative gap, about 43% in favour of single, is similar.

## Limits

The cases are developer-labelled, and most test rules the code already enforces. Three repeats measure consistency, not independent sample size. The judgement the staged reviewer applies, "check capacity before buying", is a reasonable procurement instinct; whether it should outrank starting the specialist reviews is a question for the procurement owners, not something this test set can settle.
