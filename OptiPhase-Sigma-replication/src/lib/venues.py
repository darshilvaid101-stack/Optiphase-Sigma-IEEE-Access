"""Named venues and the OpenAlex source identifiers that index their papers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VenueSpec:
    """One named venue, the OpenAlex sources that index it, and an optional issue filter."""

    key: str
    full_name: str
    openalex_source_ids: tuple[str, ...]
    openalex_issue: str | None = None


VENUE_SPECS = (
    VenueSpec(
        key="TACO",
        full_name="ACM Transactions on Architecture and Code Optimization",
        openalex_source_ids=("S26056741",),
    ),
    VenueSpec(
        key="CGO",
        full_name="IEEE/ACM International Symposium on Code Generation and Optimization",
        openalex_source_ids=("S7407088242", "S7407087452"),
    ),
    VenueSpec(
        key="PLDI",
        full_name="ACM SIGPLAN Conference on Programming Language Design and Implementation",
        openalex_source_ids=("S4210216081",),
        openalex_issue="PLDI",
    ),
    VenueSpec(
        key="ASPLOS",
        full_name="ACM International Conference on Architectural Support for "
        "Programming Languages and Operating Systems",
        openalex_source_ids=("S7407086669", "S7407087580", "S4306417705"),
    ),
    VenueSpec(
        key="CC",
        full_name="ACM SIGPLAN International Conference on Compiler Construction",
        openalex_source_ids=("S7407086238",),
    ),
    VenueSpec(
        key="PACT",
        full_name="International Conference on Parallel Architectures and Compilation Techniques",
        openalex_source_ids=("S4306419751",),
    ),
    VenueSpec(
        key="Supercomputing",
        full_name="The Journal of Supercomputing",
        openalex_source_ids=("S32326811",),
    ),
)
