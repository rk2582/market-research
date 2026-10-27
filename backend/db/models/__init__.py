"""Import every model here so Base.metadata knows all tables (used by Alembic and tests)."""

from db.models.research import CompanyRow, ResearchRunRow, ResearchSourceRow, RunCompetitorRow

__all__ = ["CompanyRow", "ResearchRunRow", "ResearchSourceRow", "RunCompetitorRow"]
