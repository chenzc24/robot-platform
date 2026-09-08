# Source provenance

Imported from `StrokeReview-source-20260904-103816.zip`.

Archive SHA256: `99afd160eb0aa344d1f61652f4b947c3b8c401be1102043e0381e0cc809c8c2e`.

Original `SOURCE_MANIFEST.sha256` is retained as the upstream manifest, not a manifest of the adapted repository copy.

Excluded bundled model weights and generated TypeScript configuration outputs:

- `frontend/vite.config.d.ts`
- `frontend/vite.config.js`
- `model-service/models/ControlNetHED.pth`
- `model-service/models/sk_model.pth`
- `model-service/models/sk_model2.pth`
- `model-service/models/table5_pidinet.pth`

Local migration changes are recorded in Git. Original archive remains unchanged.

All 95 upstream manifest entries were verified against the ZIP before adaptation. The four weight files also match the bundled weight manifest and are preserved locally at `model-service/models/`, excluded from Git.

Adaptations: root launcher/docs, generated/runtime/weight exclusions, frozen dependency installation, and a configurable frontend proxy wired to the selected backend port. No image algorithm or robot runtime code was changed.
