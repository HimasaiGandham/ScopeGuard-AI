# PS2 requirements and acceptance checklist

Source: *AI-Powered Document Forensics and Contextual Intelligence System*, sections 2–13 of `PS-2.pdf` supplied for the DataOps Innovation Hackathon.

## Goal

Investigate digital and scanned documents using text extraction, document structure, visual analysis, and cross-document comparison. Explain anomalies with evidence from the original documents. OCR output alone is not verified truth, and a detected anomaly is not proof of fraud.

## Mandatory working prototype

- [ ] Ingest multiple authorized documents in one investigation, retaining document IDs and source references.
- [ ] Extract information with OCR and present it as structured fields with source locations and confidence.
- [ ] Provide a review interface for extracted information and findings.
- [ ] Identify suspicious document regions and visual inconsistencies; highlight the relevant source region.
- [ ] Identify inconsistencies between related fields within a document.
- [ ] Identify conflicting information across related documents.
- [ ] Explain each finding, link it to supporting visual or textual evidence, and distinguish observations from suspected manipulation.
- [ ] Generate a structured investigation dossier.

## Investigation dossier contents

1. **Document overview:** identification, type, source, and processing status.
2. **Extracted information:** fields, values, confidence, structure, and source references.
3. **Contextual analysis:** field inconsistencies, missing or duplicated information, and cross-document conflicts.
4. **Visual forensic findings:** suspicious regions and observations about alterations, fonts, alignment, images, or signatures where applicable.
5. **Evidence and traceability:** original document references, highlighted regions, supporting evidence, associated extracted information, confidence, and observation status.
6. **Investigation summary:** anomalies, evidence, possible explanations, further verification, and limitations.

## Required submission deliverables

- [ ] Working prototype demonstrated with authorized sample documents.
- [ ] Architecture diagram covering OCR, document processing, AI models, computer vision, contextual analysis, data flow, and evidence management.
- [ ] Sample AI-generated investigation dossier.
- [ ] Source repository with setup, dependencies, licensing assumptions, and execution instructions.
- [ ] Demonstration dataset with genuine and artificially manipulated sample documents.
- [ ] Technical documentation describing technologies, models, methods, and processing pipeline.
- [ ] Evidence-traceability demonstration from findings to original document locations.
- [ ] Documented limitations, assumptions, unsupported scenarios, and potential false positives.

## Judges' live demonstration

The demo should show document upload and classification, OCR and structured extraction, highlighted suspicious regions, within-document and cross-document inconsistencies, relationships between findings, evidence inspection, dossier generation, source-location traceability, uncertainty, and safe failure handling.

## Judging weights

| Criterion | Points |
| --- | ---: |
| OCR and information extraction | 15 |
| Document understanding | 15 |
| Visual forensic analysis | 15 |
| Contextual intelligence | 20 |
| Evidence and traceability | 10 |
| AI reasoning and explainability | 10 |
| Technical implementation | 10 |
| Innovation | 5 |

## Boundaries and honest claims

- Use only documents and datasets authorized for the hackathon; protect sensitive information.
- Never treat OCR output as verified ground truth or automatically label every anomaly as confirmed fraud.
- Preserve human oversight for consequential decisions.
- Record what is implemented, partially implemented, planned, and unsupported.
- Advanced handwriting recognition, multilingual support, sophisticated manipulation localization, and other advanced features are optional extensions.
