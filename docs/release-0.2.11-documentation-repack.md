# v0.2.11: documentation-only archive repack

Published 2026-10-30 to https://github.com/onv83/LocalAnonymizer/releases/tag/v0.2.11 with explicit user authorization to replace the two archives. Program source tag remains `a72e29f3a3a490908743b9511d5f77d4f6eda390`. v0.2.10 asset identities/digests and release body are unchanged.

## Delivered files

- Windows ZIP: replaced `LocalAnonymizer/README.md` and `LocalAnonymizer/CHANGELOG.md`; 424 other ZIP entries unchanged byte-for-byte.
- Mac ZIP: added `README-macOS.md` and `native-macos-package/README-macOS.md`; all 689 original ZIP entries unchanged byte-for-byte. The 54 symlinks, modes, ZIP metadata and all `.app` files (including existing signature data) are preserved.
- Both application manifests are byte-identical to the original manifests: verified all 423 Windows and 577 Mac entries. Their inventories describe the application, not the outer documentation. The internal Mac manifest matches the published Mac manifest.
- Updated SHA256SUMS.txt covers both ZIPs and both manifests.

## Published checksums

```text
c140466add95d17248ea909c921ceb1e5dfc8061d8a6e48c8166eb4160634a3d  LocalAnonymizer-0.2.11-macos-arm64.manifest.json
9e9bc27e89b742315fac63622ec580cc59b21c2f6ad1a3f04af9487387aff75e  LocalAnonymizer-0.2.11-macos-arm64.zip
bd967fcc160cf336a733ddae2bd77beb459b00b39a93b4c914409a6d2a651687  LocalAnonymizer-0.2.11-windows-x64.manifest.json
93883c290ff5d0635bd35f086db6d4ec05dd8c23a3c838259f45c311a362798b  LocalAnonymizer-0.2.11-windows-x64.zip
```

Executable SHA-256 (unchanged):

- Windows: `25f7b36366411b6e17dbc06ede906b145773f8f7aa19c604a00bbe1f631c0906`
- macOS: `de9800f56771082172c332982fbf2ae220852d8b85b403ad9f263d2362d76afa`

## Verification performed

1. ZIP CRC integrity, unique safe paths, mode/metadata preservation, exact old/new member bytes outside the documentation allowlist; Mac symlink chains resolve within `.app` without cycles or escaping paths.
2. Manifest entry hashes/sizes/links and executable identities; all SHA256SUMS entries.
3. Extracted Windows EXE: `--smoke`, `--pair-smoke`, `--platform-smoke`, with all repository validators passing. Pair restoration exact; Windows secure storage and clipboard passed. No modification to the user's installed copy.
4. All five published assets downloaded afresh; compared byte-for-byte with verified upload files; repeated archive/documentation/manifest/hash validation. First download timed out after 180 seconds; clean overwrite/retry completed and passed.
5. Release description read back exactly; remote source tags unchanged; v0.2.10 asset IDs, sizes, digests and timestamps plus release body unchanged.

## Scope and remaining checks

No code changes or rebuilds. This is not a new native macOS run: original evidence remains [run 40908065255](https://github.com/onv83/LocalAnonymizer/actions/runs/40908065255). No new full pytest run for these documentation changes. macOS ARM64 remains preliminary. Real-Mac first launch/Gatekeeper, Cmd+Enter, language persistence, real DOCX/Word roundtrip, clipboard/dialogs still require manual acceptance; Intel, Developer ID/notarization and B65 native keyring first-key concurrency remain unverified.

The README audit checked build.bat/build.sh, pyproject.toml and docx_preview.py: removed duplicate incompatible developer commands and corrected platform-specific storage/WebView language and embedded-image preview description. This does not certify every historical feature claim or replace manual document review.
