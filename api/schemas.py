from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class MeshType(str, Enum):
    DESIGN = "design"
    TOPO = "topo"


class MeshInfo(BaseModel):
    id: str
    type: MeshType
    n_vertices: int
    n_faces: int
    bounds: Dict[str, float]
    filename: str
    uploaded_at: str


class SectionCreate(BaseModel):
    name: str = Field(default="S-01")
    origin: List[float] = Field(default=[0.0, 0.0], description="[x, y]")
    azimuth: float = 0.0
    length: float = 200.0
    sector: str = ""


class SectionResponse(BaseModel):
    id: str
    name: str
    origin: List[float]
    azimuth: float
    length: float
    sector: str


class SectionAutoParams(BaseModel):
    start: List[float] = Field(description="[x, y]")
    end: List[float] = Field(description="[x, y]")
    n_sections: int = 5
    azimuth: Optional[float] = None
    length: float = 200.0
    sector: str = ""
    az_method: str = "perpendicular"
    fixed_az: float = 0.0


class SectionFromFileParams(BaseModel):
    spacing: float = 20.0
    length: float = 200.0
    sector: str = "Principal"
    az_mode: str = "perpendicular"


class ProcessSettings(BaseModel):
    resolution: float = 0.5
    face_threshold: float = 40.0
    berm_threshold: float = 20.0


class TolerancesSchema(BaseModel):
    bench_height: Dict[str, float] = Field(default={"neg": 1.0, "pos": 1.5})
    face_angle: Dict[str, float] = Field(default={"neg": 5.0, "pos": 5.0})
    berm_width: Dict[str, float] = Field(default={"min": 6.0})
    inter_ramp_angle: Dict[str, float] = Field(default={"neg": 3.0, "pos": 2.0})
    overall_angle: Dict[str, float] = Field(default={"neg": 2.0, "pos": 2.0})


class BenchParamsSchema(BaseModel):
    bench_number: int
    crest_elevation: float
    crest_distance: float
    toe_elevation: float
    toe_distance: float
    bench_height: float
    face_angle: float
    berm_width: float
    is_ramp: bool = False


class ExtractionResultSchema(BaseModel):
    section_name: str
    sector: str
    benches: List[BenchParamsSchema] = []
    inter_ramp_angle: float = 0.0
    overall_angle: float = 0.0


class ProfileData(BaseModel):
    section_name: str
    sector: str
    origin: List[float]
    azimuth: float
    design: Optional[Dict[str, List[float]]] = None
    topo: Optional[Dict[str, List[float]]] = None
    reconciled_design: Optional[Dict[str, List[float]]] = None
    reconciled_topo: Optional[Dict[str, List[float]]] = None
    benches_topo: Optional[List[BenchParamsSchema]] = None


class ComparisonResult(BaseModel):
    sector: str
    section: str
    bench_num: int
    type: str  # "MATCH" | "MISSING" | "EXTRA"
    level: str
    height_design: Optional[float] = None
    height_real: Optional[float] = None
    height_dev: Optional[float] = None
    height_status: str
    angle_design: Optional[float] = None
    angle_real: Optional[float] = None
    angle_dev: Optional[float] = None
    angle_status: str
    berm_design: Optional[float] = None
    berm_real: Optional[float] = None
    berm_min: Optional[float] = None
    berm_status: str
    delta_crest: Optional[float] = None
    delta_toe: Optional[float] = None


class ProcessStatus(BaseModel):
    status: str  # "idle" | "processing" | "complete" | "error"
    current_section: Optional[int] = None
    total_sections: Optional[int] = None
    completed_sections: int = 0
    n_results: int = 0


class ExportRequest(BaseModel):
    project: str = ""
    author: str = ""
    operation: str = ""
    phase: str = ""


class SettingsResponse(BaseModel):
    process: ProcessSettings
    tolerances: TolerancesSchema


class MessageResponse(BaseModel):
    message: str


class UploadResponse(BaseModel):
    mesh_id: str
    n_vertices: int
    n_faces: int
    bounds: Dict[str, float]
