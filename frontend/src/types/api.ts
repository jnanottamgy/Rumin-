/**
 * Friendly names for the API contract.
 *
 * The source of truth is `api.generated.ts`, generated from docs/api/openapi.json
 * (`npm run generate:api`). Never edit the generated file by hand; alias from it here.
 */
import type { components } from "./api.generated";

type Schemas = components["schemas"];

export type EntityKind = Schemas["EntityKind"];
export type CompanyEntity = Schemas["CompanyRead"];
export type IndustryEntity = Schemas["IndustryRead"];
export type CountryEntity = Schemas["CountryRead"];
export type EconomicVariable = Schemas["EconomicVariableRead"];
export type Entity = CompanyEntity | IndustryEntity | CountryEntity | EconomicVariable;
export type ChangeRule = Schemas["ChangeRuleRead"];
export type ChangeType = Schemas["ChangeType"];

export type RelationshipType = Schemas["RelationshipType"];
export type StructuralLinkType = Schemas["StructuralLinkType"];
export type EdgeType = RelationshipType | StructuralLinkType;
export type Relationship = Schemas["RelationshipRead"];
export type StructuralLink = Schemas["StructuralLinkRead"];
export type NetworkEdge = Relationship | StructuralLink;
export type RelationshipTypeInfo = Schemas["RelationshipTypeRead"];
export type Polarity = Schemas["Polarity"];
export type Strength = Schemas["Strength"];
export type EvidenceLevel = Schemas["EvidenceLevel"];

export type NetworkNode = Schemas["NetworkNode"];
export type NetworkResponse = Schemas["NetworkResponse"];
export type DatasetSummary = Schemas["DatasetSummary"];

export type Scenario = Schemas["ScenarioRead"];
export type ScenarioInput = Schemas["ScenarioInput"];
export type ShockInput = Schemas["ShockInput"];
export type ScenarioPage = Schemas["ScenarioPage"];
export type EconomicVariablePage = Schemas["EconomicVariablePage"];

export type SystemStatus = Schemas["SystemStatus"];
export type Capability = Schemas["Capability"];
export type HealthResponse = Schemas["HealthResponse"];
export type ReadinessResponse = Schemas["ReadinessResponse"];

export type ErrorDetail = Schemas["ErrorDetail"];
export type ErrorResponse = Schemas["ErrorResponse"];
