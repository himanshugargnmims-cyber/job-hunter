"""
Nexus RevOps & Strategic Intelligence Toolkit

Modular suite for B2B SaaS revenue operations, pipeline modeling,
forecasting error reduction (MAPE), and ICP scoring matrices.
"""

from .forecasting_engine import RevenueForecaster
from .pipeline_velocity import PipelineVelocityCalculator
from .lead_icp_scorer import ICPScoringEngine
from .executive_kpi_dashboard import ExecutiveDashboardGenerator

__all__ = [
    "RevenueForecaster",
    "PipelineVelocityCalculator",
    "ICPScoringEngine",
    "ExecutiveDashboardGenerator"
]
