"""ICT Service - main orchestrator for market structure analysis."""

import time
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from uuid import UUID

from .schemas import (
    StructureResult,
    OHLCBar, ICTAnalysisRequest, ICTAnalysisResponse,
    StructureAnalysis, FVGAnalysis, OrderBlockAnalysis,
    LiquidityAnalysis, SessionAnalysis, ICTModelResult,
    MultiTimeframeBias, SetupScore, ExecutionDecision,
    MarketContext,
)
from .structure_engine import analyze_structure
from .fvg_engine import analyze_fvg
from .orderblock_engine import analyze_order_blocks
from .liquidity_engine import analyze_liquidity
from .session_engine import analyze_sessions
from .ict_models import detect_all_models
from .multi_timeframe import analyze_multi_timeframe
from .scoring_engine import score_setup, evaluate_execution


class ICTAnalyzer:
    """Main ICT analysis orchestrator - runs all engines on OHLC data."""

    def __init__(self, db: Optional[Session] = None, project_id: Optional[str] = None):
        self.db = db
        self.project_id = project_id

    def analyze(self, request: ICTAnalysisRequest) -> ICTAnalysisResponse:
        """Run complete ICT analysis on provided OHLC data."""
        start_time = time.time()
        response = ICTAnalysisResponse(
            symbol=request.symbol,
            timeframe=request.timeframe,
        )

        bars = request.bars
        if not bars:
            return response

        # 1. Structure Analysis
        response.structure = analyze_structure(bars, request.detect_swing_bars)

        # 2. FVG Analysis
        if request.include_fvg:
            response.fvg = analyze_fvg(bars)

        # 3. Order Block Analysis
        if request.include_order_blocks:
            response.order_blocks = analyze_order_blocks(bars)

        # 4. Liquidity Analysis
        if request.include_liquidity:
            response.liquidity = analyze_liquidity(bars, request.detect_swing_bars)

        # 5. Session Analysis
        if request.include_sessions:
            response.sessions = analyze_sessions(bars)

        # 6. ICT Model Detection
        if request.include_models:
            response.models = detect_all_models(
                bars,
                response.fvg.fvgs,
                response.order_blocks.order_blocks,
                response.liquidity.zones,
            )

        # 7. Multi-Timeframe (single TF for now)
        response.multi_timeframe = analyze_multi_timeframe(
            {request.timeframe: bars}
        )

        # 8. Scoring
        best_model = max(response.models, key=lambda m: m.quality_score) if response.models else None
        response.scores = score_setup(
            structure=response.structure,
            fvg=response.fvg,
            ob=response.order_blocks,
            liquidity=response.liquidity,
            session=response.sessions,
            model=best_model,
            htf_confluence=response.multi_timeframe.confluence_score,
        )

        # 9. Execution Decision
        response.execution = evaluate_execution(
            scores=response.scores,
            model=best_model,
            htf_bias=response.multi_timeframe.htf_bias,
            ltf_confirmation=response.multi_timeframe.ltf_confirmation,
            premium_discount=response.multi_timeframe.premium_discount,
        )

        # 10. Market Context (AI-ready)
        response.market_context = self._build_market_context(
            bars, response, best_model
        )

        response.analysis_time_ms = (time.time() - start_time) * 1000
        return response

    def _build_market_context(
        self,
        bars: list[OHLCBar],
        analysis: ICTAnalysisResponse,
        best_model: Optional[ICTModelResult],
    ) -> MarketContext:
        """Build structured market context for AI consumption."""
        current_price = bars[-1].close if bars else 0
        ctx = MarketContext(
            symbol=analysis.symbol,
            current_price=current_price,
            htf_bias=analysis.multi_timeframe.htf_bias,
            ltf_bias=analysis.multi_timeframe.ltf_confirmation,
            premium_discount=analysis.multi_timeframe.premium_discount,
            confluence=analysis.multi_timeframe.confluence_score,
        )

        # Current structure summary
        ctx.current_structure = {
            "trend": analysis.structure.trend,
            "protected_high": analysis.structure.protected_high,
            "protected_low": analysis.structure.protected_low,
            "last_bos": analysis.structure.last_bos,
            "last_mss": analysis.structure.last_mss,
        }

        # Best setup
        if best_model:
            ctx.best_setup = {
                "type": best_model.model_type,
                "direction": best_model.direction,
                "quality": best_model.quality_score,
                "entry": {
                    "min": best_model.entry_price_min,
                    "max": best_model.entry_price_max,
                },
                "stop_loss": best_model.stop_loss,
                "take_profit": best_model.take_profit,
                "risk_reward": best_model.risk_reward_ratio,
            }

        # Key levels
        key_levels = set()
        for s in analysis.structure.swing_points:
            key_levels.add(round(s.price, 4))
        for f in analysis.fvg.fvgs:
            key_levels.add(round(f.midpoint, 4))
        for b in analysis.order_blocks.order_blocks:
            key_levels.add(round(b.midpoint, 4))
        ctx.key_levels = sorted(key_levels)[:20]

        # Weak areas (touched FVGs, mitigated OBs)
        weak_areas = []
        for f in analysis.fvg.fvgs:
            if f.status in ("partially_filled", "filled"):
                weak_areas.append({
                    "type": f"fvg_{f.status}",
                    "price": f.midpoint,
                    "strength": f.reaction_strength,
                })
        for b in analysis.order_blocks.order_blocks:
            if b.is_mitigated:
                weak_areas.append({
                    "type": "mitigated_ob",
                    "price": b.midpoint,
                    "strength": b.reaction_strength,
                })
        ctx.weak_areas = weak_areas

        # Invalidation levels
        invalidation = []
        if analysis.structure.protected_high:
            invalidation.append(analysis.structure.protected_high)
        if analysis.structure.protected_low:
            invalidation.append(analysis.structure.protected_low)
        for m in analysis.models:
            if m.stop_loss:
                invalidation.append(m.stop_loss)
        ctx.invalidation_levels = sorted(set(round(x, 4) for x in invalidation))[:10]

        # Session info
        ctx.session_info = {
            "current": analysis.sessions.current_session,
            "kill_zone": analysis.sessions.current_kill_zone,
            "silver_bullet": analysis.sessions.is_silver_bullet_window,
        }

        # Recent events
        recent_events = []
        for s in analysis.structure.structures[-5:]:
            recent_events.append({
                "type": s.type,
                "price": s.price,
                "confidence": s.confidence_score,
            })
        ctx.recent_events = recent_events

        # Executive reasoning
        reasoning_parts = []
        reasoning_parts.append(
            f"{analysis.symbol} is in a {analysis.structure.trend} structure "
            f"on {analysis.timeframe}"
        )
        if analysis.multi_timeframe.htf_bias != "neutral":
            reasoning_parts.append(
                f"HTF bias is {analysis.multi_timeframe.htf_bias}"
            )
        if analysis.execution.status == "ready":
            reasoning_parts.append(f"Best setup: {best_model.model_type} ({best_model.direction})")
        reasoning_parts.append(f"Execution: {analysis.execution.status}")
        ctx.reasoning = ". ".join(reasoning_parts)

        return ctx


class ICTPersistenceService:
    """Service for persisting and querying ICT data in the database."""

    def __init__(self, db: Session, project_id: str):
        self.db = db
        self.project_id = project_id

    def save_structure(self, structure: StructureResult) -> None:
        """Save a detected structure to database."""
        from .models import ICTStructure
        model = ICTStructure(
            project_id=self.project_id,
            symbol="",
            timeframe="",
            structure_type=structure.type,
            price=structure.price,
            timestamp=structure.timestamp,
            bar_index=structure.bar_index,
            strength_score=structure.strength_score,
            confidence_score=structure.confidence_score,
        )
        self.db.add(model)

    def get_recent_structures(self, limit: int = 20) -> list[dict]:
        """Get most recent structures from database."""
        from .models import ICTStructure
        results = self.db.query(ICTStructure).filter(
            ICTStructure.project_id == self.project_id
        ).order_by(desc(ICTStructure.timestamp)).limit(limit).all()
        return [_dict(r) for r in results]


def _dict(obj):
    """Convert SQLAlchemy model to dict."""
    if obj is None:
        return None
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
