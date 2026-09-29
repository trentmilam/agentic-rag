"""chainrag: cited retrieval over primary blockchain protocol documentation.

A second vertical over the same router/citation-gating spine (``consilium``) and the
same ingest/embed/store machinery (``ragpack``) that the IETF RFC vertical uses, kept
here to show the architecture is not specific to one corpus.

This module previously relied on PEP 420 implicit-namespace behaviour, which worked
only because the repo root happened to be on ``sys.path``. It is a real package now,
so ``import chainrag`` resolves to this file rather than to whatever directory named
``chainrag`` the interpreter found first.
"""
