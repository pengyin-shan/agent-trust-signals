# Analysis summary (generated; numbers for draft filling)

Generated 2026-09-03T21:40:31.855936+00:00; Python 3.14.7; numpy 2.5.2; scipy 1.18.1; seed 202608211535.

## Execution
- Registered: 1920/1920 complete; infrastructure-incomplete 0; not run 0.
- Supplement: 194/216 complete; incomplete cells 8.
- Ledger rows 2114; complete trials without ledger row 0; ledger rows without trial 0.
- Hosted spend 100.59 USD against cap 100.00; cap exceeded: True.
- First trial 2026-08-30T20:55:59Z; last 2026-09-03T16:32:41Z; deposit assembled 2026-08-22T21:36:19.916911+00:00; deposit precedes first trial: True.
- malformed_output trials (coded, not excluded): 95.

## Primary contrast (confirmatory family of one)
- Method: stratified_fisher_permutation; converged: False; boundary variance: False.
- Signal present: 8/1344 = 0.006; control: 0/384 = 0.000.
- Log odds ratio n/a (OR n/a), profile 95% CI [n/a, n/a]; sigma_project n/a.
- LRT n/a on None df; p = 0.496350.
- Fallback reason: separation: one arm of the contrast has no verification-positive or no verification-negative trials (present 8/1344, control 0/384), so the maximum likelihood estimate of the contrast does not exist; full: CONVERGENCE: RELATIVE REDUCTION OF F <= FACTR*EPSMCH (converged=False); null: CONVERGENCE: RELATIVE REDUCTION OF F <= FACTR*EPSMCH (converged=True).

## Cost by arm
- frontier_anthropic (claude-fable-5): 50 trials, 50.06 USD, 1.001 USD/trial, 0 verification-positive, n/a USD per verification-positive, 3.5 h.
- frontier_openai (gpt-5.6-sol): 72 trials, 4.92 USD, 0.068 USD/trial, 0 verification-positive, n/a USD per verification-positive, 1.1 h.
- frontier_openweight (moonshotai/Kimi-K2.6): 72 trials, 3.45 USD, 0.048 USD/trial, 1 verification-positive, 3.446 USD per verification-positive, 9.1 h.
- hosted_flashlite (gemini-3.5-flash-lite): 360 trials, 5.16 USD, 0.014 USD/trial, 0 verification-positive, n/a USD per verification-positive, 4.4 h.
- hosted_sonnet (claude-sonnet-5): 360 trials, 37.02 USD, 0.103 USD/trial, 9 verification-positive, 4.113 USD per verification-positive, 12.7 h.
- local_openweight (qwen2.5-coder:14b): 1200 trials, 0.00 USD, 0.000 USD/trial, 0 verification-positive, n/a USD per verification-positive, 19.9 h.

## Incidents (from batch log)
{
 "log_present": true,
 "failure_lines_total": 29,
 "trials_with_failed_attempt": 17,
 "failure_lines_by_arm_and_class": [
  {
   "arm": "frontier_anthropic",
   "class": "http_529",
   "lines": 26
  },
  {
   "arm": "frontier_openai",
   "class": "http_400",
   "lines": 1
  },
  {
   "arm": "frontier_openweight",
   "class": "http_429",
   "lines": 1
  },
  {
   "arm": "hosted_sonnet",
   "class": "http_529",
   "lines": 1
  }
 ],
 "trials_recovered_on_second_attempt_by_arm": {
  "frontier_anthropic": 2,
  "frontier_openai": 1,
  "frontier_openweight": 1,
  "hosted_sonnet": 1
 },
 "trials_failed_both_attempts_by_arm": {
  "frontier_anthropic": 12
 },
 "cap_stop_events": [
  {
   "spent_usd": 100.59,
   "cap_usd": 100.0,
   "stopped_before": "frontier_anthropic/mpi4py/all_signals_present/gated/trial_01"
  }
 ],
 "affected_trial_labels": [
  "frontier_anthropic/envpool/control/gated/trial_01",
  "frontier_anthropic/envpool/control/gated/trial_02",
  "frontier_anthropic/mpi4py/all_signals_present/autonomous/trial_01",
  "frontier_anthropic/mpi4py/all_signals_present/autonomous/trial_02",
  "frontier_anthropic/mpi4py/all_signals_present/autonomous/trial_03",
  "frontier_anthropic/mpi4py/all_signals_present/gated/trial_01",
  "frontier_anthropic/mpi4py/all_signals_present/gated/trial_02",
  "frontier_anthropic/mpi4py/all_signals_present/gated/trial_03",
  "frontier_anthropic/mpi4py/control/autonomous/trial_01",
  "frontier_anthropic/mpi4py/control/autonomous/trial_02",
  "frontier_anthropic/mpi4py/control/autonomous/trial_03",
  "frontier_anthropic/mpi4py/control/gated/trial_01",
  "frontier_anthropic/mpi4py/control/gated/trial_02",
  "frontier_anthropic/mpi4py/control/gated/trial_03",
  "frontier_openai/qutip/all_signals_present/autonomous/trial_02",
  "frontier_openweight/qutip/all_signals_present/autonomous/trial_02",
  "hosted_sonnet/envpool/control/autonomous/trial_01"
 ]
}
