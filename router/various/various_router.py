from fastapi import APIRouter, HTTPException, Query
from typing import Literal, Optional, List, Dict, Union
from pydantic import BaseModel

from core.compass import (
    CompassRegistry,
    CompassDoc,
    CompassSelection,
    get_compass,
    list_compass_choices,
    list_compass_choice_cards,
    load_compass_doc,
    build_compass_prompt,
    Axis,
    AxisOrAll
)

router = APIRouter(tags=["Various"])

# Response models
class CompassChoiceCard(BaseModel):
    axis: str
    id: str
    name: str
    alias: str
    description: str

class CompassDocResponse(BaseModel):
    axis: str
    name: str
    alias: Optional[str]
    description: Optional[str]
    version: Optional[str]
    last_updated: Optional[str]
    author: Optional[str]
    body: str
    source_path: str

class CompassSelectionRequest(BaseModel):
    director: Optional[str] = None
    style: Optional[List[str]] = None

@router.get("/get_compass_values")
async def get_compass_values(compass_type: str = Query(..., description="Compass axis type: platform, director, style, or all")):
    """Get compass values for a specific axis or all axes"""
    try:
        if compass_type not in ["platform", "director", "style", "all"]:
            raise HTTPException(status_code=400, detail="compass_type must be one of: platform, director, style, all")
        
        axis_type = compass_type
        choices = list_compass_choices(axis=axis_type)
        
        return {
            "compass_type": compass_type,
            "choices": choices,
            "count": len(choices) if isinstance(choices, list) else sum(len(v) for v in choices.values())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting compass values: {str(e)}")




@router.get("/list_choices/{axis}")
async def list_choices(axis: str):
    """List all available choices for a specific axis"""
    try:
        if axis not in ["platform", "director", "style"]:
            raise HTTPException(status_code=400, detail="axis must be one of: platform, director, style")
        
        choices = list_compass_choices(axis=axis)
        return {
            "axis": axis,
            "choices": choices,
            "count": len(choices)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing choices: {str(e)}")

@router.get("/list_choice_cards/{axis}")
async def list_choice_cards(axis: str):
    """List choice cards with detailed information for a specific axis"""
    try:
        if axis not in ["platform", "director", "style"]:
            raise HTTPException(status_code=400, detail="axis must be one of: platform, director, style")
        
        cards = list_compass_choice_cards(axis=axis)
        return {
            "axis": axis,
            "cards": cards,
            "count": len(cards)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing choice cards: {str(e)}")

@router.get("/list_all_choices")
async def list_all_choices():
    """List all available choices across all axes"""
    try:
        choices = list_compass_choices(axis="all")
        return {
            "choices": choices,
            "total_count": sum(len(v) for v in choices.values())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing all choices: {str(e)}")

@router.get("/list_all_choice_cards")
async def list_all_choice_cards():
    """List all choice cards with detailed information across all axes"""
    try:
        cards = list_compass_choice_cards(axis="all")
        total_count = sum(len(v) for v in cards.values())
        return {
            "cards": cards,
            "total_count": total_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing all choice cards: {str(e)}")

@router.get("/load_doc/{axis}/{name}")
async def load_doc(axis: str, name: str):
    """Load a specific compass document"""
    try:
        if axis not in ["platform", "director", "style"]:
            raise HTTPException(status_code=400, detail="axis must be one of: platform, director, style")
        
        doc = load_compass_doc(root_dir="./compass", axis=axis, name=name)
        
        return CompassDocResponse(
            axis=doc.axis,
            name=doc.name,
            alias=doc.alias,
            description=doc.description,
            version=doc.version,
            last_updated=doc.last_updated,
            author=doc.author,
            body=doc.body,
            source_path=str(doc.source_path)
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Compass document not found: {axis}/{name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading document: {str(e)}")

@router.post("/build_prompt")
async def build_prompt(
    platform: Optional[str] = None,
    selection: Optional[CompassSelectionRequest] = None
):
    """Build a compass prompt from platform and selection"""
    try:
        compass_selection = None
        if selection:
            compass_selection = CompassSelection(
                director=selection.director,
                style=selection.style
            )
        
        prompt = build_compass_prompt(
            root_dir="./compass",
            platform=platform,
            selection=compass_selection
        )
        
        return {
            "platform": platform,
            "selection": selection.dict() if selection else None,
            "prompt": prompt,
            "prompt_length": len(prompt)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error building prompt: {str(e)}")

@router.get("/resolve_choice/{axis}/{query}")
async def resolve_choice(axis: str, query: str):
    """Resolve a choice ID from a query (name or alias)"""
    try:
        if axis not in ["platform", "director", "style"]:
            raise HTTPException(status_code=400, detail="axis must be one of: platform, director, style")
        
        compass = get_compass(root_dir="./compass")
        resolved = compass.resolve_choice_id(axis=axis, query=query)
        
        if resolved is None:
            raise HTTPException(status_code=404, detail=f"No choice found for query: {query}")
        
        return {
            "axis": axis,
            "query": query,
            "resolved_choice": resolved
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resolving choice: {str(e)}")

@router.get("/compass_info")
async def compass_info():
    """Get general compass registry information"""
    try:
        compass = get_compass(root_dir="./compass")
        all_choices = compass.list_all_choices()
        
        info = {
            "root_dir": str(compass.root_dir),
            "available_axes": list(all_choices.keys()),
            "total_choices": sum(len(choices) for choices in all_choices.values()),
            "choices_by_axis": {
                axis: {
                    "count": len(choices),
                    "choices": choices
                }
                for axis, choices in all_choices.items()
            }
        }
        
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting compass info: {str(e)}")


