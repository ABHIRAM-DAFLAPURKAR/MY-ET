import hashlib
from typing import Any, Dict, List


CACHED_ARTICLES: List[Dict[str, Any]] = [
    {
        "title": "RBI policy signals reshape borrowing expectations for Indian corporates",
        "content": "Companies are reassessing borrowing costs, liquidity plans, and treasury hedges after new RBI policy cues and inflation commentary.",
        "url": "https://economictimes.indiatimes.com/markets/bonds/india-bonds-steady-as-supply-overhang-caps-treasury-driven-gains/articleshow/128408765.cms?from=mdr",
        "published_at": "2026-03-26T08:00:00Z",
        "source": "Economic Times Wire",
        "description": "Macro policy implications for finance leaders and market participants.",
    },
    {
        "title": "Sensex rally lifts mutual fund sentiment as SIP investors stay disciplined",
        "content": "A broad market rally is improving investor confidence, but advisers continue to recommend long-term SIP discipline and diversification.",
        "url": "https://m.economictimes.com/mf/analysis/mf-tracker-this-flexicap-fund-turns-rs-10000-sip-to-rs-1-35-crore-in-over-2-decades/articleshow/129692031.cms",
        "published_at": "2026-03-26T08:15:00Z",
        "source": "ET Markets",
        "description": "Portfolio relevance for retail and mutual fund investors.",
    },
    {
        "title": "Indian SaaS startups watch rival pricing moves after new funding round",
        "content": "A fresh funding round is giving several SaaS players more room to experiment with pricing, distribution, and product bundling.",
        "url": "https://m.economictimes.com/tech/funding/saas-startup-rocketlane-raises-60-million-from-insight-partners-for-ai-push/articleshow/129800423.cms",
        "published_at": "2026-03-26T08:35:00Z",
        "source": "Startup Desk",
        "description": "Competitive and GTM implications for founders.",
    },
    {
        "title": "What inflation actually means for first-time investors building an SIP",
        "content": "Inflation affects purchasing power, expected returns, and asset allocation. New investors need plain-language guidance on what to do next.",
        "url": "https://www.fidelity.com/learning-center/personal-finance/what-is-inflation?cccampaign=Other_RealTime&ccchannel=social_organic&cccreative=&ccdate=202209&ccformat=link&ccmedia=Twitter&sf260427720=1",
        "published_at": "2026-03-26T08:45:00Z",
        "source": "ExplainET",
        "description": "Explainer-first investing context for beginners.",
    },
    {
        "title": "Treasury teams revisit cash strategy as bond yields stay elevated",
        "content": "Persistent bond-yield pressure is changing how CFOs think about working capital, debt servicing, and short-term cash deployment.",
        "url": "https://economictimes.indiatimes.com/markets/bonds/short-term-yields-fall-on-surplus-liquidity/articleshow/128401582.cms",
        "published_at": "2026-03-26T09:00:00Z",
        "source": "Policy Ledger",
        "description": "Board-ready macro and treasury implications.",
    },
    {
        "title": "Student guide: why startup layoffs and funding winters happen",
        "content": "Layoffs and funding winters often happen when growth expectations change, capital gets expensive, and investors become more selective.",
        "url": "https://techcrunch.com/2023/12/06/startup-december-layoffs/",
        "published_at": "2026-03-26T09:10:00Z",
        "source": "Campus Brief",
        "description": "Foundational explainer for students tracking business news.",
    },
    {
        "title": "Fintech founders monitor compliance costs after new policy discussion",
        "content": "Founders in fintech are recalculating compliance overhead, product speed, and partner-bank dependencies after fresh policy commentary.",
        "url": "https://bfsi.economictimes.indiatimes.com/news/articles/how-compliance-is-transforming-indian-fintech-into-a-competitive-advantage/128137397",
        "published_at": "2026-03-26T09:25:00Z",
        "source": "Founder Daily",
        "description": "Funding, competitor, and product risk angles for operators.",
    },
    {
        "title": "Explained: why market volatility matters less when your horizon is long",
        "content": "Volatility can feel alarming, but long investment horizons and regular SIPs can reduce the pressure to time the market.",
        "url": "https://corporate.vanguard.com/content/corporatesite/us/en/corp/market-volatility.html",
        "published_at": "2026-03-26T09:35:00Z",
        "source": "Investor Classroom",
        "description": "Beginner-friendly explainer for first-generation investors.",
    },
    {
        "title": "Competitor launch pushes D2C founders to rethink bundling and retention",
        "content": "A new D2C launch is shifting category pricing and retention tactics, forcing founders to revisit offer design and lifecycle messaging.",
        "url": "https://m.economictimes.com/tech/technology/vcs-hit-jackpot-as-fmcg-giants-go-on-d2c-acquisition-spree/amp_articleshow/128761488.cms",
        "published_at": "2026-03-26T09:50:00Z",
        "source": "Growth Memo",
        "description": "Competitive movement and execution implications for founders.",
    },
    {
        "title": "Macro explainer: how rate expectations influence equity valuations",
        "content": "Rate expectations change discount rates, financing conditions, and risk appetite, which can alter how equities are valued across sectors.",
        "url": "https://www.ubs.com/us/en/wealth-management/insights/market-news/article.3027064.html",
        "published_at": "2026-03-26T10:00:00Z",
        "source": "Macro Classroom",
        "description": "A bridge between macro policy and portfolio impact.",
    },
    {
        "title": "Portfolio watch: sector rotation emerges as earnings and policy signals diverge",
        "content": "Investors are reassessing sector exposure as earnings quality, macro signals, and policy expectations pull leadership in different directions.",
        "url": "https://m.economictimes.com/markets/expert-view/wait-or-buy-anand-tandons-sector-by-sector-verdict-for-nervous-investors/articleshow/129816015.cms",
        "published_at": "2026-03-26T10:10:00Z",
        "source": "Market Pulse",
        "description": "Portfolio-relevant story for mutual fund and direct equity investors.",
    },
    {
        "title": "Beginner market brief: three terms behind today's top business headline",
        "content": "This explainer breaks down yield, inflation, and liquidity in plain language so students and first-time investors can follow the headline.",
        "url": "https://www.forbes.com/advisor/investing/what-is-inflation/",
        "published_at": "2026-03-26T10:20:00Z",
        "source": "ET Learn",
        "description": "Low-jargon breakdown for students and novice investors.",
    },
]


def get_fast_articles(num_articles: int = 18, query: str = "economy", page: int = 1) -> List[Dict[str, Any]]:
    ordered = sorted(
        CACHED_ARTICLES,
        key=lambda article: hashlib.md5(
            f"{query}:{page}:{article['url']}".encode("utf-8", errors="ignore")
        ).hexdigest(),
    )
    rotation = ((max(1, page) - 1) * 4) % len(ordered)
    rotated = ordered[rotation:] + ordered[:rotation]
    return rotated[: min(num_articles, len(rotated))]
