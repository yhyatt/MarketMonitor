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
from .collectors import ArxivCollector, HuggingFaceCollector, GitHubRadar, AlphaSignalCollector, AITLDRCollector
from .filters import KeywordFilter, Deduplicator
from .store import PaperLogger, GitHubLogger, HFLogger, AITLDRLogger
from .digest import DigestFormatter, TelegramSender, EmailSender
from .health import run_health_check, PipelineHealth
from .logging_utils import get_logger


def cmd_scan(config: Config, dry_run: bool = False) -> dict:
    """Scan all sources and log new items."""
    logger = get_logger()
    logger.log_pipeline_start("scan")

    print("=" * 50)
    print("SCAN: Collecting from all sources")
    print("=" * 50)

    results = {
        "arxiv": 0,
        "huggingface": 0,
        "github": 0,
        "alphasignal": 0,
        "aitldr": 0,
    }

    keyword_filter = KeywordFilter()
    dedup = Deduplicator(config)

    # Collect arXiv papers
    print("\n[1/5] Scanning arXiv...")
    logger.log_collector_start("arXiv")
    arxiv = ArxivCollector(config)
    arxiv_papers = arxiv.collect()
    print(f"  Found {len(arxiv_papers)} papers")

    arxiv_filtered = keyword_filter.filter(arxiv_papers)
    print(f"  After keyword filter: {len(arxiv_filtered)}")

    arxiv_deduped = dedup.filter(arxiv_filtered)
    print(f"  After dedup: {len(arxiv_deduped)}")

    if not dry_run and arxiv_deduped:
        # Score and log — limit to top 20 by relevance to avoid API timeout
        try:
            from .filters import LLMScorer
            scorer = LLMScorer(config)
            # Pre-trim to avoid scoring 100+ papers (timeout risk)
            arxiv_to_score = arxiv_deduped[:20]
            logger.log_scoring_start(len(arxiv_to_score))
            scored = scorer.filter_by_threshold(arxiv_to_score, threshold=config.score_threshold, max_items=config.max_digest_items)
            logger.log_scoring_end(len(arxiv_to_score), len(scored))
            paper_logger = PaperLogger(config)
            results["arxiv"] = paper_logger.log_batch(scored)
            print(f"  Logged {results['arxiv']} papers")
            logger.log_collector_end("arXiv", results["arxiv"], status="ok")
        except Exception as e:
            print(f"  Scoring error (API key missing?): {e}")
            logger.log_collector_end("arXiv", 0, status="error", error=str(e))
            results["arxiv"] = 0
    else:
        logger.log_collector_end("arXiv", len(arxiv_deduped), status="ok" if arxiv_deduped else "degraded")

    # Collect HuggingFace items
    print("\n[2/5] Scanning HuggingFace...")
    logger.log_collector_start("HuggingFace")
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
            # Pre-trim HF items to avoid timeout (models + papers can be 100+)
            hf_to_score = hf_deduped[:25]
            logger.log_scoring_start(len(hf_to_score))
            scored = scorer.filter_by_threshold(hf_to_score, threshold=config.score_threshold, max_items=config.max_digest_items)
            logger.log_scoring_end(len(hf_to_score), len(scored))
            hf_logger = HFLogger(config)
            results["huggingface"] = hf_logger.log_batch(scored)
            print(f"  Logged {results['huggingface']} items")
            logger.log_collector_end("HuggingFace", results["huggingface"], status="ok")
        except Exception as e:
            print(f"  Scoring error: {e}")
            logger.log_collector_end("HuggingFace", 0, status="error", error=str(e))
            results["huggingface"] = 0
    else:
        logger.log_collector_end("HuggingFace", len(hf_deduped), status="ok" if hf_deduped else "degraded")

    # Collect GitHub signals
    print("\n[3/5] Scanning GitHub...")
    logger.log_collector_start("GitHub")
    github = GitHubRadar(config)
    signals = github.collect()
    flagged = [s for s in signals if s.flagged]
    print(f"  Tracked {len(signals)} repos, {len(flagged)} flagged")

    if not dry_run and flagged:
        gh_logger = GitHubLogger(config)
        results["github"] = gh_logger.log_flagged(signals)
        print(f"  Logged {results['github']} signals")
        logger.log_collector_end("GitHub", results["github"], status="ok")
    else:
        logger.log_collector_end("GitHub", len(flagged), status="ok" if flagged else "degraded")

    # Collect AlphaSignal emails
    print("\n[4/5] Scanning AlphaSignal...")
    logger.log_collector_start("AlphaSignal")
    alpha = AlphaSignalCollector(config)
    alpha_items = alpha.collect()
    print(f"  Found {len(alpha_items)} items")
    results["alphasignal"] = len(alpha_items)
    logger.log_collector_end("AlphaSignal", results["alphasignal"], status="ok" if alpha_items else "degraded")

    # Collect AI/TLDR
    print("\n[5/5] Scanning AI/TLDR...")
    logger.log_collector_start("AI/TLDR")
    aitldr = AITLDRCollector(config)
    aitldr_items = aitldr.collect()
    print(f"  Found {len(aitldr_items)} items")

    if not dry_run and aitldr_items:
        aitldr_filtered = keyword_filter.filter(aitldr_items)
        aitldr_logger = AITLDRLogger(config)
        results["aitldr"] = aitldr_logger.log_batch(aitldr_filtered)
        print(f"  Logged {results['aitldr']} items")
        logger.log_collector_end("AI/TLDR", results["aitldr"], status="ok")
    else:
        results["aitldr"] = len(aitldr_items)
        logger.log_collector_end("AI/TLDR", results["aitldr"], status="ok" if aitldr_items else "degraded")

    print("\n" + "=" * 50)
    print(f"SCAN COMPLETE: arxiv={results['arxiv']}, hf={results['huggingface']}, github={results['github']}, alpha={results['alphasignal']}, aitldr={results['aitldr']}")
    logger.log_pipeline_end("scan", "ok")

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
    aitldr_logger = AITLDRLogger(config)

    papers = paper_logger.get_unsent()
    hf_items = hf_logger.get_unsent()
    github_signals = github_logger.get_unsent_flagged()
    aitldr_items = aitldr_logger.get_unsent()

    print(f"Unsent items: {len(papers)} papers, {len(hf_items)} HF items, {len(github_signals)} GitHub signals, {len(aitldr_items)} AI/TLDR")

    if not papers and not hf_items and not github_signals and not aitldr_items:
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
        aitldr_items=aitldr_items[:10],
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
        emailer = EmailSender(config, email_to, digest.subject)
        if emailer.send(digest.html, html=True):
            print("Email sent!")
        else:
            print("Email send failed")

    # Mark items as sent
    if telegram_id or email_to:
        paper_ids = [p.get("arxiv_id") for p in papers if p.get("arxiv_id")]
        hf_ids = [h.get("id") for h in hf_items if h.get("id")]
        repo_names = [g.get("repo") for g in github_signals if g.get("repo")]
        aitldr_ids = [a.get("id") for a in aitldr_items if a.get("id")]

        paper_logger.mark_sent(paper_ids)
        hf_logger.mark_sent(hf_ids)
        github_logger.mark_sent(repo_names)
        aitldr_logger.mark_sent(aitldr_ids)
        print(f"\nMarked {len(paper_ids)} papers, {len(hf_ids)} HF items, {len(repo_names)} signals, {len(aitldr_ids)} AI/TLDR items as sent")

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
    print(f"  MOONSHOT_API_KEY: {'set' if config.moonshot_api_key else 'not set'}")
    print(f"  GITHUB_TOKEN: {'set' if config.github_token else 'not set'}")
    print("  # gws uses file-based auth else 'not set'}")


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
        choices=["scan", "digest", "run", "status", "health", "test"],
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
    elif args.command == "health":
        report = run_health_check(config)
        print(report.to_json())
        # Also print Telegram-formatted version for easy copy
        print("\n--- Telegram format ---\n")
        print(report.to_telegram())
    elif args.command == "test":
        cmd_test(config)


if __name__ == "__main__":
    main()
