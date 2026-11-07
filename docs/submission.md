# PS2 handover checklist

Use the [live demonstration](demo.md) to reproduce the workflow and the [requirements checklist](ps2-requirements.md) to review the supported scope.

Download the [PS2 submission release](https://github.com/HimasaiGandham/ScopeGuard-AI/releases/tag/ps2-submission-v1). Extract the handover ZIP and open `START-HERE.html` to navigate the deliverables. The release also includes the sample dossier as a separate PDF.

| Required category | What to give the judges |
| --- | --- |
| Working prototype | Runnable source with the [setup guide](setup.md), verified model instructions, and the live walkthrough. |
| Architecture overview | [Standalone architecture diagram](architecture-overview.svg) and the [technical architecture guide](architecture.md). |
| Sample investigation dossier | [Sample Investigation Dossier](https://github.com/HimasaiGandham/ScopeGuard-AI/releases/download/ps2-submission-v1/Sample-Investigation-Dossier.pdf) from the reviewed synthetic case. The bundle includes the matching source packet and offline evidence captures. |
| Source repository | [ScopeGuard AI on GitHub](https://github.com/HimasaiGandham/ScopeGuard-AI) and the reviewed commit or branch. Confirm that the link opens for the judges. Use the source snapshot if the organizer requests an archive. See [dependency notices](third-party.md). |
| Demonstration dataset | Generated digital registration, marked enrollment scan, unmarked control, damaged-file example, and the separately reserved packet. Include expected results in a separate evaluation folder. |
| Technical documentation | [Architecture](architecture.md), [OCR](ocr.md), [contextual analysis](contextual.md), [visual checks](visual.md), [reviewer workflow](reviewer.md), and [dossier export](dossier.md). |
| Evidence traceability | Live source and crop inspection plus offline captures that name the matching originals. Include both source locations for a cross-document lead. |
| Limits and assumptions | [Measured results and limits](limitations.md), including black ink and digital-edit misses, unavailable confidence, and possible false leads. |

Before submitting, have another team member follow the setup from a fresh checkout. Open the archive and sample PDF from a different folder. Confirm the selected repository and shared files are accessible to the judges. Follow the organizer's official announcements for the deadline, submission channel, and any additional presentation or video requirements.

Keep the original source packet with the sample report. Loopback links in the sample report refer to the saved demo case. When evaluating away from that computer, use the offline evidence captures or reproduce the case from the synthetic inputs.
