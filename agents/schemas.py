from pydantic import BaseModel, Field

class SpecialistReview(BaseModel):
    vote: str = Field(description="Must be exactly 'approved' or 'rejected'")
    critique: str = Field(description="If rejected, provide the technical reason. If approved, leave empty.")
    line_numbers: list[int] = Field(description="The specific lines of code causing the issue.")