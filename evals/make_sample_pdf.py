"""Generate evals/corpus/pump-station-maintenance.pdf (a synthetic, multi-page PDF).

Writes a minimal PDF by hand (Helvetica, one text stream per page) so the
evaluation set has a real PDF with page numbers without adding a PDF-writing
dependency. Run: uv run python evals/make_sample_pdf.py
"""

from __future__ import annotations

import textwrap
from pathlib import Path

OUT = Path(__file__).parent / "corpus" / "pump-station-maintenance.pdf"

PAGES = [
    """Pump Station Maintenance Manual, Stations PS-3 and PS-4
    SYNTHETIC SAMPLE DOCUMENT. Written for the personal-ai-brain evaluation set. \
The utility, equipment and limits are invented.
    1. Scope
    This manual covers routine maintenance of the four centrifugal pumps at stations PS-3 \
and PS-4 of the river intake. Each pump is driven by a 250 kW induction motor at 1,480 rpm \
and moves up to 1,100 cubic metres of raw water per hour.
    Maintenance is planned in three tiers: weekly walk-round inspections by the operator, \
monthly condition monitoring by the reliability technician, and an annual overhaul by \
the mechanical contractor. Chapter 2 sets the vibration limits, chapter 3 the bearing \
lubrication schedule, and chapter 4 the shutdown and isolation procedure.""",
    """2. Vibration monitoring
    Vibration is measured on both motor bearings and both pump bearings as RMS velocity \
in mm/s, in the 10 Hz to 1 kHz band, following ISO 10816-3 for machines on rigid \
foundations.
    Limits for these pumps:
    Below 2.8 mm/s - good condition, no action.
    2.8 to 4.5 mm/s - acceptable, record the trend and check monthly.
    4.5 to 7.1 mm/s - alert: increase monitoring to weekly and plan a repair.
    Above 7.1 mm/s - danger: stop the pump within 24 hours and inspect.
    A rise of more than 25% between two monthly readings is treated as an alert even when \
the absolute value is still in the acceptable band. Most alerts on these pumps have been \
caused by bearing wear or by impeller imbalance after debris strikes.""",
    """3. Bearing lubrication
    Pump bearings are grease-lubricated rolling element bearings. Use a lithium-complex \
grease of NLGI grade 2. Do not mix with polyurea greases.
    Regrease the pump bearings every 2,000 running hours with 30 grams per bearing. Regrease \
the motor bearings every 4,000 running hours with 20 grams per bearing. Add grease slowly \
with the pump running and stop when the bearing temperature starts to rise.
    Bearing temperature should stay below 80 C. A temperature above 90 C, or a rise of \
15 C above the normal running value, means the pump must be stopped and the bearing \
inspected. Over-greasing is a common cause of high temperature after maintenance.""",
    """4. Shutdown and isolation
    Before any work inside the pump casing, the pump must be isolated under the permit to \
work system. Close the suction and discharge valves, lock both with personal padlocks, \
and lock out the motor isolator at the motor control centre.
    Drain the casing through the drain valve and confirm zero pressure on the casing \
gauge before opening any flange. Two people must be present for confined-space entry \
into the suction well.
    After work, the permit holder removes the locks, the operator primes the pump, and the \
pump runs for 30 minutes under observation before it returns to automatic control.""",
]


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_stream(text: str) -> bytes:
    lines: list[str] = []
    for para in textwrap.dedent(text).split("\n"):
        lines.extend(textwrap.wrap(para.strip(), 92) or [""])
        lines.append("")
    ops = ["BT", "/F1 10 Tf", "14 TL", "56 790 Td"]
    ops += [f"({_escape(line)}) '" for line in lines]
    ops.append("ET")
    return "\n".join(ops).encode("latin-1")


def build_pdf(pages: list[str]) -> bytes:
    n = len(pages)
    # Object numbers: 1 catalog, 2 page tree, 3 font, then (page, content) pairs.
    page_ids = [4 + 2 * i for i in range(n)]
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Count {n} /Kids [{kids}] >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    for page_id, text in zip(page_ids, pages, strict=True):
        stream = _page_stream(text)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>"
        ).encode()
        objects[page_id + 1] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for num in sorted(objects):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    size = len(objects) + 1
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


if __name__ == "__main__":
    OUT.write_bytes(build_pdf(PAGES))
    print(f"wrote {OUT}")
