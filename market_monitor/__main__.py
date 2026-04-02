"""CLI for market-monitor.

Usage:
    python3 -m market_monitor scan       # Scan all sources
    python3 -m market_monitor digest     # Generate and send digest
    python3 -m market_monitor run        # Full pipeline: scan + digest
    python3 -m market_monitor status     # Show current state
    python3 -m market_monitor test       # Dry-run scan
"""

import argparse
import sys
from datetime import datetime, timezone
from typing import Optional

from .config import Config
from .collectors import ArxivCollector, HuggingFaceCollector, GitHubRadar, AlphaSignalCollector
from .filters import KeywordFilter, Deduplicator
from .store import PaperLogger, GitHubLogger, HFLogger
from .digest import DigestFormatter, TelegramSender, EmailSender


def cmd_scan(config: Config, dry_run: bool = False) -> dict:
    """Scan all sources and log new items."""
    print("=" * 50)
    print("SCAN: Collecting from all sources")
    print("=" * 50)

    results = {
        "arxiv": 0,
        "huggingface": 0,
        "github": 0,
        "alphasignal": 0,
    }

    keyword_filter = KeywordFilter()
    dedup = Deduplicator(config)

    # Collect arXiv papers
    print("\n[1/4] Scanning arXiv...")
    arxiv = ArxivCollector(config)
    arxiv_papers = arxiv.collect()
    print(f"  Found {len(arxiv_papers)} papers")

    arxiv_filtered = keyword_filter.filter(arxiv_papers)
    print(f"  After keyword filter: {len(arxiv_filtered)}")

    arxiv_deduped = dedup.filter(arxiv_filtered)
    print(f"  After dedup: {len(arxiv_deduped)}")

    if not dry_run and arxiv_deduped:
        # Score and log
        try:
            from .filters import LLMScorer
            scorer = LLMScorer(config)
            scored = scorer.filter_by_threshold(arxiv_deduped, threshold=config.score_threshold, max_items=config.max_digest_items)
            logger = PaperLogger(config)
            results["arxiv"] = logger.log_batch(scored)
            print(f"  Logged {results['arxiv']} papers")
        except Exception as e:
            print(f"  Scoring error (API key missing?): {e}")
            results["arxiv"] = 0

    # Collect HuggingFace items
    print("\n[2/4] Scanning HuggingFace...")
    hf = HuggingFaceCollector(config)
    hf_items = hf.collect()
    print(f"  Found {len(hf_items)} items")

    hf_filtered = keyword_filter.filter(hf_items)
    print(f"  After keyword filter: {len(hf_filtered)}")

    hf_deduped = dedup.filter(hf_filtered)
    print(f"  After dedup: {len(hf_deduped)}")

    if not dry_run and hf_deduped:
        try:
            from .filters import LLMScorer
            scorer = LLMScorer(config)
            scored = scorer.filter_by_threshold(hf_deduped, threshold=config.score_threshold, max_items=config.max_digest_items)
            logger = HFLogger(config)
            results["huggingface"] = logger.log_batch(scored)
            print(f"  Logged {results['huggingface']} items")
        except Exception as e:
            print(f"  Scoring error: {e}")
            results["huggingface"] = 0

    # Collect GitHub signals
    print("\n[3/4] Scanning GitHub...")
    github = GitHubRadar(config)
    signals = github.collect()
    flagged = [s for s in signals if s.flagged]
    print(f"  Tracked {len(signals)} repos, {len(flagged)} flagged")

    if not dry_run and flagged:
        logger = GitHubLogger(config)
        results["github"] = logger.log_flagged(signals)
        print(f"  Logged {results['github']} signals")

    # Collect AlphaSignal emails
    print("\n[4/4] Scanning AlphaSignal...")
    alpha = AlphaSignalCollector(config)
    alpha_items = alpha.collect()
    print(f"  Found {len(alpha_items)} items")
    results["alphasignal"] = len(alpha_items)

    print("\n" + "=" * 50)
    print(f"SCAN COMPLETE: arxiv={results['arxiv']}, hf={results['huggingface']}, github={results['github']}, alpha={results['alphasignal']}")

    return results


def cmd_digest(
    config: Config,
    telegram_id: Optional[str] = None,
    email_to: Optional[str] = None,
) -> bool:
    """Generate and send digest."""
    print("=" * 50)
    print("DIGEST: Generating weekly digest")
    print("=" * 50)

    # Load unsent items from stores
    paper_logger = PaperLogger(config)
    hf_logger = HFLogger(config)
    github_logger = GitHubLogger(config)

    papers = paper_logger.get_unsent()
    hf_items = hf_logger.get_unsent()
    github_signals = github_logger.get_unsent_flagged()

    print(f"Unsent items: {len(papers)} papers, {len(hf_items)} HF items, {len(github_signals)} GitHub signals")

    if not papers and not hf_items and not github_signals:
        print("No new items to digest")
        return False

    # Convert dicts back to ScoredItem-like objects for formatting
    from dataclasses import dataclass

    @dataclass
    class MockOriginal:
        title: str = ""
        name: str = ""
        url: str = ""
        type: str = "paper"
        arxiv_id: str = ""
        id: str = ""

    @dataclass
    class MockScored:
        original: MockOriginal
        score: int
        thesis: str
        themes: list
        strategic_signals: list
        why_it_matters: str

    @dataclass
    class MockGitHubSignal:
        repo: str
        stars: int
        delta_stars_7d: int
        velocity_pct: float
        flagged: bool
        url: str
        description: str = ""

    scored_papers = [
        MockScored(
            original=MockOriginal(
                title=p.get("title", ""),
                url=p.get("url", ""),
                arxiv_id=p.get("arxiv_id", ""),
            ),
            score=p.get("score", 0),
            thesis=p.get("thesis", ""),
            themes=p.get("themes", []),
            strategic_signals=p.get("strategic_signals", []),
            why_it_matters=p.get("why_it_matters", ""),
        )
        for p in papers
    ]

    scored_hf = [
        MockScored(
            original=MockOriginal(
                name=h.get("name", ""),
                url=h.get("url", ""),
                type=h.get("type", "item"),
                id=h.get("id", ""),
            ),
            score=h.get("score", 0),
            thesis=h.get("thesis", ""),
            themes=h.get("themes", []),
            strategic_signals=h.get("strategic_signals", []),
            why_it_matters=h.get("why_it_matters", ""),
        )
        for h in hf_items
    ]

    mock_signals = [
        MockGitHubSignal(
            repo=g.get("repo", ""),
            stars=g.get("stars", 0),
            delta_stars_7d=g.get("delta_stars_7d", 0),
            velocity_pct=g.get("velocity_pct", 0),
            flagged=g.get("flagged", True),
            url=g.get("url", ""),
            description=g.get("description", ""),
        )
        for g in github_signals
    ]

    # Generate synthesis
    weekly_synthesis = ""
    try:
        from .digest import WeeklySynthesizer
        synth = WeeklySynthesizer(config)
        weekly_synthesis = synth.synthesize(scored_papers, scored_hf, mock_signals)
    except Exception as e:
        print(f"Synthesis error: {e}")

    # Format digest
    formatter = DigestFormatter()
    digest = formatter.format(
        papers=scored_papers[:5],
        hf_items=scored_hf[:3],
        github_signals=mock_signals[:5],
        weekly_synthesis=weekly_synthesis,
    )

    print(f"\nDigest subject: {digest.subject}")
    print(f"Telegram message length: {len(digest.telegram)} chars")

    # Send Telegram
    if telegram_id:
        print(f"\nSending to Telegram {telegram_id}...")
        tg = TelegramSender()
        if tg.send_digest(telegram_id, digest.telegram):
            print("Telegram sent!")
        else:
            print("Telegram send failed")

    # Send email
    if email_to:
        print(f"\nSending email to {email_to}...")
        emailer = EmailSender(config)
        if emailer.send_digest(email_to, digest.subject, digest.html, digest.plain):
            print("Email sent!")
        else:
            print("Email send failed")

    # Mark items as sent
    if telegram_id or email_to:
        paper_ids = [p.get("arxiv_id") for p in papers if p.get("arxiv_id")]
        hf_ids = [h.get("id") for h in hf_items if h.get("id")]
        repo_names = [g.get("repo") for g in github_signals if g.get("repo")]

        paper_logger.mark_sent(paper_ids)
        hf_logger.mark_sent(hf_ids)
        github_logger.mark_sent(repo_names)
        print(f"\nMarked {len(paper_ids)} papers, {len(hf_ids)} HF items, {len(repo_names)} signals as sent")

    return True


def cmd_run(
    config: Config,
    telegram_id: Optional[str] = None,
    email_to: Optional[str] = None,
) -> bool:
    """Full pipeline: scan + digest."""
    scan_results = cmd_scan(config)
    print("\n")
    return cmd_digest(config, telegram_id, email_to)


def cmd_status(config: Config) -> None:
    """Show current state."""
    print("=" * 50)
    print("STATUS: Market Monitor")
    print("=" * 50)

    print(f"\nMemory directory: {config.memory_dir}")
    print(f"  papers.jsonl: {config.papers_jsonl.exists()}")
    print(f"  hf_releases.jsonl: {config.hf_releases_jsonl.exists()}")
    print(f"  github_signals.jsonl: {config.github_signals_jsonl.exists()}")
    print(f"  github_baseline.json: {config.github_baseline_json.exists()}")

    # Count records
    for path, name in [
        (config.papers_jsonl, "Papers"),
        (config.hf_releases_jsonl, "HF items"),
        (config.github_signals_jsonl, "GitHub signals"),
    ]:
        if path.exists():
            with open(path) as f:
                total = sum(1 for line in f if line.strip())
            with open(path) as f:
                unsent = sum(
                    1 for line in f
                    if line.strip() and not __import__("json").loads(line).get("digest_sent", False)
                )
            print(f"\n{name}: {total} total, {unsent} unsent")

    print(f"\nAPI tokens:")
    print(f"  ANTHROPIC_API_TOKEN: {'set' if config.anthropic_api_token else 'not set'}")
    print(f"  GITHUB_TOKEN: {'set' if config.github_token else 'not set'}")
    print(f"  GOG_KEYRING_PASSWORD: {'set' if config.gog_keyring_password else 'not set'}")


def cmd_test(config: Config) -> None:
    """Dry-run scan."""
    print("TEST MODE: Dry-run scan (no writes)")
    cmd_scan(config, dry_run=True)


def main():
    parser = argparse.ArgumentParser(
        description="Market Monitor - AI market intelligence service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  scan      Scan all sources and log new items
  digest    Generate and send weekly digest
  run       Full pipeline: scan + digest
  status    Show current state
  test      Dry-run scan (no writes)
""",
    )

    parser.add_argument(
        "command",
        choices=["scan", "digest", "run", "status", "test"],
        help="Command to execute",
    )
    parser.add_argument(
        "--telegram",
        help="Telegram chat ID for digest",
    )
    parser.add_argument(
        "--email",
        help="Email address for digest",
    )

    args = parser.parse_args()
    config = Config.from_env()
    config.ensure_memory_dir()

    if args.command == "scan":
        cmd_scan(config)
    elif args.command == "digest":
        cmd_digest(config, args.telegram, args.email)
    elif args.command == "run":
        cmd_run(config, args.telegram, args.email)
    elif args.command == "status":
        cmd_status(config)
    elif args.command == "test":
        cmd_test(config)


if __name__ == "__main__":
    main()
