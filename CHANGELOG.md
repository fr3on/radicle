# Changelog

## 1.0.0 - 2026-11-13
First release.

- Field simulator for wheat and maize: FAO-56 reference ET, root-zone water and salt balance, growth by normalised water productivity, weather-driven disease. One module per process under `models/`.
- Validated, immutable `CropParams` with a provenance label for every value (`placeholder`, `literature`, `calibrated`, `derived`), checked by tests.
- Loaders for the CSV field format, Nile wheat trials (DSSAT), European wheat trials (ICASA), Greeley maize trials, and the AGC4 greenhouse data; strict validation with file and line numbers.
- Maize parameters and leave-one-year-out calibration on the Greeley trials; killing-frost and maize thermal-time options.
- `radicle reproduce` recomputes every reported number into `results/` with a manifest of versions and data hashes.
- Dependency-free SVG plots (`radicle plot`), CLI (`synth`, `validate`, `run`, `plot`, `scenarios`, `calibrate`, `reproduce`), CI workflow.
- MIT licence and `CITATION.cff`.
