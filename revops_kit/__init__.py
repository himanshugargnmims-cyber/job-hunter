"""
Nexus RevOps & Strategic Intelligence Toolkit

Modular suite for B2B SaaS revenue operations, pipeline modeling,
forecasting error reduction (MAPE), ICP scoring matrices, sales comp modeling,
deal desk governance, and full-funnel cohort diagnostics.
"""

from .forecasting_engine import RevenueForecaster
from .pipeline_velocity import PipelineVelocityCalculator
from .lead_icp_scorer import ICPScoringEngine
from .executive_kpi_dashboard import ExecutiveDashboardGenerator
from .compensation_modeler import CompensationModeler
from .deal_desk_copilot import DealDeskCopilot
from .funnel_analyzer import FunnelAnalyzer

__all__ = [
    "RevenueForecaster",
    "PipelineVelocityCalculator",
    "ICPScoringEngine",
    "ExecutiveDashboardGenerator",
    "CompensationModeler",
    "DealDeskCopilot",
    "FunnelAnalyzer",
]
