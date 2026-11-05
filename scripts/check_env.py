"""Check that each external service answers. Run: python -m scripts.check_env [service ...]"""

import sys


def check_anthropic() -> str:
    raise NotImplementedError("filled in phase 1")


def check_supabase() -> str:
    raise NotImplementedError("filled in phase 1")


def check_hubspot() -> str:
    raise NotImplementedError("filled in phase 1")


CHECKS = {
    "anthropic": check_anthropic,
    "supabase": check_supabase,
    "hubspot": check_hubspot,
}


def main(names: list[str]) -> int:
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        print(f"unknown service: {', '.join(unknown)}. Options: {', '.join(CHECKS)}")
        return 2
    failed = 0
    for name in names or CHECKS:
        # Report every service, not just the first failure, so one run shows what is missing.
        try:
            print(f"{name}: ok ({CHECKS[name]()})")
        except RuntimeError as exc:
            failed += 1
            print(f"{name}: FAIL ({type(exc).__name__}: {exc})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
