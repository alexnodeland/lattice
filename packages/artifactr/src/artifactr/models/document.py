"""Generate Product Requirements Documents (PRDs) from natural language."""

from dataclasses import dataclass
from typing import Literal, TypeVar

from pydantic import BaseModel

ProductStage = Literal["MVP", "growth", "scale"]
T = TypeVar("T")


@dataclass
class HasReasoning:
    """A class that has a reasoning attribute."""

    reasoning: str


@dataclass
class Purpose(HasReasoning):
    """The purpose of the PRD."""

    purpose: str
    audience: str
    success_criteria: list[str]


@dataclass
class FeatureRequirement(HasReasoning):
    """A requirement for a feature."""

    requirement: str
    difficulty: Literal["easy", "medium", "hard"]
    hours_to_implement: float
    dependencies: list[str]
    optional: bool


@dataclass
class Deliverable(HasReasoning):
    """A deliverable for a feature."""

    name: str
    description: str
    success_criteria: list[str]


@dataclass
class Feature(HasReasoning):
    """A feature of the PRD."""

    name: str
    description: str
    requirements: list[FeatureRequirement]
    deliverables: list[Deliverable]
    priority: Literal["low", "medium", "high"]
    kpis: list[str]


@dataclass
class TimelineItem:
    """A timeline item for the PRD."""

    feature: Feature
    stage: ProductStage
    deadline_in_days: int


@dataclass
class MarketingItem(HasReasoning):
    """A marketing item for the PRD."""

    name: str
    description: str
    channels: list[str]
    priority: Literal["low", "medium", "high"]


@dataclass
class MonetizationMethod(HasReasoning):
    """A method of monetization for the product."""

    name: str
    description: str
    audience: str
    total_addressable_market_size: str
    current_saturation_of_market_percent: float
    strength_score: float
    profit_margin_percent_estimate: float


@dataclass
class MonetizationStrategy(HasReasoning):
    """A monetization strategy for the product."""

    strategy: str
    methods: list[MonetizationMethod]
    risk_factors: list[str]
    risk_assessment: str


@dataclass
class ReleaseRequirement(HasReasoning):
    """A requirement that must be met before the initial release of the product."""

    feature: Feature
    acceptance_criteria: list[str]


@dataclass
class MarketingPlan(HasReasoning):
    """A marketing plan for the product."""

    plan: str
    timeline: list[MarketingItem]
    budget_in_dollars: int


@dataclass
class Constraint(HasReasoning):
    """A known technical, business, or other constraints that limit the solution space."""

    constraint: str


@dataclass
class Assumption(HasReasoning):
    """Key assumptions that must hold true for this product to succeed or be feasible."""

    assumption: str


@dataclass
class KPI(HasReasoning):
    """A high-level Key Performance Indicator for measuring product success."""

    kpi: str
    success_criteria: list[str]


class PRD(BaseModel):
    """A Product Requirements Document.

    A product requirements document (PRD) outlines the requirements and
    functionality of the product you're going to build so that your
    development team understands what they're building, who it's for,
    and the purpose it will serve for its end users.

    A Product Requirements Document (PRD) is crucial for aligning your
    development team and stakeholders on the product's goals and specifications.
    """

    title: str
    description: str

    purpose: Purpose
    features: list[Feature]
    timeline: list[TimelineItem]
    monetization_strategy: MonetizationStrategy
    release_requirements: list[ReleaseRequirement]
    marketing_plan: MarketingPlan
    constraints: list[Constraint]
    assumptions: list[Assumption]
    kpis: list[KPI]
