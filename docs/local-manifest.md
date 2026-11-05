# Local case manifest

The Phase 3 manifest records exactly which PDF files an investigation case uses. It is a local inventory, not an OCR result or an alteration decision. The tool reads only the filenames supplied to it. It does not open `ground_truth.csv` or copy the PDFs.

## A01 example

From the repository root, install the tested PDF dependency if needed:

```powershell
python -m pip install -r requirements.txt
```

Create the A01 manifest in the local dataset folder, outside this Git repository:

```powershell
python -m docforensics.manifest create --case-id A01 --source-dir '..\output\pdf\ocr_assignment_dataset\pdfs' --output '..\output\pdf\ocr_assignment_dataset\manifests\A01.json' sample_001.pdf sample_002.pdf sample_003.pdf
```

The command refuses to replace an existing manifest. To recheck the recorded files later:

```powershell
python -m docforensics.manifest verify '..\output\pdf\ocr_assignment_dataset\manifests\A01.json'
```

Each document record has a stable case-specific ID, original filename, page count, byte size, and SHA-256 digest. Verification checks that the same files are still present, readable, and unchanged. The manifest also records the local source folder so the case can locate its inputs.

The running analysis must not receive the dataset answer key. Use `ground_truth.csv` separately, after the system produces findings, to evaluate whether those findings match known edits.
