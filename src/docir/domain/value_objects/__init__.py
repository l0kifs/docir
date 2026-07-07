# Value objects — immutable, self-validating values without identity.
#
#   * identifiers — DocId (`<type-prefix>-NNNN`) parsing and formatting.
#   * embedding   — a dense semantic vector plus cosine-similarity math.
#   * results     — read-side records (SearchHit, ScoredDocument) returned by
#                   the search / context read paths.
