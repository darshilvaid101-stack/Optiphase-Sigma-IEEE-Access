"""Defect checks on the manuscripts: leftover phrases, internal names in the body, and run-in labels printed without a title.

These checks find defects in the text, such as a file name left in the body or a label printed without its title. They
do not measure how sentences are built, so they do not score the prose.
"""

import re

LEFTOVER_PHRASES = (
    "research plan",
    "preliminary run",
    "cause is unknown",
    "vitsudent",
    "Photo to be supplied",
    "Before submission:",
)
BODY_FILE_NAME = re.compile(r"\b(?:src|data|config|tests|manuscript)/[\w/-]*(?:\.[\w-]+)*|\b[\w-]+\.py\b|\barchive_v1\b|\bprovenance\.json\b")
ORPHAN_LABEL = re.compile(r"^[a-z]: [A-Z][^\n]*", re.MULTILINE)


def phrase_hits(pdf_text):
    lowered = pdf_text.lower()
    return [phrase for phrase in LEFTOVER_PHRASES if phrase.lower() in lowered]


def orphan_label_hits(pdf_text):
    return ORPHAN_LABEL.findall(pdf_text)


def body_name_hits(body_text):
    return sorted(set(BODY_FILE_NAME.findall(body_text)))
