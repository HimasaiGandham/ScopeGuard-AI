# 🔎 Document Forensics Assistant

### DataOps Innovation Hackathon — Problem Statement 2

This project aims to help a person review a group of documents and spot details that may need a closer look. It will read information from the documents, compare related details, point to unusual areas, and explain what it found.

## 💡 Why this matters

Imagine reviewing an application form, an identity document, and a supporting letter. A name or date may differ between them. A number may appear to have been changed. Checking every page by hand takes time, and a simple text reader may miss the connection between documents.

Our goal is to bring those clues together so a reviewer can investigate them more easily.

## 🧭 How the planned system will work

1. **Add documents.** A reviewer uploads several permitted sample documents for one case.
2. **Read the information.** The system reads printed text, including text in scanned pages or images, and organizes useful details such as names, dates, and amounts.
3. **Compare the details.** It looks for missing or conflicting information within a document and across the group.
4. **Look at the pages.** It highlights areas that appear visually unusual, such as a field with different spacing or alignment.
5. **Show the evidence.** Each finding points back to the document and location that supports it.
6. **Create a report.** The system produces an investigation summary with the findings, evidence, possible explanations, and items that need human review.

### 📝 A simple example

If an application form and a supporting document show different dates of birth, the system should display both values, show where each appears, and explain the mismatch. **A mismatch is a reason to check; it is not proof of fraud.**

## 👀 What the hackathon demo should show

- Uploading and reviewing more than one sample document.
- Reading and organizing information from those documents.
- Finding visual clues and differences within or across documents.
- Clicking a finding to see its source on the original page.
- Creating a clear investigation report.

## 🚧 Current status

We have selected Problem Statement 2, documented its requirements, and started the shared data model. **The application has not been built yet.** This README describes the intended project, not features that are already available.

When a working version is ready, this page will include simple steps to run it and try the demo.

## 📚 More detail

The [requirements checklist](docs/ps2-requirements.md) records the full prototype, demo, and submission expectations from the hackathon problem statement.

The [foundation architecture](docs/architecture.md) explains how documents, findings, and source evidence will connect.

The [project work record](docs/work-log.md) tracks completed phases, decisions, checks, and remaining work.

The [foundation audit](docs/foundation-audit.md) records the checks and fixes from a review of phases 1–3.
