"""
Seeds a small demo internet-source corpus so internet plagiarism checking is
testable immediately after setup, without needing live internet access to
fetch real pages first.

Run from the backend/ directory (needs the app package + a running DB):
    python -m scripts.seed_internet_sources

This is original placeholder text written for this project (not copied from
any real source) — good enough to prove the ingestion → embedding → FAISS →
matching pipeline end-to-end, but you should replace/extend it with real
ingested sources (via `POST /api/internet-sources` or `/from-url`) before
using this for anything beyond a demo. Re-running this script is safe: it
skips any title that's already been seeded.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models.internet_source import InternetSource, InternetSourceCategory
from app.services.source_ingestion import ingest_source_from_text

DEMO_SOURCES = [
    {
        "title": "Overview of Operating System Process Scheduling",
        "category": InternetSourceCategory.WIKIPEDIA,
        "url": "https://en.wikipedia.org/wiki/Scheduling_(computing)",
        "text": """
Process scheduling is the activity by which an operating system decides which
runnable process gets access to the CPU at any given moment, since most
computers have far fewer processor cores than the number of processes that
want to run at once. A scheduler is the specific piece of kernel code that
implements this decision, and the choice of scheduling algorithm has a direct
effect on system responsiveness, throughput, and fairness among competing
tasks.

First-come first-served scheduling runs processes strictly in the order they
arrive in the ready queue, which is simple to implement but can lead to long
waiting times for short jobs stuck behind long ones, an effect commonly
called the convoy effect. Shortest-job-first scheduling instead prioritizes
whichever process needs the least remaining CPU time, which provably
minimizes average waiting time but requires the scheduler to know or
estimate future CPU bursts in advance.

Round-robin scheduling assigns each process a small fixed time slice, called
a quantum, and cycles through the ready queue so that no single process can
monopolize the CPU indefinitely. This makes round-robin especially well
suited to interactive, time-sharing systems where responsiveness matters
more than raw throughput, at the cost of higher overhead from frequent
context switches when the quantum is set too small.
""",
    },
    {
        "title": "Introduction to Convolutional Neural Networks",
        "category": InternetSourceCategory.RESEARCH_PAPER,
        "url": None,
        "text": """
Convolutional neural networks are a class of deep learning models designed
to process data with a grid-like topology, most commonly two-dimensional
images. Rather than connecting every input pixel to every neuron in the next
layer, a convolutional layer applies a small set of learnable filters across
local regions of the input, which drastically reduces the number of
parameters compared to a fully connected network while still allowing the
network to learn spatially local patterns such as edges and textures.

Pooling layers are typically inserted between convolutional layers to
progressively reduce the spatial dimensions of the feature maps, which both
lowers computational cost and provides a degree of translation invariance,
since the exact pixel location of a detected feature matters less than its
approximate position within the image. Max pooling, which keeps only the
largest activation within each pooling window, is the most widely used
variant in practice.

Because early layers of a convolutional network tend to learn generic
features like edges and color blobs regardless of the specific dataset they
were trained on, it has become common practice to reuse the early layers of
a network pretrained on a large dataset and fine-tune only the later layers
on a smaller, task-specific dataset, a technique known as transfer learning.
""",
    },
    {
        "title": "Principles of Database Normalization",
        "category": InternetSourceCategory.BOOK,
        "url": None,
        "text": """
Database normalization is the process of structuring a relational database
in accordance with a series of so-called normal forms, with the goal of
reducing data redundancy and eliminating certain kinds of insertion, update,
and deletion anomalies. A table is said to be in first normal form when
every column holds atomic, indivisible values and there are no repeating
groups of columns representing the same kind of data.

Second normal form builds on first normal form by additionally requiring
that every non-key attribute depend on the whole of a composite primary key,
not just part of it; a table already using a single-column primary key
automatically satisfies this condition once it is in first normal form.
Third normal form goes further still, requiring that non-key attributes
depend only on the primary key and not on other non-key attributes, a
situation known as a transitive dependency.

In practice, most production schemas are normalized to third normal form as
a reasonable balance between eliminating redundancy and keeping queries
simple, with selective denormalization sometimes reintroduced afterward for
performance reasons once real query patterns are known.
""",
    },
    {
        "title": "How Photosynthesis Converts Light Into Chemical Energy",
        "category": InternetSourceCategory.EDUCATIONAL_WEBSITE,
        "url": None,
        "text": """
Photosynthesis is the process by which green plants, algae, and some
bacteria convert light energy, usually from the sun, into chemical energy
stored in glucose molecules. The process takes place primarily in the
chloroplasts of plant cells, where a pigment called chlorophyll absorbs
light most strongly in the blue and red portions of the visible spectrum
while reflecting green light, which is why most plant leaves appear green
to the human eye.

The overall reaction can be split into two linked stages. The light-dependent
reactions occur in the thylakoid membranes and use absorbed light energy to
split water molecules, releasing oxygen as a byproduct while generating ATP
and NADPH. These energy carriers are then consumed in the light-independent
reactions, also called the Calvin cycle, which take place in the stroma and
use ATP and NADPH to fix carbon dioxide into three-carbon sugar molecules
that are eventually assembled into glucose.
""",
    },
    {
        "title": "Why Version Control Matters for Student Projects",
        "category": InternetSourceCategory.BLOG,
        "url": None,
        "text": """
A surprising number of students still submit coursework as a folder full of
files named project_final, project_final_v2, and project_final_v2_ACTUAL,
which is exactly the problem version control systems like Git were built to
solve. Instead of manually renaming files to track changes, Git lets you
commit a snapshot of your entire project at any point, complete with a
message explaining what changed and why, and lets you jump back to any
earlier snapshot instantly if something breaks.

Branching is where version control really starts to pay off for team
projects. Each team member can work on their own branch without touching
the main codebase, experiment freely, and only merge their changes back in
once the feature actually works, which avoids the all-too-common situation
where one broken commit blocks everyone else on the team from making
progress.
""",
    },
    {
        "title": "Data Protection Principles for Public Sector Systems",
        "category": InternetSourceCategory.GOVERNMENT,
        "url": None,
        "text": """
Government agencies that collect personal data are generally expected to
follow a small set of core data protection principles regardless of the
specific jurisdiction: data should be collected only for specified,
legitimate purposes; the amount of data collected should be limited to what
is actually necessary for those purposes; and data should not be retained
for longer than is needed to fulfill them.

Agencies are typically also required to implement appropriate technical and
organizational safeguards proportionate to the sensitivity of the data being
processed, and to be able to demonstrate accountability for how that data is
handled, which in practice means maintaining clear records of what data is
held, why it was collected, who has access to it, and how long it will be
retained before secure deletion.
""",
    },
]


def seed():
    db = SessionLocal()
    try:
        existing_titles = {t for (t,) in db.query(InternetSource.title).all()}
        added = 0
        for entry in DEMO_SOURCES:
            if entry["title"] in existing_titles:
                print(f"skip (already seeded): {entry['title']}")
                continue
            source = ingest_source_from_text(
                title=entry["title"], category=entry["category"], text=entry["text"], db=db, url=entry["url"]
            )
            print(f"seeded: {source.title} ({source.paragraph_count} paragraphs)")
            added += 1
        print(f"\nDone. {added} new source(s) seeded, {len(existing_titles)} already present.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
