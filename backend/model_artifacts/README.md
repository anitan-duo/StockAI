# Backend Model Artifacts Directory

Model weights and binaries are **not included** in this public repository.

To enable machine learning predictions, provide a compatible model artifact:

```
backend/model_artifacts/real/ensemble/v1.0/model.pkl
```

Without this file, the backend starts in fail-closed mode: market data and quotes are accessible, but predictions return `503 UNAVAILABLE` (`InsufficientDataError`).
