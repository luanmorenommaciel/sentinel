# Per-environment configuration

The **only** place a `staging`-vs-`prod` difference is allowed to live (REQ-A-07).

Promotion moves an image digest and nothing else, so the image cannot carry an
environment inside it. Anything that differs between environments — endpoints,
sizes, retention, which ClickHouse it talks to — is read from here at deploy
time, by SHA-tagged digest plus this directory.

`release.yml`'s `promote` job asserts the directory for the target stage exists
before it moves a tag. What it does **not** assert is the contents: the shape of
these files is DEC-A1's business (compute form) and DEC-A2's (ClickHouse
hosting), and T40 writes them. Until then each holds a `.gitkeep`, and that is
the honest state — the location is decided, the contents are not.

Secrets never land here. They come from a managed store, delivered as files
(T44, REQ-A-04).
