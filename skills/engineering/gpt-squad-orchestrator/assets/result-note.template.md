{
  "status": "completed",
  "outcome": "Describe the owned outcome without ceremony.",
  "verification": [
    {
      "command": "<decisive check>",
      "outcome": "PASS",
      "evidence": "<path, observation, measurement, or artifact>"
    }
  ],
  "proposedContextUpdates": [
    {
      "type": "fact",
      "claim": "<decision-relevant proposal>",
      "evidence": {"source": "<durable evidence>"}
    }
  ],
  "crossMissionImplications": ["<affected mission or None>"],
  "remainingDecisionRelevantUncertainty": []
}

For an independent challenger, also include:

```json
{
  "verdict": "PASS | FAIL | UNRESOLVED",
  "distinctEvidence": "<method or evidence path not copied from the lead>"
}
```

Submit through `result-submit` with the exact checkout snapshot hash. The SQLite row, not this template or generated Markdown, is the sealed result.
