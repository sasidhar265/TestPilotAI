using QualityLifecycle.Automation.Builders;
using QualityLifecycle.Automation.Models;
using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace QualityLifecycle.Automation.Services;

public interface IQuotationRequestStrategy
{
    QuotationRequestModel Build(QuotationRequestBuilder builder);
}

public sealed class ApprovedQuotationRequestStrategy : IQuotationRequestStrategy
{
    public QuotationRequestModel Build(QuotationRequestBuilder builder) => builder.Build();
}

// The caller supplies explicit approved values through the typed fluent builder.
public sealed class ConfiguredQuotationRequestStrategy : IQuotationRequestStrategy
{
    private readonly Action<QuotationRequestBuilder> configure;
    public ConfiguredQuotationRequestStrategy(Action<QuotationRequestBuilder> configure)
    {
        this.configure = configure;
    }

    public QuotationRequestModel Build(QuotationRequestBuilder builder)
    {
        configure(builder);
        return builder.Build();
    }
}

public sealed class QuotationRequestService
{
    private readonly IQuotationRequestStrategy strategy;
    public QuotationRequestService(IQuotationRequestStrategy strategy)
    {
        this.strategy = strategy;
    }

    public string BuildJson(string approvedPayloadPath) => JsonSerializer.Serialize(
        strategy.Build(QuotationRequestBuilder.FromFile(approvedPayloadPath)));
}
