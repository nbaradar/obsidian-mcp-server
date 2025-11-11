"""Pydantic input models for vault management operations.

This module defines input models for vault management tools:
- List configured vaults
- Set active vault for session
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ListVaultsInput(BaseModel):
    """Input model for list_vaults tool.

    Lists all configured vaults and session state. Takes no parameters,
    but using a model maintains API consistency.

    Examples:
        >>> ListVaultsInput()
    """

    # No fields required - this model exists for API consistency
    # All tools use Pydantic models even if they have no parameters

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [{}]
        }


class SetActiveVaultInput(BaseModel):
    """Input model for set_active_vault tool.

    Sets the active vault for the conversation session. All subsequent tool
    calls that omit the vault parameter will use this vault.

    Examples:
        >>> SetActiveVaultInput(vault="personal")
        >>> SetActiveVaultInput(vault="work")
    """

    vault: str = Field(
        min_length=1,
        description=(
            "Friendly vault name from vaults.yaml configuration. "
            "Examples: 'nader', 'work', 'personal'. "
            "Use list_vaults() to discover valid names."
        ),
        examples=["personal", "work", "nader"]
    )

    @field_validator('vault')
    @classmethod
    def validate_vault(cls, v: str) -> str:
        """Validate vault name format.

        Args:
            v: The vault name to validate

        Returns:
            The validated vault name

        Raises:
            ValueError: If vault name is empty or only whitespace
        """
        cleaned = v.strip()

        if not cleaned:
            raise ValueError(
                "Vault name cannot be empty. "
                "Provide a valid vault name from vaults.yaml configuration. "
                "Use list_vaults() to see available vaults."
            )

        return cleaned

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {"vault": "personal"},
                {"vault": "work"},
                {"vault": "nader"}
            ]
        }
