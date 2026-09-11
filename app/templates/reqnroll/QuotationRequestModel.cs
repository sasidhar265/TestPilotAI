using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Generated.StepDefinitions;

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record QuotationRequestModel
{
    [JsonPropertyName("Outlet")]
    public required OutletModel Outlet { get; init; }
    [JsonPropertyName("Finance")]
    public required FinanceModel Finance { get; init; }
    [JsonPropertyName("Vehicle")]
    public required VehicleModel Vehicle { get; init; }
    [JsonPropertyName("Parameters")]
    public required ParametersModel Parameters { get; init; }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record OutletModel
{
    [JsonPropertyName("code")]
    public required string Code { get; init; }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record FinanceModel
{
    [JsonPropertyName("ProductId")]
    public required string ProductId { get; init; }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record VehicleModel
{
    [JsonPropertyName("CapCode")]
    public required string CapCode { get; init; }
    [JsonPropertyName("VehicleRegistrationNumber")]
    public required string VehicleRegistrationNumber { get; init; }
    [JsonPropertyName("VehicleRegstrationDate")]
    public required string VehicleRegstrationDate { get; init; }
    [JsonPropertyName("VehicleMake")]
    public required string VehicleMake { get; init; }
    [JsonPropertyName("PriceTotal")]
    public required decimal PriceTotal { get; init; }
    [JsonPropertyName("YearOfManufacture")]
    public required int YearOfManufacture { get; init; }
    [JsonPropertyName("ExteriorColor")]
    public required string ExteriorColor { get; init; }
    [JsonPropertyName("QualifyingOrMargin")]
    public required string QualifyingOrMargin { get; init; }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ParametersModel
{
    [JsonPropertyName("Deposit")]
    public required decimal Deposit { get; init; }
    [JsonPropertyName("Term")]
    public required int Term { get; init; }
    [JsonPropertyName("AnnualMileage")]
    public required int AnnualMileage { get; init; }
    [JsonPropertyName("CustomerRate")]
    public required decimal CustomerRate { get; init; }
    [JsonPropertyName("PartExchange")]
    public required decimal PartExchange { get; init; }
    [JsonPropertyName("Settlement")]
    public required decimal Settlement { get; init; }
    [JsonPropertyName("CalcTargetType")]
    public required string CalcTargetType { get; init; }
}

