# Word restore fixture

Synthetic regression fixture for the DOCX original-layout restore path.

- `source.docx`: created only from synthetic text and two generated 1×1 PNG images, then saved by Microsoft Word 16.0. Contains a heading, two synthetic names separated by a hard break, a numbered list, a table with a vertically merged cell, and two inline pictures. The second picture is followed by a hard break and a caption.
- `edited.docx`: the exported anonymized document opened, edited, and saved by Microsoft Word 16.0. Both name groups and the second picture caption contain synthetic user edits.
- `recovery.larecovery`: the matching recovery companion produced by the application.

No user document or real personal data was used. Core/app identity fields, custom XML in the source, revision/session identifiers, and local-path markers were removed. The standard Word compatibility settings remain; their manual-review warning was explicitly inspected during fixture generation.

The test verifies SHA-256 hashes before use, restores through `AnonymizerService`, proves the original-layout branch ran, compares both embedded images byte-for-byte, checks original formatting parts and user formatting, and rejects leftover markers. The fixture is also opened read-only in Microsoft Word during local release verification; CI does not require Word.
