from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.11.0"
version = "None"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'https://w3id.org/eagle/iso-land-monitoring/',
     'default_range': 'string',
     'description': 'LinkML schema modeling the EAGLE object-oriented land '
                    'characterisation framework and mapping it to ISO 19144 '
                    '(LCML/LUML/LCHML) metalanguage descriptors.\n',
     'id': 'https://w3id.org/eagle/iso-land-monitoring',
     'imports': ['linkml:types'],
     'name': 'eagle_iso_land_monitoring',
     'prefixes': {'eagle': {'prefix_prefix': 'eagle',
                            'prefix_reference': 'https://dd.eionet.europa.eu/vocabulary/landcover/eagle/'},
                  'iso': {'prefix_prefix': 'iso',
                          'prefix_reference': 'https://standards.isotc211.org/19144/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'skos': {'prefix_prefix': 'skos',
                           'prefix_reference': 'http://www.w3.org/2004/02/skos/core#'}},
     'source_file': 'src\\model\\eagle-iso-mapping.linkml.yaml'} )

class BarCodeValueEnum(str, Enum):
    BCV_0 = "BCV_0"
    """
    Absent or irrelevant
    """
    BCV_1 = "BCV_1"
    """
    Optional / typical occurrence
    """
    BCV_2 = "BCV_2"
    """
    Selective mandatory (EITHER-OR)
    """
    BCV_3 = "BCV_3"
    """
    Cumulative mandatory (AND)
    """
    BCV_4 = "BCV_4"
    """
    Paired mandatory (at least two occur)
    """
    BCV_5 = "BCV_5"
    """
    Exclusive mandatory (ONLY-THIS-ONE)
    """
    BCV_X = "BCV_X"
    """
    Explicitly excluded
    """


class ISOPresenceEnum(str, Enum):
    Fixed = "Fixed"
    """
    Mandatory presence (maps to BCV 3)
    """
    Conditional = "Conditional"
    """
    Conditional presence
    """
    Optional = "Optional"
    """
    Optional presence (maps to BCV 1)
    """
    Exclusive = "Exclusive"
    """
    Exclusive presence (maps to BCV 2 / BCV 5)
    """
    Precluded = "Precluded"
    """
    Explicitly excluded presence (maps to BCV X)
    """


class FunctionalRelationshipEnum(str, Enum):
    Primary = "Primary"
    """
    Primary socio-economic function
    """
    Secondary = "Secondary"
    """
    Secondary function
    """
    Dominant = "Dominant"
    """
    Dominant use
    """


class TemporalRelationshipEnum(str, Enum):
    Coexistant = "Coexistant"
    """
    Continuous simultaneous occurrence
    """
    LinearTimeSequence = "LinearTimeSequence"
    """
    Sequential succession (e.g. crop rotation)
    """
    Cyclic = "Cyclic"
    """
    Regular seasonal repetition
    """



class LandUnit(ConfiguredBaseModel):
    """
    Discrete spatial geometry (data instance or grid cell) holding land characterisation observations.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/eagle/iso-land-monitoring'})

    id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['LandUnit']} })
    name: Optional[str] = Field(default=None, description="""Human-readable name or designation of the land unit.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandUnit']} })
    geometry_type: Optional[str] = Field(default=None, description="""Spatial representation type (e.g. Polygon, GridCell_1ha).""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandUnit']} })
    land_cover_components: Optional[list[LandCoverComponent]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandUnit']} })
    land_use_attributes: Optional[list[LandUseAttribute]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandUnit']} })
    land_characteristics: Optional[list[LandCharacteristic]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandUnit']} })


class LandCoverComponent(ConfiguredBaseModel):
    """
    Base biophysical surface element (EAGLE LCC) mapped to ISO 19144-2 LC_Element.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/eagle/iso-land-monitoring'})

    uri: Optional[str] = Field(default=None, description="""Persistent identifier from the Eionet Data Dictionary.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    label: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    bcv_operator: Optional[BarCodeValueEnum] = Field(default=None, description="""EAGLE Bar Code Value assigned to the element.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    iso_presence_type: Optional[ISOPresenceEnum] = Field(default=None, description="""Equivalent ISO 19144-2 PresenceType.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    min_cover: Optional[int] = Field(default=None, description="""Minimum percentage cover threshold (0-100%).""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    max_cover: Optional[int] = Field(default=None, description="""Maximum percentage cover threshold (0-100%).""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    stratum_id: Optional[int] = Field(default=None, description="""Vertical layer/stratum ID in ISO LCML.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    characteristics: Optional[list[LandCharacteristic]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })


class AbioticComponent(LandCoverComponent):
    """
    Artificial and natural non-vegetated surfaces.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/eagle/iso-land-monitoring'})

    soil_sealing_degree: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['AbioticComponent']} })
    surface_material: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['AbioticComponent']} })
    uri: Optional[str] = Field(default=None, description="""Persistent identifier from the Eionet Data Dictionary.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    label: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    bcv_operator: Optional[BarCodeValueEnum] = Field(default=None, description="""EAGLE Bar Code Value assigned to the element.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    iso_presence_type: Optional[ISOPresenceEnum] = Field(default=None, description="""Equivalent ISO 19144-2 PresenceType.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    min_cover: Optional[int] = Field(default=None, description="""Minimum percentage cover threshold (0-100%).""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    max_cover: Optional[int] = Field(default=None, description="""Maximum percentage cover threshold (0-100%).""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    stratum_id: Optional[int] = Field(default=None, description="""Vertical layer/stratum ID in ISO LCML.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    characteristics: Optional[list[LandCharacteristic]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })


class BioticComponent(LandCoverComponent):
    """
    Woody, herbaceous, and other biological cover features.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/eagle/iso-land-monitoring'})

    leaf_form: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['BioticComponent']} })
    foliage_persistence: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['BioticComponent']} })
    growth_form: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['BioticComponent']} })
    crown_cover_density: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['BioticComponent']} })
    uri: Optional[str] = Field(default=None, description="""Persistent identifier from the Eionet Data Dictionary.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    label: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    bcv_operator: Optional[BarCodeValueEnum] = Field(default=None, description="""EAGLE Bar Code Value assigned to the element.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    iso_presence_type: Optional[ISOPresenceEnum] = Field(default=None, description="""Equivalent ISO 19144-2 PresenceType.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    min_cover: Optional[int] = Field(default=None, description="""Minimum percentage cover threshold (0-100%).""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    max_cover: Optional[int] = Field(default=None, description="""Maximum percentage cover threshold (0-100%).""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    stratum_id: Optional[int] = Field(default=None, description="""Vertical layer/stratum ID in ISO LCML.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    characteristics: Optional[list[LandCharacteristic]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })


class WaterComponent(LandCoverComponent):
    """
    Liquid and solid water bodies.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/eagle/iso-land-monitoring'})

    water_state: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WaterComponent']} })
    salinity: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WaterComponent']} })
    uri: Optional[str] = Field(default=None, description="""Persistent identifier from the Eionet Data Dictionary.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    label: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    bcv_operator: Optional[BarCodeValueEnum] = Field(default=None, description="""EAGLE Bar Code Value assigned to the element.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    iso_presence_type: Optional[ISOPresenceEnum] = Field(default=None, description="""Equivalent ISO 19144-2 PresenceType.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    min_cover: Optional[int] = Field(default=None, description="""Minimum percentage cover threshold (0-100%).""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    max_cover: Optional[int] = Field(default=None, description="""Maximum percentage cover threshold (0-100%).""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    stratum_id: Optional[int] = Field(default=None, description="""Vertical layer/stratum ID in ISO LCML.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    characteristics: Optional[list[LandCharacteristic]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })


class LandUseAttribute(ConfiguredBaseModel):
    """
    Socio-economic function or activity (EAGLE LUA / HILUCS) mapped to ISO 19144-3 LUML.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/eagle/iso-land-monitoring'})

    uri: Optional[str] = Field(default=None, description="""Persistent identifier from the Eionet Data Dictionary.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    label: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    hilucs_code: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandUseAttribute']} })
    iso_function_type: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandUseAttribute']} })
    functional_relationship: Optional[FunctionalRelationshipEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandUseAttribute']} })
    temporal_relationship: Optional[TemporalRelationshipEnum] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandUseAttribute']} })


class LandCharacteristic(ConfiguredBaseModel):
    """
    Bio-physical parameter, spatial pattern, management practice, or status parameter (EAGLE LCH).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/eagle/iso-land-monitoring'})

    uri: Optional[str] = Field(default=None, description="""Persistent identifier from the Eionet Data Dictionary.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    label: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent', 'LandUseAttribute', 'LandCharacteristic']} })
    characteristic_type: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCharacteristic']} })
    numeric_value: Optional[float] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCharacteristic']} })
    unit: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCharacteristic']} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
LandUnit.model_rebuild()
LandCoverComponent.model_rebuild()
AbioticComponent.model_rebuild()
BioticComponent.model_rebuild()
WaterComponent.model_rebuild()
LandUseAttribute.model_rebuild()
LandCharacteristic.model_rebuild()
