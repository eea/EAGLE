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


linkml_meta = LinkMLMeta({'default_prefix': 'eagle',
     'description': 'Complete LinkML model for the conceptual mapping of CORINE '
                    'classes CLC112, CLC212 and CLC322',
     'id': 'https://w3id.org/eagle-iso-mapping-corine',
     'imports': ['linkml:types'],
     'name': 'eagle_lcml_crosswalk_corine',
     'prefixes': {'eagle': {'prefix_prefix': 'eagle',
                            'prefix_reference': 'https://example.org/eagle-schema/'},
                  'lcml': {'prefix_prefix': 'lcml',
                           'prefix_reference': 'https://example.org/iso19144-2/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'skos': {'prefix_prefix': 'skos',
                           'prefix_reference': 'http://www.w3.org/2004/02/skos/core#'}},
     'source_file': 'src\\model\\eagle-lcml-mapping.linkml.yaml'} )

class EagleMatrixValue(str, Enum):
    """
    EAGLE Matrix Values for Land Cover Components
    """
    number_1 = "1"
    """
    Optional element (Conditional Temporal)
    """
    number_2 = "2"
    """
    EITHER-OR relationship (Exclusive)
    """
    number_3 = "3"
    """
    Mandatory element (Fixed)
    """


class LcmlPresenceType(str, Enum):
    """
    ISO 19144-2 Presence Types mapped to EAGLE Values
    """
    ConditionalTemporal = "ConditionalTemporal"
    Exclusive = "Exclusive"
    Fixed = "Fixed"
    Precluded = "Precluded"
    """
    Explicit exclusion (e.g., for rice/hops in CLC212)
    """


class EagleLccType(str, Enum):
    """
    Specific Land Cover Components (LCC)
    """
    SealedArtificialSurface = "SealedArtificialSurface"
    BioticVegetation = "BioticVegetation"
    SpecificBuildings = "SpecificBuildings"
    BareSoil = "BareSoil"
    HerbaceousVegetation = "HerbaceousVegetation"
    NaturalSurfaces = "NaturalSurfaces"
    Trees = "Trees"
    Shrubs = "Shrubs"
    Algae = "Algae"
    LichenMosses = "LichenMosses"
    Forbs = "Forbs"
    Graminoids = "Graminoids"


class LcmlIrrigationType(str, Enum):
    """
    ISO 19144-2 Cultivated and Managed Vegetation Characteristic
    """
    Sprinkler = "Sprinkler"
    """
    Specific irrigation type
    """
    Manual = "Manual"
    """
    Manual irrigation
    """
    Unspecified = "Unspecified"
    """
    Irrigation Applied, Method Unspecified
    """



class CorineClass(ConfiguredBaseModel):
    """
    Base class for mapping a CORINE nomenclature
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/eagle-iso-mapping-corine'})

    class_code: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['CorineClass']} })
    class_name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['CorineClass']} })
    components: Optional[list[LandCoverComponent]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['CorineClass']} })
    characteristics: Optional[list[LandCharacteristic]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['CorineClass']} })


class LandCharacteristic(ConfiguredBaseModel):
    """
    Land Characteristics (LCH)
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/eagle-iso-mapping-corine'})

    characteristic_type: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCharacteristic']} })
    irrigation_type: Optional[LcmlIrrigationType] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCharacteristic']} })
    is_mappable_to_lcml: Optional[bool] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCharacteristic']} })


class LandCoverComponent(ConfiguredBaseModel):
    """
    LCC definition including smart default mapping
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/eagle-iso-mapping-corine',
         'rules': [{'description': 'Reconstruct coverage thresholds for CLC112 using '
                                   'factor 055',
                    'postconditions': {'slot_conditions': {'coverage_max': {'equals_number': 80,
                                                                            'name': 'coverage_max'},
                                                           'coverage_min': {'equals_number': 30,
                                                                            'name': 'coverage_min'}}},
                    'preconditions': {'slot_conditions': {'eagle_factor': {'equals_string': '055',
                                                                           'name': 'eagle_factor'}}}},
                   {'description': 'Reconstruct coverage thresholds for CLC212 using '
                                   'factor >75%',
                    'postconditions': {'slot_conditions': {'coverage_max': {'equals_number': 100,
                                                                            'name': 'coverage_max'},
                                                           'coverage_min': {'equals_number': 75,
                                                                            'name': 'coverage_min'}}},
                    'preconditions': {'slot_conditions': {'eagle_factor': {'equals_string': '075_plus',
                                                                           'name': 'eagle_factor'}}}}]})

    lcc_type: EagleLccType = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    eagle_value: Optional[EagleMatrixValue] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    presence_type: Optional[LcmlPresenceType] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    eagle_factor: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    coverage_min: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    coverage_max: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })
    floristic_aspects: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['LandCoverComponent']} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
CorineClass.model_rebuild()
LandCharacteristic.model_rebuild()
LandCoverComponent.model_rebuild()
