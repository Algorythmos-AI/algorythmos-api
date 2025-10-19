"""
Workflow service for managing processing workflows.

Workflows are chains of processors that execute in sequence.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import WorkflowDB, ProcessorDB


async def create_workflow(
    session: AsyncSession,
    tenant_id: str,
    name: str,
    steps: List[dict],
    description: Optional[str] = None,
    enabled: bool = True,
    metadata: Optional[dict] = None
) -> WorkflowDB:
    """
    Create a new workflow.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        name: Workflow name
        steps: List of workflow steps (each step references a processor)
        description: Optional description
        enabled: Whether workflow is enabled
        metadata: Additional metadata
    
    Returns:
        Created workflow
    
    Raises:
        ValueError: If workflow name already exists or step validation fails
    """
    # Check for duplicate name (among non-deleted workflows)
    existing = await session.execute(
        select(WorkflowDB).where(
            and_(
                WorkflowDB.tenant_id == tenant_id,
                WorkflowDB.name == name,
                WorkflowDB.is_deleted == False
            )
        )
    )
    if existing.scalars().first():
        raise ValueError(f"Workflow with name '{name}' already exists")
    
    # Validate steps reference existing processors
    for step in steps:
        processor_id = step.get("processor_id")
        if processor_id:
            processor = await session.execute(
                select(ProcessorDB).where(
                    and_(
                        ProcessorDB.id == processor_id,
                        ProcessorDB.tenant_id == tenant_id,
                        ProcessorDB.is_deleted == False
                    )
                )
            )
            if not processor.scalars().first():
                raise ValueError(f"Processor with ID '{processor_id}' not found")
    
    workflow = WorkflowDB(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        description=description or "",
        steps=steps,
        enabled=enabled,
        version=1,
        workflow_metadata=metadata,
        is_deleted=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    session.add(workflow)
    await session.commit()
    await session.refresh(workflow)
    
    return workflow


async def get_workflow(
    session: AsyncSession,
    tenant_id: str,
    workflow_id: str
) -> Optional[WorkflowDB]:
    """
    Get workflow by ID.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        workflow_id: Workflow ID
    
    Returns:
        Workflow or None if not found
    """
    result = await session.execute(
        select(WorkflowDB).where(
            and_(
                WorkflowDB.id == workflow_id,
                WorkflowDB.tenant_id == tenant_id,
                WorkflowDB.is_deleted == False
            )
        )
    )
    return result.scalars().first()


async def list_workflows(
    session: AsyncSession,
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
    enabled: Optional[bool] = None
) -> Tuple[List[WorkflowDB], int]:
    """
    List workflows with pagination and filtering.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        limit: Maximum number of results
        offset: Number of results to skip
        enabled: Filter by enabled status
    
    Returns:
        Tuple of (workflows list, total count)
    """
    # Build query with filters
    conditions = [
        WorkflowDB.tenant_id == tenant_id,
        WorkflowDB.is_deleted == False
    ]
    
    if enabled is not None:
        conditions.append(WorkflowDB.enabled == enabled)
    
    # Get total count
    count_result = await session.execute(
        select(func.count()).select_from(WorkflowDB).where(and_(*conditions))
    )
    total = count_result.scalar() or 0
    
    # Get items
    result = await session.execute(
        select(WorkflowDB)
        .where(and_(*conditions))
        .order_by(WorkflowDB.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    items = list(result.scalars().all())
    return items, total


async def update_workflow(
    session: AsyncSession,
    tenant_id: str,
    workflow_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    steps: Optional[List[dict]] = None,
    enabled: Optional[bool] = None,
    metadata: Optional[dict] = None
) -> Optional[WorkflowDB]:
    """
    Update workflow.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        workflow_id: Workflow ID
        name: Optional new name
        description: Optional new description
        steps: Optional new steps
        enabled: Optional new enabled status
        metadata: Optional new metadata
    
    Returns:
        Updated workflow or None if not found
    
    Raises:
        ValueError: If name already exists or step validation fails
    """
    workflow = await get_workflow(session, tenant_id, workflow_id)
    if not workflow:
        return None
    
    # Check name uniqueness if changing
    if name and name != workflow.name:
        existing = await session.execute(
            select(WorkflowDB).where(
                and_(
                    WorkflowDB.tenant_id == tenant_id,
                    WorkflowDB.name == name,
                    WorkflowDB.is_deleted == False,
                    WorkflowDB.id != workflow_id
                )
            )
        )
        if existing.scalars().first():
            raise ValueError(f"Workflow with name '{name}' already exists")
        workflow.name = name
    
    # Validate and update steps
    if steps:
        for step in steps:
            processor_id = step.get("processor_id")
            if processor_id:
                processor = await session.execute(
                    select(ProcessorDB).where(
                        and_(
                            ProcessorDB.id == processor_id,
                            ProcessorDB.tenant_id == tenant_id,
                            ProcessorDB.is_deleted == False
                        )
                    )
                )
                if not processor.scalars().first():
                    raise ValueError(f"Processor with ID '{processor_id}' not found")
        
        workflow.steps = steps
        workflow.version += 1  # Increment version on steps change
    
    # Update other fields
    if description is not None:
        workflow.description = description
    if enabled is not None:
        workflow.enabled = enabled
    if metadata is not None:
        workflow.workflow_metadata = metadata
    
    workflow.updated_at = datetime.utcnow()
    
    await session.commit()
    await session.refresh(workflow)
    
    return workflow


async def delete_workflow(
    session: AsyncSession,
    tenant_id: str,
    workflow_id: str
) -> bool:
    """
    Soft delete workflow.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        workflow_id: Workflow ID
    
    Returns:
        True if deleted, False if not found
    """
    workflow = await get_workflow(session, tenant_id, workflow_id)
    if not workflow:
        return False
    
    workflow.is_deleted = True
    workflow.updated_at = datetime.utcnow()
    
    await session.commit()
    return True


async def execute_workflow(
    session: AsyncSession,
    tenant_id: str,
    workflow_id: str,
    input_data: dict
) -> dict:
    """
    Execute a workflow with given input.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        workflow_id: Workflow ID
        input_data: Input data for workflow
    
    Returns:
        Workflow execution result
    
    Raises:
        ValueError: If workflow not found or disabled
    """
    workflow = await get_workflow(session, tenant_id, workflow_id)
    if not workflow:
        raise ValueError(f"Workflow with ID '{workflow_id}' not found")
    
    if not workflow.enabled:
        raise ValueError(f"Workflow '{workflow.name}' is disabled")
    
    # Execute workflow steps
    current_data = input_data
    step_results = []
    
    for i, step in enumerate(workflow.steps):
        processor_id = step.get("processor_id")
        step_config = step.get("config", {})
        
        # Get processor
        processor = await session.execute(
            select(ProcessorDB).where(
                and_(
                    ProcessorDB.id == processor_id,
                    ProcessorDB.tenant_id == tenant_id,
                    ProcessorDB.is_deleted == False
                )
            )
        )
        processor_obj = processor.scalars().first()
        
        if not processor_obj:
            raise ValueError(f"Processor '{processor_id}' not found in step {i+1}")
        
        if not processor_obj.enabled:
            raise ValueError(f"Processor '{processor_obj.name}' is disabled in step {i+1}")
        
        # Execute processor (placeholder - actual implementation would invoke the processor)
        # For now, just pass through the data with metadata
        step_result = {
            "step": i + 1,
            "processor_id": processor_id,
            "processor_name": processor_obj.name,
            "processor_type": processor_obj.processor_type,
            "input": current_data,
            "output": current_data,  # Placeholder - actual execution would transform data
            "config": step_config
        }
        
        step_results.append(step_result)
        current_data = step_result["output"]
    
    return {
        "workflow_id": workflow_id,
        "workflow_name": workflow.name,
        "input": input_data,
        "output": current_data,
        "steps": step_results,
        "status": "success"
    }
