# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""Performance-focused version matching API for m2.

This module mirrors the public API from ``conda.models.version`` so callers can
swap implementations transparently.
"""

from __future__ import annotations

from ..models.version import (  # noqa: F401
    OPERATOR_MAP,
    OPERATOR_START,
    BaseSpec,
    BuildNumberMatch,
    VersionMatch,
    VersionOrder,
    VersionSpec,
    compatible_release_operator,
    normalized_version,
    treeify,
    untreeify,
    ver_eval,
)
