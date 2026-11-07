"""An article as a PDF document or a PowerPoint deck.

Both are built from one ExportContent, so whatever the reader sees (including
a translation) is what they download. No I/O here; the route gathers the
content and sends the bytes.

PDF: reportlab, A4, the article as published with its score, sources and a
link back. PowerPoint: python-pptx, 16:9, a title slide, the key points, one
slide per section of the article, and the sourcing and score.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from . import insights

INK = (0x13, 0x39, 0x55)
QUIET = (0x44, 0x60, 0x74)
SITE = "Sterling Wire"


@dataclass
class ExportContent:
    title: str
    summary: str
    body_html: str
    byline: str
    dateline: str
    score: float | None
    band: str | None
    approved_by: str | None
    url: str
    points: list[str] = field(default_factory=list)
    sources: list[tuple[str, str]] = field(default_factory=list)  #(label, url)
    lang: str = "en"
    labels: dict = field(default_factory=dict)


DEFAULT_LABELS = {
    "in_brief": "In brief",
    "credibility": "Credibility score",
    "sources": "Sources",
    "approved_by": "Approved by",
    "downloaded": "Downloaded from",
    "read_online": "Read it online, with its sources and corrections",
    "sourcing": "Sourcing and score",
    "summary_note": "AI generated",
}


def _label(content: ExportContent, key: str) -> str:
    return content.labels.get(key) or DEFAULT_LABELS[key]


def _cjk(content: ExportContent) -> bool:
    return content.lang.startswith("zh")


def _blocks(body_html: str) -> list[insights.Paragraph]:
    return [p for p in insights.paragraphs(body_html) if p.text.strip()]


def _sections(body_html: str) -> list[tuple[str | None, list[str]]]:
    """The article split at its subheadings: (heading, paragraphs)."""
    out: list[tuple[str | None, list[str]]] = [(None, [])]
    for block in _blocks(body_html):
        if block.heading:
            out.append((block.text, []))
        else:
            out[-1][1].append(block.text)
    return [(h, ps) for h, ps in out if ps]


#--------------------------------------------------------------------------- #
# PDF
#--------------------------------------------------------------------------- #

def to_pdf(content: ExportContent) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        HRFlowable, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer,
    )

    ink = colors.Color(*(c / 255 for c in INK))
    quiet = colors.Color(*(c / 255 for c in QUIET))
    if _cjk(content):
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        serif = sans = bold = serif_bold = "STSong-Light"
        wrap = "CJK"
    else:
        serif, serif_bold, sans, bold = "Times-Roman", "Times-Bold", "Helvetica", "Helvetica-Bold"
        wrap = None

    def style(name, **kw):
        base = dict(name=name, fontName=serif, fontSize=11, leading=16, textColor=ink,
                    alignment=TA_LEFT, wordWrap=wrap)
        base.update(kw)
        return ParagraphStyle(**base)

    s_site = style("site", fontName=sans, fontSize=8, textColor=quiet, leading=10)
    s_title = style("title", fontName=serif_bold, fontSize=24, leading=29, spaceAfter=8)
    s_standfirst = style("standfirst", fontSize=13, leading=18, textColor=quiet, spaceAfter=8)
    s_meta = style("meta", fontName=sans, fontSize=8.5, leading=12, textColor=quiet)
    s_score = style("score", fontName=bold, fontSize=10, leading=14)
    s_h = style("h", fontName=serif_bold, fontSize=14, leading=18, spaceBefore=10, spaceAfter=4)
    s_label = style("label", fontName=bold, fontSize=8, leading=10, textColor=quiet, spaceBefore=6)
    s_body = style("body", spaceAfter=7)
    s_point = style("point", fontSize=10.5, leading=15)
    s_small = style("small", fontName=sans, fontSize=8, leading=11, textColor=quiet)

    e = lambda text: escape(text or "")
    story = [
        Paragraph(e(SITE.upper()), s_site), Spacer(1, 4 * mm),
        Paragraph(e(content.title), s_title),
    ]
    if content.summary:
        story.append(Paragraph(e(content.summary), s_standfirst))
    story.append(Paragraph(e(f"{content.byline} · {content.dateline}"), s_meta))
    if content.approved_by:
        story.append(Paragraph(e(f"{_label(content, 'approved_by')} {content.approved_by}"), s_meta))
    if content.score is not None:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            e(f"{_label(content, 'credibility')}: {round(content.score)}/100"
              + (f" · {content.band}" if content.band else "")), s_score))
    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=0.6, color=quiet))

    if content.points:
        story.append(Paragraph(e(_label(content, "in_brief").upper()), s_label))
        story.append(ListFlowable(
            [ListItem(Paragraph(e(p), s_point), leftIndent=10) for p in content.points],
            bulletType="bullet", bulletColor=quiet, leftIndent=12))
        story.append(Paragraph(e(_label(content, "summary_note")), s_small))
        story.append(HRFlowable(width="100%", thickness=0.4, color=quiet, spaceBefore=6))

    story.append(Spacer(1, 2 * mm))
    for block in _blocks(content.body_html):
        story.append(Paragraph(e(block.text), s_h if block.heading else s_body))

    if content.sources:
        story.append(HRFlowable(width="100%", thickness=0.4, color=quiet, spaceBefore=8))
        story.append(Paragraph(e(_label(content, "sources").upper()), s_label))
        for i, (label, url) in enumerate(content.sources, 1):
            story.append(Paragraph(
                f"{i}. {e(label)}<br/><font color='#446074'>{e(url)}</font>", s_small))
            story.append(Spacer(1, 1.5 * mm))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        e(f"{_label(content, 'downloaded')} {SITE}. {_label(content, 'read_online')}: ")
        + f"<link href='{e(content.url)}'>{e(content.url)}</link>", s_small))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(sans, 7.5)
        canvas.setFillColor(quiet)
        canvas.drawString(18 * mm, 10 * mm, f"{SITE} · {content.url}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, str(doc.page))
        canvas.restoreState()

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title=content.title,
                            author=content.byline, subject=SITE)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


#--------------------------------------------------------------------------- #
# PowerPoint
#--------------------------------------------------------------------------- #

MAX_BULLETS = 5


def _bare(url: str) -> str:
    """An address without its scheme or www., shortened for a slide."""
    return re.sub(r"^https?://(www\.)?", "", url)[:80]


def _bullets_for(paragraphs: list[str]) -> list[str]:
    """A section's paragraphs as slide bullets: the opening sentence of each."""
    out = []
    for p in paragraphs:
        first = insights.sentences(p)
        if first:
            text = first[0]
            if len(text) > 220:
                text = text[:217].rsplit(" ", 1)[0] + "…"
            out.append(text)
        if len(out) == MAX_BULLETS:
            break
    return out


def to_pptx(content: ExportContent) -> bytes:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Emu, Inches, Pt

    ink, quiet = RGBColor(*INK), RGBColor(*QUIET)
    font = "Microsoft YaHei" if _cjk(content) else "Georgia"
    ui_font = "Microsoft YaHei" if _cjk(content) else "Calibri"

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    W = prs.slide_width
    margin = Inches(0.8)

    def text_box(slide, left, top, width, height, lines, size, color=ink, face=font,
                 bold=False, bullets=False, spacing=6):
        box = slide.shapes.add_textbox(left, top, width, height)
        frame = box.text_frame
        frame.word_wrap = True
        for i, line in enumerate(lines):
            para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
            run = para.add_run()
            run.text = ("•  " if bullets else "") + line
            run.font.size = Pt(size)
            run.font.color.rgb = color
            run.font.name = face
            run.font.bold = bold
            para.space_after = Pt(spacing)
        return box

    def rule(slide, top):
        line = slide.shapes.add_shape(1, margin, top, W - 2 * margin, Emu(18000))
        line.fill.solid()
        line.fill.fore_color.rgb = ink
        line.line.fill.background()

    def footer(slide):
        text_box(slide, margin, Inches(6.85), W - 2 * margin, Inches(0.4),
                 [f"{SITE} · {content.url}"], 10, quiet, ui_font)

    #Title slide
    slide = prs.slides.add_slide(blank)
    text_box(slide, margin, Inches(0.7), W - 2 * margin, Inches(0.4), [SITE.upper()], 12, quiet, ui_font, True)
    rule(slide, Inches(1.2))
    text_box(slide, margin, Inches(1.5), W - 2 * margin, Inches(2.6), [content.title], 40, ink, font, True)
    if content.summary:
        text_box(slide, margin, Inches(4.2), W - 2 * margin, Inches(1.2), [content.summary], 20, quiet)
    meta = [f"{content.byline} · {content.dateline}"]
    if content.score is not None:
        meta.append(f"{_label(content, 'credibility')}: {round(content.score)}/100"
                    + (f" · {content.band}" if content.band else ""))
    text_box(slide, margin, Inches(5.6), W - 2 * margin, Inches(1), meta, 14, ink, ui_font)

    #Key points
    if content.points:
        slide = prs.slides.add_slide(blank)
        text_box(slide, margin, Inches(0.6), W - 2 * margin, Inches(0.8),
                 [_label(content, "in_brief")], 30, ink, font, True)
        rule(slide, Inches(1.45))
        text_box(slide, margin, Inches(1.8), W - 2 * margin, Inches(4.5),
                 content.points, 20, ink, font, bullets=True, spacing=14)
        text_box(slide, margin, Inches(6.4), W - 2 * margin, Inches(0.4),
                 [_label(content, "summary_note")], 11, quiet, ui_font)
        footer(slide)

    #One slide per section of the article
    for heading, paragraphs in _sections(content.body_html):
        slide = prs.slides.add_slide(blank)
        text_box(slide, margin, Inches(0.6), W - 2 * margin, Inches(0.8),
                 [heading or content.title], 28, ink, font, True)
        rule(slide, Inches(1.45))
        text_box(slide, margin, Inches(1.8), W - 2 * margin, Inches(4.8),
                 _bullets_for(paragraphs), 18, ink, font, bullets=True, spacing=12)
        footer(slide)

    #Sourcing and score
    slide = prs.slides.add_slide(blank)
    text_box(slide, margin, Inches(0.6), W - 2 * margin, Inches(0.8),
             [_label(content, "sourcing")], 28, ink, font, True)
    rule(slide, Inches(1.45))
    lines = []
    if content.score is not None:
        lines.append(f"{_label(content, 'credibility')}: {round(content.score)}/100"
                     + (f" · {content.band}" if content.band else ""))
    if content.approved_by:
        lines.append(f"{_label(content, 'approved_by')} {content.approved_by}")
    text_box(slide, margin, Inches(1.8), W - 2 * margin, Inches(1), lines, 18, ink, ui_font)
    sources = [f"{label} — {_bare(url)}" for label, url in content.sources[:8]]
    if sources:
        text_box(slide, margin, Inches(3.0), W - 2 * margin, Inches(3.6),
                 sources, 13, quiet, ui_font, bullets=True, spacing=6)
    text_box(slide, margin, Inches(6.4), W - 2 * margin, Inches(0.4),
             [f"{_label(content, 'read_online')}: {content.url}"], 12, ink, ui_font)

    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()
