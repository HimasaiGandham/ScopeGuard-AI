# PS2 live demonstration

Use the [setup guide](setup.md) and [English OCR model instructions](ocr.md) before the rehearsal. The scanned form has no text layer, so its fields exercise real OCR. The demonstration uses fictitious student values and original project-created documents.

## Prepare the packet

From the repository root, generate a new packet outside the checkout:

```powershell
.\.venv\Scripts\python.exe scripts/create_demo_packet.py ..\scopeguard-demo --packet rehearsal
```

The generator creates `inputs/`, an unmarked comparison scan in `controls/`, and `evaluation/expected.json`. Upload only files from `inputs/`. Use the evaluation key after processing to check values, findings, and file fingerprints. The app receives no evaluation labels. Keep `controls/` and `evaluation/` separate from the case data directory.

The packet includes a digital Student Registration, an image-only Enrollment Confirmation with blue ink across a printed reference line, and a deliberately damaged PDF. The two forms concern the same fictitious enrollment. The clean scan preserves the Enrollment Confirmation before the mark. No organizer documents or real identities are used in this packet.

For the final test, generate a separate packet using `--packet holdout` and a different output folder. Keep it out of practice and avoid changing the detector based on that result. Process its inputs before opening its evaluation key.

## Five minute walkthrough

| Time | Show | What to explain |
| --- | --- | --- |
| 0:00–0:45 | Open `/ingest` and upload the three inputs. | The app saves two documents, rejects the damaged file with a reason, and flags the scan's blue mark for review. Open the crop. |
| 0:45–1:40 | Open the reviewer workspace, confirm the related enrollment, and click **Process this case**. | The registration uses digital text. The scan uses local English OCR and identifies the Enrollment Confirmation layout. Click an extracted value to show its original source. |
| 1:40–2:45 | Inspect the internal Student ID conflict and both cross-document findings. | The registration contains two ID values. The enrollment adds comparison evidence for the ID and a different course code. The shared ID occurrence links the internal and cross-document observations. Open both sources for a cross-document lead. |
| 2:45–3:35 | Inspect the visual finding and change the page size. | The highlight follows the printed reference line and the crop shows the blue ink. The visual lead and the contextual conflicts are different observations. Numeric confidence remains unavailable. |
| 3:35–4:35 | Enter a reviewer name, note and review each lead, and acknowledge uncertainty. Generate and download the dossier. | Review decisions and source references are recorded against the selected runs. The report shows the rejected upload and all six required sections. |
| 4:35–5:00 | Open the unmarked control or show the recorded results and limits. | The clean control produced zero visual leads. The reserved black-ink case had a contextual mismatch but no visual lead. The prototype leaves authenticity unverified. |

The timing is a rehearsal guide. Use the time allotted by the organizers. Keep the generated inputs, a downloaded sample report, and offline evidence captures available as a fallback. Identify the fallback as a previous run if the live case cannot finish.

## Final rehearsal checks

- Start from a fresh checkout with the pinned dependencies and verified model. Confirm the ingestion screen opens.
- Compare the selected extraction, contextual findings, visual findings, decisions, and source hashes to the downloaded PDF. Reopen the case and check that the download persists.
- Open a crop and both source locations for a contextual lead. Change the page size and confirm the highlight stays on the same field.
- Verify the unmarked control and the reserved packet separately. Record misses, unexpected leads, or unsupported results after processing.
- Ask a teammate to follow the setup on a clean machine and verify that the judges can open every link you plan to submit.

See the [measured results and limits](limitations.md) and [submission checklist](submission.md).
