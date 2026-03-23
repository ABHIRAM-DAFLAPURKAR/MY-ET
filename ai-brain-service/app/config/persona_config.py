from app.services.model_loader import get_matcher

# Semantic anchor phrases (concept clusters → embedding centroid)
ANCHOR_TEXTS = {
    "investor": (
        "stock market KPI valuation revenue growth risk factors portfolio "
        "dividend inflation equity earnings macroeconomic"
    ),
    "founder": (
        "venture capital pivot product-market fit seed round scaling burn rate "
        "competitor funding traction runway startup"
    ),
    "student": (
        "how-to guide fundamentals introduction to explained simply career roadmap "
        "tutorial basics learn education beginner"
    ),
}

_matcher = get_matcher()
ANCHORS = {persona: _matcher.encode(text) for persona, text in ANCHOR_TEXTS.items()}

PERSONAS = ["student", "founder", "investor"]

# Experience prompts (instruction + raw text → transformer)
EXPERIENCE_PROMPTS = {
    "student": "simplify for a beginner: ",
    "founder": "analyze strategic impact for a startup: ",
    "investor": "extract financial KPIs and market risk: ",
}

PERSONA_PROMPTS = {
    "student": {
        "prefix": EXPERIENCE_PROMPTS["student"],
        "max_len": 72,
        "min_len": 28,
    },
    "founder": {
        "prefix": EXPERIENCE_PROMPTS["founder"],
        "max_len": 90,
        "min_len": 40,
    },
    "investor": {
        "prefix": EXPERIENCE_PROMPTS["investor"],
        "max_len": 90,
        "min_len": 40,
    },
}
