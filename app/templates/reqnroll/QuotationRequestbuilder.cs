using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Generated.StepDefinitions;

// The supplied JSON is the only default request; no business fields are inferred.
public sealed class QuotationRequestBuilder
{
    private QuotationRequestModel request;
    private QuotationRequestBuilder(QuotationRequestModel request)
    {
        this.request = request;
    }

    public static QuotationRequestBuilder FromJson(string json) => new(
        JsonSerializer.Deserialize<QuotationRequestModel>(json)
        ?? throw new JsonException("Quotation request cannot be null."));

    public static QuotationRequestBuilder FromFile(string path) => FromJson(File.ReadAllText(path));

    public QuotationRequestBuilder WithOutletCode(string value)
    {
        request = request with
        {
            Outlet = request.Outlet with
            {
                Code = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithProductId(string value)
    {
        request = request with
        {
            Finance = request.Finance with
            {
                ProductId = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithCapCode(string value)
    {
        request = request with
        {
            Vehicle = request.Vehicle with
            {
                CapCode = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithVehicleRegistrationNumber(string value)
    {
        request = request with
        {
            Vehicle = request.Vehicle with
            {
                VehicleRegistrationNumber = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithVehicleRegstrationDate(string value)
    {
        request = request with
        {
            Vehicle = request.Vehicle with
            {
                VehicleRegstrationDate = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithVehicleMake(string value)
    {
        request = request with
        {
            Vehicle = request.Vehicle with
            {
                VehicleMake = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithPriceTotal(decimal value)
    {
        request = request with
        {
            Vehicle = request.Vehicle with
            {
                PriceTotal = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithYearOfManufacture(int value)
    {
        request = request with
        {
            Vehicle = request.Vehicle with
            {
                YearOfManufacture = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithExteriorColor(string value)
    {
        request = request with
        {
            Vehicle = request.Vehicle with
            {
                ExteriorColor = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithQualifyingOrMargin(string value)
    {
        request = request with
        {
            Vehicle = request.Vehicle with
            {
                QualifyingOrMargin = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithDeposit(decimal value)
    {
        request = request with
        {
            Parameters = request.Parameters with
            {
                Deposit = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithTerm(int value)
    {
        request = request with
        {
            Parameters = request.Parameters with
            {
                Term = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithAnnualMileage(int value)
    {
        request = request with
        {
            Parameters = request.Parameters with
            {
                AnnualMileage = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithCustomerRate(decimal value)
    {
        request = request with
        {
            Parameters = request.Parameters with
            {
                CustomerRate = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithPartExchange(decimal value)
    {
        request = request with
        {
            Parameters = request.Parameters with
            {
                PartExchange = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithSettlement(decimal value)
    {
        request = request with
        {
            Parameters = request.Parameters with
            {
                Settlement = value
            }
        };
        return this;
    }

    public QuotationRequestBuilder WithCalcTargetType(string value)
    {
        request = request with
        {
            Parameters = request.Parameters with
            {
                CalcTargetType = value
            }
        };
        return this;
    }

    public QuotationRequestModel Build() => request with
    {
        Outlet = request.Outlet with
        {
        },
        Finance = request.Finance with
        {
        },
        Vehicle = request.Vehicle with
        {
        },
        Parameters = request.Parameters with
        {
        }
    };

    public string BuildJson() => JsonSerializer.Serialize(Build());
}
