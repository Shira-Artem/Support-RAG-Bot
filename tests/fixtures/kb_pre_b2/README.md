# Historical KB for recorded replays

These 45 documents are an immutable subset of the pre-B2 knowledge base at the
Git commit recorded in `manifest.json`. Only tests replaying earlier evidence use
this directory. Runtime ingestion and tests of the current corpus use
`data/knowledge` in the project root.

The Markdown files retain CRLF bytes because recorded selector IDs include the
SHA-256 of the original Windows working-tree files. `.gitattributes` disables
newline conversion here. The manifest records the normalized Git/LF hash, so the
content can independently be checked against its immutable source commit.

The corpus remains historical: its wording, metadata and statuses do not override
the colleague's reviewed B2 cards. No test status is changed to hide a failure.
