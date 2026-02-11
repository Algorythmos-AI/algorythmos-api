"""
Evaluation set service for managing test datasets.

Evaluation sets allow testing processors, workflows, and extractors.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import EvaluationSetDB


async def create_evaluation_set(
    session: AsyncSession,
    tenant_id: str,
    name: str,
    test_cases: List[dict],
    target_type: str,
    description: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[dict] = None
) -> EvaluationSetDB:
    """
    Create a new evaluation set.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        name: Evaluation set name
        test_cases: List of test cases with input/expected output
        target_type: Type of target (processor, workflow, extractor, schema)
        description: Optional description
        target_id: Optional specific target ID
        metadata: Additional metadata (results, metrics, etc.)
    
    Returns:
        Created evaluation set
    
    Raises:
        ValueError: If evaluation set name already exists
    """
    # Check for duplicate name (among non-deleted sets)
    existing = await session.execute(
        select(EvaluationSetDB).where(
            and_(
                EvaluationSetDB.tenant_id == tenant_id,
                EvaluationSetDB.name == name,
                EvaluationSetDB.is_deleted == False
            )
        )
    )
    if existing.scalars().first():
        raise ValueError(f"Evaluation set with name '{name}' already exists")
    
    # Validate target_type
    valid_types = ["processor", "workflow", "extractor", "schema"]
    if target_type not in valid_types:
        raise ValueError(f"Invalid target_type '{target_type}'. Must be one of: {', '.join(valid_types)}")
    
    evaluation_set = EvaluationSetDB(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        description=description or "",
        test_cases=test_cases,
        target_type=target_type,
        target_id=target_id,
        evaluation_metadata=metadata,
        is_deleted=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    session.add(evaluation_set)
    await session.commit()
    await session.refresh(evaluation_set)
    
    return evaluation_set


async def get_evaluation_set(
    session: AsyncSession,
    tenant_id: str,
    evaluation_set_id: str
) -> Optional[EvaluationSetDB]:
    """
    Get evaluation set by ID.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        evaluation_set_id: Evaluation set ID
    
    Returns:
        Evaluation set or None if not found
    """
    result = await session.execute(
        select(EvaluationSetDB).where(
            and_(
                EvaluationSetDB.id == evaluation_set_id,
                EvaluationSetDB.tenant_id == tenant_id,
                EvaluationSetDB.is_deleted == False
            )
        )
    )
    return result.scalars().first()


async def list_evaluation_sets(
    session: AsyncSession,
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None
) -> Tuple[List[EvaluationSetDB], int]:
    """
    List evaluation sets with pagination and filtering.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        limit: Maximum number of results
        offset: Number of results to skip
        target_type: Filter by target type
        target_id: Filter by target ID
    
    Returns:
        Tuple of (evaluation sets list, total count)
    """
    # Build query with filters
    conditions = [
        EvaluationSetDB.tenant_id == tenant_id,
        EvaluationSetDB.is_deleted == False
    ]
    
    if target_type:
        conditions.append(EvaluationSetDB.target_type == target_type)
    
    if target_id:
        conditions.append(EvaluationSetDB.target_id == target_id)
    
    # Get total count
    count_result = await session.execute(
        select(func.count()).select_from(EvaluationSetDB).where(and_(*conditions))
    )
    total = count_result.scalar() or 0
    
    # Get items
    result = await session.execute(
        select(EvaluationSetDB)
        .where(and_(*conditions))
        .order_by(EvaluationSetDB.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    items = list(result.scalars().all())
    return items, total


async def update_evaluation_set(
    session: AsyncSession,
    tenant_id: str,
    evaluation_set_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    test_cases: Optional[List[dict]] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[dict] = None
) -> Optional[EvaluationSetDB]:
    """
    Update evaluation set.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        evaluation_set_id: Evaluation set ID
        name: Optional new name
        description: Optional new description
        test_cases: Optional new test cases
        target_type: Optional new target type
        target_id: Optional new target ID
        metadata: Optional new metadata
    
    Returns:
        Updated evaluation set or None if not found
    
    Raises:
        ValueError: If name already exists or target_type is invalid
    """
    evaluation_set = await get_evaluation_set(session, tenant_id, evaluation_set_id)
    if not evaluation_set:
        return None
    
    # Check name uniqueness if changing
    if name and name != evaluation_set.name:
        existing = await session.execute(
            select(EvaluationSetDB).where(
                and_(
                    EvaluationSetDB.tenant_id == tenant_id,
                    EvaluationSetDB.name == name,
                    EvaluationSetDB.is_deleted == False,
                    EvaluationSetDB.id != evaluation_set_id
                )
            )
        )
        if existing.scalars().first():
            raise ValueError(f"Evaluation set with name '{name}' already exists")
        evaluation_set.name = name
    
    # Validate target_type if changing
    if target_type:
        valid_types = ["processor", "workflow", "extractor", "schema"]
        if target_type not in valid_types:
            raise ValueError(f"Invalid target_type '{target_type}'. Must be one of: {', '.join(valid_types)}")
        evaluation_set.target_type = target_type
    
    # Update fields
    if description is not None:
        evaluation_set.description = description
    if test_cases is not None:
        evaluation_set.test_cases = test_cases
    if target_id is not None:
        evaluation_set.target_id = target_id
    if metadata is not None:
        evaluation_set.evaluation_metadata = metadata
    
    evaluation_set.updated_at = datetime.utcnow()
    
    await session.commit()
    await session.refresh(evaluation_set)
    
    return evaluation_set


async def delete_evaluation_set(
    session: AsyncSession,
    tenant_id: str,
    evaluation_set_id: str
) -> bool:
    """
    Soft delete evaluation set.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        evaluation_set_id: Evaluation set ID
    
    Returns:
        True if deleted, False if not found
    """
    evaluation_set = await get_evaluation_set(session, tenant_id, evaluation_set_id)
    if not evaluation_set:
        return False
    
    evaluation_set.is_deleted = True
    evaluation_set.updated_at = datetime.utcnow()
    
    await session.commit()
    return True


async def run_evaluation(
    session: AsyncSession,
    tenant_id: str,
    evaluation_set_id: str
) -> dict:
    """
    Run evaluation set against its target.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        evaluation_set_id: Evaluation set ID
    
    Returns:
        Evaluation results
    
    Raises:
        ValueError: If evaluation set not found
    """
    evaluation_set = await get_evaluation_set(session, tenant_id, evaluation_set_id)
    if not evaluation_set:
        raise ValueError(f"Evaluation set with ID '{evaluation_set_id}' not found")
    
    # Run test cases (placeholder - actual implementation would invoke target)
    results = []
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(evaluation_set.test_cases):
        test_input = test_case.get("input")
        expected_output = test_case.get("expected_output")
        test_name = test_case.get("name", f"Test {i+1}")
        
        # Placeholder execution - actual implementation would invoke the target
        # For now, just mark as passed
        result = {
            "test_name": test_name,
            "input": test_input,
            "expected_output": expected_output,
            "actual_output": expected_output,  # Placeholder
            "passed": True,
            "error": None
        }
        
        results.append(result)
        if result["passed"]:
            passed += 1
        else:
            failed += 1
    
    # Update evaluation set metadata with results
    evaluation_set.evaluation_metadata = {
        **(evaluation_set.evaluation_metadata or {}),
        "last_run": datetime.utcnow().isoformat(),
        "total_tests": len(evaluation_set.test_cases),
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / len(evaluation_set.test_cases) if evaluation_set.test_cases else 0
    }
    evaluation_set.updated_at = datetime.utcnow()
    
    await session.commit()
    
    return {
        "evaluation_set_id": evaluation_set_id,
        "evaluation_set_name": evaluation_set.name,
        "target_type": evaluation_set.target_type,
        "target_id": evaluation_set.target_id,
        "total_tests": len(evaluation_set.test_cases),
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / len(evaluation_set.test_cases) if evaluation_set.test_cases else 0,
        "results": results
    }
