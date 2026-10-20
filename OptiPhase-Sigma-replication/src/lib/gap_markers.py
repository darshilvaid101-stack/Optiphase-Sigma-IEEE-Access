"""Extended gap tier: limitation discourse markers and compiler-specific cluster keyword rules, documented.

The strict tier uses the 30 patterns in config/gap_regex_patterns.json only. The extended tier widens recall
with limitation discourse cues, then assigns each sentence to the cluster whose compiler-specific keywords it
matches most. Generic words (for example "overhead" or "workload") are deliberately absent from the cluster
keywords: in hardware and systems abstracts they describe runtime costs, which is not the compile-time
or benchmark-generalisation sense of clusters G4 and G6.
"""

import re

EXTENDED_MARKERS = (
    r"\b(?:limitations?|limited|limits?|drawbacks?|shortcomings?|weakness(?:es)?|caveats?|pitfalls?|bottlenecks?)\b",
    r"\b(?:fails?|failed|failing|unable|cannot|does not|do not|did not|not (?:yet )?"
    r"(?:address|account for|consider|model|support|handle|cover|evaluate|capture))\b",
    r"\b(?:remains?|remain|left) (?:open|unexplored|unclear|unknown|unaddressed|unresolved)\b",
    r"\b(?:lacks?|lacking|absence of|no support for|no means to)\b",
    r"\b(?:only (?:evaluated|tested|considered|supports?|applies|applicable)|restricted to|limited to|confined to)\b",
    r"\b(?:neglects?|neglected|ignores?|ignored|overlooks?|overlooked|omits?|omitted|misses?|missed)\b",
    r"\b(?:future work|left for future|remains? to be|we leave|open problem|open question)\b",
)
CLUSTER_KEYWORDS = {
    "G1": (
        r"phase[- ]ordering", r"pass[- ]ordering", r"pass manager", r"pass (?:interactions?|pipelines?)",
        r"(?:analysis|analyses) (?:invalidation|preservation|caching)", r"invalidat\w* (?:the )?analys",
        r"ScalarEvolution|\bSCEV\b", r"dominator tree|DominatorTree", r"alias analysis",
        r"pass interference|destructive pass",
    ),
    "G2": (
        r"instruction count", r"static (?:size|instructions?|code size)", r"code size", r"vectori[sz]\w*",
        r"loop unroll\w*", r"\bSIMD\b", r"register pressure", r"\bspill\w*", r"loop depth", r"vector width",
    ),
    "G3": (
        r"translation validation", r"miscompil\w*", r"refinement", r"soundness", r"undefined behaviou?r",
        r"\bUB\b", r"\bpoison\b", r"\bSMT\b", r"\bAlive2?\b", r"equivalence (?:check|proof)s?",
        r"verified compiler", r"formal(?:ly)? verif\w*",
    ),
    "G4": (
        r"compil(?:e|ation)[- ]time", r"build time", r"compilation (?:overhead|cost|speed)",
        r"redundant (?:pass|passes|optimi[sz]ations?)", r"idempoten\w*", r"fixed[- ]point",
        r"pass (?:bloat|pruning|execution)", r"optimi[sz]ation (?:time|overhead)",
    ),
    "G5": (
        r"multi[- ]?objective", r"\bPareto\b", r"trade-?offs?", r"scalari[sz]\w*", r"weighted sum",
        r"hypervolume", r"single[- ]objective", r"objective (?:function|trade)",
    ),
    "G6": (
        r"PolyBench", r"MiBench", r"micro-?benchmarks?", r"synthetic (?:benchmarks?|loops?|kernels?)",
        r"cross-suite", r"generali[sz]\w* (?:to|across) (?:real|other|diverse|unseen)",
        r"real-world (?:programs?|applications?|code)", r"benchmark (?:suites?|diversity|coverage)",
        r"overfit\w*", r"SPEC CPU",
    ),
}
CONTRAST_CUES = (
    r"\b(?:however|although|though|despite|unlike|whereas|but|while|nevertheless|nonetheless|yet|without|"
    r"nor|neither|not|no|rather than|instead of|versus)\b",
)
PROBLEM_CUES = (
    r"\b(?:challenges?|challenging|difficult|hard|hinder\w*|impede\w*|suboptimal|sub-optimal|"
    r"inefficien\w*|poor|degrad\w*|overhead|costly|expensive|slow\w*|inaccura\w*|imprecis\w*|incomplete|"
    r"insufficient|inadequate|gaps?|needs?|requires?|requiring)\b",
)
COMPILED_CUES = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in CONTRAST_CUES + PROBLEM_CUES
)
COMPILED_MARKERS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in EXTENDED_MARKERS)
COMPILED_CLUSTERS = {
    cluster: tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    for cluster, patterns in CLUSTER_KEYWORDS.items()
}
# Candidate tier: broader keywords. Their precision is measured by a fixed-sample audit (see the summary).
BROAD_CLUSTER_KEYWORDS = {
    "G1": (
        r"phase[- ]ordering", r"pass[- ]ordering", r"pass manager", r"pass interaction", r"interference",
        r"invalidat", r"analys[ie]s", r"SCEV", r"ScalarEvolution", r"dominator", r"alias",
    ),
    "G2": (
        r"instruction count", r"code size", r"static (?:size|instructions?)", r"vectori[sz]", r"unroll",
        r"SIMD", r"register pressure", r"spill", r"loop depth", r"vector width", r"loop nest",
    ),
    "G3": (
        r"verif", r"soundness", r"miscompil", r"refinement", r"translation validation", r"undefined behavio",
        r"\bUB\b", r"poison", r"correctness", r"proof", r"formal", r"\bSMT\b", r"Alive",
    ),
    "G4": (
        r"compil(?:e|ation)[- ]?time", r"build time", r"overhead", r"redundant", r"idempot", r"fixed[- ]point",
        r"compilation (?:cost|time|overhead)", r"pass (?:bloat|pruning)", r"wall[- ]clock",
    ),
    "G5": (
        r"multi[- ]?objective", r"Pareto", r"trade-?off", r"scalari[sz]", r"weighted sum", r"objectives?",
        r"hypervolume", r"energy", r"single[- ]objective",
    ),
    "G6": (
        r"benchmark", r"generali[sz]", r"PolyBench", r"MiBench", r"workloads?", r"real[- ]world",
        r"overfit", r"synthetic", r"\bkernels?\b", r"embedded",
    ),
}
COMPILED_BROAD_CLUSTERS = {
    cluster: tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    for cluster, patterns in BROAD_CLUSTER_KEYWORDS.items()
}


def matched_markers(sentence):
    """Limitation markers and, when no marker fires, the contrast or problem cues that do."""
    markers = [pattern.pattern for pattern in COMPILED_MARKERS if pattern.search(sentence)]
    if markers:
        return markers
    return [pattern.pattern for pattern in COMPILED_CUES if pattern.search(sentence)]


def assign_cluster(sentence, compiled_clusters=COMPILED_CLUSTERS):
    """Return the cluster with the most keyword hits (ties go to the lower-numbered cluster), or None."""
    scores = {
        cluster: sum(1 for pattern in patterns if pattern.search(sentence))
        for cluster, patterns in compiled_clusters.items()
    }
    best_score = max(scores.values())
    if best_score == 0:
        return None
    return min(cluster for cluster, score in scores.items() if score == best_score)
