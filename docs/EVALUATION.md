# Evaluation results

Snapshot of the committed baseline (`eval/baseline.json`, blessed run `20261113T120346Z-f299518`, compare run `20261113T134349Z-f299518`). Regenerate with `./run.sh eval report 20261113T120346Z-f299518` and copy to this file.

> A refusal threshold (`REFUSAL_THRESHOLD=0.7`) was added after this run; it only affects the out-of-scope negative questions, which are excluded from the RAGAS aggregates below. The negative table therefore reflects the pre-threshold run and will be refreshed on the next eval run.

> Headline numbers in the README use the **baseline mean** of the two blessed runs (e.g. 0.882 faithfulness); the "Overall" table below is for this single run (0.903).

# Evaluation run 20261113T120346Z-f299518

_Generated 2026-11-13T13:42:34+00:00. Scores describe this machine, this generator (`google/gemma-4-e4b`) and this judge (`qwen/qwen3.5-9b`); they are not comparable to a hosted model or a different judge._

- Questions scored: **30**
- RAGAS: `0.4.3`
- Retrieval: `top_k=5`, `similarity_threshold=0.6`
- Collection: `f1-regs`

## Overall

| Metric | Mean | Median | Scored | Failed | Std dev |
|---|---|---|---|---|---|
| faithfulness | 0.903 | 1.000 | 30 | 0 | 0.193 |
| context_recall | 0.906 | 1.000 | 30 | 0 | 0.236 |
| context_precision | 0.867 | 1.000 | 30 | 0 | 0.290 |
| answer_correctness | 0.781 | 0.774 | 30 | 0 | 0.130 |

### By difficulty

| Group | n | faithfulness | context_recall | context_precision | answer_correctness |
|---|---|---|---|---|---|
| easy | 10 | 0.855 | 0.900 | 0.892 | 0.830 |
| hard | 8 | 0.836 | 0.821 | 0.800 | 0.659 |
| medium | 12 | 0.987 | 0.967 | 0.892 | 0.821 |

### By section

| Group | n | faithfulness | context_recall | context_precision | answer_correctness |
|---|---|---|---|---|---|
| A | 5 | 0.911 | 1.000 | 0.983 | 0.724 |
| B | 7 | 0.929 | 1.000 | 1.000 | 0.798 |
| B,C | 1 | 1.000 | 1.000 | 1.000 | 0.731 |
| C | 4 | 0.812 | 0.750 | 0.625 | 0.843 |
| D | 3 | 0.842 | 0.889 | 1.000 | 0.782 |
| D,E | 1 | 0.833 | 0.500 | 0.200 | 0.741 |
| E | 3 | 0.949 | 0.667 | 0.678 | 0.780 |
| F | 6 | 0.929 | 1.000 | 0.894 | 0.780 |

## Retrieval and citations

| Check | Value |
|---|---|
| Clause recall | 0.819 |
| Answers with a citation | 0.267 |
| Citations that resolve | 1.000 |
| Answers with a resolved citation | 0.267 |
| Cited sources / returned sources | 0.288 |
| Sources per answer | 4.97 |
| Latency mean (s) | 77.1 |
| Latency median (s) | 81.7 |

## Negative questions (out of scope)

_These three questions were scored before the refusal threshold was added; with `REFUSAL_THRESHOLD=0.7` in place they are expected to return no sources and pass._

| Question | Result | Sources | Invented citation | Reason |
|---|---|---|---|---|
| Q31 | FAIL | 5 | no | returned sources without refusing |
| Q32 | FAIL | 5 | no | returned sources without refusing |
| Q33 | FAIL | 5 | no | returned sources without refusing |

## Lowest-scoring answers

| Question | Difficulty | Answer correctness | Weakest | Answer |
|---|---|---|---|---|
| Q30 | hard | 0.562 | context_precision (0.200) | **When the Breach Arises:** A "Material Overspend Breach" arises when: 1. The Power Unit Manufacturer submits its Full Year Reporting Documentation and the Relevant Costs reported … |
| Q28 | hard | 0.583 | answer_correctness (0.583) | The following explanation is based on the provided excerpts: **Activity Qualifying for Shutdown Exception:** * Work on a test bench or computer resource qualifies as an exception i… |
| Q2 | easy | 0.615 | answer_correctness (0.615) | When at least 75% of the Scheduled Race Distance has been completed, the winner is awarded 25 points [1]. This determination is based on: * The leader having completed 75% or more … |
| Q26 | hard | 0.619 | answer_correctness (0.619) | Based on the provided excerpts, here is the analysis: **Breach Classification** The breach is classified as a **Material Overspend Breach**, because the Relevant Costs have been de… |
| Q21 | hard | 0.623 | faithfulness (0.556) | Based on the provided regulations, here is the explanation: The Race points column that applies when the leader has completed 40% of the Scheduled Race Distance is **Column 2** [So… |

## Baseline

Compared with baseline run `20261113T120346Z-f299518`.

| Metric | Baseline | This run | Delta | Noise | Verdict |
|---|---|---|---|---|---|
| faithfulness | 0.882 | 0.903 | +0.021 | 0.041 | within noise |
| context_recall | 0.906 | 0.906 | +0.000 | 0.000 | within noise |
| context_precision | 0.867 | 0.867 | +0.000 | 0.000 | within noise |
| answer_correctness | 0.775 | 0.781 | +0.006 | 0.012 | within noise |
